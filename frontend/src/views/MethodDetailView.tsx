import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { MethodChip, PaperCard } from "@/components";
import { MethodFigure } from "@/components/MethodFigure";
import MethodUsageChart from "@/components/MethodUsageChart";
import MarkdownText from "@/components/MarkdownText";
import { apiClient } from "@/lib/api";
import { slugify } from "@/lib/slug";
import { transformPaperForCard } from "@/lib/transform";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";

type SortKey = "trending" | "new" | "cited";
const SORT_OPTIONS: Array<[SortKey, string]> = [
  ["trending", "trending"],
  ["new", "newest"],
  ["cited", "most cited"],
];

const RELATED_METHODS_BY_SLUG: Record<string, string[]> = {
  "on-policy-distillation": [
    "fine-tuning",
    "post-training",
    "rlvr",
    "rlhf",
    "direct-preference-optimization-dpo",
  ],
  mcp: ["agent-skills"],
  "agent-skills": ["mcp"],
};

const methodHistoryMonths = (introducedYear?: number) => {
  if (!introducedYear) return 24;
  const now = new Date();
  const monthsSinceJanuary =
    (now.getUTCFullYear() - introducedYear) * 12 + now.getUTCMonth() + 1;
  return Math.min(120, Math.max(6, monthsSinceJanuary));
};

