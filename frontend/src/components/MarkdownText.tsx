import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Link } from 'react-router-dom';
import 'katex/dist/katex.min.css';

interface MarkdownTextProps {
  text: string;
  className?: string;
}

const INTERNAL_HOSTS = new Set([
  'paperswithcode.co',
  'www.paperswithcode.co',
  'localhost',
  '127.0.0.1',
  '167.235.148.241',
]);

const INTERNAL_PATH_PREFIXES = ['/methods', '/paper', '/papers', '/tasks', '/benchmark'];

const resolveInternalPath = (href: string | undefined): string | null => {
  if (!href) return null;
  if (href.startsWith('/')) {
    return INTERNAL_PATH_PREFIXES.some((p) => href === p || href.startsWith(`${p}/`))
      ? href
      : null;
  }
  try {
    const url = new URL(href, window.location.origin);
    if (!INTERNAL_HOSTS.has(url.hostname)) return null;
    const path = `${url.pathname}${url.search}${url.hash}`;
    return INTERNAL_PATH_PREFIXES.some((p) => path === p || path.startsWith(`${p}/`))
      ? path
      : null;
  } catch {
    return null;
  }
};

const MarkdownText = ({ text, className = '' }: MarkdownTextProps) => {
  return (
    <div className={className}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          a: ({ href, children, ...props }) => {
            const internalPath = resolveInternalPath(href);
            if (internalPath) {
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
