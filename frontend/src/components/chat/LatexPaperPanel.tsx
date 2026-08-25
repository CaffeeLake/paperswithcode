import React from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, FileCode2, X } from "lucide-react";

import { apiUrl } from "@/lib/apiUrl";
import type { ArtifactBlock } from "@/lib/chat";
import type { LatexPaperArtifactDescriptor } from "@/lib/chatSessions";
import { useArtifactPanel } from "./useArtifactPanel";

interface PaperManifest {
  root_document: string;
  files: Array<{ path: string; media_type: string }>;
}

function sourceUrl(artifactId: string, versionId: string, path: string): string {
  return apiUrl(`/api/v1/chat/artifacts/${encodeURIComponent(artifactId)}/versions/${encodeURIComponent(versionId)}/source/${path.split("/").map(encodeURIComponent).join("/")}`);
}

export const LatexPaperPanel: React.FC<{
  block: ArtifactBlock;
  forceDialog?: boolean;
  readerFallback?: boolean;
}> = ({ block, forceDialog = false }) => {
  const panel = useArtifactPanel();
  const closePanel = panel.close;
  const [narrow, setNarrow] = React.useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(max-width: 760px)").matches,
  );
  const panelRef = React.useRef<HTMLElement>(null);
  const pushedHistoryRef = React.useRef(false);
  const dialog = forceDialog || narrow;
  React.useEffect(() => {
    const query = window.matchMedia?.("(max-width: 760px)");
    if (!query) return;
    const update = () => setNarrow(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);
  React.useEffect(() => {
    if (!dialog) return;
    panelRef.current?.querySelector<HTMLElement>("[data-artifact-close]")?.focus();
    window.history.pushState({ ...window.history.state, pwcArtifactPanel: true }, "");
    pushedHistoryRef.current = true;
    const onPopState = () => {
      pushedHistoryRef.current = false;
      closePanel();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closePanel();
      if (pushedHistoryRef.current) {
        pushedHistoryRef.current = false;
        window.history.back();
      }
    };
    window.addEventListener("popstate", onPopState);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("popstate", onPopState);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [closePanel, dialog]);
  const descriptorQuery = useQuery({
    queryKey: ["chat-latex-paper", block.artifact_id],
    queryFn: async () => {
      const response = await fetch(apiUrl(`/api/v1/chat/artifacts/${encodeURIComponent(block.artifact_id!)}`), {
        credentials: "include", cache: "no-store",
      });
      if (!response.ok) throw new Error("Could not load paper details");
      return response.json() as Promise<LatexPaperArtifactDescriptor>;
    },
    enabled: Boolean(block.artifact_id),
    staleTime: 5_000,
  });
  const descriptor = descriptorQuery.data;
  const source = descriptor?.source_head;
  const preview = descriptor?.preview_head;
  const manifestQuery = useQuery({
    queryKey: ["chat-latex-paper-manifest", block.artifact_id, source?.version_id],
    queryFn: async () => {
      const response = await fetch(apiUrl(`/api/v1/chat/artifacts/${encodeURIComponent(block.artifact_id!)}/versions/${encodeURIComponent(source!.version_id)}/manifest`), {
        credentials: "include", cache: "no-store",
      });
      if (!response.ok) throw new Error("Could not load paper files");
      return response.json() as Promise<PaperManifest>;
    },
    enabled: panel.state.tab === "files" && Boolean(source?.version_id),
    staleTime: Number.POSITIVE_INFINITY,
  });
  const sourcePath = panel.state.sourceFile ?? manifestQuery.data?.root_document;
  const sourceQuery = useQuery({
    queryKey: ["chat-latex-paper-source", block.artifact_id, source?.version_id, sourcePath],
    queryFn: async () => {
      const response = await fetch(sourceUrl(block.artifact_id!, source!.version_id, sourcePath!), {
        credentials: "include", cache: "no-store",
      });
      if (!response.ok) throw new Error("Could not load paper source");
      return response.text();
    },
    enabled: panel.state.tab === "files" && Boolean(source?.version_id && sourcePath),
    staleTime: Number.POSITIVE_INFINITY,
  });
  const previewUrl = preview
    ? apiUrl(`/api/v1/chat/artifacts/${encodeURIComponent(block.artifact_id!)}/versions/${encodeURIComponent(preview.version_id)}/preview`)
    : null;
  const textFiles = manifestQuery.data?.files.filter((file) => (
    file.media_type === "text/x-tex" || file.media_type === "application/x-bibtex"
  )) ?? [];
  const outOfDate = Boolean(source && preview && source.version_id !== preview.version_id);
  const close = () => {
    closePanel();
    if (dialog && pushedHistoryRef.current) {
      pushedHistoryRef.current = false;
      window.history.back();
    }
  };

  return <section
    ref={panelRef}
    className={`chat-artifact-panel${dialog ? " is-dialog" : " is-docked"}`}
    role={dialog ? "dialog" : "complementary"}
    aria-modal={dialog ? true : undefined}
    aria-label={block.title}
    data-testid="latex-paper-panel"
  >
    <header>
      <div><span>Private paper</span><h2>{block.title}</h2></div>
      <button type="button" data-artifact-close aria-label={dialog ? "Back to conversation" : "Close paper"} onClick={close}><X /></button>
    </header>
    <nav aria-label="Paper views">
      <button type="button" aria-pressed={panel.state.tab === "preview"} className={panel.state.tab === "preview" ? "active" : ""} onClick={() => panel.setTab("preview")}>Preview</button>
      <button type="button" aria-pressed={panel.state.tab === "files"} className={panel.state.tab === "files" ? "active" : ""} onClick={() => panel.setTab("files")}>Files</button>
    </nav>
    <div className="chat-artifact-panel-body">
      {panel.state.tab === "preview"
        ? previewUrl
          ? <iframe title={`Preview of ${block.title}`} src={previewUrl} className="h-full w-full border-0" />
          : <p>Preview is compiling. The stored source is available in Files.</p>
        : <div className="chat-artifact-source-workspace">
            <nav aria-label="Paper source files">
              {textFiles.map((file) => <button type="button" key={file.path} aria-pressed={sourcePath === file.path} onClick={() => panel.setSourceFile(file.path)}>{file.path}</button>)}
            </nav>
            <pre><code>{sourceQuery.isError ? "Source could not be loaded." : sourceQuery.data ?? "Loading source…"}</code></pre>
          </div>}
    </div>
    <footer>
      <div className="chat-artifact-metadata">
        {outOfDate && <strong>Out of date</strong>}
        {source && <span>Source v{source.version} · {source.compile_status}</span>}
      </div>
      <div className="chat-artifact-actions">
        {previewUrl && <a href={previewUrl} download><Download /> PDF</a>}
        {source && sourcePath && <a href={sourceUrl(block.artifact_id!, source.version_id, sourcePath)} download><FileCode2 /> Source</a>}
      </div>
    </footer>
  </section>;
};
