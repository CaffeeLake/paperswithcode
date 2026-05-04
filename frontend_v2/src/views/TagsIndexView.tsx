import React, { useMemo } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";

/**
 * Browse page: render the 6 backend areas verbatim, each with their tasks
 * (PLAN.md §4.2). v2's curated MODALITY_GROUPS is dropped — we use the
 * `Area` rows from the backend directly.
 */
const TagsIndexView: React.FC = () => {
  const areasQ = useQuery({
    queryKey: ["areas-all"],
    queryFn: () => apiClient.getAreas({ page_size: 50, ordering: "name" }),
    staleTime: 10 * 60 * 1000,
  });

  // Resolve tasks per area in parallel.
  const tasksQ = useQuery({
    queryKey: ["tasks-for-areas", areasQ.data?.results.map((a) => a.id).join(",")],
    queryFn: async () => {
      const areaIds = areasQ.data?.results.map((a) => a.id) || [];
      const buckets = await Promise.all(
        areaIds.map((id) =>
          apiClient.getAreaTasks(id, { page_size: 100 }).then((res) => ({ id, results: res.results })),
        ),
      );
      return Object.fromEntries(buckets.map((b) => [b.id, b.results])) as Record<string, typeof buckets[0]["results"]>;
    },
    enabled: !!areasQ.data?.results?.length,
    staleTime: 10 * 60 * 1000,
  });

  const totalTasks = useMemo(() => {
    if (!tasksQ.data) return 0;
    return Object.values(tasksQ.data).reduce((s, arr) => s + arr.length, 0);
  }, [tasksQ.data]);

  if (areasQ.error || tasksQ.error) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Failed to load taxonomy. Please try again.</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            All <em>Domains</em>
          </h1>
          <div className="feed-subtitle">Browse research by area. Click any task to see trending work.</div>
        </div>
      </div>

      {areasQ.isLoading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i}>
              <Skeleton className="h-8 w-1/3 mb-4" />
              <div className="tag-grid">
                {Array.from({ length: 6 }).map((__, j) => (
                  <Skeleton key={j} className="h-24" />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        areasQ.data?.results?.map((area) => {
          const tasks = tasksQ.data?.[area.id] || [];
          if (tasks.length === 0) return null;
          const totalPapers = tasks.reduce((s, t) => s + (t.paper_count || 0), 0);
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
                  {area.description && (
                    <div
                      style={{
                        fontFamily: "var(--serif)",
                        fontStyle: "italic",
                        fontSize: 13,
                        color: "var(--ink-soft)",
                      }}
                    >
                      {area.description}
                    </div>
                  )}
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--ink-faint)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {tasks.length} {tasks.length === 1 ? "task" : "tasks"} · {totalPapers.toLocaleString()} papers
                </div>
              </div>
              <div className="tag-grid">
                {tasks.map((t) => {
                  const slug = t.slug || "";
                  const c = chipColors(hueFromSlug(slug));
                  return (
                    <Link key={t.id} to={`/tasks/${slug}`} className="tag-cell">
                      <div className="name">
                        <span className="dot" style={{ background: c.dot }}></span>
                        {t.name.toLowerCase()}
                      </div>
                      <div className="meta">
                        <span>{(t.paper_count ?? 0).toLocaleString()} papers</span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </section>
          );
        })
      )}

      {totalTasks > 0 && (
        <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)", marginTop: 24 }}>
          {totalTasks} tasks across {areasQ.data?.results.length} areas.
        </div>
      )}
    </div>
  );
};

export default TagsIndexView;
