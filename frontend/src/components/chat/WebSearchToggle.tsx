import React from "react";
import { Globe2 } from "lucide-react";

interface WebSearchToggleProps {
  enabled: boolean;
  onChange: (enabled: boolean) => void;
  disabled?: boolean;
}

const WebSearchToggle: React.FC<WebSearchToggleProps> = ({
  enabled,
  onChange,
  disabled = false,
}) => (
  <button
    type="button"
    className={`chat-web-search-toggle${enabled ? " is-enabled" : ""}`}
    role="switch"
    aria-checked={enabled}
    aria-label="Web search"
    title="Allow public-web search when useful; enabled search queries are processed by Exa"
    disabled={disabled}
    onClick={() => onChange(!enabled)}
  >
    <Globe2 size={15} aria-hidden="true" />
    <span>Web</span>
  </button>
);

export default WebSearchToggle;
