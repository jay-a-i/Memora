import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Button } from '../ui/Button';
import { IconSend } from '../ui/Icon';

/**
 * Message composer.
 *
 * Enter sends, Shift+Enter inserts a newline, and the textarea grows with its
 * content up to a cap. While a reply is streaming the send control becomes a
 * Stop control, which is also what prevents a duplicate submission.
 */

interface MessageComposerProps {
  /** True while a reply is streaming. */
  streaming: boolean;
  /**
   * Receives the question and, if the send fails, a callback that restores it.
   * The box is cleared on submit, so without that callback a failure (a wrong
   * key, an unreachable backend) discarded the text with nothing to retype from.
   */
  onSend: (question: string, onFailure: (question: string) => void) => void;
  onStop: () => void;
}

const MAX_TEXTAREA_HEIGHT = 200;

export function MessageComposer({ streaming, onSend, onStop }: MessageComposerProps) {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Read inside the restore callback, which must not close over a stale copy.
  const valueRef = useRef(value);
  valueRef.current = value;

  // Grow with content, then scroll internally once the cap is reached.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [value]);

  function submit() {
    const question = value.trim();
    if (!question || streaming) return;
    onSend(question, (failed) => {
      // Only restores if the user has not already typed something new.
      if (valueRef.current.trim() === '') {
        setValue(failed);
        textareaRef.current?.focus();
      }
    });
    setValue('');
    textareaRef.current?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  }

  const canSend = value.trim().length > 0 && !streaming;

  return (
    <div className="border-t border-grey-200 bg-grey-100/80 px-3 pb-3 pt-2.5 sm:px-5 sm:pb-4">
      <div className="mx-auto w-full max-w-3xl">
        <div
          className={`flex items-end gap-2 rounded-lg border bg-grey-25 px-2.5 py-2 transition-colors ${
            streaming ? 'border-grey-200' : 'border-grey-300 focus-within:border-grey-500'
          }`}
        >
          <label htmlFor="composer" className="sr-only">
            Message Memora
          </label>
          <textarea
            id="composer"
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Ask a question about your documents"
            rows={1}
            disabled={streaming}
            aria-describedby="composer-hint"
            className="max-h-[200px] min-h-[24px] w-full resize-none bg-transparent py-1 text-sm leading-relaxed text-grey-900 placeholder:text-grey-400 focus:outline-none disabled:cursor-not-allowed disabled:text-grey-400"
          />

          {streaming ? (
            <Button variant="outline" size="sm" onClick={onStop} className="mb-0.5">
              Stop
            </Button>
          ) : (
            <Button
              variant="solid"
              size="sm"
              onClick={submit}
              disabled={!canSend}
              aria-label="Send message"
              icon={<IconSend className="h-3.5 w-3.5" />}
              className="mb-0.5"
            />
          )}
        </div>

        <p id="composer-hint" className="mt-1.5 px-0.5 text-[11px] text-grey-400">
          Enter to send, Shift+Enter for a new line. Answers come from your uploaded documents.
        </p>
      </div>
    </div>
  );
}
