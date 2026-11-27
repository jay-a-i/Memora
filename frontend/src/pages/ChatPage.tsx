import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Sidebar } from '../sidebar/Sidebar';
import { MessageList } from '../components/chat/MessageList';
import { MessageComposer } from '../components/chat/MessageComposer';
import { ToolActivity } from '../components/chat/ToolActivity';
import { Button } from '../components/ui/Button';
import { Notice } from '../components/ui/Notice';
import { IconMenu } from '../components/ui/Icon';
import { useChat } from '../hooks/useChat';
import { useSessions } from '../hooks/useSessions';
import { useDocuments } from '../hooks/useDocuments';
import type { ChatSessionDto, DocumentDto } from '../types/api';

/**
 * The conversation workspace.
 *
 * Owns the shell layout, routing between sessions, and the drawer behaviour
 * on narrow screens. Conversation and document state live in hooks so this
 * component stays a composition of parts.
 */

export function ChatPage() {
  // Present on /c/:sessionId, absent on "/". <Routes> keeps this component
  // mounted across the switch, so an in-flight stream survives navigation.
  const { sessionId } = useParams<{ sessionId?: string }>();
  const navigate = useNavigate();

  const sessions = useSessions();
  const documents = useDocuments();

  const { createSession, refresh: refreshSessions } = sessions;
  const { initialised, sessions: sessionList, restoreLastSession, rememberSession } = sessions;

  const [drawerOpen, setDrawerOpen] = useState(false);

  /**
   * Resolves the session to stream into, creating one on first send so an
   * abandoned empty session never lands in the sidebar.
   */
  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId;
    const created = await createSession();
    void refreshSessions();
    navigate(`/c/${created.id}`, { replace: true });
    return created.id;
  }, [sessionId, createSession, refreshSessions, navigate]);

  const chat = useChat({
    sessionId: sessionId ?? null,
    ensureSession,
    onTurnComplete: () => {
      // Reordering the sidebar by recency is only correct after a turn lands.
      void refreshSessions();
    },
  });

  /*
   * Restore the last conversation on a cold load. The id is also in the URL,
   * so this only applies when the app is opened at the root path.
   */
  const [restored, setRestored] = useState(false);
  useEffect(() => {
    if (restored || sessionId || !initialised) return;
    setRestored(true);
    if (sessionList.length === 0) return;

    const last = restoreLastSession();
    const exists = last !== null && sessionList.some((s) => s.id === last);
    navigate(exists ? `/c/${last}` : `/c/${sessionList[0].id}`, { replace: true });
  }, [restored, sessionId, initialised, sessionList, restoreLastSession, navigate]);

  /*
   * Remember the active session so a reload returns to the same conversation.
   * Only written when a session is actually active -- clearing on "/" would
   * wipe the stored id before the restore effect above gets to read it.
   */
  useEffect(() => {
    if (sessionId) rememberSession(sessionId);
  }, [sessionId, rememberSession]);

  function handleNewChat() {
    setDrawerOpen(false);
    navigate('/');
  }

  async function handleDeleteSession(session: ChatSessionDto) {
    const removed = await sessions.removeSession(session.id);
    // Navigate only after the backend confirms the delete. On failure the row
    // stays in place and removeSession surfaces the reason.
    if (removed && session.id === sessionId) navigate('/', { replace: true });
  }

  async function handleDeleteDocument(document: DocumentDto) {
    await documents.remove(document.id);
  }

  const activeTitle =
    sessions.sessions.find((s) => s.id === sessionId)?.title ?? 'New Chat';

  return (
    <div className="flex h-full w-full overflow-hidden bg-grey-100">
      {/* Static sidebar from the md breakpoint up. */}
      <aside className="hidden w-[264px] shrink-0 md:block">
        <Sidebar
          sessions={sessions.sessions}
          activeSessionId={sessionId ?? null}
          sessionsLoading={sessions.loading}
          sessionsError={sessions.error}
          onSelectSession={(id) => navigate(`/c/${id}`)}
          onDeleteSession={handleDeleteSession}
          onNewChat={handleNewChat}
          onRetrySessions={() => void sessions.refresh()}
          documents={documents.documents}
          documentsLoading={documents.loading}
          documentsError={documents.error}
          uploadRejection={documents.rejection}
          uploading={documents.uploading}
          onUpload={documents.upload}
          onDeleteDocument={handleDeleteDocument}
          onDismissRejection={documents.dismissRejection}
          onRetryDocuments={() => void documents.refresh()}
        />
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-13 shrink-0 items-center gap-3 border-b border-grey-200 bg-grey-100/80 px-3 py-2.5 backdrop-blur-sm sm:px-5">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setDrawerOpen(true)}
            aria-label="Open navigation"
            aria-expanded={drawerOpen}
            className="md:hidden"
            icon={<IconMenu className="h-4 w-4" />}
          />

          <h1 className="min-w-0 flex-1 truncate text-sm font-medium text-grey-800">
            {activeTitle}
          </h1>

          {chat.sending && (
            <span className="shrink-0 text-[11px] text-grey-400" role="status" aria-live="polite">
              Responding
            </span>
          )}
        </header>

        {chat.historyError && (
          <div className="px-3 pt-3 sm:px-5">
            <Notice title="Could not load this conversation" onRetry={() => void chat.reload()}>
              {chat.historyError.message}
            </Notice>
          </div>
        )}

        {chat.error && (
          <div className="px-3 pt-3 sm:px-5">
            <Notice
              title={
                chat.error.isNetworkError
                  ? 'Connection interrupted'
                  : chat.error.isAuthError
                    ? 'API key rejected'
                    : chat.error.isConflict
                      ? 'Unfinished turn'
                      : chat.error.isValidationError
                        ? 'Invalid request'
                        : 'The request failed'
              }
              onRetry={() => void chat.retry()}
              onDismiss={chat.clearError}
              retryLabel={chat.needsResume ? 'Resume' : 'Retry'}
            >
              {chat.error.message}
              {chat.interrupted && ' The partial answer above was kept.'}
            </Notice>
          </div>
        )}

        {/* Shown when a turn is stopped or recovered from history, so the user
            always has an explicit way to continue it with the same turn_id. */}
        {!chat.error && chat.needsResume && (
          <div className="px-3 pt-3 sm:px-5">
            <Notice
              tone="warning"
              title={chat.interrupted ? 'Response interrupted' : 'Response not finished'}
              onRetry={() => void chat.retry()}
              retryLabel={chat.interrupted ? 'Resume' : 'Retry'}
            >
              {chat.interrupted
                ? 'The previous turn was stopped before the backend finished. The partial answer above was kept; resume it to complete this turn.'
                : 'The last turn has no saved answer. Retry it before asking a new question.'}
            </Notice>
          </div>
        )}

        <MessageList
          messages={chat.messages}
          loading={chat.loadingHistory}
          hasSession={sessionId !== undefined}
          hasOlder={chat.nextBeforeSeq !== null}
          loadingOlder={chat.loadingOlder}
          olderError={chat.olderError?.message ?? null}
          onLoadOlder={() => void chat.loadOlder()}
          activitySlot={
            chat.activeTools.length > 0 || chat.completedTools.length > 0 ? (
              <ToolActivity
                active={chat.activeTools}
                completed={chat.completedTools}
                streaming={chat.sending}
              />
            ) : null
          }
          emptyAction={
            documents.documents.length === 0 ? (
              <p className="text-[11px] text-grey-400">
                Add a document from the sidebar to get started.
              </p>
            ) : undefined
          }
        />

        <MessageComposer
          streaming={chat.sending}
          disabled={chat.loadingHistory || chat.needsResume}
          onSend={(question) => void chat.sendMessage(question)}
          onStop={chat.stop}
        />
      </main>

      {/* Drawer navigation below the md breakpoint. */}
      {drawerOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div
            className="absolute inset-0 bg-grey-950/25"
            onClick={() => setDrawerOpen(false)}
            aria-hidden="true"
          />
          <div className="absolute inset-y-0 left-0 w-[85%] max-w-[300px] shadow-[0_0_40px_-8px_rgb(22_22_22/0.3)]">
            <Sidebar
              sessions={sessions.sessions}
              activeSessionId={sessionId ?? null}
              sessionsLoading={sessions.loading}
              sessionsError={sessions.error}
              onSelectSession={(id) => navigate(`/c/${id}`)}
              onDeleteSession={handleDeleteSession}
              onNewChat={handleNewChat}
              onRetrySessions={() => void sessions.refresh()}
              documents={documents.documents}
              documentsLoading={documents.loading}
              documentsError={documents.error}
              uploadRejection={documents.rejection}
              uploading={documents.uploading}
              onUpload={documents.upload}
              onDeleteDocument={handleDeleteDocument}
              onDismissRejection={documents.dismissRejection}
              onRetryDocuments={() => void documents.refresh()}
              onClose={() => setDrawerOpen(false)}
            />
          </div>
        </div>
      )}
    </div>
  );
}
