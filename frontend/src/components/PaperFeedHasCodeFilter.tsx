import React from "react";
import { Github } from "lucide-react";

export const PaperFeedHasCodeFilter: React.FC<{
  active: boolean;
  onChange: (active: boolean) => void;
}> = ({ active, onChange }) => (
  <button
    type="button"
    className={`sort-btn paper-feed-code-filter ${active ? "active" : ""}`}
    aria-pressed={active}
    onClick={() => onChange(!active)}
  >
    <Github aria-hidden="true" size={13} />
    Has code
  </button>
);
