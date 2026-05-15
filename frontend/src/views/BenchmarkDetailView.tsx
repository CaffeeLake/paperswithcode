import React, { useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";
import type { Evaluation, MetricDirections, Task } from "@/lib/api";
import { formatMetricValue } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import LatexTitle from "@/components/LatexTitle";

interface SotaPoint {
  value: number;
  dateLabel: string;
  modelName: string;
  paperTitle: string;
  paperRouteId: string | null;
}

interface BenchmarkChartProps {
  points: SotaPoint[];
  metric: string;
}

// Always plots raw values: larger values appear higher on the Y-axis, smaller
// values appear lower, regardless of whether the metric is higher- or
// lower-is-better. Direction only affects which points `computeSeries` chooses
// as the running best, not the visual orientation of the chart.
const BenchmarkChart: React.FC<BenchmarkChartProps> = ({ points: dataPoints, metric }) => {
  const navigate = useNavigate();
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const W = 880;
  const H = 320;
  const padL = 60;
  const padR = 30;
  const padT = 24;
  const padB = 50;
  const values = dataPoints.map((d) => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const step = innerW / Math.max(1, dataPoints.length - 1);
  const points = dataPoints.map((dp, i) => {
    const x = padL + i * step;
    const norm = (dp.value - min) / range;
    const y = padT + innerH * (1 - norm);
    return { x, y, data: dp };
  });
  let path = `M${points[0].x},${points[0].y}`;
  for (let i = 1; i < points.length; i++) {
    const p0 = points[i - 1];
    const p1 = points[i];
    const cx = (p0.x + p1.x) / 2;
    path += ` C${cx},${p0.y} ${cx},${p1.y} ${p1.x},${p1.y}`;
  }
  const tickCount = 5;

  const clearHover = (i: number) => setHoverIdx((cur) => (cur === i ? null : cur));
  const handleClick = (routeId: string | null) => {
    if (routeId) navigate(`/paper/${routeId}`);
  };

  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
      <text
        x={padL - 38}
        y={padT + innerH / 2}
        fontSize="11"
        fontFamily="var(--mono)"
        fill="var(--ink-faint)"
        textAnchor="middle"
        transform={`rotate(-90 ${padL - 38} ${padT + innerH / 2})`}
      >
        {metric}
      </text>
      {Array.from({ length: tickCount }).map((_, i) => {
        const norm = i / (tickCount - 1);
        const y = padT + innerH * (1 - norm);
        const dataAtNorm = min + range * norm;
        return (
          <g key={i}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="var(--hairline)" strokeWidth="1" />
            <text x={padL - 10} y={y + 4} fontSize="11" fontFamily="var(--mono)" fill="var(--ink-faint)" textAnchor="end">
              {formatMetricValue(dataAtNorm)}
            </text>
          </g>
        );
      })}
      {points.map((p, i) => (
        <text key={i} x={p.x} y={H - padB + 18} fontSize="11" fontFamily="var(--mono)" fill="var(--ink-soft)" textAnchor="middle">
          {p.data.dateLabel}
        </text>
      ))}
      <path d={path} stroke="var(--accent)" strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
      {points.map((p, i) => {
        const isHover = hoverIdx === i;
        const label = p.data.modelName || p.data.paperTitle || "Unknown model";
        const ariaLabel = `${label}: ${formatMetricValue(p.data.value)} on ${p.data.dateLabel}`;
        const clickable = !!p.data.paperRouteId;
        return (
          <g key={i}>
            <circle
              cx={p.x}
              cy={p.y}
              r={isHover ? 6 : 4.5}
              fill={isHover ? "var(--accent)" : "var(--bg-elevated)"}
              stroke="var(--accent)"
              strokeWidth="2"
              style={{ transition: "r 0.12s ease, fill 0.12s ease" }}
            />
            <circle
              cx={p.x}
              cy={p.y}
              r="14"
              fill="transparent"
              style={{ cursor: clickable ? "pointer" : "default", outline: "none" }}
              tabIndex={0}
              role={clickable ? "link" : "img"}
              aria-label={ariaLabel}
              onMouseEnter={() => setHoverIdx(i)}
              onMouseLeave={() => clearHover(i)}
              onFocus={() => setHoverIdx(i)}
              onBlur={() => clearHover(i)}
              onClick={() => handleClick(p.data.paperRouteId)}
              onKeyDown={(e) => {
                if (clickable && (e.key === "Enter" || e.key === " ")) {
                  e.preventDefault();
                  handleClick(p.data.paperRouteId);
                }
              }}
            >
              <title>{ariaLabel}</title>
            </circle>
          </g>
        );
      })}
      {hoverIdx !== null && (() => {
        const p = points[hoverIdx];
        const rawLabel = p.data.modelName || p.data.paperTitle || "Unknown model";
        const label = rawLabel.length > 40 ? rawLabel.slice(0, 39) + "…" : rawLabel;
        const meta = `${formatMetricValue(p.data.value)} · ${p.data.dateLabel}`;
        const charW = 6.6;
        const tooltipW = Math.max(140, Math.min(320, Math.max(label.length, meta.length) * charW + 24));
        const tooltipH = 46;
        let tx = p.x - tooltipW / 2;
        if (tx < padL) tx = padL;
        if (tx + tooltipW > W - padR) tx = W - padR - tooltipW;
        const aboveDot = p.y - tooltipH - 14 >= padT;
        const ty = aboveDot ? p.y - tooltipH - 12 : p.y + 12;
        return (
          <g pointerEvents="none">
            <rect
              x={tx}
              y={ty}
              width={tooltipW}
              height={tooltipH}
              rx="6"
              ry="6"
              fill="var(--bg-elevated)"
              stroke="var(--hairline-strong)"
              strokeWidth="1"
              style={{ filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.08))" }}
            />
            <text
              x={tx + 12}
              y={ty + 19}
              fontSize="12"
              fontFamily="var(--sans)"
              fill="var(--ink)"
              fontWeight={500}
            >
              {label}
            </text>
            <text
              x={tx + 12}
              y={ty + 36}
              fontSize="11"
              fontFamily="var(--mono)"
              fill="var(--ink-soft)"
            >
              {meta}
            </text>
          </g>
        );
      })()}
    </svg>
  );
};

/**
 * Compute the SOTA progression (running best) from evaluations sorted by
 * paper.published. Mirrors the v1 Benchmark.tsx logic.
 */
function computeSeries(
  evals: Evaluation[],
  bestMetric: string,
  arrow: "↑" | "↓",
): { points: SotaPoint[]; sota: number; sotaModel: string } {
  if (evals.length === 0) return { points: [], sota: 0, sotaModel: "" };

  // Sort by published date ascending; require numeric values for the metric.
  const items = evals
    .map((e) => {
      const raw = e.metrics?.[bestMetric];
      const n = typeof raw === "string" ? parseFloat(raw) : (raw as number);
      const date = e.paper_published_date || "";
      return { eval: e, value: n, date };
    })
    .filter((x) => Number.isFinite(x.value) && x.date)
    .sort((a, b) => a.date.localeCompare(b.date));

  const points: SotaPoint[] = [];
  let runningBest: number | null = null;
  for (const it of items) {
    const better = runningBest == null
      ? true
      : arrow === "↓"
        ? it.value < runningBest
        : it.value > runningBest;
    if (better) {
      runningBest = it.value;
      points.push({
        value: it.value,
        dateLabel: it.date.slice(0, 7),
        modelName: it.eval.model_name || "",
        paperTitle: it.eval.paper_title || "",
        paperRouteId: it.eval.paper_arxiv_id || it.eval.paper_id || null,
      });
    }
  }
  // The leaderboard's top row drives the headline SOTA.
  const top = [...evals].sort((a, b) => (a.best_rank ?? 9999) - (b.best_rank ?? 9999))[0];
  const sotaRaw = top?.metrics?.[bestMetric];
  const sota = typeof sotaRaw === "string" ? parseFloat(sotaRaw) : ((sotaRaw as number) ?? 0);
  const sotaModel = top?.model_name || top?.paper_title || "";

  return { points, sota, sotaModel };
}

const BenchmarkDetailView: React.FC = () => {
  const { datasetSlug } = useParams<{ datasetSlug: string }>();
  const [searchParams] = useSearchParams();
  // The "See all" button on PaperDetailView's evaluation card links here
  // with `?task=<slug>` so we can keep that task as the breadcrumb context
  // for benchmarks linked to multiple tasks (e.g. COCO val2017).
  const taskSlugFromQuery = searchParams.get("task") || undefined;
  const [bestMetric, setBestMetric] = useState<string | undefined>(undefined);

  // Fetching the dataset with `include_paper=true` collapses the previous
  // dataset → paper waterfall into a single round trip.  See PLAN.md §5.
  const datasetQ = useQuery({
    queryKey: ["dataset", datasetSlug, "with-paper"],
    queryFn: () => apiClient.getDatasetBySlug(datasetSlug!, { include_paper: true }),
    enabled: !!datasetSlug,
    staleTime: 10 * 60 * 1000,
  });

  const evalsQ = useQuery({
    queryKey: ["dataset-evals", datasetQ.data?.id, bestMetric],
    queryFn: () => apiClient.getEvaluationsByDataset(datasetQ.data!.id, bestMetric),
    enabled: !!datasetQ.data?.id,
    staleTime: 5 * 60 * 1000,
  });

  const datasetTasksQ = useQuery<Task[]>({
    queryKey: ["dataset-tasks", datasetQ.data?.id],
    queryFn: () => apiClient.getDatasetTasks(datasetQ.data!.id),
    enabled: !!datasetQ.data?.id,
    staleTime: 10 * 60 * 1000,
  });

  const directionsQ = useQuery<MetricDirections>({
    queryKey: ["metric-directions"],
    queryFn: () => apiClient.getMetricDirections(),
    staleTime: 60 * 60 * 1000,
  });

  const allMetrics = useMemo(() => {
    const set = new Set<string>();
    (evalsQ.data || []).forEach((e) => {
      if (e.best_metric) set.add(e.best_metric);
      Object.keys(e.metrics || {}).forEach((k) => set.add(k));
    });
    return Array.from(set);
  }, [evalsQ.data]);

  const activeMetric = bestMetric || evalsQ.data?.[0]?.best_metric || allMetrics[0] || "";
  const direction = directionsQ.data?.directions?.[activeMetric] || "higher_is_better";
  const arrow: "↑" | "↓" = direction === "lower_is_better" ? "↓" : "↑";

  const { points: chartPoints, sota, sotaModel } = useMemo(
    () => computeSeries(evalsQ.data || [], activeMetric, arrow),
    [evalsQ.data, activeMetric, arrow],
  );

  // For breadcrumb context: prefer the task carried in `?task=<slug>` (set
  // by PaperDetailView's "See all" link). Fall back to the alphabetically
  // first linked task — the API already orders by Task.name.
  const primaryTask = useMemo(() => {
    const tasks = datasetTasksQ.data || [];
    if (tasks.length === 0) return null;
    if (taskSlugFromQuery) {
      const match = tasks.find((t) => t.slug === taskSlugFromQuery);
      if (match) return match;
    }
    return tasks[0];
  }, [datasetTasksQ.data, taskSlugFromQuery]);

  if (datasetQ.isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-1/2 mb-6" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (datasetQ.error || !datasetQ.data) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Benchmark not found.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const dataset = datasetQ.data;
  const sortedRows = (evalsQ.data || []).slice().sort((a, b) => (a.best_rank ?? 9999) - (b.best_rank ?? 9999));
  const showHarness = Boolean(dataset.supports_harness);

  const introducingPaper = dataset.introducing_paper ?? undefined;
  const fallbackArxivIdFromUrl = (() => {
    if (!dataset.paper_url) return null;
    const match = dataset.paper_url.match(/arxiv\.org\/(?:abs|pdf)\/([\w.-]+)/i);
    if (match && match[1]) return match[1].replace(/\.pdf$/i, "");
    const localMatch = dataset.paper_url.match(/\/(?:paper|abs|pdf)\/([\w.-]+)/i);
    if (localMatch && localMatch[1]) return localMatch[1].replace(/\.pdf$/i, "");
    return null;
  })();
  const sourcePaperArxivId = introducingPaper?.arxiv_id || fallbackArxivIdFromUrl;
  const localSourcePaperArxivId = sourcePaperArxivId;
  const sourcePaperTitle =
    introducingPaper?.title || dataset.introducing_paper_title || null;
  const sourcePaperYear = introducingPaper?.published?.slice(0, 4) || dataset.introduced_year || null;
  const hasSource = !!sourcePaperArxivId || !!dataset.paper_url || !!sourcePaperTitle;

  return (
    <div className="page">
      <div className="bm-page">
        <div className="breadcrumb">
          <Link to="/tasks">Tasks</Link>
          {primaryTask && (
            <>
              <span className="sep">/</span>
              <Link to={`/tasks/${primaryTask.slug || primaryTask.id}`}>
                {primaryTask.name}
              </Link>
            </>
          )}
          <span className="sep">/</span>
          <span style={{ color: "var(--accent-text)" }}>{dataset.name}</span>
        </div>

        <h1 className="bm-title">{dataset.name}</h1>
        <div className="bm-subtitle">
          {activeMetric && (
            <>
              <span className="metric-tag">{activeMetric}</span>
              <span style={{ color: "var(--hairline-strong)", margin: "0 8px" }}>·</span>
            </>
          )}
          {sotaModel ? (
            <span>
              Best: <span className="best-name">{formatMetricValue(sota)}</span> by <span className="best-name" style={{ fontStyle: "normal" }}>{sotaModel}</span>
            </span>
          ) : (
            <span>{sortedRows.length} evaluations</span>
          )}
        </div>

        {dataset.description && (
          <p style={{ fontFamily: "var(--serif)", color: "var(--ink-soft)", maxWidth: 760, marginBottom: 16 }}>
            {dataset.description}
          </p>
        )}

        {hasSource && (
          <div className="method-source" style={{ marginTop: 0, marginBottom: 18 }}>
            <span className="method-source-label">Source</span>
            {localSourcePaperArxivId ? (
              <Link
                to={`/paper/${localSourcePaperArxivId}`}
                target="_blank"
                rel="noopener noreferrer"
                className="method-source-link"
              >
                <span className="method-source-title">
                  {sourcePaperTitle ? (
                    <LatexTitle title={sourcePaperTitle} />
                  ) : (
                    `arXiv:${localSourcePaperArxivId}`
                  )}
                </span>
                {sourcePaperYear && (
                  <span className="method-source-meta">{sourcePaperYear}</span>
                )}
              </Link>
            ) : dataset.paper_url ? (
              <a
                href={dataset.paper_url}
                target="_blank"
                rel="noopener noreferrer"
                className="method-source-link"
              >
                <span className="method-source-title">
                  {sourcePaperTitle ? (
                    <LatexTitle title={sourcePaperTitle} />
                  ) : sourcePaperArxivId ? (
                    `arXiv:${sourcePaperArxivId}`
                  ) : (
                    dataset.paper_url
                  )}
                </span>
                {sourcePaperYear && (
                  <span className="method-source-meta">{sourcePaperYear}</span>
                )}
              </a>
            ) : (
              <div className="method-source-link is-static">
                <span className="method-source-title">
                  {sourcePaperTitle ? <LatexTitle title={sourcePaperTitle} /> : null}
                </span>
                {sourcePaperYear && (
                  <span className="method-source-meta">{sourcePaperYear}</span>
                )}
              </div>
            )}
          </div>
        )}

        {allMetrics.length > 1 && (
          <div className="bm-actions">
            <span style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)", marginRight: 8 }}>
              METRIC
            </span>
            {allMetrics.map((m) => (
              <button
                key={m}
                className={`bm-action-btn ${m === activeMetric ? "is-active" : ""}`}
                onClick={() => setBestMetric(m)}
              >
                {m}
              </button>
            ))}
          </div>
        )}

        {chartPoints.length >= 2 && (
          <div className="bm-card">
            <div className="bm-card-head">
              <div className="bm-card-title">SOTA progression</div>
            </div>
            <div className="bm-chart-wrap">
              <BenchmarkChart points={chartPoints} metric={activeMetric} />
            </div>
            <div className="bm-chart-foot">
              <span className="legend-dot"></span>
              Best result over time · hover a point to see the model · click to open the paper
            </div>
          </div>
        )}

        <div className="bm-card">
          <div className="bm-card-head">
            <div className="bm-card-title">Leaderboard</div>
          </div>
          {evalsQ.isLoading ? (
            <div style={{ padding: 16 }}>
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full mb-2" />
              ))}
            </div>
          ) : sortedRows.length === 0 ? (
            <div className="no-results">No evaluations submitted yet.</div>
          ) : (
            <table className="bm-table">
              <thead>
                <tr>
                  <th className="col-rank">Rank</th>
                  <th className="col-model">Model</th>
                  {showHarness && <th className="col-harness">Harness</th>}
                  <th className="col-value">{activeMetric} {arrow}</th>
                  <th className="col-paper">Paper</th>
                  <th className="col-year">Year</th>
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((e, i) => {
                  const paperRouteId = e.paper_arxiv_id || e.paper_id;
                  const paperLabel =
                    e.paper_title || (e.paper_arxiv_id ? `arXiv:${e.paper_arxiv_id}` : null);
                  return (
                    <tr key={e.id}>
                      <td className="col-rank">{e.best_rank ?? i + 1}</td>
                      <td className="col-model">{e.model_name || "—"}</td>
                      {showHarness && (
                        <td className="col-harness">{e.harness || "—"}</td>
                      )}
                      <td className={`col-value ${i === 0 ? "is-best" : ""}`}>
                        {formatMetricValue(e.metrics?.[activeMetric])}
                      </td>
                      <td className="col-paper">
                        {paperRouteId ? (
                          <Link to={`/paper/${paperRouteId}`}>{paperLabel || "—"}</Link>
                        ) : (
                          paperLabel || "—"
                        )}
                      </td>
                      <td className="col-year">{e.paper_published_date?.slice(0, 4) || "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};

export default BenchmarkDetailView;
