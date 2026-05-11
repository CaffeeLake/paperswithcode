import React, { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Icon, PaperCard } from "@/components";
import { apiClient } from "@/lib/api";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { useInfinitePapers } from "@/hooks/usePapers";
import { useDebounce } from "@/hooks/useDebounce";
import { PERIODS, usePeriodFilter } from "@/hooks/usePeriodFilter";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useQuery } from "@tanstack/react-query";

type SortKey = "trending" | "new" | "cited";
const SORT_OPTIONS: Array<[SortKey, string]> = [
  ["trending", "trending"],
  ["new", "newest"],
  ["cited", "most cited"],
];

const PapersListView: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlSearch = searchParams.get("search") || "";
  const [searchInput, setSearchInput] = useState(urlSearch);
  const debouncedSearch = useDebounce(searchInput, 300);

  // Mirror debounced text into the URL so the search is bookmarkable.
  useEffect(() => {
    if (debouncedSearch === urlSearch) return;
    const next = new URLSearchParams(searchParams);
    if (debouncedSearch) next.set("search", debouncedSearch);
    else next.delete("search");
    setSearchParams(next, { replace: true });
  }, [debouncedSearch]); // eslint-disable-line react-hooks/exhaustive-deps

  const [sortBy, setSortBy] = useState<SortKey>("new");
  const { period, setPeriod, publishedAfter } = usePeriodFilter("All Time");

  const orderBy =
    sortBy === "trending"
      ? "trending"
      : sortBy === "cited"
        ? "citation_count"
        : "date_published";
  const infinite = useInfinitePapers({
    page_size: 20,
    order_by: orderBy,
    order_dir: "desc",
    search: debouncedSearch || undefined,
    published_after: publishedAfter,
    include_resources: false,
  });

  const topTasks = useQuery({
    queryKey: ["top-tasks-sidebar"],
    queryFn: () => apiClient.getTasks({ ordering: "-paper_count", page_size: 8 }),
    staleTime: 10 * 60 * 1000,
  });

  const cards = useMemo(() => {
    const all = infinite.data?.pages.flatMap((p) => p.results) || [];
    return all.map(transformPaperForCard);
  }, [infinite.data]);

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "200px" });
  useEffect(() => {
    if (isIntersecting && infinite.hasNextPage && !infinite.isFetchingNextPage) {
      infinite.fetchNextPage();
    }
  }, [isIntersecting, infinite.hasNextPage, infinite.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  const totalCount = infinite.data?.pages?.[0]?.count ?? 0;

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            All <em>Papers</em>
          </h1>
          <div className="feed-subtitle">
            Search the full corpus. {totalCount > 0 && `${totalCount.toLocaleString()} papers indexed.`}
          </div>
        </div>
        <div className="period-switch">
          {PERIODS.map((p) => (
            <button key={p} className={`period-btn ${period === p ? "active" : ""}`} onClick={() => setPeriod(p)}>
              {p}
            </button>
          ))}
        </div>
      </div>

      <div className="papers-search-row">
        <div className="papers-search-input-wrap">
          <Icon name="search" size={14} />
          <input
            className="papers-search-input"
            placeholder="Search title or abstract…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>
      </div>

      <div className="layout-with-sidebar">
        <aside className="sidebar">
          <div className="sidebar-section">
            <div className="sidebar-label">Top Domains</div>
            {topTasks.isLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-5 w-full" />
                ))}
              </div>
            )}
            {topTasks.data?.results?.map((task) => (
              <Link key={task.id} to={`/tasks/${task.slug}`} className="sidebar-link">
                {displayTaskName(task.name, task.slug)}
                {task.paper_count != null && <span className="count">{task.paper_count}</span>}
              </Link>
            ))}
          </div>
        </aside>

        <div>
          <div className="sort-bar">
            <div className="sort-options">
              {SORT_OPTIONS.map(([k, l]) => (
                <button
                  key={k}
                  className={`sort-btn ${sortBy === k ? "active" : ""}`}
                  onClick={() => setSortBy(k)}
                >
                  {l}
                </button>
              ))}
            </div>
            <div className="results-count">{cards.length} loaded</div>
          </div>

          {infinite.error && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>Failed to load papers. Please try again.</AlertDescription>
            </Alert>
          )}

          {infinite.isLoading ? (
            <div className="paper-list">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="paper-card">
                  <Skeleton className="h-[220px] w-[160px]" />
                  <div className="paper-body" style={{ flex: 1, gap: 12 }}>
                    <Skeleton className="h-6 w-3/4" />
                    <Skeleton className="h-4 w-1/2" />
                    <Skeleton className="h-12 w-full" />
                  </div>
                </div>
              ))}
            </div>
          ) : cards.length === 0 ? (
            <div className="no-results">No matching papers.</div>
          ) : (
            <>
              <div className="paper-list">
                {cards.map((p, i) => (
                  <PaperCard key={p.id} paper={p} rank={i + 1} />
                ))}
              </div>
              <div ref={sentinelRef} style={{ height: 1 }} />
              {infinite.isFetchingNextPage && (
                <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>
                  Loading more…
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default PapersListView;
