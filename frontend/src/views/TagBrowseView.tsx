import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { MethodChip, PaperCard } from "@/components";
import { apiClient } from "@/lib/api";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { useInfiniteTaskPapers } from "@/hooks/usePapers";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";

type SortKey = "trending" | "new" | "cited";
const SORT_OPTIONS: Array<[SortKey, string]> = [
  ["trending", "trending"],
  ["new", "newest"],
  ["cited", "most cited"],
];

const TagBrowseView: React.FC = () => {
  const { taskSlug } = useParams<{ taskSlug: string }>();
  const navigate = useNavigate();
  const [sortBy, setSortBy] = useState<SortKey>("trending");
  const [benchmarksExpanded, setBenchmarksExpanded] = useState(false);

  const taskQ = useQuery({
    queryKey: ["task", taskSlug],
    queryFn: () => apiClient.getTask(taskSlug!),
    enabled: !!taskSlug,
    staleTime: 10 * 60 * 1000,
  });

  // Sister tasks: tasks under the same area_id.
  const sistersQ = useQuery({
    queryKey: ["task-sisters", taskQ.data?.area_id, taskQ.data?.id],
    queryFn: () =>
      apiClient.getTasks({ area_id: Number(taskQ.data!.area_id), page_size: 50 }),
    enabled: !!taskQ.data?.area_id,
    staleTime: 10 * 60 * 1000,
  });

  // Datasets associated with this task — surfaced as benchmark links.
  const datasetsQ = useQuery({
    queryKey: ["task-datasets", taskQ.data?.id],
    queryFn: () => apiClient.getDatasets({ task_id: Number(taskQ.data!.id), page_size: 100, ordering: "-paper_count" }),
    enabled: !!taskQ.data?.id,
    staleTime: 10 * 60 * 1000,
  });

  const orderBy =
    sortBy === "trending"
      ? "trending"
      : sortBy === "cited"
        ? "citation_count"
        : "date_published";
  const papersQ = useInfiniteTaskPapers({
    taskId: taskQ.data?.id || "",
    page_size: 20,
    order_by: orderBy,
    order_dir: "desc",
    include_resources: false,
    enabled: !!taskQ.data?.id,
  });

  const cards = useMemo(() => {
    const all = papersQ.data?.pages.flatMap((p) => p.results) || [];
    return all.map(transformPaperForCard);
  }, [papersQ.data]);

  // Common methods: derived from the loaded papers' methods array.
  const commonMethods = useMemo(() => {
    const counts: Record<string, { id: string; name: string; slug: string; count: number }> = {};
    papersQ.data?.pages.forEach((page) =>
      page.results.forEach((paper) =>
        (paper.methods || []).forEach((m) => {
          const key = m.slug || m.id;
          if (!counts[key]) counts[key] = { id: m.id, name: m.name, slug: m.slug || "", count: 0 };
          counts[key].count++;
        }),
      ),
    );
    return Object.values(counts).sort((a, b) => b.count - a.count).slice(0, 8);
  }, [papersQ.data]);

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "200px" });
  useEffect(() => {
    if (isIntersecting && papersQ.hasNextPage && !papersQ.isFetchingNextPage) {
      papersQ.fetchNextPage();
    }
  }, [isIntersecting, papersQ.hasNextPage, papersQ.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  if (taskQ.isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-1/2 mb-4" />
        <Skeleton className="h-6 w-1/3 mb-8" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (taskQ.error || !taskQ.data) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Task not found.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const task = taskQ.data;
  const taskName = displayTaskName(task.name, task.slug);
  const sisters = (sistersQ.data?.results || []).filter((s) => s.id !== task.id);
  const datasets = datasetsQ.data?.results || [];

  return (
    <div className="page">
      <div className="breadcrumb">
        <Link to="/">Papers</Link>
        <span className="sep">/</span>
        <Link to="/tasks">Tasks</Link>
        <span className="sep">/</span>
        <span style={{ color: "var(--accent-text)" }}>{task.name.toUpperCase()}</span>
      </div>

      <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent-text)", letterSpacing: "0.1em", marginBottom: 8 }}>
        TASK
      </div>
      <h1 className="domain-mega-title">{taskName}</h1>
      {task.description && <p className="task-explainer">{task.description}</p>}
      <div className="task-quickstats">
        <span>
          <span className="num">{(task.paper_count ?? 0).toLocaleString()}</span>PAPERS
        </span>
        <span>
          <span className="num">{datasets.length}</span>BENCHMARKS
        </span>
        <span>
          <span className="num">{commonMethods.length}+</span>METHODS USED
        </span>
      </div>

      <div className="task-page-grid" style={{ marginTop: 28 }}>
        <div>
          {datasets.length > 0 && (
            <>
              <div className="task-section-head">
                <div className="task-section-eyebrow">Leaderboards · click any</div>
                <div className="task-section-title">
                  Benchmarks <span className="meta">[{datasets.length}]</span>
                </div>
              </div>
              {(benchmarksExpanded ? datasets : datasets.slice(0, 5)).map((d, i) => (
                <div key={d.id} className="bench-row" onClick={() => navigate(`/benchmark/${d.slug || d.id}`)}>
                  <div className="bench-row-num">{String(i + 1).padStart(2, "0")}</div>
                  <div className="bench-row-main">
                    <div className="bench-row-name">{d.name}</div>
                    <div className="bench-row-sub">
                      {d.paper_count != null && (
                        <span>
                          <strong>{d.paper_count}</strong> ENTRIES
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="bench-row-arrow">→</div>
                </div>
              ))}
              {datasets.length > 5 && (
                <button
                  type="button"
                  className="bench-show-more"
                  onClick={() => setBenchmarksExpanded((v) => !v)}
                >
                  {benchmarksExpanded
                    ? "− show top 5"
                    : `+ show ${datasets.length - 5} more benchmarks`}
                </button>
              )}
            </>
          )}

          <div className="task-section-head" style={{ marginTop: 36 }}>
            <div className="task-section-eyebrow">Top trending · sort below</div>
            <div className="task-section-title">
              Papers <span className="meta">[{(task.paper_count ?? 0).toLocaleString()}]</span>
            </div>
          </div>

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
            <div className="results-count">
              {cards.length} loaded in <span>{taskName}</span>
            </div>
          </div>

          {papersQ.isLoading ? (
            <div className="paper-list">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-40 w-full" />
              ))}
            </div>
          ) : cards.length === 0 ? (
            <div className="no-results">No papers in this task yet.</div>
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

        <aside className="task-side">
          {sisters.length > 0 && (
            <div className="side-block">
              <div className="side-block-num">01/</div>
              <div className="side-block-label">Sister Tasks</div>
              {sisters.slice(0, 8).map((s) => (
                <Link key={s.id} to={`/tasks/${s.slug}`} className="side-link-row">
                  <span>{displayTaskName(s.name, s.slug)}</span>
                  {s.paper_count != null && <span className="count">{s.paper_count.toLocaleString()}</span>}
                </Link>
              ))}
            </div>
          )}

          {commonMethods.length > 0 && (
            <div className="side-block">
              <div className="side-block-num">02/</div>
              <div className="side-block-label">Common Methods</div>
              {commonMethods.map((m) => (
                <div key={m.id} className="side-method-row">
                  <MethodChip method={{ slug: m.slug, name: m.name }} />
                  <span className="num">·{m.count}</span>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
};

export default TagBrowseView;
