import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Link } from 'react-router-dom';
import 'katex/dist/katex.min.css';

import { PaperPreviewLink } from '@/components/paper-preview/PaperPreviewLink';
import { extractPaperRouteId, resolveInternalPath } from '@/lib/internalLinks';

interface MarkdownTextProps {
  text: string;
  className?: string;
}

const MarkdownText = ({ text, className = '' }: MarkdownTextProps) => {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ href, children, node: _node, ...props }) => {
            const internalPath = resolveInternalPath(href);
            if (internalPath) {
              const routeId = extractPaperRouteId(internalPath);
              if (routeId) {
                return (
                  <PaperPreviewLink routeId={routeId} to={internalPath} {...props}>
                    {children}
                  </PaperPreviewLink>
                );
              }
              return (
                <Link to={internalPath} {...props}>
                  {children}
                </Link>
              );
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                {children}
              </a>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
};

export default MarkdownText;
