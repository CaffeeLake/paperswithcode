import { useLayoutEffect, useRef } from "react";
import type { FormEvent } from "react";
import { ExternalLink, Github, X } from "lucide-react";
import { Link } from "react-router-dom";

export interface PdfToolbarResources {
  repository?: { href: string; stars: number };
  projectPage?: { href: string; label: string };
  huggingFace?: { href: string; count: number };
}

interface PdfToolbarProps {
  paperTitle: string;
  paperHref: string;
  resources?: PdfToolbarResources;
  page: number;
  pages: number;
  zoomPercent: number;
  searchOpen: boolean;
  searchQuery: string;
  searchMatch: number;
  searchCount: number;
  searching: boolean;
  onPage: (page: number) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onToggleSearch: () => void;
  onCloseSearch: () => void;
  onSearchQuery: (query: string) => void;
  onSearch: (direction: 1 | -1) => void;
}

export function PdfToolbar({
  paperTitle,
  paperHref,
  resources,
  page,
  pages,
  zoomPercent,
  searchOpen,
  searchQuery,
  searchMatch,
  searchCount,
  searching,
  onPage,
  onZoomIn,
  onZoomOut,
  onToggleSearch,
  onCloseSearch,
  onSearchQuery,
  onSearch,
}: PdfToolbarProps) {
  const toolbarRef = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const toolbar = toolbarRef.current;
    const logo = document.querySelector<HTMLElement>(".app-header .brand-mark");
    if (!toolbar || !logo) return;
    const alignTitle = () => {
      const inset = logo.getBoundingClientRect().left - toolbar.getBoundingClientRect().left;
      toolbar.style.setProperty("--reader-title-inset", `${Math.max(10, inset)}px`);
    };
    alignTitle();
    const observer = new ResizeObserver(alignTitle);
    observer.observe(toolbar);
    observer.observe(logo);
    return () => observer.disconnect();
  }, []);

  const submitPage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = Number(new FormData(event.currentTarget).get("page"));
    if (Number.isInteger(value)) onPage(value);
  };
  return <div ref={toolbarRef} className="pdf-toolbar" aria-label="PDF controls">
    <div className="pdf-toolbar-paper">
      <Link className="pdf-toolbar-title" to={paperHref} title={paperTitle} aria-label={`${paperTitle} — open paper page`}>
        {paperTitle}
      </Link>
      {resources?.repository && <a
        className="pdf-toolbar-resource"
        href={resources.repository.href}
        target="_blank"
        rel="noopener noreferrer"
        title="Official GitHub repository"
        aria-label="Open official GitHub repository"
      >
        <Github size={15} strokeWidth={1.8} aria-hidden="true" />
        <span aria-label={`${resources.repository.stars} GitHub stars`}>★ {resources.repository.stars.toLocaleString()}</span>
      </a>}
      {resources?.projectPage && <a
        className="pdf-toolbar-resource"
        href={resources.projectPage.href}
        target="_blank"
        rel="noopener noreferrer"
        title={resources.projectPage.href}
        aria-label={`Open project page at ${resources.projectPage.label}`}
      >
        <ExternalLink size={14} strokeWidth={1.8} aria-hidden="true" />
        <span>{resources.projectPage.label}</span>
      </a>}
      {resources?.huggingFace && <a
        className="pdf-toolbar-resource"
        href={resources.huggingFace.href}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Open ${resources.huggingFace.count} Hugging Face ${resources.huggingFace.count === 1 ? "artifact" : "artifacts"}`}
      >
        <span aria-hidden="true">🤗</span>
        <span>{resources.huggingFace.count} HF {resources.huggingFace.count === 1 ? "artifact" : "artifacts"}</span>
      </a>}
    </div>
    <div className="pdf-toolbar-controls">
      <div className="pdf-toolbar-group">
        <button type="button" onClick={() => onPage(page - 1)} disabled={page <= 1} aria-label="Previous page">←</button>
        <form onSubmit={submitPage} className="pdf-page-form">
          <label className="sr-only" htmlFor="pdf-current-page">Current page</label>
          <input id="pdf-current-page" name="page" type="number" min={1} max={pages || 1} defaultValue={page} key={page} aria-label={`Page ${page} of ${pages || "unknown"}`} />
          <span aria-hidden="true">/ {pages || "—"}</span>
        </form>
        <button type="button" onClick={() => onPage(page + 1)} disabled={!pages || page >= pages} aria-label="Next page">→</button>
      </div>
      <div className="pdf-toolbar-group">
        <button type="button" onClick={onZoomOut} aria-label="Zoom out">−</button>
        <span className="pdf-zoom-value" aria-live="polite">{zoomPercent}%</span>
        <button type="button" onClick={onZoomIn} aria-label="Zoom in">+</button>
        <button type="button" onClick={onToggleSearch} aria-expanded={searchOpen} aria-controls="pdf-search-controls">Search</button>
      </div>
    </div>
    {searchOpen && <div id="pdf-search-controls" className="pdf-search-controls">
      <label className="sr-only" htmlFor="pdf-search-input">Search document</label>
      <input
        id="pdf-search-input"
        autoFocus
        value={searchQuery}
        onChange={(event) => onSearchQuery(event.target.value)}
        placeholder="Search document"
      />
      <span role="status">{searching ? "Searching…" : searchQuery ? `${searchCount ? searchMatch + 1 : 0} of ${searchCount}` : ""}</span>
      <button type="button" onClick={() => onSearch(-1)} disabled={!searchCount} aria-label="Previous match">↑</button>
      <button type="button" onClick={() => onSearch(1)} disabled={!searchCount} aria-label="Next match">↓</button>
      <button type="button" onClick={onCloseSearch} aria-label="Close search" title="Close search">
        <X size={16} aria-hidden="true" />
      </button>
    </div>}
  </div>;
}
