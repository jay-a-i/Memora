import type { ReactNode } from 'react';

/**
 * Inline failure notice.
 *
 * Errors are shown with a heavier border, an icon and text weight rather than
 * a colour wash, so failures stay legible within the monochrome palette.
 */

type Tone = 'error' | 'warning' | 'info';

interface NoticeProps {
  tone?: Tone;
  title: string;
  children?: ReactNode;
  onRetry?: () => void;
  retryLabel?: string;
  onDismiss?: () => void;
}

const TONES: Record<Tone, string> = {
  // Failure reads as a double-weight border; warnings stay single but softer.
  error: 'border-grey-400 bg-grey-100',
  warning: 'border-grey-300 bg-grey-50',
  info: 'border-grey-200 bg-grey-50',
};

export function Notice({
  tone = 'error',
  title,
  children,
  onRetry,
  retryLabel = 'Try again',
  onDismiss,
}: NoticeProps) {
  return (
    <div
      role="alert"
      className={`rounded-md border px-3.5 py-3 ${TONES[tone]} ${
        tone === 'error' ? 'border-l-[3px]' : ''
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p
            className={`text-xs ${
              tone === 'error' ? 'font-semibold text-grey-900' : 'font-medium text-grey-700'
            }`}
          >
            {title}
          </p>
          {children && (
            <div className="mt-1 text-xs leading-relaxed text-grey-600">{children}</div>
          )}
        </div>
        {onDismiss && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss"
            className="-mr-1 -mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-xs text-grey-500 transition-colors hover:bg-grey-200 hover:text-grey-900"
          >
            Dismiss
          </button>
        )}
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-2.5 rounded border border-grey-300 bg-grey-25 px-2.5 py-1 text-xs font-medium text-grey-800 transition-colors hover:border-grey-400 hover:bg-grey-100"
        >
          {retryLabel}
        </button>
      )}
    </div>
  );
}
