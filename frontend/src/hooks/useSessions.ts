import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError } from '../api/client';
import {
  createSession as createSessionRequest,
  deleteSession as deleteSessionRequest,
  listSessions,
} from '../api/chat';
import type { ChatSessionDto } from '../types/api';

/**
 * Session list state.
 *
 * The backend is the source of truth; this hook only caches what it last
 * fetched. The active session id is mirrored to localStorage purely so a
 * reload can restore where the user was.
 */

const ACTIVE_SESSION_KEY = 'memora.activeSessionId';

function readStoredSessionId(): string | null {
  try {
    return window.localStorage.getItem(ACTIVE_SESSION_KEY);
  } catch {
    return null;
  }
}

function storeSessionId(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(ACTIVE_SESSION_KEY, id);
    else window.localStorage.removeItem(ACTIVE_SESSION_KEY);
  } catch {
    // A non-persisted session id still works for this tab.
  }
}

export interface UseSessionsResult {
  sessions: ChatSessionDto[];
  loading: boolean;
  error: ApiError | null;
  /** Resolves once the initial load settles, used to defer the empty state. */
  initialised: boolean;
  refresh: () => Promise<void>;
  createSession: (title?: string) => Promise<ChatSessionDto>;
  removeSession: (id: string) => Promise<void>;
  restoreLastSession: () => string | null;
  rememberSession: (id: string | null) => void;
}

export function useSessions(): UseSessionsResult {
  const [sessions, setSessions] = useState<ChatSessionDto[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [initialised, setInitialised] = useState(false);

  // Guards against a stale response overwriting a newer one.
  const requestId = useRef(0);

  const refresh = useCallback(async () => {
    const id = ++requestId.current;
    try {
      const data = await listSessions();
      if (id !== requestId.current) return;
      setSessions(data);
      setError(null);
    } catch (cause) {
      if (id !== requestId.current) return;
      setError(cause instanceof ApiError ? cause : new ApiError('Failed to load sessions.', 0, true));
    } finally {
      if (id === requestId.current) {
        setLoading(false);
        setInitialised(true);
      }
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const createSession = useCallback(
    async (title?: string) => {
      const session = await createSessionRequest(title);
      // Newest first locally so the list does not appear to lag the selection.
      setSessions((current) => [session, ...current]);
      return session;
    },
    [],
  );

  const removeSession = useCallback(
    async (id: string) => {
      try {
        await deleteSessionRequest(id);
      } catch (cause) {
        // Recorded on the shared error state so the sidebar's existing notice
        // surfaces it; rethrowing would leave the dialog to handle it too.
        setError(
          cause instanceof ApiError
            ? cause
            : new ApiError('Could not delete the conversation.', 0, true),
        );
        return;
      }
      setSessions((current) => current.filter((s) => s.id !== id));
    },
    [],
  );

  const restoreLastSession = useCallback(() => readStoredSessionId(), []);

  const rememberSession = useCallback((id: string | null) => storeSessionId(id), []);

  return {
    sessions,
    loading,
    error,
    initialised,
    refresh,
    createSession,
    removeSession,
    restoreLastSession,
    rememberSession,
  };
}
