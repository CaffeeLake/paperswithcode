import React from "react";

import type { ArtifactBlock } from "@/lib/chat";
import type { LatexPaperArtifactDescriptor } from "@/lib/chatSessions";
import { artifactPanelKey, useArtifactPanel } from "./useArtifactPanel";

export const LatexPaperArtifact: React.FC<{
  descriptor: LatexPaperArtifactDescriptor;
}> = ({ descriptor }) => {
  const panel = useArtifactPanel();
  const { open, register, unregister } = panel;
  const opened = React.useRef<string | null>(null);
  const version = descriptor.source_head ?? descriptor.preview_head;
  const block = React.useMemo<ArtifactBlock | null>(() => version ? {
    kind: "artifact",
    schema_version: 1,
    scope: "owner",
    artifact_id: descriptor.artifact_id,
    version_id: version.version_id,
    identifier: "latex-paper",
    version: version.version,
    artifact_kind: "latex_paper",
    title: descriptor.title,
    status: "ready",
    preview_mime: "application/pdf",
    source_language: "latex",
    total_bytes: 0,
  } : null, [descriptor.artifact_id, descriptor.title, version]);
  const key = block ? artifactPanelKey(block) : null;

  React.useEffect(() => {
    if (!block || !key) return;
    register(block);
    if (opened.current !== key) {
      opened.current = key;
      open(block);
    }
    return () => unregister(key);
  }, [block, key, open, register, unregister]);

  return null;
};
