import { useState } from 'react';
import { IconChevron, IconDocument } from '../ui/Icon';
import type { RetrievalSource } from '../../types/api';

/**
 * Source list rendered beneath an assistant answer.
 *
 * The chat stream does not currently emit sources, so this renders nothing
 * unless the backend supplies them. Nothing is invented when the list is
 * empty: an answer without sources simply has no source section.
 */

interface SourcesProps {
  sources?: RetrievalSource[];
}

/** Builds the secondary line: chunk index, filename, and snippet if present. */
function describeSource(source: RetrievalSource): string {
  const parts: string[] = [];
  if (source.filename) parts.push(source.filename);
  if (source.chunk !== undefined) parts.push(`Chunk ${source.chunk}`);
  if (source.score !== undefined) parts.push(`Score ${source.score.toFixed(2)}`);
  return parts.join(' · ');
}

export function Sources({ sources }: SourcesProps) {
  const [expanded, setExpanded] = useState(false);

  if (!sources || sources.length === 0) return null;

  return (
    <section className="mt-5 border-t border-grey-200 pt-3.5">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="group flex w-full items-center gap-1.5 text-left text-xs font-medium text-grey-600 transition-colors hover:text-grey-900"
      >
        <IconChevron
          className={`h-3 w-3 transition-transform duration-150 ${expanded ? 'rotate-90' : ''}`}
        />
        <span>Sources</span>
        <span className="tabular-nums text-grey-400">{sources.length}</span>
      </button>

      {expanded && (
        <ol className="mt-2.5 space-y-2">
          {sources.map((source, index) => {
            const detail = describeSource(source);
            return (
              <li
                key={`${source.label}-${index}`}
                className="rounded-md border border-grey-200 bg-grey-50 px-3 py-2"
              >
                <div className="flex items-start gap-2">
                  <IconDocument className="mt-0.5 h-3.5 w-3.5 text-grey-400" />
                  <div className="min-w-0 flex-1">
                    {source.url ? (
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="block truncate text-xs font-medium text-grey-800 underline decoration-grey-300 underline-offset-2 transition-colors hover:decoration-grey-700"
                      >
                        {source.label}
                      </a>
                    ) : (
                      <p className="truncate text-xs font-medium text-grey-800">{source.label}</p>
                    )}

                    {detail && <p className="mt-0.5 truncate text-[11px] text-grey-500">{detail}</p>}

                    {source.snippet && (
                      <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-grey-600">
                        {source.snippet}
                      </p>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
