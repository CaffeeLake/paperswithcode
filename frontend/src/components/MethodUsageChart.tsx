import { useState } from "react";

import type { MethodTrendPoint } from "@/lib/api/catalog.types";

interface MethodUsageChartProps {
  history: MethodTrendPoint[];
  methodName: string;
}

const WIDTH = 720;
const HEIGHT = 138;
const MARGIN = { top: 8, right: 10, bottom: 25, left: 36 };
const MIN_X_LABEL_SPACING = 56;
const monthFormatter = new Intl.DateTimeFormat("en", {
  month: "short",
  year: "2-digit",
  timeZone: "UTC",
});
const yearFormatter = new Intl.DateTimeFormat("en", {
  year: "numeric",
  timeZone: "UTC",
});

const formatMonth = (date: string) =>
  monthFormatter.format(new Date(`${date}T00:00:00Z`));

const selectXLabelIndices = (historyLength: number, slotWidth: number) => {
  if (historyLength === 0) return new Set<number>();

  const representativeStep =
    historyLength > 48 ? 12 : historyLength > 36 ? 6 : historyLength > 18 ? 3 : 2;
  const minimumStep = Math.max(1, Math.ceil(MIN_X_LABEL_SPACING / slotWidth));
  const step = Math.max(representativeStep, minimumStep);
  const finalIndex = historyLength - 1;
  const indices = new Set<number>([0, finalIndex]);

  for (let index = step; index < finalIndex; index += step) {
    if ((finalIndex - index) * slotWidth >= MIN_X_LABEL_SPACING) {
      indices.add(index);
    }
  }

  return indices;
};

const coverageDescription = (point: MethodTrendPoint) => {
  if (
    point.coverage_status === undefined ||
    ["complete", "not_applicable"].includes(point.coverage_status)
  ) {
    return null;
  }
  const progress =
    point.processed_paper_count !== undefined &&
    point.eligible_paper_count !== undefined
      ? `; ${point.processed_paper_count.toLocaleString()} of ${point.eligible_paper_count.toLocaleString()} eligible papers processed`
      : "";
  return `Historical tagging ${
    point.coverage_status === "failed" ? "needs retry" : "in progress"
  }${progress}`;
};

const MethodUsageChart = ({ history, methodName }: MethodUsageChartProps) => {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const maximum = Math.max(1, ...history.map((point) => point.paper_count));
  const chartWidth = WIDTH - MARGIN.left - MARGIN.right;
  const chartHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const slotWidth = history.length ? chartWidth / history.length : chartWidth;
  const barWidth = Math.max(2, slotWidth * 0.68);
  const xLabelIndices = selectXLabelIndices(history.length, slotWidth);
  const yTicks = Array.from(new Set([0, Math.ceil(maximum / 2), maximum]));
  const activePoint = activeIndex == null ? null : history[activeIndex];
  const activeCoverage = activePoint ? coverageDescription(activePoint) : null;

  return (
    <div className="method-usage-chart-wrap">
      <svg
        className="method-usage-chart"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="group"
        aria-label={`${methodName}: papers mentioning this method by publication month`}
      >
        <title>{methodName}: papers mentioning this method by publication month</title>
        {yTicks.map((tick) => {
          const y = MARGIN.top + chartHeight - (tick / maximum) * chartHeight;
          return (
            <g key={tick}>
              <line
                className="method-usage-gridline"
                x1={MARGIN.left}
                x2={WIDTH - MARGIN.right}
                y1={y}
                y2={y}
              />
              <text
                className="method-usage-y-label"
                x={MARGIN.left - 8}
                y={y + 3}
                textAnchor="end"
              >
                {tick}
              </text>
            </g>
          );
        })}
        {history.map((point, index) => {
          const height = (point.paper_count / maximum) * chartHeight;
          const displayHeight = point.paper_count > 0 ? Math.max(1, height) : 0;
          const x = MARGIN.left + slotWidth * index + (slotWidth - barWidth) / 2;
          const y = MARGIN.top + chartHeight - displayHeight;
          const isActive = activeIndex === index;
          const isCurrent = index === history.length - 1;
          const coverage = coverageDescription(point);
          return (
            <g
              key={point.start_date}
              className={`method-usage-bar${isActive ? " is-active" : ""}${
                isCurrent ? " is-current" : ""
              }`}
              tabIndex={0}
              role="img"
              aria-label={`${formatMonth(point.start_date)}: ${point.paper_count} ${
                point.paper_count === 1 ? "paper" : "papers"
              }${coverage ? `. ${coverage}` : ""}`}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseLeave={() => setActiveIndex(null)}
              onFocus={() => setActiveIndex(index)}
              onBlur={() => setActiveIndex(null)}
            >
              <rect
                className="method-usage-bar-hit"
                x={MARGIN.left + slotWidth * index}
                y={MARGIN.top}
                width={slotWidth}
                height={chartHeight}
              />
              <rect
                className="method-usage-bar-mark"
                x={x}
                y={y}
                width={barWidth}
                height={displayHeight}
                rx="1.5"
              />
            </g>
          );
        })}
        {history.map((point, index) =>
          xLabelIndices.has(index) ? (
            <text
              key={point.start_date}
              className="method-usage-x-label"
              x={MARGIN.left + slotWidth * (index + 0.5)}
              y={HEIGHT - 11}
              textAnchor="middle"
            >
              {history.length > 48
                ? yearFormatter.format(new Date(`${point.start_date}T00:00:00Z`))
                : formatMonth(point.start_date)}
            </text>
          ) : null,
        )}
      </svg>
      {activePoint && (
        <div className="method-usage-tooltip" role="status">
          <strong>{formatMonth(activePoint.start_date)}</strong>
          <span>
            {activePoint.paper_count}{" "}
            {activePoint.paper_count === 1 ? "paper" : "papers"}
            {activeIndex === history.length - 1 ? " · month to date" : ""}
          </span>
          <span>
            {(activePoint.catalog_share ?? 0).toFixed(2)}% of{" "}
            {(activePoint.catalog_paper_count ?? 0).toLocaleString()} catalog papers
          </span>
          {activeCoverage && <span>{activeCoverage}</span>}
        </div>
      )}
    </div>
  );
};

export default MethodUsageChart;
