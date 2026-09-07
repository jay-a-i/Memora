import { cn } from "@/lib/utils";
import type { Message } from "@/types/api";

interface MessageBubbleProps {
  message: Message;
  isStreaming?: boolean;
}

export function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "flex w-full",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      <div
        className={cn(
          "max-w-[80%] whitespace-pre-wrap rounded-lg px-4 py-2 text-sm shadow-sm",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground"
        )}
      >
        {message.content}
        {isStreaming && !isUser && (
          <span className="ml-1 inline-block animate-pulse">▍</span>
        )}
      </div>
    </div>
  );
}
