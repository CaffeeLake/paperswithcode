import { useState } from "react";

import type { MethodTrendPoint } from "@/lib/api";

interface MethodUsageChartProps {
  history: MethodTrendPoint[];
  methodName: string;
}

const WIDTH = 720;
const HEIGHT = 220;
const MARGIN = { top: 18, right: 12, bottom: 34, left: 44 };
const monthFormatter = new Intl.DateTimeFormat("en", {
  month: "short",
  year: "2-digit",
  timeZone: "UTC",
});

const formatMonth = (date: string) =>
  monthFormatter.format(new Date(`${date}T00:00:00Z`));

const MethodUsageChart = ({ history, methodName }: MethodUsageChartProps) => {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const maximum = Math.max(1, ...history.map((point) => point.paper_count));
  const chartWidth = WIDTH - MARGIN.left - MARGIN.right;
  const chartHeight = HEIGHT - MARGIN.top - MARGIN.bottom;
  const slotWidth = history.length ? chartWidth / history.length : chartWidth;
  const barWidth = Math.max(2, slotWidth * 0.68);
  const labelEvery = history.length > 36 ? 6 : history.length > 18 ? 3 : 2;
  const yTicks = Array.from(new Set([0, Math.ceil(maximum / 2), maximum]));
  const activePoint = activeIndex == null ? null : history[activeIndex];

  return (
    <div className="method-usage-chart-wrap">
      <svg
        className="method-usage-chart"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="group"
        aria-label={`${methodName}: papers using this method by publication month`}
      >
        <title>{methodName}: papers using this method by publication month</title>
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
          return (
            <g
              key={point.start_date}
              className={`method-usage-bar${isActive ? " is-active" : ""}`}
              tabIndex={0}
              role="img"
              aria-label={`${formatMonth(point.start_date)}: ${point.paper_count} ${
                point.paper_count === 1 ? "paper" : "papers"
              }`}
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
          index % labelEvery === 0 || index === history.length - 1 ? (
            <text
              key={point.start_date}
              className="method-usage-x-label"
              x={MARGIN.left + slotWidth * (index + 0.5)}
              y={HEIGHT - 11}
              textAnchor="middle"
            >
              {formatMonth(point.start_date)}
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
          </span>
        </div>
      )}
    </div>
  );
};

export default MethodUsageChart;
