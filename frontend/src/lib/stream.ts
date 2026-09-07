// Streaming consumer for POST /chat/stream.
// The backend returns text/plain chunks; we read them progressively
// via ReadableStream and TextDecoder({ stream: true }) so multi-byte UTF-8
// sequences that straddle chunk boundaries decode correctly.

import type { Message, Role } from "@/types/api";

const API_BASE: string = import.meta.env.VITE_API_URL;

export interface StreamHandlers {
  onChunk: (text: string) => void;
  onDone: () => void;
  onError: (err: Error) => void;
  signal: AbortSignal;
}

export function streamChat(
  sessionId: number,
  message: string,
  handlers: StreamHandlers
): void {
  (async () => {
    let res: Response;
    try {
      res = await fetch(`${API_BASE}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message }),
        signal: handlers.signal,
      });
    } catch (e) {
      if (handlers.signal.aborted) return; // expected on cancel
      handlers.onError(e instanceof Error ? e : new Error(String(e)));
      return;
    }

    if (!res.ok || !res.body) {
      handlers.onError(new Error(`Stream failed: ${res.status}`));
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");

    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const text = decoder.decode(value, { stream: true });
        if (text.length > 0) handlers.onChunk(text);
      }
      handlers.onDone();
    } catch (e) {
      if (handlers.signal.aborted) return;
      handlers.onError(e instanceof Error ? e : new Error(String(e)));
    }
  })();
}

// Helper used by useChatSession to produce the immutable message list update.
export function appendToLast(
  messages: Message[],
  role: Role,
  chunk: string
): Message[] {
  const last = messages[messages.length - 1];
  if (last && last.role === role) {
    return [...messages.slice(0, -1), { ...last, content: last.content + chunk }];
  }
  return [...messages, { role, content: chunk }];
}
