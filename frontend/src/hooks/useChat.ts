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
  sources?: RetrievalSource[];
  /** True while tokens are still arriving for this message. */
  streaming?: boolean;
  /** Set when this turn ended in a failure, enabling retry. */
  failed?: boolean;
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

export interface ToolActivity {
  name: string;
  status: string;
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
  interrupted: boolean;
  sendMessage: (question: string) => Promise<void>;
  retry: () => Promise<void>;
  stop: () => void;
  reload: () => Promise<void>;
  clearError: () => void;
}

let idCounter = 0;
function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-${idCounter}`;
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

  const abortRef = useRef<AbortController | null>(null);
  const lastQuestionRef = useRef<string | null>(null);
  // Read inside the stream callbacks, which must not re-subscribe on change.
  const onTurnCompleteRef = useRef(onTurnComplete);
  onTurnCompleteRef.current = onTurnComplete;

  // Reload the transcript whenever the session changes.
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      setHistoryError(null);
      return;
    }

    let cancelled = false;
    setLoadingHistory(true);

    getSessionHistory(sessionId)
      .then((history) => {
        if (cancelled) return;
        setMessages(
          history.messages
            .filter(isRenderable)
            .map((m) => ({ id: nextId(m.role), role: m.role, content: m.content })),
        );
        setHistoryError(null);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setHistoryError(toApiError(cause, 'Could not load this conversation.'));
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // Abandon any in-flight stream when the component unmounts or the session
  // changes, so tokens cannot land in the next conversation.
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, [sessionId]);

  const runStream = useCallback(
    async (question: string, targetSessionId: string) => {
      const assistantId = nextId('assistant');

      setSending(true);
      setError(null);
      setInterrupted(false);
      setActiveTools([]);
      setCompletedTools([]);
      setMessages((current) => [
        ...current,
        {
          id: assistantId,
          role: 'assistant',
          content: '',
          streaming: true,
        },
      ]);

      const controller = new AbortController();
      abortRef.current = controller;

      /** Appends to the streaming assistant message only. */
      const appendToStream = (text: string) => {
        setMessages((current) =>
          current.map((m) =>
            m.id === assistantId ? { ...m, content: m.content + text } : m,
          ),
        );
      };

      const patchStream = (patch: Partial<ChatMessage>) => {
        setMessages((current) =>
          current.map((m) => (m.id === assistantId ? { ...m, ...patch } : m)),
        );
      };

      try {
        await streamChat({
          request: {
            session_id: targetSessionId,
            // Only the new question is sent; the backend recovers prior turns
            // from PostgreSQL and treats the final message as the question.
            messages: [{ role: 'user', content: question }],
          },
          signal: controller.signal,
          onEvent: (event) => {
            switch (event.type) {
              case 'chunk':
                appendToStream(event.content);
                break;

              case 'tool_start':
                // The backend discards text emitted before a tool call
                // (chat.py resets current_parts on on_tool_start) and keeps
                // only the final segment. Mirror that here so what is on
                // screen matches what gets persisted and re-read on reload.
                patchStream({ content: '' });
                setActiveTools((current) => [
                  ...current.filter((t) => t.name !== event.name),
                  { name: event.name, status: event.status },
                ]);
                break;

              case 'tool_end':
                setActiveTools((current) => {
                  const finished = current.find((t) => t.name === event.name);
                  if (finished) {
                    setCompletedTools((done) =>
                      done.some((t) => t.name === event.name)
                        ? done
                        : [...done, finished],
                    );
                  }
                  return current.filter((t) => t.name !== event.name);
                });
                break;

              case 'sources':
                patchStream({ sources: event.sources });
                break;

              case 'done':
                patchStream({ streaming: false });
                break;

              case 'error':
                // Reported inside the stream because the response has already
                // started; the partial answer stays on screen.
                patchStream({ streaming: false, failed: true });
                setError(new ApiError(event.message, 500));
                break;
            }
          },
        });

        patchStream({ streaming: false });
      } catch (cause) {
        if (controller.signal.aborted) {
          // A user-initiated stop is not a failure; keep the partial answer.
          patchStream({ streaming: false });
          setInterrupted(true);
        } else {
          const apiError = toApiError(cause, 'The response stream was interrupted.');
          patchStream({ streaming: false, failed: true });
          setError(apiError);
        }
      } finally {
        abortRef.current = null;
        setSending(false);
        setActiveTools([]);
        onTurnCompleteRef.current?.();
      }
    },
    [],
  );

  const sendMessage = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || sending) return;

      lastQuestionRef.current = trimmed;

      // The user turn is rendered immediately; the backend persists it before
      // the stream opens, so the optimistic copy matches stored state.
      setMessages((current) => [
        ...current,
        { id: nextId('user'), role: 'user', content: trimmed },
      ]);

      try {
        const targetSessionId = await ensureSession();
        await runStream(trimmed, targetSessionId);
      } catch (cause) {
        const apiError = toApiError(cause, 'Could not start the conversation.');
        // Drop the optimistic user turn; it was never persisted.
        setMessages((current) => current.slice(0, -1));
        setError(apiError);
      }
    },
    [sending, ensureSession, runStream],
  );

  const retry = useCallback(async () => {
    const question = lastQuestionRef.current;
    if (!question || sending) return;

    // Remove the failed assistant turn; the user question stays because the
    // backend already committed it.
    setMessages((current) => {
      const last = current[current.length - 1];
      return last?.role === 'assistant' ? current.slice(0, -1) : current;
    });
    setError(null);

    try {
      const targetSessionId = await ensureSession();
      await runStream(question, targetSessionId);
    } catch (cause) {
      setError(toApiError(cause, 'Could not retry the request.'));
    }
  }, [sending, ensureSession, runStream]);

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const reload = useCallback(async () => {
    if (!sessionId) return;
    const history = await getSessionHistory(sessionId);
    setMessages(
      history.messages
        .filter(isRenderable)
        .map((m) => ({ id: nextId(m.role), role: m.role, content: m.content })),
    );
  }, [sessionId]);

  const clearError = useCallback(() => setError(null), []);

  return {
    messages,
    loadingHistory,
    historyError,
    sending,
    activeTools,
    completedTools,
    error,
    interrupted,
    sendMessage,
    retry,
    stop,
    reload,
    clearError,
  };
}
