import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { MessageItem } from './MessageItem';
import { Button } from '../ui/Button';
import { EmptyState, MessageSkeleton } from '../ui/Skeleton';
import { IconArrowDown, IconSearch } from '../ui/Icon';
import type { ChatMessage } from '../../hooks/useChat';

/**
 * Scrollable transcript.
 *
 * Auto-scroll follows the stream only while the reader is already at the
 * bottom. Scrolling up is treated as an intent to read, so incoming tokens do
 * not yank the viewport away; a jump-to-latest control appears instead.
 */

interface MessageListProps {
  messages: ChatMessage[];
  loading: boolean;
  hasSession: boolean;
  /**
   * Rendered immediately above the final message, so tool activity stays
   * attached to the answer it belongs to instead of floating at the top.
   */
  activitySlot?: ReactNode;
  emptyAction?: ReactNode;
}

/** Distance from the bottom, in px, still treated as "following along". */
const STICKY_THRESHOLD_PX = 80;

export function MessageList({
  messages,
  loading,
  hasSession,
  activitySlot,
  emptyAction,
}: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const [pinned, setPinned] = useState(true);

  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    setPinned(distance <= STICKY_THRESHOLD_PX);
  }, []);

  /*
   * Runs before paint so tokens never appear one frame at the wrong offset.
   * Instant scroll is deliberate: smooth behaviour lags a fast token stream
   * and leaves the caret behind the text.
   */
  useLayoutEffect(() => {
    if (!pinned) return;
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [messages, pinned]);

  // Jump to the newest message when a conversation is first opened.
  useEffect(() => {
    if (!hasSession) {
      setPinned(true);
      return;
    }
    bottomRef.current?.scrollIntoView({ block: 'end' });
  }, [hasSession]);

  const jumpToLatest = useCallback(() => {
    bottomRef.current?.scrollIntoView({ block: 'end' });
    setPinned(true);
  }, []);

  if (!hasSession) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <EmptyState
          icon={<IconSearch className="h-6 w-6" />}
          title="Start a conversation"
          description="Ask a question and Memora will search your uploaded documents to answer it."
          action={emptyAction}
        />
      </div>
    );
  }

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="scrollbar-thin h-full overflow-y-auto overscroll-contain px-3 py-4 sm:px-5"
      >
        <div className="mx-auto w-full max-w-3xl">
          {loading && messages.length === 0 ? (
            <MessageSkeleton />
          ) : (
            messages.map((message, index) => (
              <div key={message.id}>
                {/* Activity belongs to the turn being produced, so it sits
                    directly above the newest message rather than the top. */}
                {activitySlot && index === messages.length - 1 && activitySlot}
                <MessageItem message={message} />
              </div>
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      {!pinned && messages.length > 0 && (
        <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
          <Button
            variant="outline"
            size="sm"
            onClick={jumpToLatest}
            icon={<IconArrowDown className="h-3.5 w-3.5" />}
            className="pointer-events-auto shadow-[0_2px_8px_-2px_rgb(22_22_22/0.18)]"
          >
            Latest
          </Button>
        </div>
      )}
    </div>
  );
}
