import React from "react";

import { HuggingFaceLogo, Icon } from "@/components";

const FeedFilterCheckbox: React.FC<{
  checked: boolean;
  icon: React.ReactNode;
  label: string;
  onChange: (checked: boolean) => void;
}> = ({ checked, icon, label, onChange }) => (
  <label className="sort-btn paper-feed-filter">
    <input
      type="checkbox"
      className="paper-feed-filter-checkbox"
      checked={checked}
      onChange={(event) => onChange(event.target.checked)}
    />
    <span className="paper-feed-filter-icon" aria-hidden="true">
      {icon}
    </span>
    {label}
  </label>
);

export const PaperFeedFilters: React.FC<{
  hasCode: boolean;
  hasHfArtifacts: boolean;
  onHasCodeChange: (checked: boolean) => void;
  onHasHfArtifactsChange: (checked: boolean) => void;
}> = ({
  hasCode,
  hasHfArtifacts,
  onHasCodeChange,
  onHasHfArtifactsChange,
}) => (
  <div
    className="paper-feed-filter-options"
    role="group"
    aria-label="Paper filters"
  >
    <FeedFilterCheckbox
      checked={hasCode}
      icon={<Icon name="github" size={13} />}
      label="Has code"
      onChange={onHasCodeChange}
    />
    <FeedFilterCheckbox
      checked={hasHfArtifacts}
      icon={<HuggingFaceLogo size={14} />}
      label="Has HF artifacts"
      onChange={onHasHfArtifactsChange}
    />
  </div>
);
