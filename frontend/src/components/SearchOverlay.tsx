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
import { apiClient } from "@/lib/api";
import { useDebounce } from "@/hooks/useDebounce";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { displayTaskName } from "@/lib/transform";

interface SearchOverlayProps {
  open: boolean;
  onClose: () => void;
}

const SearchOverlay: React.FC<SearchOverlayProps> = ({ open, onClose }) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const [query, setQuery] = React.useState("");
  const debouncedQuery = useDebounce(query, 200);

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
    queryKey: ["search-papers", debouncedQuery],
    queryFn: () =>
      apiClient.getPapers({ search: debouncedQuery, page_size: 6, latest_only: true }),
    enabled: open && debouncedQuery.length >= 2,
    staleTime: 60_000,
  });

  const tasksQ = useQuery({
    queryKey: ["search-tasks", debouncedQuery],
    queryFn: () => apiClient.getTasks({ q: debouncedQuery, page_size: 6 }),
    enabled: open && debouncedQuery.length >= 2,
    staleTime: 60_000,
  });

  const methodsQ = useQuery({
    queryKey: ["search-methods", debouncedQuery],
    queryFn: () => apiClient.getMethods({ q: debouncedQuery, page_size: 6 }),
    enabled: open && debouncedQuery.length >= 2,
    staleTime: 60_000,
  });

  if (!open) return null;

  const matchedTasks = tasksQ.data?.results || [];
  const matchedMethods = methodsQ.data?.results || [];
  const matchedPapers = papersQ.data?.results || [];
  const isLoading = papersQ.isFetching || tasksQ.isFetching || methodsQ.isFetching;
  const hasResults = matchedTasks.length || matchedPapers.length || matchedMethods.length;

  const go = (path: string) => {
    onClose();
    navigate(path);
  };

  return (
    <div className="search-overlay" onClick={onClose}>
      <div className="search-modal" onClick={(e) => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="search-modal-input"
          placeholder="Search papers, tasks, or methods…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="search-results">
          {!debouncedQuery && (
            <div className="search-empty">Try “diffusion”, “object detection”, or an arXiv id.</div>
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
          {matchedPapers.length > 0 && (
            <>
              <div className="search-section-label">Papers · {matchedPapers.length}</div>
              {matchedPapers.map((p) => (
                <div key={p.id} className="search-result" onClick={() => go(`/paper/${p.arxiv_id}`)}>
                  <div className="search-result-title">
                    <LatexTitle title={p.title} />
                  </div>
                  <div className="search-result-meta">
                    <span>arXiv:{p.arxiv_id}</span>
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
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default SearchOverlay;
