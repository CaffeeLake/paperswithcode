import type { FormEvent } from "react";
import { Link } from "react-router-dom";

interface PdfToolbarProps {
  paperTitle: string;
  paperHref: string;
  page: number;
  pages: number;
  zoomPercent: number;
  searchOpen: boolean;
  searchQuery: string;
  searchMatch: number;
  searchCount: number;
  searching: boolean;
  originalUrl: string;
  onPage: (page: number) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onToggleSearch: () => void;
  onSearchQuery: (query: string) => void;
  onSearch: (direction: 1 | -1) => void;
}

export function PdfToolbar({
  paperTitle,
  paperHref,
  page,
  pages,
  zoomPercent,
  searchOpen,
  searchQuery,
  searchMatch,
  searchCount,
  searching,
  originalUrl,
  onPage,
  onZoomIn,
  onZoomOut,
  onToggleSearch,
  onSearchQuery,
  onSearch,
}: PdfToolbarProps) {
  const submitPage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const value = Number(new FormData(event.currentTarget).get("page"));
    if (Number.isInteger(value)) onPage(value);
  };
  return <div className="pdf-toolbar" aria-label="PDF controls">
    <div className="pdf-toolbar-paper">
      <Link to={paperHref} title={paperTitle} aria-label={`${paperTitle} — open paper page`}>
        {paperTitle}
      </Link>
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
        <a href={originalUrl} target="_blank" rel="noopener noreferrer" download>Open original</a>
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
    </div>}
  </div>;
}
