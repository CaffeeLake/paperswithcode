import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Flame } from "lucide-react";

import { apiClient } from "@/lib/api";
import type { Method } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { TaxonomySuggestionTile } from "@/components/TaxonomySuggestionTile";

/**
 * Methods index — methods grouped by `area_id`, sorted by paper_count desc
 * within each area (PLAN.md §4.3). v2's METHOD_CATEGORIES bucketing is
 * dropped; backend areas are the single source of grouping truth.
 */
const MethodsIndexView: React.FC = () => {
  const areasQ = useQuery({
    queryKey: ["areas-all"],
    queryFn: () => apiClient.getAreas({ page_size: 50, ordering: "name" }),
    staleTime: 10 * 60 * 1000,
  });

  // The methods table is small (~hundreds of rows); fetch the whole list in
  // one request ordered by paper_count desc, then group by area client-side.
  // Backend aggregates paper_count via a single GROUP BY, so this is one DB
  // round-trip rather than the previous N+1 plus page-walking waterfall.
  const methodsQ = useQuery({
    queryKey: ["methods-all"],
    queryFn: async () => {
      const res = await apiClient.getMethods({
        page: 1,
        page_size: 500,
        ordering: "-paper_count",
        include_trends: true,
      });
      return res.results;
    },
    staleTime: 10 * 60 * 1000,
  });

  const grouped = useMemo(() => {
    if (!methodsQ.data || !areasQ.data) return null;
    const byArea: Record<string, Method[]> = {};
    methodsQ.data.forEach((m) => {
      const key = m.area_id ?? "_unassigned";
      (byArea[key] ||= []).push(m);
    });
    Object.values(byArea).forEach((arr) => arr.sort((a, b) => (b.paper_count || 0) - (a.paper_count || 0)));
    return byArea;
  }, [methodsQ.data, areasQ.data]);

  const trendingMethodIds = useMemo(() => {
    const ranked = (methodsQ.data || [])
      .filter((method) => (method.trend_score || 0) > 0)
      .sort((a, b) => (b.trend_score || 0) - (a.trend_score || 0));
    const topCount = Math.ceil(ranked.length * 0.25);
    return new Set(ranked.slice(0, topCount).map((method) => method.id));
  }, [methodsQ.data]);

  if (areasQ.error || methodsQ.error) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Failed to load methods.</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            Methods <em>library</em>
          </h1>
          <div className="feed-subtitle">
            Common techniques used across AI research. Trend scores show papers
            using each method per 30 days, measured over the latest 90 days;
            the flame marks the top quartile.
          </div>
        </div>
      </div>

      {(areasQ.isLoading || methodsQ.isLoading) ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i}>
              <Skeleton className="h-8 w-1/3 mb-4" />
              <div className="tag-grid">
                {Array.from({ length: 8 }).map((__, j) => (
                  <Skeleton key={j} className="h-20" />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        areasQ.data?.results?.map((area) => {
          const methods = grouped?.[area.id] || [];
          if (methods.length === 0) return null;
          const totalPapers = methods.reduce((s, m) => s + (m.paper_count || 0), 0);
          return (
            <section key={area.id} style={{ marginBottom: 48 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  gap: 24,
                  paddingBottom: 12,
                  borderBottom: "1px solid var(--hairline-strong)",
                }}
              >
                <div>
                  <h2
                    style={{
                      fontFamily: "var(--serif)",
                      fontSize: 26,
                      fontWeight: 500,
                      letterSpacing: "-0.02em",
                      marginBottom: 4,
                    }}
                  >
                    {area.name}
                  </h2>
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--ink-faint)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {methods.length} methods · {totalPapers.toLocaleString()} papers
                </div>
              </div>
              <div className="tag-grid">
                {methods.map((m) => (
                  <Link key={m.id} to={`/methods/${m.slug || m.id}`} className="tag-cell">
                    <div className="name" style={{ fontFamily: "var(--mono)", fontSize: 15 }}>
                      {m.name}
                      {trendingMethodIds.has(m.id) && (
                        <Flame
                          className="method-trending-icon"
                          size={15}
                          aria-label="Top quartile by recent method usage"
                        />
                      )}
                    </div>
                    <div className="meta">
                      <span>{(m.paper_count ?? 0).toLocaleString()} papers</span>
                      {(m.trend_score ?? 0) > 0 && (
                        <>
                          <span>·</span>
                          <span className="method-trend-score">
                            {(m.trend_score ?? 0).toFixed(1)}/mo
                          </span>
                        </>
                      )}
                      {m.introduced_year != null && (
                        <>
                          <span>·</span>
                          <span>{m.introduced_year}</span>
                        </>
                      )}
                    </div>
                  </Link>
                ))}
                <TaxonomySuggestionTile kind="method" />
              </div>
            </section>
          );
        })
      )}
    </div>
  );
};

export default MethodsIndexView;
