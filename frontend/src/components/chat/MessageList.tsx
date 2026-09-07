import { useEffect, useRef } from "react";
import { ScrollArea } from "@/components/ui/scroll-area";
import { MessageBubble } from "@/components/chat/MessageBubble";
import type { Message } from "@/types/api";

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
}

export function MessageList({ messages, isStreaming }: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to the bottom as new tokens arrive.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages, isStreaming]);

  return (
    <ScrollArea ref={scrollRef} className="flex-1 px-4 py-6">
      <div className="mx-auto flex w-full max-w-3xl flex-col gap-4">
        {messages.map((m, i) => (
          <MessageBubble
            key={i}
            message={m}
            isStreaming={
              isStreaming && i === messages.length - 1 && m.role === "assistant"
            }
          />
        ))}
      </div>
    </ScrollArea>
  );
}
