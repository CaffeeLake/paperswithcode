import { useEffect, useRef } from 'react';
import katex from 'katex';
import 'katex/dist/katex.min.css';

interface LatexTextProps {
  text: string;
  className?: string;
}

/**
 * Component that renders text with LaTeX math expressions
 * Supports both inline math ($...$) and display math ($$...$$)
 * Can be used for paper titles, abstracts, or any other text content
 */
const LatexText = ({ text, className = '' }: LatexTextProps) => {
  const containerRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    try {
      // Parse the text and render LaTeX expressions
      const renderedText = renderLatexInText(text);
      containerRef.current.innerHTML = renderedText;
    } catch (error) {
      // Fallback to plain text if rendering fails
      console.error('Error rendering LaTeX in text:', error);
      containerRef.current.textContent = text;
    }
  }, [text]);

  return <span ref={containerRef} className={className} />;
};

/**
 * Parse and render LaTeX expressions in a text string
 * Supports:
 * - Inline math: $expression$
 * - Display math: $$expression$$
 */
function renderLatexInText(text: string): string {
  // First, handle display math ($$...$$)
  let result = text.replace(/\$\$(.*?)\$\$/g, (match, latex) => {
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

// Component aliases for backward compatibility and different use cases
const LatexTitle = ({ title, className = '' }: { title: string; className?: string }) => (
  <LatexText text={title} className={className} />
);

// Export LatexTitle as default for backward compatibility with existing code
export default LatexTitle;
export { LatexText, LatexTitle };
