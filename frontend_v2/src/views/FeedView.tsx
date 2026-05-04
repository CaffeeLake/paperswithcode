import React, { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PaperCard } from "@/components";
import { apiClient } from "@/lib/api";
import { transformPaperForCard, transformTrendingForCard } from "@/lib/transform";
import { usePapers, useTrendingPapers } from "@/hooks/usePapers";
import { PERIODS, usePeriodFilter } from "@/hooks/usePeriodFilter";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useQuery } from "@tanstack/react-query";

type SortKey = "trending" | "new" | "cited";

const SORT_OPTIONS: Array<[SortKey, string]> = [
  ["trending", "trending"],
  ["new", "newest"],
  ["cited", "most cited"],
];

const FeedView: React.FC = () => {
  const [sortBy, setSortBy] = useState<SortKey>("trending");
  const { period, setPeriod, publishedAfter } = usePeriodFilter("This Week");

  // Sidebar: top tasks by paper count.
  const topTasks = useQuery({
    queryKey: ["top-tasks-sidebar"],
    queryFn: () => apiClient.getTasks({ ordering: "-paper_count", page_size: 8 }),
    staleTime: 10 * 60 * 1000,
  });

  // Trending uses the dedicated /papers/trending endpoint (PLAN.md §4.6).
  const trending = useTrendingPapers({ limit: 30, enabled: sortBy === "trending" });

  // Other sort modes use /papers with order_by + period filter.
  const orderBy = sortBy === "cited" ? "citation_count" : "date_published";
  const papers = usePapers({
    page_size: 30,
    order_by: orderBy,
    order_dir: "desc",
    published_after: publishedAfter,
    include_resources: true,
    enabled: sortBy !== "trending",
  });

  const cards = useMemo(() => {
    if (sortBy === "trending") {
      return (trending.data || []).map(transformTrendingForCard);
    }
    return (papers.data?.results || []).map(transformPaperForCard);
  }, [sortBy, trending.data, papers.data]);

  const isLoading = sortBy === "trending" ? trending.isLoading : papers.isLoading;
  const error = sortBy === "trending" ? trending.error : papers.error;

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            Trending <em>Research</em>
          </h1>
          <div className="feed-subtitle">Curated daily from arXiv and Hugging Face</div>
        </div>
        <div style={{ display: "flex", gap: 16, alignItems: "center", flexWrap: "wrap" }}>
          <div className="period-switch">
            {PERIODS.map((p) => (
              <button
                key={p}
                className={`period-btn ${period === p ? "active" : ""}`}
                onClick={() => setPeriod(p)}
              >
                {p}
              </button>
            ))}
          </div>
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
                {task.name}
                {task.paper_count != null && <span className="count">{task.paper_count}</span>}
              </Link>
            ))}
            <Link to="/tasks" className="sidebar-link" style={{ marginTop: 8, fontStyle: "italic" }}>
              all domains →
            </Link>
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
            <div className="results-count">{cards.length} papers</div>
          </div>

          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertDescription>Failed to load papers. Please try again.</AlertDescription>
            </Alert>
          )}

          {isLoading ? (
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
            <div className="no-results">No papers in this window.</div>
          ) : (
            <div className="paper-list">
              {cards.map((p, i) => (
                <PaperCard key={p.id} paper={p} rank={i + 1} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default FeedView;
