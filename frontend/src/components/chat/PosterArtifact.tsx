import React from "react";
import { Download, ExternalLink, FileCode2, Image, X } from "lucide-react";

import { apiUrl } from "@/lib/apiUrl";
import type { ArtifactBlock } from "@/lib/chat";

const POSTERLY_SOURCE = "https://github.com/Chenruishuo/posterly/tree/b9f42e5578a49a27525a68f85376bb3bb25af86f";

interface Manifest {
  entrypoint: string;
  gate_report: string;
  downloads: Array<{ path: string; label: string }>;
  canvas: { width: number; height: number; unit: string; orientation: string };
  direction: string;
  omitted_branding: string[];
  gate_summary: string[];
}

interface VersionSummary {
  version_id: string;
  version: number;
  gate_status: ArtifactBlock["gate_status"];
  total_bytes: number;
}

function publicShareId(): string | null {
  if (typeof window === "undefined") return null;
  const match = window.location.pathname.match(/^\/share\/([^/]+)/u);
  return match ? decodeURIComponent(match[1]) : null;
}

function urls(block: ArtifactBlock) {
  if (block.scope === "public") {
    const share = publicShareId();
    if (!share || !block.public_capability) return null;
    const root = `/api/v1/chat/shares/${encodeURIComponent(share)}/artifacts/${encodeURIComponent(block.public_capability)}`;
    return {
      preview: apiUrl(`${root}/preview`),
      png: apiUrl(`${root}/download/png`),
      pdf: apiUrl(`${root}/download/pdf`),
      manifest: null,
      source: null,
      gate: null,
    };
  }
  if (!block.artifact_id || !block.version_id) return null;
  const root = `/api/v1/chat/artifacts/${encodeURIComponent(block.artifact_id)}/versions/${encodeURIComponent(block.version_id)}`;
  return {
    preview: apiUrl(`${root}/preview`),
    png: apiUrl(`${root}/download/${encodeURIComponent("poster.png")}`),
    pdf: null,
    manifest: apiUrl(`${root}/manifest`),
    source: (path: string) => apiUrl(`${root}/source/${path.split("/").map(encodeURIComponent).join("/")}`),
    gate: (path: string) => apiUrl(`${root}/source/${path.split("/").map(encodeURIComponent).join("/")}`),
    download: (path: string) => apiUrl(`${root}/download/${path.split("/").map(encodeURIComponent).join("/")}`),
  };
}

const gateLabel = (status?: ArtifactBlock["gate_status"]) => ({
  passed: "Passed",
  warnings: "Passed with warnings",
  failed: "Non-final draft",
}[status ?? "passed"]);

