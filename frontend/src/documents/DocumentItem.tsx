import { Button } from '../components/ui/Button';
import { IconFile, IconTrash } from '../components/ui/Icon';
import { DocumentStatusBadge } from './DocumentStatusBadge';
import type { DocumentDto } from '../types/api';

/**
 * One uploaded document.
 *
 * A FAILED document keeps its filename readable and states the reason beneath
 * it, since the failure text from the backend is the only diagnostic
 * available to the user.
 */

interface DocumentItemProps {
  document: DocumentDto;
  onDelete: (document: DocumentDto) => void;
}

function formatSizeAndType(document: DocumentDto): string {
  const type = document.file_type.replace(/^\./, '').toUpperCase();
  return type ? type : 'FILE';
}

export function DocumentItem({ document, onDelete }: DocumentItemProps) {
  const failed = document.status === 'FAILED';

  return (
    <div
      className={`group relative flex items-start gap-2.5 rounded-md px-2.5 py-2 transition-colors hover:bg-grey-150 ${
        // A failed row carries a heavier left rule, its counterpart to the
        // badge's heavier border.
        failed ? 'border-l-2 border-l-grey-500 bg-grey-100' : 'border-l-2 border-l-transparent'
      }`}
    >
      <IconFile className="mt-0.5 h-4 w-4 shrink-0 text-grey-400" />

      <div className="min-w-0 flex-1">
        <p
          className={`truncate text-[13px] leading-tight ${
            failed ? 'font-medium text-grey-900' : 'text-grey-700'
          }`}
          title={document.filename}
        >
          {document.filename}
        </p>

        <div className="mt-1 flex items-center gap-2">
          <span className="tabular-nums text-[10px] uppercase tracking-wide text-grey-400">
            {formatSizeAndType(document)}
          </span>
          <DocumentStatusBadge status={document.status} />
        </div>

        {failed && document.error_message && (
          <p className="mt-1.5 text-[11px] leading-relaxed text-grey-600">
            {document.error_message}
          </p>
        )}
      </div>

      {/* pointer-events-none until hover or focus, so the invisible control is not
          clickable before it is revealed. */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => onDelete(document)}
        aria-label={`Delete ${document.filename}`}
        className="pointer-events-none h-6 w-6 shrink-0 p-0 opacity-0 transition-opacity focus-visible:pointer-events-auto focus-visible:opacity-100 group-hover:pointer-events-auto group-hover:opacity-100"
        icon={<IconTrash className="h-3.5 w-3.5" />}
      />
    </div>
  );
}
