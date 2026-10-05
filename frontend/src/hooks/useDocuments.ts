import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';
import {
  deleteDocument as deleteDocumentRequest,
  listDocuments,
  uploadDocument as uploadDocumentRequest,
} from '../api/documents';
import { ALLOWED_EXTENSIONS, MAX_UPLOAD_BYTES } from '../config';
import type { DocumentDto } from '../types/api';

/** Poll cadence while at least one document is still PROCESSING. */
const PROCESSING_POLL_MS = 2000;

export interface UploadRejection {
  filename: string;
  reason: string;
}

export interface UseDocumentsResult {
  documents: DocumentDto[];
  loading: boolean;
  error: ApiError | null;
  uploading: boolean;
  /** Non-null after a client-side or server-side upload rejection. */
  rejection: UploadRejection | null;
  upload: (file: File) => Promise<boolean>;
  remove: (id: string) => Promise<void>;
  refresh: () => Promise<void>;
  dismissRejection: () => void;
}

/**
 * Rejects a file before it reaches the network when it cannot possibly be
 * accepted, so the user gets an immediate reason rather than a round trip.
 */
function validateFile(file: File): string | null {
  const name = file.name.toLowerCase();

  if (!ALLOWED_EXTENSIONS.some((allowed) => name.endsWith(allowed))) {
    return `Unsupported format. Allowed formats: ${ALLOWED_EXTENSIONS.join(', ')}`;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `File exceeds the ${Math.round(MAX_UPLOAD_BYTES / (1024 * 1024))} MB limit.`;
  }
  if (file.size === 0) {
    return 'The file is empty.';
  }
  return null;
}

export function useDocuments(): UseDocumentsResult {
  const [documents, setDocuments] = useState<DocumentDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [uploading, setUploading] = useState(false);
  const [rejection, setRejection] = useState<UploadRejection | null>(null);

  const requestId = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++requestId.current;
    try {
      const data = await listDocuments();
      if (id !== requestId.current) return;
      setDocuments(data.documents);
      setError(null);
    } catch (cause) {
      if (id !== requestId.current) return;
      setError(
        cause instanceof ApiError ? cause : new ApiError('Failed to load documents.', 0, true),
      );
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  /*
   * Ingestion runs as a FastAPI background task, so the status returned by the
   * upload response is already stale by the time the list is refetched. Poll
   * while anything is PROCESSING and stop as soon as the set is quiescent.
   */
  const hasProcessing = documents.some((doc) => doc.status === 'PROCESSING');

  useEffect(() => {
    if (!hasProcessing) return;
    const timer = window.setInterval(() => {
      void refresh();
    }, PROCESSING_POLL_MS);
    return () => window.clearInterval(timer);
  }, [hasProcessing, refresh]);

  const upload = useCallback(
    async (file: File): Promise<boolean> => {
      const invalid = validateFile(file);
      if (invalid) {
        setRejection({ filename: file.name, reason: invalid });
        return false;
      }

      setUploading(true);
      setRejection(null);
      try {
        await uploadDocumentRequest(file);
        // The response already reports PROCESSING; refresh picks it up along
        // with anything else that changed in the meantime.
        await refresh();
        return true;
      } catch (cause) {
        setRejection({
          filename: file.name,
          reason:
            cause instanceof ApiError
              ? cause.message
              : 'The upload could not be completed.',
        });
        return false;
      } finally {
        setUploading(false);
      }
    },
    [refresh],
  );

  const remove = useCallback(
    async (id: string) => {
      // Optimistic removal keeps the list responsive; a failure restores it.
      const snapshot = documents;
      setDocuments((current) => current.filter((doc) => doc.id !== id));
      try {
        await deleteDocumentRequest(id);
      } catch (cause) {
        setDocuments(snapshot);
        setError(
          cause instanceof ApiError ? cause : new ApiError('Could not delete the document.', 0, true),
        );
      }
    },
    [documents],
  );

  const dismissRejection = useCallback(() => setRejection(null), []);

  return {
    documents,
    loading,
    error,
    uploading,
    rejection,
    upload,
    remove,
    refresh,
    dismissRejection,
  };
}