export const PosterArtifact: React.FC<{ block: ArtifactBlock }> = ({ block }) => {
  const [open, setOpen] = React.useState(false);
  const [tab, setTab] = React.useState<"preview" | "source">("preview");
  const [manifest, setManifest] = React.useState<Manifest | null>(null);
  const [source, setSource] = React.useState<string | null>(null);
  const [versions, setVersions] = React.useState<VersionSummary[]>([]);
  const [selected, setSelected] = React.useState<VersionSummary | null>(null);
  const previousStatus = React.useRef(block.status);
  const effective = selected ? {
    ...block,
    version_id: selected.version_id,
    version: selected.version,
    gate_status: selected.gate_status,
    total_bytes: selected.total_bytes,
  } : block;
  const cardLinks = urls(block);
  const links = urls(effective);

  React.useEffect(() => {
    if (previousStatus.current === "generating" && block.status === "ready" && block.scope === "owner") {
      setOpen(true);
    }
    previousStatus.current = block.status;
  }, [block.scope, block.status]);

  React.useEffect(() => {
    if (!open || block.scope !== "owner" || !block.artifact_id || versions.length) return;
    void fetch(apiUrl(`/api/v1/chat/artifacts/${encodeURIComponent(block.artifact_id)}`), {
      credentials: "include", cache: "no-store",
    })
      .then((response) => response.ok ? response.json() as Promise<{ versions: VersionSummary[] }> : Promise.reject())
      .then((result) => setVersions(result.versions))
      .catch(() => undefined);
  }, [block.artifact_id, block.scope, open, versions.length]);

  React.useEffect(() => {
    if (!open || !links?.manifest || manifest) return;
    void fetch(links.manifest, { credentials: "include", cache: "no-store" })
      .then((response) => response.ok ? response.json() as Promise<Manifest> : Promise.reject())
      .then(setManifest)
      .catch(() => undefined);
  }, [links?.manifest, manifest, open]);

  React.useEffect(() => {
    if (tab !== "source" || source !== null || !manifest || !links?.source) return;
    const sourceUrl = links.source(manifest.entrypoint);
    void fetch(sourceUrl, { credentials: "include", cache: "no-store" })
      .then((response) => response.ok ? response.text() : Promise.reject())
      .then(setSource)
      .catch(() => setSource("Source could not be loaded."));
  }, [links, manifest, source, tab]);

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
  if (!links || !cardLinks) return null;
  const pdfPath = manifest?.downloads[0]?.path;
  const pdfUrl = block.scope === "public"
    ? links.pdf
    : pdfPath && typeof links.download === "function"
      ? links.download(pdfPath)
      : null;
  const pngUrl = block.scope === "public" ? links.png : links.preview;

  return <>
    <button type="button" className="chat-artifact-card" onClick={() => setOpen(true)}>
      <img src={cardLinks.preview} alt={`Preview of ${block.title}`} />
      <span className="chat-artifact-card-copy">
        <span className="chat-artifact-kicker"><Image aria-hidden="true" /> Posterly · v{block.version}</span>
        <strong>{block.title}</strong>
        <small className={`chat-artifact-gate chat-artifact-gate-${block.gate_status}`}>{gateLabel(block.gate_status)}</small>
      </span>
    </button>
    {open && <div className="chat-artifact-overlay" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) setOpen(false);
    }}>
      <section className="chat-artifact-panel" role="dialog" aria-modal="true" aria-label={block.title}>
        <header>
          <div><span>Posterly artifact</span><h2>{block.title}</h2></div>
          {versions.length > 1 && <label className="chat-artifact-version">Version
            <select value={effective.version_id} onChange={(event) => {
              setSelected(versions.find((item) => item.version_id === event.target.value) ?? null);
              setManifest(null); setSource(null); setTab("preview");
            }}>
              {[...versions].reverse().map((item) => <option value={item.version_id} key={item.version_id}>v{item.version}</option>)}
            </select>
          </label>}
          <button type="button" aria-label="Close poster" onClick={() => setOpen(false)}><X /></button>
        </header>
        <nav aria-label="Poster views">
          <button type="button" className={tab === "preview" ? "active" : ""} onClick={() => setTab("preview")}>Preview</button>
          {block.scope === "owner" && <button type="button" className={tab === "source" ? "active" : ""} onClick={() => setTab("source")}>Source</button>}
        </nav>
        <div className="chat-artifact-panel-body">
          {tab === "preview"
            ? <img src={links.preview} alt={`Full preview of ${block.title}`} />
            : <pre><code>{source ?? "Loading source…"}</code></pre>}
        </div>
        <footer>
          <div className="chat-artifact-metadata">
            <strong>{gateLabel(effective.gate_status)}</strong>
            {manifest && <span>{manifest.canvas.width} × {manifest.canvas.height} {manifest.canvas.unit} · {manifest.canvas.orientation} · {manifest.direction}</span>}
            {manifest?.gate_summary.map((warning) => <span key={warning}>{warning}</span>)}
          </div>
          <div className="chat-artifact-actions">
            <a href={pngUrl} download><Download /> PNG</a>
            {effective.gate_status !== "failed" && pdfUrl && <a href={pdfUrl} download><Download /> PDF</a>}
            {block.scope === "owner" && manifest && links.source && <a href={links.source(manifest.entrypoint)} download><FileCode2 /> HTML</a>}
            {block.scope === "owner" && manifest && links.gate && <a href={links.gate(manifest.gate_report)} download>Gate report</a>}
            <a href={POSTERLY_SOURCE} target="_blank" rel="noreferrer"><ExternalLink /> Posterly source · AGPL-3.0</a>
          </div>
        </footer>
      </section>
    </div>}
  </>;
};
