import React, { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";
import type { Evaluation, MetricDirections } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface BenchmarkChartProps {
  series: number[];
  dates: string[];
  metric: string;
  arrow: "↑" | "↓";
}

const BenchmarkChart: React.FC<BenchmarkChartProps> = ({ series, dates, metric, arrow }) => {
  const W = 880;
  const H = 320;
  const padL = 60;
  const padR = 30;
  const padT = 24;
  const padB = 50;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = max - min || 1;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const step = innerW / Math.max(1, series.length - 1);
  const points = series.map((v, i) => {
    const x = padL + i * step;
    const norm = arrow === "↓" ? (max - v) / range : (v - min) / range;
    const y = padT + innerH * (1 - norm);
    return [x, y, v] as [number, number, number];
  });
  let path = `M${points[0][0]},${points[0][1]}`;
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    const cx = (x0 + x1) / 2;
    path += ` C${cx},${y0} ${cx},${y1} ${x1},${y1}`;
  }
  const tickCount = 5;
  const fmt = (v: number): string => {
    if (Math.abs(v) >= 100) return v.toFixed(0);
    if (Math.abs(v) >= 10) return v.toFixed(1);
    if (Math.abs(v) >= 1) return v.toFixed(2);
    return v.toFixed(3);
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
        const dataAtNorm = arrow === "↓" ? max - range * norm : min + range * norm;
        return (
          <g key={i}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="var(--hairline)" strokeWidth="1" />
            <text x={padL - 10} y={y + 4} fontSize="11" fontFamily="var(--mono)" fill="var(--ink-faint)" textAnchor="end">
              {fmt(dataAtNorm)}
            </text>
          </g>
        );
      })}
      {points.map((p, i) => (
        <text key={i} x={p[0]} y={H - padB + 18} fontSize="11" fontFamily="var(--mono)" fill="var(--ink-soft)" textAnchor="middle">
          {dates[i] || ""}
        </text>
      ))}
      <path d={path} stroke="var(--accent)" strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
      {points.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r="4.5" fill="var(--bg-elevated)" stroke="var(--accent)" strokeWidth="2" />
      ))}
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
): { series: number[]; dates: string[]; sota: number; sotaModel: string } {
  if (evals.length === 0) return { series: [], dates: [], sota: 0, sotaModel: "" };

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

  const series: number[] = [];
  const dates: string[] = [];
  let runningBest: number | null = null;
  for (const it of items) {
    const better = runningBest == null
      ? true
      : arrow === "↓"
        ? it.value < runningBest
        : it.value > runningBest;
    if (better) {
      runningBest = it.value;
      series.push(it.value);
      dates.push(it.date.slice(0, 7));
    }
  }
  // The leaderboard's top row drives the headline SOTA.
  const top = [...evals].sort((a, b) => (a.best_rank ?? 9999) - (b.best_rank ?? 9999))[0];
  const sotaRaw = top?.metrics?.[bestMetric];
  const sota = typeof sotaRaw === "string" ? parseFloat(sotaRaw) : ((sotaRaw as number) ?? 0);
  const sotaModel = top?.model_name || top?.paper_title || "";

  return { series, dates, sota, sotaModel };
}

const BenchmarkDetailView: React.FC = () => {
  const { datasetSlug } = useParams<{ datasetSlug: string }>();
  const [bestMetric, setBestMetric] = useState<string | undefined>(undefined);

  const datasetQ = useQuery({
    queryKey: ["dataset", datasetSlug],
    queryFn: () => apiClient.getDatasetBySlug(datasetSlug!),
    enabled: !!datasetSlug,
    staleTime: 10 * 60 * 1000,
  });

  const evalsQ = useQuery({
    queryKey: ["dataset-evals", datasetQ.data?.id, bestMetric],
    queryFn: () => apiClient.getEvaluationsByDataset(datasetQ.data!.id, bestMetric),
    enabled: !!datasetQ.data?.id,
    staleTime: 5 * 60 * 1000,
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

  const { series, dates, sota, sotaModel } = useMemo(
    () => computeSeries(evalsQ.data || [], activeMetric, arrow),
    [evalsQ.data, activeMetric, arrow],
  );

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

  return (
    <div className="page">
      <div className="bm-page">
        <div className="breadcrumb">
          <Link to="/tasks">Tasks</Link>
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
              Best: <span className="best-name">{sota}</span> by <span className="best-name" style={{ fontStyle: "normal" }}>{sotaModel}</span>
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

        {series.length >= 2 && (
          <div className="bm-card">
            <div className="bm-card-head">
              <div className="bm-card-title">SOTA progression</div>
            </div>
            <div className="bm-chart-wrap">
              <BenchmarkChart series={series} dates={dates} metric={activeMetric} arrow={arrow} />
            </div>
            <div className="bm-chart-foot">
              <span className="legend-dot"></span>
              Best result over time · running best by paper publish date
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
                  <th className="col-value">{activeMetric} {arrow}</th>
                  <th className="col-paper">Paper</th>
                  <th className="col-year">Year</th>
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((e, i) => (
                  <tr key={e.id}>
                    <td className="col-rank">{e.best_rank ?? i + 1}</td>
                    <td className="col-model">{e.model_name || "—"}</td>
                    <td className={`col-value ${i === 0 ? "is-best" : ""}`}>
                      {e.metrics?.[activeMetric] ?? "—"}
                    </td>
                    <td className="col-paper">
                      {e.paper_arxiv_id ? (
                        <Link to={`/paper/${e.paper_arxiv_id}`}>{e.paper_title || `arXiv:${e.paper_arxiv_id}`}</Link>
                      ) : (
                        e.paper_title || "—"
                      )}
                    </td>
                    <td className="col-year">{e.paper_published_date?.slice(0, 4) || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
};

export default BenchmarkDetailView;
