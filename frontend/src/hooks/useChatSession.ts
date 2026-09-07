// Active chat session: messages, streaming state, send/abort.
// Persists the last-selected sessionId in localStorage (keyed by username) so
// reloads land the user back where they left off.

import { useCallback, useEffect, useRef, useState } from "react";
import { getMessages } from "@/lib/api";
import { appendToLast, streamChat } from "@/lib/stream";
import type { Message } from "@/types/api";

function storageKey(username: string): string {
  return `memora.activeSessionId.${username}`;
}

export function useChatSession(username: string | null) {
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Rehydrate active session id from localStorage on first username match.
  useEffect(() => {
    if (!username) return;
    const raw = localStorage.getItem(storageKey(username));
    if (raw) {
      const n = Number(raw);
      if (Number.isInteger(n) && n > 0) {
        setSessionId(n);
      }
    }
  }, [username]);

  // Persist session id when it changes.
  useEffect(() => {
    if (!username) return;
    if (sessionId) {
      localStorage.setItem(storageKey(username), String(sessionId));
    } else {
      localStorage.removeItem(storageKey(username));
    }
  }, [username, sessionId]);

  // Load messages whenever the active session changes.
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await getMessages(sessionId);
        if (!cancelled) setMessages(data);
      } catch {
        if (!cancelled) setMessages([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  const selectSession = useCallback((id: number) => {
    setSessionId(id);
  }, []);

  const clearSession = useCallback(() => {
    setSessionId(null);
    setMessages([]);
  }, []);

  const sendMessage = useCallback(
    (text: string) => {
      if (!sessionId || isStreaming) return;
      // Append the user's message immediately.
      setMessages((prev) => [...prev, { role: "user", content: text }]);
      // Reserve an empty assistant bubble.
      setMessages((prev) => [...prev, { role: "assistant", content: "" }]);
      setIsStreaming(true);

      const controller = new AbortController();
      abortRef.current = controller;

      streamChat(sessionId, text, {
        onChunk: (chunk) => {
          setMessages((prev) => appendToLast(prev, "assistant", chunk));
        },
        onDone: () => {
          setIsStreaming(false);
          abortRef.current = null;
        },
        onError: () => {
          setIsStreaming(false);
          abortRef.current = null;
          // Drop the empty/partial assistant bubble; user bubble stays.
          setMessages((prev) => {
            const last = prev[prev.length - 1];
            if (last && last.role === "assistant" && last.content === "") {
              return prev.slice(0, -1);
            }
            return prev;
          });
        },
        signal: controller.signal,
      });
    },
    [sessionId, isStreaming]
  );

  const cancelStream = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return {
    sessionId,
    messages,
    isStreaming,
    selectSession,
    clearSession,
    sendMessage,
    cancelStream,
  };
}
