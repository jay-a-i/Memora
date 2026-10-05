import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';

/**
 * Renders assistant markdown.
 *
 * Typography is styled through the .prose-memora rules in index.css rather
 * than per-element classes, which keeps this component declarative. Syntax
 * highlighting is deliberately not applied: any highlighter would introduce
 * colour, and the design system allows grey only. External links are marked
 * `noopener noreferrer` and open in a new tab.
 */

const components: Components = {
  a({ href, children, ...props }) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
        {children}
      </a>
    );
  },
};

interface MarkdownProps {
  children: string;
}

export function Markdown({ children }: MarkdownProps) {
  return (
    <div className="prose-memora">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
