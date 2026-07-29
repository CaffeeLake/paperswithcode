import React from "react";

export const PaperFeedHasCodeFilter: React.FC<{
  active: boolean;
  onChange: (active: boolean) => void;
}> = ({ active, onChange }) => (
  <label className="sort-btn paper-feed-code-filter">
    <input
      type="checkbox"
      className="paper-feed-code-checkbox"
      checked={active}
      onChange={(event) => onChange(event.target.checked)}
    />
    Has code
  </label>
);
