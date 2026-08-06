import React from "react";

import type { Paper } from "@/lib/api";

interface PaperMentionPickerProps {
  open: boolean;
  query: string;
  results: Paper[];
  activeIndex: number;
  loading: boolean;
  error: boolean;
  onSelect: (paper: Paper) => void;
  id?: string;
  optionIdPrefix?: string;
}

export const PaperMentionPicker: React.FC<PaperMentionPickerProps> = ({
  open,
  query,
  results,
  activeIndex,
  loading,
  error,
  onSelect,
  id = "chat-paper-picker",
  optionIdPrefix = "chat-paper-option",
}) => {
  if (!open) return null;
  const status = !query.trim()
    ? "Type to search papers"
    : loading
      ? "Searching papers…"
      : error
        ? "Paper search is unavailable"
        : results.length
          ? `${results.length} paper${results.length === 1 ? "" : "s"} found`
          : "No papers found";
  return (
    <div className="chat-paper-picker" id={id} role="listbox" aria-label="Paper results">
      <div className="chat-paper-picker-status" role="status" aria-live="polite">{status}</div>
      {results.map((paper, index) => {
        const routeId = paper.arxiv_id || paper.id;
        const secondary = paper.arxiv_id || (() => {
          try { return paper.source_url ? new URL(paper.source_url).hostname : "External resource"; }
          catch { return "External resource"; }
        })();
        return (
          <button
            type="button"
            id={`${optionIdPrefix}-${index}`}
            key={routeId}
            role="option"
            aria-selected={index === activeIndex}
            className={`chat-paper-option${index === activeIndex ? " is-active" : ""}`}
            onMouseDown={(event) => {
              event.preventDefault();
              onSelect(paper);
            }}
          >
            <span className="chat-paper-option-title">{paper.title}</span>
            <span className="chat-paper-option-meta">{secondary}</span>
          </button>
        );
      })}
    </div>
  );
};
