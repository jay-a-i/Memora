import { useEffect, useState } from 'react';
import { IconSearch, IconSpinner } from '../ui/Icon';
import type { ToolActivity as ToolActivityType } from '../../hooks/useChat';

/**
 * Tool activity indicator.
 *
 * Kept quieter than the answer itself: a small icon plus one line of muted
 * text. Running tools are listed live; once the turn ends the whole block
 * collapses to a single summary line that can be reopened.
 */

/**
 * Maps a backend tool name to plain language.
 *
 * The backend reports raw LangChain tool names (hybrid_search, doc_inspector,
 * web_search). An unrecognised name falls back to the backend's own status
 * text, then to a readable form of the name, so new tools still get a label.
 */
const TOOL_LABELS: Record<string, string> = {
  hybrid_search: 'Searching knowledge base',
  doc_inspector: 'Inspecting document',
  web_search: 'Searching the web',
  metadata_filter: 'Filtering documents',
};

function labelFor(name: string, status: string): string {
  const known = TOOL_LABELS[name];
  if (known) return `${known}...`;

  if (status) return status.endsWith('...') ? status : `${status}...`;
  return `${name.replace(/[_-]+/g, ' ')}...`;
}

interface ToolActivityProps {
  active: ToolActivityType[];
  completed: ToolActivityType[];
  /** True until the turn finishes, so the list stays visible while working. */
  streaming: boolean;
}

export function ToolActivity({ active, completed, streaming }: ToolActivityProps) {
  const [expanded, setExpanded] = useState(false);

  // Reveal the list whenever a tool starts, so activity is never missed.
  useEffect(() => {
    if (active.length > 0) setExpanded(true);
  }, [active.length]);

  if (active.length === 0 && completed.length === 0) return null;

  // Collapsed summary, shown only once the turn has finished.
  if (!streaming && !expanded) {
    const count = completed.length;
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        aria-expanded={false}
        className="mb-2.5 self-start text-[11px] text-grey-400 transition-colors hover:text-grey-700"
      >
        {count === 1 ? '1 tool used' : `${count} tools used`}
      </button>
    );
  }

  /*
   * Active entries take precedence over completed ones so a tool that runs
   * more than once appears as a single, currently-running row.
   */
  const entries = [
    ...active,
    ...completed.filter((done) => !active.some((run) => run.name === done.name)),
  ];

  return (
    <div className="mb-2.5 flex flex-col gap-1.5" role="status" aria-live="polite">
      {entries.map((tool) => {
        const running = active.some((t) => t.name === tool.name);
        return (
          <div key={tool.name} className="flex items-center gap-2 text-xs">
            {running ? (
              <IconSpinner className="h-3 w-3 text-grey-500" />
            ) : (
              <IconSearch className="h-3 w-3 text-grey-400" />
            )}
            <span
              className={
                running ? 'font-medium text-grey-600' : 'text-grey-400 line-through decoration-grey-300'
              }
            >
              {labelFor(tool.name, tool.status)}
            </span>
          </div>
        );
      })}

      {!streaming && (
        <button
          type="button"
          onClick={() => setExpanded(false)}
          aria-expanded={true}
          className="self-start text-[11px] text-grey-400 transition-colors hover:text-grey-700"
        >
          Hide tool activity
        </button>
      )}
    </div>
  );
}
