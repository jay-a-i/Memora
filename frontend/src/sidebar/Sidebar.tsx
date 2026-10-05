import { useState } from 'react';
import { Button } from '../components/ui/Button';
import { IconCompose, IconClose } from '../components/ui/Icon';
import { Notice } from '../components/ui/Notice';
import { Modal } from '../components/ui/Modal';
import { DocumentItem } from '../documents/DocumentItem';
import { DocumentSkeleton, EmptyState } from '../components/ui/Skeleton';
import { SessionList } from './SessionList';
import { UploadDocument } from '../documents/UploadDocument';
import { config } from '../config';
import type { ChatSessionDto, DocumentDto } from '../types/api';
import type { ApiError } from '../api/client';
import type { UploadRejection } from '../hooks/useDocuments';

/**
 * Application sidebar: branding, new chat, session history and documents.
 *
 * Rendered as a static column on desktop and as a modal drawer on narrow
 * screens, where it would otherwise push the conversation off-screen.
 */

interface SidebarProps {
  sessions: ChatSessionDto[];
  activeSessionId: string | null;
  sessionsLoading: boolean;
  sessionsError: ApiError | null;
  onSelectSession: (id: string) => void;
  /** Runs after the delete is confirmed in the dialog. */
  onDeleteSession: (session: ChatSessionDto) => Promise<void>;
  onNewChat: () => void;
  onRetrySessions: () => void;

  documents: DocumentDto[];
  documentsLoading: boolean;
  documentsError: ApiError | null;
  uploadRejection: UploadRejection | null;
  uploading: boolean;
  onUpload: (file: File) => Promise<boolean>;
  onDeleteDocument: (document: DocumentDto) => Promise<void>;
  onDismissRejection: () => void;
  onRetryDocuments: () => void;

  /** True when rendered as a drawer; the close button is only shown then. */
  onClose?: () => void;
}

export function Sidebar(props: SidebarProps) {
  const {
    sessions,
    activeSessionId,
    sessionsLoading,
    sessionsError,
    onSelectSession,
    onDeleteSession,
    onNewChat,
    onRetrySessions,
    documents,
    documentsLoading,
    documentsError,
    uploadRejection,
    uploading,
    onUpload,
    onDeleteDocument,
    onDismissRejection,
    onRetryDocuments,
    onClose,
  } = props;

  const [sessionPendingDelete, setSessionPendingDelete] = useState<ChatSessionDto | null>(null);
  const [documentPendingDelete, setDocumentPendingDelete] = useState<DocumentDto | null>(null);

  async function confirmSessionDelete() {
    if (!sessionPendingDelete) return;
    const target = sessionPendingDelete;
    setSessionPendingDelete(null);
    await onDeleteSession(target);
  }

  async function confirmDocumentDelete() {
    if (!documentPendingDelete) return;
    const target = documentPendingDelete;
    setDocumentPendingDelete(null);
    await onDeleteDocument(target);
  }

  return (
    <div className="flex h-full min-h-0 flex-col border-r border-grey-200 bg-grey-150">
      <header className="flex items-center justify-between px-4 pb-3 pt-4">
        <span className="text-[15px] font-semibold tracking-tight text-grey-900">Memora</span>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            aria-label="Close navigation"
            className="-mr-1 rounded p-1 text-grey-500 transition-colors hover:bg-grey-200 hover:text-grey-900"
          >
            <IconClose className="h-4 w-4" />
          </button>
        )}
      </header>

      <div className="px-3">
        <Button
          variant="solid"
          onClick={onNewChat}
          icon={<IconCompose className="h-4 w-4" />}
          className="w-full"
        >
          New Chat
        </Button>
      </div>

      {/* Sessions take the flexible space; the list scrolls independently. */}
      <nav aria-label="Conversations" className="mt-4 min-h-0 flex-1 overflow-y-auto">
        <h2 className="px-4 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.09em] text-grey-400">
          Conversations
        </h2>

        {sessionsError && (
          <div className="px-3 pb-2">
            <Notice
              title={sessionsError.isAuthError ? 'API key rejected' : 'Could not load conversations'}
              onRetry={onRetrySessions}
            >
              {sessionsError.message}
            </Notice>
          </div>
        )}

        <SessionList
          sessions={sessions}
          activeId={activeSessionId}
          loading={sessionsLoading}
          onSelect={(id) => {
            onSelectSession(id);
            onClose?.();
          }}
          onDelete={setSessionPendingDelete}
          onNewChat={onNewChat}
        />
      </nav>

      <section aria-label="Documents" className="max-h-[45%] shrink-0 border-t border-grey-200">
        <div className="flex items-center justify-between px-4 pb-1.5 pt-3">
          <h2 className="text-[10px] font-semibold uppercase tracking-[0.09em] text-grey-400">
            Documents
          </h2>
          {documents.length > 0 && (
            <span className="tabular-nums text-[10px] text-grey-400">{documents.length}</span>
          )}
        </div>

        {documentsError && (
          <div className="px-3 pb-2">
            <Notice title="Could not load documents" onRetry={onRetryDocuments}>
              {documentsError.message}
            </Notice>
          </div>
        )}

        {uploadRejection && (
          <div className="px-3 pb-2">
            <Notice
              tone="warning"
              title="Upload failed"
              onDismiss={onDismissRejection}
            >
              <span className="font-medium text-grey-700">{uploadRejection.filename}</span>
              <span className="mt-0.5 block">{uploadRejection.reason}</span>
            </Notice>
          </div>
        )}

        <div className="min-h-0 overflow-y-auto">
          {documentsLoading ? (
            <div className="space-y-1 px-3 pb-2">
              <DocumentSkeleton />
              <DocumentSkeleton />
            </div>
          ) : documents.length === 0 ? (
            <EmptyState
              title="No documents"
              description="Upload a file and Memora will index it for retrieval."
            />
          ) : (
            <ul role="list" className="space-y-0.5 px-2 pb-1">
              {documents.map((document) => (
                <li key={document.id}>
                  <DocumentItem document={document} onDelete={setDocumentPendingDelete} />
                </li>
              ))}
            </ul>
          )}
        </div>

        <UploadDocument onUpload={onUpload} uploading={uploading} />
      </section>

      {!config.hasSecurityKey() && (
        <p className="border-t border-grey-200 px-4 py-2.5 text-[11px] leading-relaxed text-grey-500">
          No API key set. Add <code className="font-mono">VITE_APP_SECURITY_KEY</code> to the
          frontend environment.
        </p>
      )}

      <Modal
        open={sessionPendingDelete !== null}
        onClose={() => setSessionPendingDelete(null)}
        title="Delete conversation?"
        description={
          sessionPendingDelete
            ? `"${sessionPendingDelete.title}" and all of its messages will be removed. This cannot be undone.`
            : undefined
        }
      >
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setSessionPendingDelete(null)}>
            Cancel
          </Button>
          <Button variant="solid" onClick={confirmSessionDelete}>
            Delete
          </Button>
        </div>
      </Modal>

      <Modal
        open={documentPendingDelete !== null}
        onClose={() => setDocumentPendingDelete(null)}
        title="Delete document?"
        description={
          documentPendingDelete
            ? `"${documentPendingDelete.filename}" and its indexed chunks will be removed.`
            : undefined
        }
      >
        <div className="flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setDocumentPendingDelete(null)}>
            Cancel
          </Button>
          <Button variant="solid" onClick={confirmDocumentDelete}>
            Delete
          </Button>
        </div>
      </Modal>
    </div>
  );
}
