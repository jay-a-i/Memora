import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';
import { getSessionHistory } from '../api/chat';
import { streamChat } from '../utils/sse';
import type { ChatMessageDto, RetrievalSource } from '../types/api';

/** A message as the UI needs it: the DTO plus client-only render state. */
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  /** The logical turn this message belongs to, when known. */
  turnId?: string;
  sources?: RetrievalSource[];
  /** True while tokens are still arriving for this message. */
  streaming?: boolean;
  /** Set when this turn ended in a failure, enabling retry. */
  failed?: boolean;
}

export interface ToolActivity {
  name: string;
  status: string;
}

/**
 * One logical user turn that has not completed. It is kept so a retry or a
 * resume reuses the original `turn_id`, the original question and the original
 * session. The backend rejects a reused ID with different content, and it
 * rejects a new question while an earlier turn is unfinished.
 */
interface PendingTurn {
  /** Null only while a brand-new session is still being created. */
  sessionId: string | null;
  turnId: string;
  question: string;
}

export interface UseChatOptions {
  sessionId: string | null;
  /**
   * Resolves the session to stream into, creating one when none is active.
   * Keeps session creation out of the streaming path.
   */
  ensureSession: () => Promise<string>;
  /** Called after a turn completes so the session list can reorder. */
  onTurnComplete?: () => void;
}

export interface UseChatResult {
  messages: ChatMessage[];
  loadingHistory: boolean;
  historyError: ApiError | null;
  sending: boolean;
  /** Populated while any tool is running. */
  activeTools: ToolActivity[];
  /** Tools that already finished this turn, collapsed into a summary. */
  completedTools: ToolActivity[];
  error: ApiError | null;
  /** True when the last turn was stopped before it finished. */
  interrupted: boolean;
  /** True when an unfinished turn exists for the active session. */
  needsResume: boolean;
  /** Cursor for the next older history page; null when nothing is older. */
  nextBeforeSeq: number | null;
  loadingOlder: boolean;
  olderError: ApiError | null;
  sendMessage: (question: string) => Promise<void>;
  /** Retries or resumes the pending turn with its original turn_id. */
  retry: () => Promise<void>;
  stop: () => void;
  reload: () => Promise<void>;
  loadOlder: () => Promise<void>;
  clearError: () => void;
}

/** Messages fetched per history request. Matches the backend default. */
const HISTORY_PAGE_SIZE = 50;

/**
 * Generates one stable ID for a logical user turn.
 *
 * `crypto.randomUUID()` is 36 characters, inside the backend's 1-64 limit.
 * The fallback is used on non-secure origins where `crypto.randomUUID` is
 * unavailable; it stays unique enough for one browser session.
 */
