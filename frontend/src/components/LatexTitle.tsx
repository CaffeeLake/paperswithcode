import { useEffect, useRef } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';

interface LatexTitleProps {
  title: string;
  className?: string;
}

/**
 * Component that renders paper titles with LaTeX math expressions
 * Supports both inline math ($...$) and display math ($$...$$)
 */
const LatexTitle = ({ title, className = '' }: LatexTitleProps) => {
  const containerRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    try {
      // Parse the title and render LaTeX expressions
      const renderedTitle = renderLatexInTitle(title);
      containerRef.current.innerHTML = renderedTitle;
    } catch (error) {
      // Fallback to plain text if rendering fails
      console.error('Error rendering LaTeX in title:', error);
      containerRef.current.textContent = title;
    }
  }, [title]);

  return <span ref={containerRef} className={className} />;
};

/**
 * Parse and render LaTeX expressions in a title string
 * Supports:
 * - Inline math: $expression$
 * - Display math: $$expression$$
 */
function renderLatexInTitle(title: string): string {
  // First, handle display math ($$...$$)
  let result = title.replace(/\$\$(.*?)\$\$/g, (match, latex) => {
    try {
      return katex.renderToString(latex.trim(), {
        displayMode: true,
        throwOnError: false,
      });
    } catch (error) {
      console.error('Error rendering display math:', error);
      return match;
    }
  });

  // Then, handle inline math ($...$)
  result = result.replace(/\$([^$]+?)\$/g, (match, latex) => {
    try {
      return katex.renderToString(latex.trim(), {
        displayMode: false,
        throwOnError: false,
      });
    } catch (error) {
      console.error('Error rendering inline math:', error);
      return match;
    }
  });

  return result;
}

export default LatexTitle;
