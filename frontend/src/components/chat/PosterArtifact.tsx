import React from "react";
import { FileCode2, Image } from "lucide-react";

import type { ArtifactBlock } from "@/lib/chat";
import { artifactUrls, gateLabel } from "./ArtifactPanel";
import { artifactPanelKey, useArtifactPanel } from "./useArtifactPanel";

export const PosterArtifact: React.FC<{ block: ArtifactBlock }> = ({ block }) => {
  const panel = useArtifactPanel();
  const register = panel.register;
  const unregister = panel.unregister;
  const key = artifactPanelKey(block);

  React.useEffect(() => {
    register(block);
  }, [block, register]);
  React.useEffect(() => () => unregister(key), [key, unregister]);

  if (block.status === "generating") {
    return <div className="chat-artifact-card chat-artifact-generating" role="status">
      <span className="chat-artifact-pulse" aria-hidden="true" />
      <span><strong>{block.title}</strong><small>Publishing Posterly preview…</small></span>
    </div>;
  }
  if (block.status === "error") {
    return <div className="chat-artifact-card chat-artifact-error" role="alert">
      <FileCode2 aria-hidden="true" /><span><strong>{block.title}</strong><small>{block.error_message ?? "Poster publication failed."}</small></span>
    </div>;
  }
  const links = artifactUrls(block);
  if (!links) return null;
  const selected = panel.state.open && panel.state.selectedKey === key;
  return <button
    type="button"
    className={`chat-artifact-card${selected ? " is-selected" : ""}`}
    aria-pressed={selected}
    onClick={(event) => panel.open(block, event.currentTarget)}
  >
    <img src={links.preview} alt={`Preview of ${block.title}`} />
    <span className="chat-artifact-card-copy">
      <span className="chat-artifact-kicker"><Image aria-hidden="true" /> Posterly · v{block.version}</span>
      <strong>{block.title}</strong>
      <small className={`chat-artifact-gate chat-artifact-gate-${block.gate_status}`}>{gateLabel(block.gate_status)}</small>
    </span>
  </button>;
};