function newTurnId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `turn-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * The transcript can also carry system and tool rows, which are internal
 * plumbing. This narrows the DTO union to the two renderable roles.
 */
function isRenderable(message: ChatMessageDto): message is ChatMessageDto & {
  role: 'user' | 'assistant';
} {
  return message.role === 'user' || message.role === 'assistant';
}

/**
 * Stable key for a stored message.
 *
 * A session has at most one user and one assistant row per turn (enforced by
 * the backend's unique constraint), so turn + role is a stable identity across
 * paginated requests. Using it rather than a fresh counter id is what makes
 * prepending older pages duplicate-free.
 */
function historicalId(message: ChatMessageDto): string {
  return `${message.turn_id}:${message.role}`;
}

function toView(message: ChatMessageDto & { role: 'user' | 'assistant' }): ChatMessage {
  return {
    id: historicalId(message),
    role: message.role,
    content: message.content,
    turnId: message.turn_id,
  };
}

/**
 * Finds the newest user turn that has no assistant answer in the same page.
 *
 * Only the newest history page is inspected. The backend rejects new turns
 * while an earlier one is unfinished, so an unfinished turn is always the last
 * user message and therefore present in that page.
 */
function findUnfinishedTurn(messages: ChatMessageDto[]): ChatMessageDto | null {
  const answered = new Set<string>();
  for (const message of messages) {
    if (message.role === 'assistant') answered.add(message.turn_id);
  }

  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.role === 'user' && !answered.has(message.turn_id)) {
      return message;
    }
  }

  return null;
}

function toApiError(cause: unknown, fallback: string): ApiError {
  if (cause instanceof ApiError) return cause;
  if (cause instanceof DOMException && cause.name === 'AbortError') {
    return new ApiError('The request was stopped.', 0, true);
  }
  return new ApiError(fallback, 0, true);
}

export function useChat({
  sessionId,
  ensureSession,
  onTurnComplete,
}: UseChatOptions): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState<ApiError | null>(null);
  const [sending, setSending] = useState(false);
  const [activeTools, setActiveTools] = useState<ToolActivity[]>([]);
  const [completedTools, setCompletedTools] = useState<ToolActivity[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [interrupted, setInterrupted] = useState(false);
  const [pendingTurn, setPendingTurnState] = useState<PendingTurn | null>(null);
  const [nextBeforeSeq, setNextBeforeSeq] = useState<number | null>(null);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [olderError, setOlderError] = useState<ApiError | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const lastQuestionRef = useRef<string | null>(null);
  const pendingTurnRef = useRef<PendingTurn | null>(null);
  const sendingRef = useRef(false);
  /** True from turn setup until the stream itself takes ownership. */
  const creatingTurnRef = useRef(false);
  const sessionIdRef = useRef<string | null>(sessionId);
  const historyRequestId = useRef(0);
  const olderRequestId = useRef(0);
  /** Invalidates callbacks from a stream that no longer owns the transcript. */
  const runTokenRef = useRef(0);
  /** Set once `reload` exists, so the stream can re-sync after a 409. */
  const reloadRef = useRef<() => void>(() => {});

  sessionIdRef.current = sessionId;

  // Read inside the stream callbacks, which must not re-subscribe on change.
  const onTurnCompleteRef = useRef(onTurnComplete);
  onTurnCompleteRef.current = onTurnComplete;

  const setPendingTurn = useCallback((turn: PendingTurn | null) => {
    pendingTurnRef.current = turn;
    setPendingTurnState(turn);
  }, []);

  const applyHistory = useCallback(
    (history: ChatMessageDto[], targetSession: string) => {
      setMessages(history.filter(isRenderable).map(toView));

      const unfinished = findUnfinishedTurn(history);
      if (unfinished) {
        setPendingTurn({
          sessionId: targetSession,
          turnId: unfinished.turn_id,
          question: unfinished.content,
        });
        setInterrupted(true);
      } else if (pendingTurnRef.current?.sessionId === targetSession) {
        // The stored transcript no longer has an unfinished turn (for example
        // it completed in another tab), so drop the stale resume prompt.
        setPendingTurn(null);
        setInterrupted(false);
      }
    },
    [setPendingTurn],
  );

  // Reload the transcript whenever the session changes.
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      setHistoryError(null);
      setOlderError(null);
      setNextBeforeSeq(null);
      setLoadingHistory(false);
      return;
    }

    const requestId = ++historyRequestId.current;
    setLoadingHistory(true);
    setHistoryError(null);
    setOlderError(null);
    setNextBeforeSeq(null);

    getSessionHistory(sessionId, { limit: HISTORY_PAGE_SIZE })
      .then((history) => {
        if (requestId !== historyRequestId.current) return;
        setNextBeforeSeq(history.next_before_seq);

        /*
         * A live turn owns the tail of the transcript. This matters on the
         * lazy-creation path: sending the first message navigates to /c/{id},
         * which fires this fetch while the optimistic turn is still streaming.
         * Replacing messages here would erase that turn.
         */
        const pending = pendingTurnRef.current;
        if (pending && (pending.sessionId === null || pending.sessionId === sessionId)) {
          return;
        }

        applyHistory(history.messages, sessionId);
      })
      .catch((cause: unknown) => {
        if (requestId !== historyRequestId.current) return;
        setHistoryError(toApiError(cause, 'Could not load this conversation.'));
      })
      .finally(() => {
        if (requestId === historyRequestId.current) setLoadingHistory(false);
      });
  }, [sessionId, applyHistory]);

  /*
   * Abandon an in-flight stream when navigating to a different conversation.
   *
   * The exception is the session change caused by creating a session for the
   * turn that is already in flight: that activation must not abort its own
   * stream. Any other navigation drops the pending marker for the old session;
   * its claimed user message stays in PostgreSQL, so reopening it re-detects
   * the unfinished turn from history.
   */
  useEffect(() => {
    const pending = pendingTurnRef.current;
    const activatingOwnTurn =
      pending !== null &&
      (pending.sessionId === null || pending.sessionId === sessionId) &&
      (creatingTurnRef.current || sendingRef.current);
    if (activatingOwnTurn) return;

    setPendingTurn(null);

    runTokenRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
    sendingRef.current = false;
    setSending(false);
    setActiveTools([]);
    setCompletedTools([]);
    setError(null);
    setInterrupted(false);
  }, [sessionId, setPendingTurn]);

  // Abandon any in-flight stream on unmount so no state update lands after
  // the component is gone.
  useEffect(() => {
    return () => {
      runTokenRef.current += 1;
      abortRef.current?.abort();
      abortRef.current = null;
      sendingRef.current = false;
      creatingTurnRef.current = false;
    };
  }, []);

  const runStream = useCallback(
    async (question: string, turnId: string, targetSessionId: string) => {
      const runToken = ++runTokenRef.current;
      const assistantId = `local-assistant-${turnId}`;
      const isCurrent = () =>
        runToken === runTokenRef.current && sessionIdRef.current === targetSessionId;

      creatingTurnRef.current = false;
      sendingRef.current = true;
      setSending(true);
      setError(null);
      setInterrupted(false);
      setActiveTools([]);
      setCompletedTools([]);

      // Replace any earlier attempt for this turn with one fresh placeholder.
      setMessages((current) => [
        ...current.filter((message) => !(message.turnId === turnId && message.role === 'assistant')),
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          turnId,
          streaming: true,
        },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;
      let sawDone = false;
      let sawError = false;

      /** Appends to the streaming assistant message only. */
      const appendToStream = (text: string) => {
        if (!isCurrent()) return;
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId ? { ...message, content: message.content + text } : message,
          ),
        );
      };

      const patchStream = (patch: Partial<ChatMessage>) => {
        if (!isCurrent()) return;
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId ? { ...message, ...patch } : message,
          ),
        );
      };

      try {
        await streamChat({
          request: {
            session_id: targetSessionId,
            // Only the new question is sent; the backend recovers prior turns
            // from PostgreSQL and treats the final message as the question.
            messages: [{ role: 'user', content: question }],
            turn_id: turnId,
          },
          signal: controller.signal,
          onEvent: (event) => {
            if (!isCurrent()) return;

            switch (event.type) {
              case 'chunk':
                appendToStream(event.content);
                break;

              case 'tool_start':
                // The backend discards text emitted before a tool call
                // (chat.py resets current_parts on tool_start) and keeps only
                // the final segment. Mirror that here so what is on screen
                // matches what gets persisted and re-read on reload.
                patchStream({ content: '' });
                setActiveTools((current) => [
                  ...current.filter((tool) => tool.name !== event.name),
                  { name: event.name, status: event.status },
                ]);
                break;

              case 'tool_end':
                // chat.py resets its accumulated parts on tool_end as well, so
                // any text rendered before this boundary is not persisted.
                patchStream({ content: '' });
                setActiveTools((current) => {
                  const finished = current.find((tool) => tool.name === event.name);
                  if (finished) {
                    setCompletedTools((done) =>
                      done.some((tool) => tool.name === event.name)
                        ? done
                        : [...done, finished],
                    );
                  }
                  return current.filter((tool) => tool.name !== event.name);
                });
                break;

              case 'sources':
                patchStream({ sources: event.sources });
                break;

              case 'done':
                sawDone = true;
                patchStream({ streaming: false });
                break;

              case 'error':
                // Reported inside the stream because the response has already
                // started; the partial answer stays on screen and the turn
                // remains resumable with the same turn_id.
                sawError = true;
                patchStream({ streaming: false, failed: true });
                setError(new ApiError(event.message, 500));
                break;
            }
          },
        });

        if (!isCurrent()) return;

        if (sawDone) {
          patchStream({ streaming: false });
          setPendingTurn(null);
          setInterrupted(false);
        } else if (!sawError) {
          // The connection ended without the backend's done frame, so the
          // stored answer may be incomplete. Keep the turn resumable.
          patchStream({ streaming: false, failed: true });
          setError(
            new ApiError(
              'The response ended before it was marked complete. Resume this turn to finish it.',
              0,
              true,
            ),
          );
        }
      } catch (cause) {
        if (!isCurrent()) return;

        if (controller.signal.aborted) {
          // A user-initiated stop is not a failure; keep the partial answer
          // and leave the turn pending so it can be resumed.
          patchStream({ streaming: false });
          setInterrupted(true);
        } else {
          const apiError = toApiError(cause, 'The response stream was interrupted.');
          patchStream({ streaming: false, failed: true });
          setError(apiError);

          /*
           * A conflict means the backend did not accept this turn (for
           * example another tab left an earlier turn unfinished). This turn
           * was never claimed, so drop its marker and reload the transcript to
           * discover the turn that actually needs resuming.
           */
          if (apiError.isConflict) {
            setPendingTurn(null);
            reloadRef.current();
          }
        }
      } finally {
        /*
         * Only the newest run may clear shared stream state. A stale run (its
         * turn was abandoned by navigating away) must not unset `sending` for
         * a newer run in whatever conversation is now active.
         */
        if (runToken === runTokenRef.current) {
          abortRef.current = null;
          sendingRef.current = false;
          setSending(false);
          setActiveTools([]);
          onTurnCompleteRef.current?.();
        }
      }
    },
    [setPendingTurn],
  );

  const sendMessage = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || sendingRef.current || loadingHistory) return;

      /*
       * The backend answers 409 while any earlier turn is unfinished. Block
       * locally instead of submitting, so the user is pointed at the resume
       * action rather than shown a conflict after the optimistic question.
       */
      const pending = pendingTurnRef.current;
      if (pending && pending.sessionId === sessionIdRef.current) {
        setError(
          new ApiError(
            'An earlier response is unfinished. Resume it before asking a new question.',
            409,
          ),
        );
        return;
      }

      lastQuestionRef.current = trimmed;

      const turnId = newTurnId();
      const userId = `local-user-${turnId}`;

      // Mark the turn pending before navigation, so the history fetch that the
      // lazy session creation triggers cannot erase the optimistic question.
      creatingTurnRef.current = true;
      setPendingTurn({ sessionId: sessionIdRef.current, turnId, question: trimmed });
      setMessages((current) => [
        ...current,
        { id: userId, role: 'user', content: trimmed, turnId },
      ]);

      let targetSessionId: string;
      try {
        targetSessionId = await ensureSession();
      } catch (cause) {
        // Nothing reached the backend, so the turn is not resumable: remove
        // the optimistic question and let a normal retry send it fresh.
        creatingTurnRef.current = false;
        setPendingTurn(null);
        setMessages((current) => current.filter((message) => message.id !== userId));
        setError(toApiError(cause, 'Could not start the conversation.'));
        return;
      }

      setPendingTurn({ sessionId: targetSessionId, turnId, question: trimmed });
      await runStream(trimmed, turnId, targetSessionId);
    },
    [ensureSession, loadingHistory, runStream, setPendingTurn],
  );

  const retry = useCallback(async () => {
    if (sendingRef.current) return;

    const pending = pendingTurnRef.current;
    if (!pending) {
      // The previous attempt failed before a turn was claimed (for example
      // session creation failed). Re-sending is a genuinely new turn.
      const question = lastQuestionRef.current;
      if (question) await sendMessage(question);
      return;
    }

    let targetSessionId = pending.sessionId;
    if (!targetSessionId) {
      creatingTurnRef.current = true;
      try {
        targetSessionId = await ensureSession();
      } catch (cause) {
        creatingTurnRef.current = false;
        setError(toApiError(cause, 'Could not resume the conversation.'));
        return;
      }
      setPendingTurn({ ...pending, sessionId: targetSessionId });
    }

    // A pending turn belongs to its original session; never run it elsewhere.
    if (targetSessionId !== sessionIdRef.current) return;

    setError(null);
    // The user question stays; only the failed/partial answer is replaced.
    setMessages((current) =>
      current.filter(
        (message) => !(message.role === 'assistant' && message.turnId === pending.turnId),
      ),
    );

    await runStream(pending.question, pending.turnId, targetSessionId);
  }, [ensureSession, runStream, sendMessage, setPendingTurn]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reload = useCallback(async () => {
    if (!sessionId) return;

    const requestId = ++historyRequestId.current;
    setLoadingHistory(true);
    setHistoryError(null);

    try {
      const history = await getSessionHistory(sessionId, { limit: HISTORY_PAGE_SIZE });
      if (requestId !== historyRequestId.current || sessionIdRef.current !== sessionId) return;
      setNextBeforeSeq(history.next_before_seq);
      applyHistory(history.messages, sessionId);
    } catch (cause) {
      if (requestId !== historyRequestId.current || sessionIdRef.current !== sessionId) return;
      // Caught rather than thrown: callers use `void reload()` from an event
      // handler, and an unhandled rejection would surface in the console.
      setHistoryError(toApiError(cause, 'Could not load this conversation.'));
    } finally {
      if (requestId === historyRequestId.current) setLoadingHistory(false);
    }
  }, [sessionId, applyHistory]);

  reloadRef.current = () => {
    void reload();
  };

  const loadOlder = useCallback(async () => {
    if (!sessionId || nextBeforeSeq === null || loadingOlder) return;

    const cursor = nextBeforeSeq;
    const requestId = ++olderRequestId.current;
    setLoadingOlder(true);
    setOlderError(null);

    try {
      const page = await getSessionHistory(sessionId, {
        limit: HISTORY_PAGE_SIZE,
        before_seq: cursor,
      });
      if (requestId !== olderRequestId.current || sessionIdRef.current !== sessionId) return;

      setNextBeforeSeq(page.next_before_seq);
      setMessages((current) => {
        const seen = new Set(current.map((message) => message.id));
        const older = page.messages
          .filter(isRenderable)
          .map(toView)
          .filter((message) => !seen.has(message.id));
        return [...older, ...current];
      });
    } catch (cause) {
      if (requestId !== olderRequestId.current || sessionIdRef.current !== sessionId) return;
      setOlderError(toApiError(cause, 'Could not load older messages.'));
    } finally {
      if (requestId === olderRequestId.current) setLoadingOlder(false);
    }
  }, [sessionId, nextBeforeSeq, loadingOlder]);

  const clearError = useCallback(() => setError(null), []);

  const needsResume =
    pendingTurn !== null &&
    pendingTurn.sessionId === sessionId &&
    !sending &&
    !loadingHistory;

  return {
    messages,
    loadingHistory,
    historyError,
    sending,
    activeTools,
    completedTools,
    error,
    interrupted,
    needsResume,
    nextBeforeSeq,
    loadingOlder,
    olderError,
    sendMessage,
    retry,
    stop,
    reload,
    loadOlder,
    clearError,
  };
}
