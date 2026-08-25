import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, FileCode2, FilePlus2, Pencil, Save, Trash2, X } from "lucide-react";

import { apiUrl } from "@/lib/apiUrl";
import type { ArtifactBlock } from "@/lib/chat";
import type { LatexPaperArtifactDescriptor } from "@/lib/chatSessions";
import { LatexSourceEditor } from "./LatexSourceEditor";
import { useArtifactPanel } from "./useArtifactPanel";

interface PaperManifest {
  root_document: string;
  files: Array<{ path: string; media_type: string }>;
}

interface Draft {
  parentVersionId: string;
  files: Record<string, string>;
}

function sourceUrl(artifactId: string, versionId: string, path: string): string {
  return apiUrl(`/api/v1/chat/artifacts/${encodeURIComponent(artifactId)}/versions/${encodeURIComponent(versionId)}/source/${path.split("/").map(encodeURIComponent).join("/")}`);
}

function draftKey(artifactId: string): string {
  return `pwc:latex-paper-draft:${artifactId}`;
}

function sameFiles(left: Record<string, string>, right: Record<string, string>): boolean {
  const leftPaths = Object.keys(left).sort();
  const rightPaths = Object.keys(right).sort();
  return leftPaths.length === rightPaths.length
    && leftPaths.every((path, index) => path === rightPaths[index] && left[path] === right[path]);
}

function isSupportedPath(path: string): boolean {
  return !path.includes("\\") && /^(?!\/)(?!.*(?:^|\/)\.\.?\/)[^\0]{1,300}\.(?:tex|bib)$/iu.test(path);
}

