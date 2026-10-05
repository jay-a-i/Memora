import { SessionItem } from './SessionItem';
import { EmptyState, SessionSkeleton } from '../components/ui/Skeleton';
import { IconSearch } from '../components/ui/Icon';
import type { ChatSessionDto } from '../types/api';

interface SessionListProps {
  sessions: ChatSessionDto[];
  activeId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onDelete: (session: ChatSessionDto) => void;
  onNewChat: () => void;
}

export function SessionList({
  sessions,
  activeId,
  loading,
  onSelect,
  onDelete,
  onNewChat,
}: SessionListProps) {
  if (loading) {
    return (
      <div className="space-y-1 p-2">
        <SessionSkeleton />
        <SessionSkeleton />
        <SessionSkeleton />
      </div>
    );
  }

  if (sessions.length === 0) {
    return (
      <EmptyState
        icon={<IconSearch className="h-5 w-5" />}
        title="No conversations yet"
        description="Your conversations will appear here once you ask a question."
        action={
          <button
            type="button"
            onClick={onNewChat}
            className="text-xs font-medium text-grey-700 underline decoration-grey-300 underline-offset-2 transition-colors hover:decoration-grey-700"
          >
            Start one now
          </button>
        }
      />
    );
  }

  return (
    <ul className="space-y-0.5 p-2" role="list">
      {sessions.map((session) => (
        <li key={session.id}>
          <SessionItem
            session={session}
            active={session.id === activeId}
            onSelect={onSelect}
            onDelete={onDelete}
          />
        </li>
      ))}
    </ul>
  );
}
