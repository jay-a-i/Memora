// Sidebar list of chat sessions for the active user.

import { useCallback, useEffect, useState } from "react";
import { createSession, getSessions } from "@/lib/api";
import type { Session } from "@/types/api";

export function useSessions(username: string | null) {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!username) return;
    setLoading(true);
    try {
      const data = await getSessions(username);
      setSessions(data);
    } finally {
      setLoading(false);
    }
  }, [username]);

  const create = useCallback(async (): Promise<number | null> => {
    if (!username) return null;
    const { session_id } = await createSession(username);
    await refresh();
    return session_id;
  }, [username, refresh]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return { sessions, loading, refresh, create };
}