export const LatexPaperPanel: React.FC<{
  block: ArtifactBlock;
  forceDialog?: boolean;
  readerFallback?: boolean;
}> = ({ block, forceDialog = false }) => {
  const panel = useArtifactPanel();
  const queryClient = useQueryClient();
  const closePanel = panel.close;
  const [narrow, setNarrow] = React.useState(
    () => typeof window !== "undefined" && window.matchMedia?.("(max-width: 760px)").matches,
  );
  const [files, setFiles] = React.useState<Record<string, string>>({});
  const [baseline, setBaseline] = React.useState<Record<string, string>>({});
  const [draftParent, setDraftParent] = React.useState<string | null>(null);
  const [checkedOut, setCheckedOut] = React.useState(false);
  const [staleDraft, setStaleDraft] = React.useState(false);
  const [editorError, setEditorError] = React.useState<string | null>(null);
  const initializedVersion = React.useRef<string | null>(null);
  const panelRef = React.useRef<HTMLElement>(null);
  const pushedHistoryRef = React.useRef(false);
  const dialog = forceDialog || narrow;
  const draftIsDirty = draftParent !== null && !sameFiles(files, baseline);

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
      if (draftIsDirty && !window.confirm("Discard unsaved paper edits?")) {
        window.history.pushState({ ...window.history.state, pwcArtifactPanel: true }, "");
        pushedHistoryRef.current = true;
        return;
      }
      pushedHistoryRef.current = false;
      closePanel();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      if (draftIsDirty && !window.confirm("Discard unsaved paper edits?")) return;
      closePanel();
      if (pushedHistoryRef.current) { pushedHistoryRef.current = false; window.history.back(); }
    };
    window.addEventListener("popstate", onPopState);
    document.addEventListener("keydown", onKeyDown);
    return () => { window.removeEventListener("popstate", onPopState); document.removeEventListener("keydown", onKeyDown); };
  }, [closePanel, dialog, draftIsDirty]);
  React.useEffect(() => {
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!draftIsDirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [draftIsDirty]);

  const descriptorQuery = useQuery({
    queryKey: ["chat-latex-paper", block.artifact_id],
    queryFn: async () => {
      const response = await fetch(apiUrl(`/api/v1/chat/artifacts/${encodeURIComponent(block.artifact_id!)}`), {
        credentials: "include", cache: "no-store",
      });
      if (!response.ok) throw new Error("Could not load paper details");
      return response.json() as Promise<LatexPaperArtifactDescriptor>;
    },
    enabled: Boolean(block.artifact_id), staleTime: 5_000,
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
    enabled: panel.state.tab === "files" && Boolean(source?.version_id), staleTime: Number.POSITIVE_INFINITY,
  });
  const textFiles = manifestQuery.data?.files.filter((file) => (
    file.media_type === "text/x-tex" || file.media_type === "application/x-bibtex"
  )) ?? [];
  const sourceFilesQuery = useQuery({
    queryKey: ["chat-latex-paper-source-files", block.artifact_id, source?.version_id],
    queryFn: async () => Object.fromEntries(await Promise.all(textFiles.map(async (file) => {
      const response = await fetch(sourceUrl(block.artifact_id!, source!.version_id, file.path), {
        credentials: "include", cache: "no-store",
      });
      if (!response.ok) throw new Error("Could not load paper source");
      return [file.path, await response.text()] as const;
    }))),
    enabled: panel.state.tab === "files" && Boolean(source?.version_id && textFiles.length),
    staleTime: Number.POSITIVE_INFINITY,
  });
  React.useEffect(() => { setCheckedOut(false); }, [source?.version_id]);
  React.useEffect(() => {
    if (!source?.version_id || !sourceFilesQuery.data || initializedVersion.current === source.version_id) return;
    const serverFiles = sourceFilesQuery.data;
    let recovered = serverFiles;
    let stale = false;
    let recoveredParent = source.version_id;
    try {
      const stored = window.localStorage.getItem(draftKey(block.artifact_id!));
      const draft = stored ? JSON.parse(stored) as Draft : null;
      if (draft?.files && typeof draft.files === "object") {
        recovered = draft.files;
        stale = draft.parentVersionId !== source.version_id;
        recoveredParent = draft.parentVersionId;
      }
    } catch { /* An invalid local draft must not prevent a safe server checkout. */ }
    initializedVersion.current = source.version_id;
    setFiles(recovered);
    setBaseline(serverFiles);
    setDraftParent(recoveredParent);
    setStaleDraft(stale);
    setCheckedOut(true);
    if (stale) setEditorError("This local draft is based on an older paper version. Copy or discard it before saving the latest version.");
    if (!panel.state.sourceFile || !recovered[panel.state.sourceFile]) panel.setSourceFile(manifestQuery.data?.root_document ?? null);
  }, [block.artifact_id, manifestQuery.data?.root_document, panel, source?.version_id, sourceFilesQuery.data]);
  React.useEffect(() => {
    if (!draftParent || !block.artifact_id) return;
    const key = draftKey(block.artifact_id);
    if (!draftIsDirty) { window.localStorage.removeItem(key); return; }
    window.localStorage.setItem(key, JSON.stringify({ parentVersionId: draftParent, files } satisfies Draft));
  }, [block.artifact_id, draftIsDirty, draftParent, files]);

  const saveMutation = useMutation({
    mutationFn: async () => {
      if (!source?.version_id) throw new Error("Paper source is not ready to save");
      const response = await fetch(apiUrl(`/api/v1/chat/artifacts/${encodeURIComponent(block.artifact_id!)}/save-compile`), {
        method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ expected_parent_version_id: source.version_id, files: Object.entries(files).map(([path, content]) => ({ path, content })) }),
      });
      const body = await response.json().catch(() => null) as LatexPaperArtifactDescriptor | { detail?: { message?: string } } | null;
      if (!response.ok) throw new Error((body as { detail?: { message?: string } } | null)?.detail?.message ?? "Could not save paper");
      return body as LatexPaperArtifactDescriptor;
    },
    onSuccess: (saved) => {
      queryClient.setQueryData(["chat-latex-paper", block.artifact_id], saved);
      queryClient.invalidateQueries({ queryKey: ["chat-latex-paper-manifest", block.artifact_id] });
      queryClient.invalidateQueries({ queryKey: ["chat-latex-paper-source-files", block.artifact_id] });
      initializedVersion.current = saved.source_head?.version_id ?? null;
      setBaseline(files);
      setDraftParent(saved.source_head?.version_id ?? null);
      window.localStorage.removeItem(draftKey(block.artifact_id!));
      setEditorError(null);
      setStaleDraft(false);
      panel.setTab("preview");
    },
    onError: (error) => setEditorError(error instanceof Error ? error.message : "Could not save paper"),
  });

  const refreshMutation = useMutation({
    mutationFn: async () => {
      const response = await fetch(apiUrl(`/api/v1/chat/artifacts/${encodeURIComponent(block.artifact_id!)}/refresh-compile`), {
        method: "POST", credentials: "include",
      });
      if (!response.ok) throw new Error("Could not refresh paper compilation");
      return response.json() as Promise<LatexPaperArtifactDescriptor>;
    },
    onSuccess: (updated) => queryClient.setQueryData(["chat-latex-paper", block.artifact_id], updated),
  });
  const refreshCompile = refreshMutation.mutate;
  const sourceVersionId = source?.version_id;
  const sourceCompileStatus = source?.compile_status;
  React.useEffect(() => {
    if (!sourceVersionId || !block.artifact_id || !["queued", "compiling"].includes(sourceCompileStatus ?? "")) return;
    const timer = window.setTimeout(() => refreshCompile(), 2_000);
    return () => window.clearTimeout(timer);
  }, [block.artifact_id, refreshCompile, sourceCompileStatus, sourceVersionId]);

  const sourcePath = panel.state.sourceFile ?? manifestQuery.data?.root_document ?? null;
  const canEdit = descriptor?.editing_enabled === true && Boolean(source?.version_id) && checkedOut && !staleDraft && !saveMutation.isPending;
  const previewUrl = preview
    ? apiUrl(`/api/v1/chat/artifacts/${encodeURIComponent(block.artifact_id!)}/versions/${encodeURIComponent(preview.version_id)}/preview`)
    : null;
  const outOfDate = Boolean(source && preview && source.version_id !== preview.version_id);
  const guardDirty = () => !draftIsDirty || window.confirm("Discard unsaved paper edits?");
  const selectFile = (path: string) => {
    if (path !== sourcePath && draftIsDirty && !window.confirm("Switch files? Unsaved edits stay in this browser.")) return;
    panel.setSourceFile(path);
  };
  const addFile = () => {
    const path = window.prompt("New TeX or BibTeX file name", "section.tex");
    if (!path) return;
    if (!isSupportedPath(path) || files[path]) { setEditorError("Choose a new safe .tex or .bib filename."); return; }
    if (Object.keys(files).length >= 100) { setEditorError("A paper can contain at most 100 files."); return; }
    setFiles({ ...files, [path]: "" }); setEditorError(null); panel.setSourceFile(path);
  };
  const renameFile = () => {
    if (!sourcePath || sourcePath === manifestQuery.data?.root_document) return;
    const path = window.prompt("Rename file", sourcePath);
    if (!path || path === sourcePath) return;
    if (!isSupportedPath(path) || files[path]) { setEditorError("Choose a new safe .tex or .bib filename."); return; }
    const next = { ...files, [path]: files[sourcePath] }; delete next[sourcePath]; setFiles(next); panel.setSourceFile(path);
  };
  const deleteFile = () => {
    if (!sourcePath || sourcePath === manifestQuery.data?.root_document) return;
    if (!window.confirm(`Delete ${sourcePath}?`)) return;
    const next = { ...files }; delete next[sourcePath]; setFiles(next); panel.setSourceFile(manifestQuery.data?.root_document ?? null);
  };
  const discardStaleDraft = () => {
    if (!staleDraft || !window.confirm("Discard this stale local draft?")) return;
    window.localStorage.removeItem(draftKey(block.artifact_id!));
    setFiles(baseline);
    setDraftParent(source?.version_id ?? null);
    setStaleDraft(false);
    setEditorError(null);
  };
  const close = () => {
    if (!guardDirty()) return;
    closePanel();
    if (dialog && pushedHistoryRef.current) { pushedHistoryRef.current = false; window.history.back(); }
  };
  const askAiToFix = () => {
    if (!source || source.compile_status !== "failed" || source.repair_exhausted) return;
    const diagnostics = (source.compile_diagnostics ?? []).slice(0, 20).map((item) => (
      `${item.file ?? "project"}${item.line ? `:${item.line}` : ""}: ${item.message}`
    )).join("\n");
    panel.askAiToFix(
      `Repair the failed paper source version ${source.version_id}. Use pwc-paper to inspect and repair it; make no more than three attempts. Compiler diagnostics:\n${diagnostics || "No compiler diagnostic was available."}`,
    );
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
          ? <iframe key={preview?.version_id} title={`Preview of ${block.title}`} src={previewUrl} className="h-full w-full border-0" />
          : <p>Preview is compiling. The stored source is available in Files.</p>
        : <div className="chat-artifact-source-workspace">
            <nav aria-label="Paper source files">
              {textFiles.map((file) => <button type="button" key={file.path} aria-pressed={sourcePath === file.path} onClick={() => selectFile(file.path)}>{file.path}</button>)}
              {canEdit && <button type="button" className="latex-file-action" aria-label="Add TeX file" onClick={addFile}><FilePlus2 /> Add file</button>}
            </nav>
            <div className="latex-editor-column">
              {sourcePath && files[sourcePath] !== undefined
                ? <LatexSourceEditor path={sourcePath} value={files[sourcePath]} readOnly={!canEdit} onChange={(content) => setFiles({ ...files, [sourcePath]: content })} />
                : <p>{sourceFilesQuery.isError ? "Source could not be loaded." : "Loading source…"}</p>}
              {canEdit && sourcePath && sourcePath !== manifestQuery.data?.root_document && <div className="latex-file-buttons">
                <button type="button" onClick={renameFile}><Pencil /> Rename</button>
                <button type="button" onClick={deleteFile}><Trash2 /> Delete</button>
              </div>}
            </div>
          </div>}
    </div>
    <footer>
      <div className="chat-artifact-metadata" aria-live="polite">
        {outOfDate && <strong>Out of date</strong>}
        {source && <span>Source v{source.version} · {source.compile_status}</span>}
        {source?.compile_diagnostics?.map((diagnostic, index) => <button
          type="button"
          key={`${diagnostic.file ?? "global"}:${diagnostic.line ?? ""}:${index}`}
          onClick={() => diagnostic.file && panel.setSourceFile(diagnostic.file)}
          className="latex-compile-diagnostic"
        >{diagnostic.file ? `${diagnostic.file}${diagnostic.line ? `:${diagnostic.line}` : ""}: ` : ""}{diagnostic.message}</button>)}
        {editorError && <span role="alert">{editorError}</span>}
        {staleDraft && <button type="button" onClick={discardStaleDraft}>Discard stale local draft</button>}
      </div>
      <div className="chat-artifact-actions">
        {source?.compile_status === "failed" && !source.repair_exhausted && <button type="button" onClick={askAiToFix}>Ask AI to fix</button>}
        {source?.compile_status === "failed" && source.repair_exhausted && <span role="status">AI repair attempts exhausted</span>}
        {panel.state.tab === "files" && canEdit && <button type="button" disabled={!draftIsDirty} onClick={() => saveMutation.mutate()}><Save />{saveMutation.isPending ? "Saving…" : "Save & Compile"}</button>}
        {previewUrl && <a href={previewUrl} download><Download /> PDF</a>}
        {source && sourcePath && <a href={sourceUrl(block.artifact_id!, source.version_id, sourcePath)} download><FileCode2 /> Source</a>}
      </div>
    </footer>
  </section>;
};
