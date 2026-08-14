/**
 * Global ⌘K search overlay.
 *
 * Switched from the v2 prototype's hardcoded `PAPERS.filter(...)` to debounced
 * server-side search via `/api/v1/papers/?search=…` (PLAN.md §6).
 */

import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import LatexTitle from "@/components/LatexTitle";
import { catalogApi } from "@/lib/api/catalog";
import { papersApi } from "@/lib/api/papers";
import { isChatEnabled } from "@/lib/apiUrl";
import { useDebounce } from "@/hooks/useDebounce";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { displayTaskName } from "@/lib/transform";

interface SearchOverlayProps {
  open: boolean;
  onClose: () => void;
}

const PAPER_PAGE_SIZE = 10;

const SearchOverlay: React.FC<SearchOverlayProps> = ({ open, onClose }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const [query, setQuery] = React.useState("");
  const [paperPage, setPaperPage] = React.useState(1);
  const debouncedQuery = useDebounce(query, 200);
  const chatEnabled = isChatEnabled();

  useEffect(() => {
    if (!open) return;
    inputRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const papersQ = useQuery({
    queryKey: ["search-papers", debouncedQuery, paperPage],
    queryFn: () => papersApi.search(debouncedQuery, paperPage, PAPER_PAGE_SIZE),
    enabled: open && debouncedQuery.length >= 2,
    staleTime: 60_000,
  });

  const tasksQ = useQuery({
    queryKey: ["search-tasks", debouncedQuery],
    queryFn: () => catalogApi.listTasks({ q: debouncedQuery, page_size: 6 }),
    enabled: open && debouncedQuery.length >= 2,
    staleTime: 60_000,
  });

  const methodsQ = useQuery({
    queryKey: ["search-methods", debouncedQuery],
    queryFn: () => catalogApi.listMethods({ q: debouncedQuery, page_size: 6 }),
    enabled: open && debouncedQuery.length >= 2,
    staleTime: 60_000,
  });

  const benchmarksQ = useQuery({
    queryKey: ["search-benchmarks", debouncedQuery],
    queryFn: () =>
      catalogApi.listDatasets({
        q: debouncedQuery,
        page_size: 6,
      }),
    enabled: open && debouncedQuery.length >= 2,
    staleTime: 60_000,
  });

  if (!open) return null;

  const matchedTasks = tasksQ.data?.results || [];
  const matchedMethods = methodsQ.data?.results || [];
  const matchedBenchmarks = benchmarksQ.data?.results || [];
  const matchedPapers = papersQ.data?.results || [];
  const isLoading =
    papersQ.isFetching ||
    tasksQ.isFetching ||
    methodsQ.isFetching ||
    benchmarksQ.isFetching;
  const hasResults =
    matchedTasks.length ||
    matchedPapers.length ||
    matchedMethods.length ||
    matchedBenchmarks.length;

  const go = (path: string) => {
    onClose();
    navigate(path);
  };

  // Enter hands the query to the AI assistant on /chat; browsing the live
  // results below remains click/tab-driven as before.
  const askAssistant = () => {
    const q = query.trim();
    if (q) go(`/chat?q=${encodeURIComponent(q)}`);
  };

  return (
    <div className="search-overlay" onClick={onClose}>
      <div className="search-modal" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="search-modal-input"
          placeholder="Search papers, tasks, methods, or benchmarks…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setPaperPage(1);
          }}
          onKeyDown={(e) => {
            if (chatEnabled && e.key === "Enter") {
              e.preventDefault();
              askAssistant();
            }
          }}
        />
        <div className="search-results">
          {chatEnabled && query.trim() && (
            <button type="button" className="search-ask-row" onClick={askAssistant}>
              <span className="search-ask-chip">assistant</span>
              <span className="search-ask-text">Ask: “{query.trim()}”</span>
              <kbd>↵</kbd>
            </button>
          )}
          {!debouncedQuery && (
            <div className="search-empty">
              Try “diffusion”, “object detection”, or an arXiv id.
              {chatEnabled && (
                <span className="search-empty-sub">Press Enter to ask the assistant</span>
              )}
            </div>
          )}
          {debouncedQuery && !isLoading && !hasResults && (
            <div className="search-empty">No matches for "{query}"</div>
          )}
          {matchedTasks.length > 0 && (
            <>
              <div className="search-section-label">Tasks · {matchedTasks.length}</div>
              {matchedTasks.map((t) => {
                const c = chipColors(hueFromSlug(t.slug || ""));
                return (
                  <div
                    key={t.id}
                    className="search-result-tag"
                    onClick={() => go(`/tasks/${t.slug}`)}
                  >
                    <span
                      className="dot"
                      style={{ width: 6, height: 6, borderRadius: "50%", background: c.dot }}
                    ></span>
                    <span className="name">{displayTaskName(t.name, t.slug)}</span>
                    {t.paper_count != null && <span className="count">{t.paper_count} papers</span>}
                  </div>
                );
              })}
            </>
          )}
          {matchedMethods.length > 0 && (
            <>
              <div className="search-section-label">Methods · {matchedMethods.length}</div>
              {matchedMethods.map((m) => (
                <div
                  key={m.id}
                  className="search-result-tag"
                  onClick={() => go(`/methods/${m.slug || m.id}`)}
                >
                  <span style={{ fontFamily: "var(--mono)", fontWeight: 600 }}>{m.name}</span>
                  {m.paper_count != null && <span className="count">{m.paper_count} papers</span>}
                </div>
              ))}
            </>
          )}
          {matchedBenchmarks.length > 0 && (
            <>
              <div className="search-section-label">Benchmarks · {matchedBenchmarks.length}</div>
              {matchedBenchmarks.map((d) => (
                <div
                  key={d.id}
                  className="search-result-tag"
                  onClick={() => go(`/benchmark/${d.slug || d.id}`)}
                >
                  <span className="name">{d.name}</span>
                  {d.paper_count != null && d.paper_count > 0 && (
                    <span className="count">{d.paper_count} entries</span>
                  )}
                </div>
              ))}
            </>
          )}
          {matchedPapers.length > 0 && (
            <>
              <div className="search-section-label">Papers · page {paperPage}</div>
              {matchedPapers.map((p) => (
                <div key={p.id} className="search-result" onClick={() => go(`/paper/${p.arxiv_id || p.id}`)}>
                  <div className="search-result-title">
                    <LatexTitle title={p.title} />
                  </div>
                  <div className="search-result-meta">
                    <span>{p.arxiv_id ? `arXiv:${p.arxiv_id}` : "External resource"}</span>
                    {p.authors?.[0] && (
                      <>
                        <span>·</span>
                        <span>{p.authors[0]}{p.authors.length > 1 ? " et al." : ""}</span>
                      </>
                    )}
                    {p.citation_count != null && (
                      <>
                        <span>·</span>
                        <span>↑ {p.citation_count.toLocaleString()}</span>
                      </>
                    )}
                  </div>
                </div>
              ))}
              {(papersQ.data?.previous_page || papersQ.data?.next_page) && (
                <div className="search-paper-pagination">
                  <button
                    type="button"
                    disabled={!papersQ.data.previous_page || papersQ.isFetching}
                    onClick={() => setPaperPage(papersQ.data?.previous_page || 1)}
                  >
                    Previous
                  </button>
                  <span>Page {paperPage}</span>
                  <button
                    type="button"
                    disabled={!papersQ.data.next_page || papersQ.isFetching}
                    onClick={() => {
                      if (papersQ.data?.next_page) setPaperPage(papersQ.data.next_page);
                    }}
                  >
                    Next
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default SearchOverlay;
