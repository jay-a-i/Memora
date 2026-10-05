import { Markdown } from './Markdown';
import { StreamingCursor } from './StreamingCursor';
import { Sources } from './Sources';
import type { ChatMessage } from '../../hooks/useChat';

/**
 * One conversation turn.
 *
 * User turns are compact and right-aligned on a plain surface; assistant
 * turns get the full reading measure with markdown. Neither is wrapped in a
 * heavy card -- separation comes from alignment, spacing and a hairline rule.
 */

interface MessageItemProps {
  message: ChatMessage;
}

export function MessageItem({ message }: MessageItemProps) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end px-1 py-2.5">
        <div className="max-w-[85%] rounded-lg rounded-br-sm border border-grey-200 bg-grey-50 px-3.5 py-2.5 sm:max-w-[75%]">
          <p className="prose-user">{message.content}</p>
        </div>
      </div>
    );
  }

  const isEmpty = message.content.length === 0;

  return (
    <div className="px-1 py-2.5">
      <div className="max-w-3xl">
        {isEmpty && message.streaming ? (
          // Nothing has arrived yet; the tool indicator carries the moment.
          <p className="text-xs italic text-grey-400">Thinking...</p>
        ) : (
          <Markdown>{message.content}</Markdown>
        )}

        {message.streaming && !isEmpty && <StreamingCursor />}

        <Sources sources={message.sources} />
      </div>
    </div>
  );
}
