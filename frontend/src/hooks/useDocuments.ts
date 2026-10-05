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
  // Ids removed optimistically but not yet confirmed by the server. A poll that
  // was already in flight when the delete began can resolve with the deleted
  // row still in its payload, which put the row back on screen until the next
  // tick. Filtering these ids out of every refresh closes that window.
  const pendingDeletes = useRef<Set<string>>(new Set());
  // Holds the removed row itself, so a failed delete can put back exactly that
  // document instead of a stale copy of the whole list.
  const rollbackRef = useRef<Map<string, DocumentDto | null>>(new Map());

  const refresh = useCallback(async () => {
    const id = ++requestId.current;
    try {
      const data = await listDocuments();
      if (id !== requestId.current) return;
      // Drop rows whose delete has not been confirmed yet, so a poll issued
      // before the DELETE completed cannot resurrect them.
      const removed = pendingDeletes.current;
      setDocuments(
        removed.size > 0
          ? data.documents.filter((doc) => !removed.has(doc.id))
          : data.documents,
      );
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
      //
      // The rollback re-inserts only this one document rather than restoring a
      // whole snapshot. Restoring the render-time list overwrote whatever a
      // concurrent poll or upload had since written, so a failed delete could
      // discard a document that had just been uploaded.
      pendingDeletes.current.add(id);
      setDocuments((current) => {
        const removed = current.find((doc) => doc.id === id) ?? null;
        rollbackRef.current.set(id, removed);
        return current.filter((doc) => doc.id !== id);
      });

      try {
        await deleteDocumentRequest(id);
        // Any poll response still in flight is now stale; bump the generation so
        // it is discarded rather than re-adding the row.
        requestId.current += 1;
        pendingDeletes.current.delete(id);
      } catch (cause) {
        pendingDeletes.current.delete(id);
        const removed = rollbackRef.current.get(id) ?? null;
        rollbackRef.current.delete(id);
        setDocuments((current) =>
          removed && !current.some((doc) => doc.id === id)
            ? [...current, removed]
            : current,
        );
        setError(
          cause instanceof ApiError ? cause : new ApiError('Could not delete the document.', 0, true),
        );
      }
    },
    [],
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
