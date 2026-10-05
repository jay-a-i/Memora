import { Button } from '../components/ui/Button';
import { IconTrash } from '../components/ui/Icon';
import type { ChatSessionDto } from '../types/api';

/**
 * One row in the session list.
 *
 * The active session is distinguished by a filled surface, a heavier left
 * rule and full-strength text; inactive rows are muted. No colour is involved.
 */

interface SessionItemProps {
  session: ChatSessionDto;
  active: boolean;
  onSelect: (id: string) => void;
  onDelete: (session: ChatSessionDto) => void;
}

/** "New Chat" is the backend's placeholder title; the first question is better. */
function isPlaceholderTitle(title: string): boolean {
  return title.trim().toLowerCase() === 'new chat';
}

function relativeTime(iso: string | null): string {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';

  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return 'just now';

  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;

  const days = Math.round(hours / 24);
  if (days < 7) return `${days}d ago`;

  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function SessionItem({ session, active, onSelect, onDelete }: SessionItemProps) {
  const label = isPlaceholderTitle(session.title)
    ? 'Untitled conversation'
    : session.title;

  return (
    <div
      className={`group relative flex items-center rounded-md transition-colors ${
        active ? 'bg-grey-200' : 'hover:bg-grey-150'
      }`}
    >
      {active && (
        <span
          aria-hidden="true"
          className="absolute inset-y-1.5 left-0 w-[2px] rounded-full bg-grey-600"
        />
      )}

      <button
        type="button"
        onClick={() => onSelect(session.id)}
        aria-current={active ? 'page' : undefined}
        className="flex min-w-0 flex-1 flex-col items-start gap-0.5 rounded-md py-2 pl-3 pr-8 text-left"
      >
        <span
          className={`w-full truncate text-[13px] leading-tight ${
            active ? 'font-medium text-grey-900' : 'text-grey-700'
          }`}
        >
          {label}
        </span>
        <span className="tabular-nums text-[11px] text-grey-400">
          {relativeTime(session.updated_at ?? session.created_at)}
        </span>
      </button>

      {/*
        Revealed on hover, but always reachable by keyboard.

        pointer-events-none until hover or focus: `opacity-0` alone left the
        button fully hit-testable at its absolute position, sitting on top of the
        row's own select button, so a click on an un-hovered row could open the
        delete dialog for what looked like a different target.
      */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onDelete(session)}
        aria-label={`Delete conversation: ${label}`}
        className="pointer-events-none absolute right-1 top-1/2 h-6 w-6 -translate-y-1/2 p-0 opacity-0 transition-opacity focus-visible:pointer-events-auto focus-visible:opacity-100 group-hover:pointer-events-auto group-hover:opacity-100"
        icon={<IconTrash className="h-3.5 w-3.5" />}
      />
    </div>
  );
}
