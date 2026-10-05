import type { ReactNode } from 'react';

/**
 * Placeholder blocks for loading states.
 *
 * Preferred over spinners because they preserve the shape of the content that
 * is arriving, which makes the wait feel shorter.
 */

interface SkeletonProps {
  className?: string;
}

export function Skeleton({ className = '' }: SkeletonProps) {
  return <div className={`animate-pulse-soft rounded bg-grey-200 ${className}`} aria-hidden="true" />;
}

/** Mirrors the rhythm of a streamed assistant answer. */
export function MessageSkeleton() {
  return (
    <div className="space-y-3 py-2" aria-hidden="true">
      <Skeleton className="h-3.5 w-[85%]" />
      <Skeleton className="h-3.5 w-[68%]" />
      <Skeleton className="h-3.5 w-[74%]" />
    </div>
  );
}

/** Mirrors a session row in the sidebar. */
export function SessionSkeleton() {
  return (
    <div className="space-y-2 px-3 py-2" aria-hidden="true">
      <Skeleton className="h-3 w-[70%]" />
      <Skeleton className="h-3 w-[45%]" />
    </div>
  );
}

/** Mirrors a document row in the sidebar. */
export function DocumentSkeleton() {
  return (
    <div className="space-y-2 px-3 py-2" aria-hidden="true">
      <Skeleton className="h-3 w-[80%]" />
      <Skeleton className="h-3 w-[35%]" />
    </div>
  );
}

export function EmptyState({
  icon,
  title,
  description,
  action,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      {icon && <div className="mb-3 text-grey-300">{icon}</div>}
      <p className="text-sm font-medium text-grey-700">{title}</p>
      {description && (
        <p className="mt-1.5 max-w-xs text-xs leading-relaxed text-grey-500">{description}</p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
