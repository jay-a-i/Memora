import { EmptyState } from "@/components/chat/EmptyState";
import { ChatInput } from "@/components/chat/ChatInput";
import { MessageList } from "@/components/chat/MessageList";
import type { Message } from "@/types/api";

interface ChatPaneProps {
  username: string;
  sessionId: number | null;
  messages: Message[];
  isStreaming: boolean;
  onSend: (text: string) => void;
}

export function ChatPane({
  username,
  sessionId,
  messages,
  isStreaming,
  onSend,
}: ChatPaneProps) {
  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-border px-6 py-3">
        <h1 className="text-lg font-semibold">
          Hey {username.charAt(0).toUpperCase() + username.slice(1)}!
        </h1>
      </header>

      {sessionId === null ? (
        <EmptyState />
      ) : (
        <MessageList messages={messages} isStreaming={isStreaming} />
      )}

      {sessionId !== null && (
        <ChatInput
          onSend={onSend}
          disabled={isStreaming}
          placeholder={
            isStreaming ? "Memora is replying…" : "Type a message..."
          }
        />
      )}

      {sessionId === null && (
        <div className="border-t border-border bg-background px-4 py-3 text-center text-sm text-muted-foreground">
          Create or select a chat to start messaging.
        </div>
      )}
    </div>
  );
}
