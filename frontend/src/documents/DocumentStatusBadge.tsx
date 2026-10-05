import { IconCheck, IconSpinner, IconWarning } from '../components/ui/Icon';
import type { DocumentStatus } from '../types/api';

/**
 * Processing state, expressed without colour.
 *
 * Each state is distinguished by icon, border weight, letter-spacing and
 * opacity together, so the three remain separable at a glance and under any
 * monochrome rendering.
 */

interface DocumentStatusBadgeProps {
  status: DocumentStatus;
  compact?: boolean;
}

export function DocumentStatusBadge({ status, compact = false }: DocumentStatusBadgeProps) {
  if (status === 'COMPLETED') {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-[0.07em] text-grey-500">
        <IconCheck className="h-3 w-3 text-grey-600" />
        {!compact && 'Indexed'}
      </span>
    );
  }

  if (status === 'FAILED') {
    return (
      <span className="inline-flex items-center gap-1 rounded-sm border border-grey-400 px-1 py-px text-[10px] font-semibold uppercase tracking-[0.07em] text-grey-800">
        <IconWarning className="h-3 w-3" />
        {!compact && 'Failed'}
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-1 text-[10px] font-medium uppercase tracking-[0.07em] text-grey-500">
      <IconSpinner className="h-3 w-3 animate-spin text-grey-500" />
      {!compact && 'Processing'}
    </span>
  );
}
