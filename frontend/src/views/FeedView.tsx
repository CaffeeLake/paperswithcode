import React, { useEffect, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { PaperCard } from "@/components";
import { apiClient } from "@/lib/api";
import { displayTaskName, transformPaperForCard, transformTrendingForCard } from "@/lib/transform";
import { useInfinitePapers, useTrendingPapers } from "@/hooks/usePapers";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { PERIODS, type Period } from "@/hooks/usePeriodFilter";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { useQuery } from "@tanstack/react-query";

type OrderBy = "trending" | "date_published" | "citation_count";
type TimeWindow = "today" | "week" | "month" | "all_time";

const SORT_OPTIONS: Array<[OrderBy, string]> = [
  ["trending", "trending"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
];

const PERIOD_TO_TIME: Record<Period, TimeWindow> = {
  Today: "today",
  "This Week": "week",
  "This Month": "month",
  "All Time": "all_time",
};

const TIME_TO_PERIOD: Record<TimeWindow, Period> = {
  today: "Today",
  week: "This Week",
  month: "This Month",
  all_time: "All Time",
};

const TIME_TO_MAX_AGE_DAYS: Record<TimeWindow, number> = {
  today: 1,
  week: 7,
  month: 30,
  all_time: 365,
};

const parseOrderBy = (value: string | null): OrderBy => {
  if (value === "trending" || value === "date_published" || value === "citation_count") {
    return value;
  }
  return "trending";
};

const parseTime = (value: string | null): TimeWindow => {
  if (value === "today" || value === "week" || value === "month" || value === "all_time") {
    return value;
  }
  return "all_time";
};

const FeedView: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const orderBy = parseOrderBy(searchParams.get("order_by"));
  const timeWindow = parseTime(searchParams.get("time"));
  const period = TIME_TO_PERIOD[timeWindow];

  const setOrderBy = (nextOrderBy: OrderBy) => {
    const next = new URLSearchParams(searchParams);
    next.set("order_by", nextOrderBy);
    setSearchParams(next);
  };

  const setTimeWindow = (nextPeriod: Period) => {
    const next = new URLSearchParams(searchParams);
    next.set("time", PERIOD_TO_TIME[nextPeriod]);
    setSearchParams(next);
  };

  // Sidebar: top tasks by paper count.
  const topTasks = useQuery({
    queryKey: ["top-tasks-sidebar"],
    queryFn: () => apiClient.getTopTasks({ limit: 8 }),
    staleTime: 10 * 60 * 1000,
  });

  // Sidebar: tasks whose share of recent papers is rising vs their baseline.
  // Independent of Top Domains; overlapping entries appear in both sections
  // so neither list misrepresents its own signal.
  const trendingTasks = useQuery({
    queryKey: ["trending-tasks-sidebar"],
    queryFn: () => apiClient.getTrendingTasks({ limit: 8 }),
    staleTime: 10 * 60 * 1000,
  });

  const infinite = useInfinitePapers({
    page_size: 30,
    order_by: orderBy,
    order_dir: "desc",
    time: timeWindow,
    include_resources: true,
    enabled: orderBy !== "trending",
  });

  const trendingPapers = useTrendingPapers({
    limit: 30,
    max_age_days: TIME_TO_MAX_AGE_DAYS[timeWindow],
    enabled: orderBy === "trending",
  });

  const cards = useMemo(() => {
    if (orderBy === "trending") {
      return (trendingPapers.data || []).map(transformTrendingForCard);
    }
    const all = infinite.data?.pages.flatMap((p) => p.results) || [];
    return all.map(transformPaperForCard);
  }, [orderBy, infinite.data, trendingPapers.data]);

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "400px" });
  useEffect(() => {
    if (orderBy !== "trending" && isIntersecting && infinite.hasNextPage && !infinite.isFetchingNextPage) {
      infinite.fetchNextPage();
    }
  }, [orderBy, isIntersecting, infinite.hasNextPage, infinite.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  const isLoading = orderBy === "trending" ? trendingPapers.isLoading : infinite.isLoading;
  const error = orderBy === "trending" ? trendingPapers.error : infinite.error;

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
                onClick={() => setTimeWindow(p)}
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
            {topTasks.data?.map((task) => (
              <Link key={task.id} to={`/tasks/${task.slug}`} className="sidebar-link">
                {displayTaskName(task.name, task.slug)}
                {task.paper_count != null && <span className="count">{task.paper_count}</span>}
              </Link>
            ))}
            <Link to="/tasks" className="sidebar-link" style={{ marginTop: 8, fontStyle: "italic" }}>
              all domains →
            </Link>
          </div>

          <div className="sidebar-section">
            <div className="sidebar-label">Trending Domains</div>
            {trendingTasks.isLoading && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {Array.from({ length: 6 }).map((_, i) => (
                  <Skeleton key={i} className="h-5 w-full" />
                ))}
              </div>
            )}
            {trendingTasks.data?.results?.length === 0 && !trendingTasks.isLoading && (
              <div style={{ fontSize: 12, color: "var(--ink-faint)" }}>
                No domains gaining momentum right now.
              </div>
            )}
            {trendingTasks.data?.results?.map((task) => (
              <Link key={task.id} to={`/tasks/${task.slug}`} className="sidebar-link">
                {displayTaskName(task.name, task.slug)}
                <span className="count">{task.share_lift.toFixed(1)}x</span>
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
                  className={`sort-btn ${orderBy === k ? "active" : ""}`}
                  onClick={() => setOrderBy(k)}
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
            <>
              <div className="paper-list">
                {cards.map((p, i) => (
                  <PaperCard key={p.id} paper={p} rank={i + 1} />
                ))}
              </div>
              {orderBy !== "trending" && (
                <>
                  <div ref={sentinelRef} style={{ height: 1 }} />
                  {infinite.isFetchingNextPage && (
                    <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>
                      Loading more…
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default FeedView;
