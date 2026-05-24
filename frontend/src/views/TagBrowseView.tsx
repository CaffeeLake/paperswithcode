import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQueries, useQuery } from "@tanstack/react-query";

import { MethodChip, PaperCard } from "@/components";
import { apiClient } from "@/lib/api";
import type { Task } from "@/lib/api";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { useInfiniteTaskPapers } from "@/hooks/usePapers";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";

type OrderBy = "trending" | "date_published" | "citation_count";
const SORT_OPTIONS: Array<[OrderBy, string]> = [
  ["trending", "trending"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
];

const parseOrderBy = (value: string | null): OrderBy => {
  if (value === "trending" || value === "date_published" || value === "citation_count") {
    return value;
  }
  return "trending";
};

const SUBTASK_BENCH_PREVIEW = 3;

// Hide single-evaluation benchmarks from default task-page lists. The
// benchmark detail page still loads by slug and ignores this filter, so a
// sparse benchmark linked directly from a paper remains reachable.
const MIN_BENCH_EVAL_COUNT = 2;

const sortSubtasksForDisplay = (subtasks: Task[]) =>
  [...subtasks].sort((a, b) => {
    const aIsClassic = a.slug === "classic-language-modeling";
    const bIsClassic = b.slug === "classic-language-modeling";

    if (aIsClassic !== bIsClassic) return aIsClassic ? 1 : -1;
    return 0;
  });

const TagBrowseView: React.FC = () => {
  const { taskSlug } = useParams<{ taskSlug: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const orderBy = parseOrderBy(searchParams.get("order_by"));
  const setOrderBy = (next: OrderBy) => {
    const params = new URLSearchParams(searchParams);
    params.set("order_by", next);
    setSearchParams(params);
  };
  const [benchmarksExpanded, setBenchmarksExpanded] = useState(false);
  const [expandedSubtasks, setExpandedSubtasks] = useState<Set<string>>(() => new Set());

  const taskQ = useQuery({
    queryKey: ["task", taskSlug],
    queryFn: () => apiClient.getTask(taskSlug!),
    enabled: !!taskSlug,
    staleTime: 10 * 60 * 1000,
  });

  // Parent task chain for the breadcrumb. The endpoint returns parents ordered
  // immediate-parent first, so we reverse to render root -> leaf.
  const parentsQ = useQuery({
    queryKey: ["task-parents", taskQ.data?.id],
    queryFn: () => apiClient.getTaskParents(taskQ.data!.id),
    enabled: !!taskQ.data?.id,
    staleTime: 10 * 60 * 1000,
  });

  // Sister tasks: tasks under the same area_id. `visible_only=true` mirrors
  // the public `/tasks` taxonomy so hidden tasks (`is_visible=false`) don't
  // appear in the sidebar even when they share an area with the current task.
  const sistersQ = useQuery({
    queryKey: ["task-sisters", taskQ.data?.area_id, taskQ.data?.id],
    queryFn: () =>
      apiClient.getTasks({
        area_id: Number(taskQ.data!.area_id),
        page_size: 50,
        visible_only: true,
      }),
    enabled: !!taskQ.data?.area_id,
    staleTime: 10 * 60 * 1000,
  });

  // Subtasks (child tasks). Parent task pages render these as cards; benchmarks
  // are owned by the most-specific child task in the hierarchy. `visible_only`
  // hides children flagged `is_visible=false`.
  const subtasksQ = useQuery({
    queryKey: ["task-children", taskQ.data?.id],
    queryFn: () =>
      apiClient.getTaskChildren(taskQ.data!.id, {
        page_size: 50,
        visible_only: true,
      }),
    enabled: !!taskQ.data?.id,
    staleTime: 10 * 60 * 1000,
  });

  // Per-subtask benchmark queries depend on this list, so derive it before
  // the dataset useQueries call. Classic LM is the historical catch-all, so
  // keep it after the capability-oriented subtasks.
  const visibleSubtasks = useMemo(
    () => sortSubtasksForDisplay(subtasksQ.data?.results || []),
    [subtasksQ.data],
  );

  // Direct benchmarks for this task only. Subtask benchmarks render in their
  // own per-subtask section below, so this list intentionally excludes
  // descendants — otherwise parent tasks like `object-detection` would have
  // their own benchmarks (e.g. `COCO val2017`, `Open Images V7`) hidden the
  // moment any subtask happened to expose a benchmark too.
  const datasetsQ = useQuery({
    queryKey: ["task-datasets", taskQ.data?.id, false, MIN_BENCH_EVAL_COUNT],
    queryFn: () =>
      apiClient.getDatasets({
        task_id: Number(taskQ.data!.id),
        page_size: 100,
        ordering: "-paper_count",
        min_eval_count: MIN_BENCH_EVAL_COUNT,
      }),
    enabled: !!taskQ.data?.id,
    staleTime: 10 * 60 * 1000,
  });

  // Per-subtask top benchmarks. Fetched in parallel so each subtask section can
  // render its own preview list. page_size:20 gives the "show more" expand
  // something to reveal without an extra round trip.
  const subtaskDatasetQs = useQueries({
    queries: visibleSubtasks.map((s) => ({
      queryKey: ["task-datasets", s.id, false, MIN_BENCH_EVAL_COUNT],
      queryFn: () =>
        apiClient.getDatasets({
          task_id: Number(s.id),
          page_size: 20,
          ordering: "-paper_count",
          min_eval_count: MIN_BENCH_EVAL_COUNT,
        }),
      staleTime: 10 * 60 * 1000,
    })),
  });

  const papersQ = useInfiniteTaskPapers({
    taskId: taskQ.data?.id || "",
    page_size: 12,
    order_by: orderBy,
    order_dir: "desc",
    include_resources: true,
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
  const hasVisibleSubtaskBenchmarks = visibleSubtasks.some((_, idx) => {
    const subDatasets = subtaskDatasetQs[idx]?.data?.results || [];
    return subDatasets.length > 0;
  });
  const shouldShowBenchmarkList = datasets.length > 0;

  // Total unique benchmarks for the BENCHMARKS quickstat: direct task
  // benchmarks plus visible subtask benchmarks, deduped by dataset id so a
  // benchmark linked to both the parent and a subtask only counts once.
  const totalBenchmarkCount = (() => {
    const ids = new Set<string>();
    datasets.forEach((d) => ids.add(d.id));
    subtaskDatasetQs.forEach((q) =>
      (q.data?.results || []).forEach((d) => ids.add(d.id)),
    );
    return ids.size;
  })();

  const toggleSubtaskExpanded = (subtaskId: string) => {
    setExpandedSubtasks((prev) => {
      const next = new Set(prev);
      if (next.has(subtaskId)) next.delete(subtaskId);
      else next.add(subtaskId);
      return next;
    });
  };

  return (
    <div className="page">
      <div className="breadcrumb">
        <Link to="/">Papers</Link>
        <span className="sep">/</span>
        <Link to="/tasks">Tasks</Link>
        {[...(parentsQ.data || [])].reverse().map((parent) => (
          <React.Fragment key={parent.id}>
            <span className="sep">/</span>
            <Link to={`/tasks/${parent.slug || parent.id}`}>
              {displayTaskName(parent.name, parent.slug)}
            </Link>
          </React.Fragment>
        ))}
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
          <span className="num">{totalBenchmarkCount}</span>BENCHMARKS
        </span>
        <span>
          <span className="num">{commonMethods.length}+</span>METHODS USED
        </span>
      </div>

      <div className="task-page-grid" style={{ marginTop: 28 }}>
        <div>
          {shouldShowBenchmarkList && (
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

          {hasVisibleSubtaskBenchmarks && (
            <>
              <div
                className="task-section-head"
                style={shouldShowBenchmarkList ? { marginTop: 36 } : undefined}
              >
                <div className="task-section-eyebrow">Benchmarks by capability</div>
                <div className="task-section-title">
                  Subtasks <span className="meta">[{visibleSubtasks.length}]</span>
                </div>
              </div>
              <div className="subtask-grid">
                {visibleSubtasks.map((s, idx) => {
                  const q = subtaskDatasetQs[idx];
                  const subDatasets = q?.data?.results || [];
                  if (subDatasets.length === 0) return null;
                  const isExpanded = expandedSubtasks.has(s.id);
                  const visibleDatasets = isExpanded
                    ? subDatasets
                    : subDatasets.slice(0, SUBTASK_BENCH_PREVIEW);
                  const remaining = subDatasets.length - SUBTASK_BENCH_PREVIEW;
                  return (
                    <div key={s.id} className="subtask-section">
                      <div className="subtask-head">
                        <Link to={`/tasks/${s.slug || s.id}`} className="subtask-head-name">
                          {displayTaskName(s.name, s.slug)}
                        </Link>
                        <span className="subtask-head-meta">
                          [{subDatasets.length} benchmark{subDatasets.length === 1 ? "" : "s"}]
                        </span>
                      </div>
                      {visibleDatasets.map((d, i) => (
                        <div
                          key={d.id}
                          className="bench-row"
                          onClick={() => navigate(`/benchmark/${d.slug || d.id}`)}
                        >
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
                      {remaining > 0 && (
                        <button
                          type="button"
                          className="bench-show-more"
                          onClick={() => toggleSubtaskExpanded(s.id)}
                        >
                          {isExpanded
                            ? `− show top ${SUBTASK_BENCH_PREVIEW}`
                            : `+ show ${remaining} more benchmark${remaining === 1 ? "" : "s"}`}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
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
                  className={`sort-btn ${orderBy === k ? "active" : ""}`}
                  onClick={() => setOrderBy(k)}
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
