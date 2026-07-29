import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MethodUsageChart from "@/components/MethodUsageChart";
import type { MethodTrendPoint } from "@/lib/api";

const history: MethodTrendPoint[] = [
  {
    start_date: "2026-01-01",
    end_date: "2026-01-31",
    paper_count: 3,
    eligible_paper_count: 10,
    processed_paper_count: 4,
    coverage_ratio: 0.4,
    coverage_status: "running",
    catalog_paper_count: 100,
    catalog_share: 3,
  },
  {
    start_date: "2026-02-01",
    end_date: "2026-02-28",
    paper_count: 5,
    eligible_paper_count: 12,
    processed_paper_count: 12,
    coverage_ratio: 1,
    coverage_status: "complete",
    catalog_paper_count: 120,
    catalog_share: 4.17,
  },
];

const monthlyHistory = (length: number): MethodTrendPoint[] =>
  Array.from({ length }, (_, index) => {
    const start = new Date(Date.UTC(2024, 11 + index, 1));
    const end = new Date(Date.UTC(2024, 12 + index, 0));
    return {
      start_date: start.toISOString().slice(0, 10),
      end_date: end.toISOString().slice(0, 10),
      paper_count: index + 1,
      catalog_paper_count: 100,
      catalog_share: index + 1,
    };
  });

describe("MethodUsageChart", () => {
  it("keeps partial coverage bars filled and exposes progress as metadata", () => {
    const { container } = render(
      <MethodUsageChart history={history} methodName="CLIP" />,
    );
    const partialBar = screen.getByRole("img", {
      name: /Jan 26: 3 papers\. Historical tagging in progress; 4 of 10 eligible papers processed/,
    });

    expect(partialBar).toHaveClass("method-usage-bar");
    expect(partialBar).not.toHaveClass("is-partial");
    expect(container.querySelectorAll(".method-usage-bar-mark")).toHaveLength(2);

    fireEvent.mouseEnter(partialBar);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Historical tagging in progress; 4 of 10 eligible papers processed",
    );
  });

  it("keeps the final x-axis label clear of nearby representative ticks", () => {
    const { container } = render(
      <MethodUsageChart history={monthlyHistory(20)} methodName="CLIP" />,
    );
    const labels = Array.from(
      container.querySelectorAll<SVGTextElement>(".method-usage-x-label"),
    );
    const positions = labels.map((label) => Number(label.getAttribute("x")));

    expect(labels[0]).toHaveTextContent("Dec 24");
    expect(labels.at(-1)).toHaveTextContent("Jul 26");
    expect(labels.map((label) => label.textContent)).not.toContain("Jun 26");
    expect(
      positions.every(
        (position, index) =>
          index === 0 || position - positions[index - 1] >= 56,
      ),
    ).toBe(true);
  });
});