const MethodDetailView: React.FC = () => {
  const { methodSlug } = useParams<{ methodSlug: string }>();
  const [sortBy, setSortBy] = useState<SortKey>("trending");

  const methodQ = useQuery({
    queryKey: ["method", methodSlug],
    queryFn: () => apiClient.getMethod(methodSlug!),
    enabled: !!methodSlug,
    staleTime: 10 * 60 * 1000,
  });

  const areasQ = useQuery({
    queryKey: ["areas-all"],
    queryFn: () => apiClient.getAreas({ page_size: 50, ordering: "name" }),
    enabled: !!methodQ.data?.area_id,
    staleTime: 10 * 60 * 1000,
  });

  const historyMonths = methodHistoryMonths(methodQ.data?.introduced_year);
  const trendQ = useQuery({
    queryKey: ["method-trend", methodSlug, historyMonths],
    queryFn: () =>
      apiClient.getMethodTrend(methodSlug!, { history_months: historyMonths }),
    enabled: !!methodSlug && !!methodQ.data,
    staleTime: 10 * 60 * 1000,
  });

  const orderBy: "trending" | "citation_count" | "date_published" =
    sortBy === "trending" ? "trending" : sortBy === "cited" ? "citation_count" : "date_published";
  const papersQ = useInfiniteQuery({
    queryKey: ["method-papers-infinite", methodSlug, orderBy],
    queryFn: ({ pageParam = 1 }) =>
      apiClient.getMethodPapers(methodSlug!, {
        page: pageParam as number,
        page_size: 20,
        order_by: orderBy,
        order_dir: "desc",
        include_resources: true,
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: !!methodSlug,
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
  });

  // Related methods: use curated siblings where available, otherwise fall back
  // to the most-popular methods in the same area.
  const relatedQ = useQuery({
    queryKey: ["related-methods", methodQ.data?.slug, methodQ.data?.area_id, methodQ.data?.id],
    queryFn: async () => {
      const curatedSlugs = RELATED_METHODS_BY_SLUG[methodQ.data!.slug];
      if (curatedSlugs) {
        return Promise.all(curatedSlugs.map((slug) => apiClient.getMethod(slug)));
      }

      const res = await apiClient.getMethods({
        area_id: methodQ.data!.area_id!,
        exclude_id: methodQ.data!.id,
        ordering: "-paper_count",
        page_size: 8,
      });
      return res.results;
    },
    enabled: !!methodQ.data && (!!RELATED_METHODS_BY_SLUG[methodQ.data.slug] || !!methodQ.data.area_id),
    staleTime: 10 * 60 * 1000,
  });

  const cards = useMemo(() => {
    const all = papersQ.data?.pages.flatMap((p) => p.results) || [];
    return all.map(transformPaperForCard);
  }, [papersQ.data]);

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "200px" });
  useEffect(() => {
    if (isIntersecting && papersQ.hasNextPage && !papersQ.isFetchingNextPage) {
      papersQ.fetchNextPage();
    }
  }, [isIntersecting, papersQ.hasNextPage, papersQ.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  if (methodQ.isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-1/2 mb-4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (methodQ.error || !methodQ.data) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Method not found.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const m = methodQ.data;
  const area = areasQ.data?.results.find((candidate) => candidate.id === m.area_id);

  return (
    <div className="page">
      <div className="breadcrumb">
        <Link to="/methods">Methods</Link>
        {area && (
          <>
            <span className="sep">/</span>
            <Link to={`/methods#area-${slugify(area.name)}`}>{area.name}</Link>
          </>
        )}
        <span className="sep">/</span>
        <span style={{ color: "var(--ink)" }}>{m.name}</span>
      </div>

      <div
        className={`tag-hero method-hero-grid${
          m.slug === "grokking" ? " method-hero-grid--wide-figure" : ""
        }`}
      >
        <div>
          <div className="tag-hero-eyebrow">METHOD</div>
          <h1 className="tag-hero-title method-hero-title">{m.name}</h1>
          {m.full_name && m.full_name !== m.name && (
            <div style={{ fontFamily: "var(--serif)", fontSize: 16, fontStyle: "italic", color: "var(--ink-soft)", marginTop: 8 }}>
              {m.full_name}
            </div>
          )}
          {m.description && (
            <MarkdownText className="method-description" text={m.description} />
          )}
          {m.source_url && m.source_title && (
            <div className="method-source">
              <span className="method-source-label">Source</span>
              <a className="method-source-link" href={m.source_url} target="_blank" rel="noopener noreferrer">
                <span className="method-source-title">{m.source_title}</span>
                {m.introduced_year && <span className="method-source-meta">{m.introduced_year}</span>}
              </a>
            </div>
          )}
          <div className="tag-hero-meta">
            <div className="stat">
              <span className="label">Papers using</span>
              <span className="value">{(m.paper_count ?? 0).toLocaleString()}</span>
            </div>
            {trendQ.data && (
              <div className="stat">
                <span className="label">Recent use</span>
                <span className="value">
                  {trendQ.data.trend_score.toFixed(1)}
                  <small>/mo</small>
                </span>
              </div>
            )}
            {m.introduced_year != null && (
              <div className="stat">
                <span className="label">Introduced</span>
                <span className="value">{m.introduced_year}</span>
              </div>
            )}
          </div>
          {trendQ.isLoading ? (
            <Skeleton className="h-36 w-full method-trend-skeleton" />
          ) : trendQ.data ? (
            <section className="method-trend-panel method-trend-panel--compact">
              <div className="method-trend-header">
                <div>
                  <div className="method-trend-eyebrow">Usage trend</div>
                  <h2>Papers using {m.name}</h2>
                  <p>
                    {m.introduced_year &&
                    methodHistoryMonths(m.introduced_year) < 120
                      ? `Monthly papers since ${m.introduced_year}.`
                      : `Monthly papers over the latest ${trendQ.data.history_months} months.`}
                  </p>
                </div>
                <div className="method-trend-summary">
                  <strong>{trendQ.data.recent_paper_count}</strong>
                  <span>papers / {trendQ.data.recent_days}d</span>
                </div>
              </div>
              <MethodUsageChart
                history={trendQ.data.history}
                methodName={m.name}
              />
            </section>
          ) : null}
        </div>
        <figure className="method-figure-card">
          <MethodFigure method={m} />
          {m.image_credit && (
            <figcaption>
              <MarkdownText className="method-image-credit" text={m.image_credit} />
            </figcaption>
          )}
        </figure>
      </div>

      {(relatedQ.data?.length ?? 0) > 0 && (
        <div className="filter-row">
          <span className="label">Related methods</span>
          {relatedQ.data!.map((rm) => (
            <MethodChip key={rm.id} method={{ slug: rm.slug, name: rm.name }} />
          ))}
        </div>
      )}

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
        <div className="results-count">{cards.length} papers using {m.name}</div>
      </div>

      {papersQ.isLoading ? (
        <div className="paper-list">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : cards.length === 0 ? (
        <div className="no-results">No papers tagged with this method yet.</div>
      ) : (
        <>
          <div className="paper-list">
            {cards.map((p, i) => (
              <PaperCard key={p.id} paper={p} rank={i + 1} />
            ))}
          </div>
          <div ref={sentinelRef} style={{ height: 1 }} />
          {papersQ.isFetchingNextPage && (
            <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>Loading more…</div>
          )}
        </>
      )}
    </div>
  );
};

export default MethodDetailView;
