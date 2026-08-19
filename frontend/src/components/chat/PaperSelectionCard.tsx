import { useEffect, useId, useRef, useState } from "react";

import type { PaperSelectionDraft } from "@/lib/chat";

interface PaperSelectionCardProps {
  selection: PaperSelectionDraft;
  editable?: boolean;
  onRemove?: () => void;
}

export function PaperSelectionCard({
  selection,
  editable = false,
  onRemove,
}: PaperSelectionCardProps) {
  const quoteId = useId();
  const quoteRef = useRef<HTMLQuoteElement>(null);
  const [expanded, setExpanded] = useState(false);
  const [overflows, setOverflows] = useState(false);
  const label = `Selection · Page ${selection.page}`;

  useEffect(() => {
    const element = quoteRef.current;
    if (!element || expanded) return;
    setOverflows(element.scrollHeight > element.clientHeight + 1);
  }, [expanded, selection.text]);

  return (
    <div className={`chat-paper-selection${editable ? " is-editable" : ""}`}>
      <div className="chat-paper-selection-header">
        <span className="chat-paper-selection-label">{label}</span>
        <div className="chat-paper-selection-actions">
          {(overflows || expanded) && (
            <button
              type="button"
              className="chat-paper-selection-toggle"
              aria-expanded={expanded}
              aria-controls={quoteId}
              onClick={() => setExpanded((value) => !value)}
            >
              {expanded ? "Collapse" : "Expand"}
            </button>
          )}
          {editable && onRemove && (
            <button
              type="button"
              className="chat-paper-selection-remove"
              aria-label="Remove selected paper passage"
              onClick={onRemove}
            >
              Remove
            </button>
          )}
        </div>
      </div>
      <blockquote
        id={quoteId}
        ref={quoteRef}
        className={`chat-paper-selection-quote${expanded ? " is-expanded" : ""}`}
      >
        {selection.text}
      </blockquote>
    </div>
  );
}
