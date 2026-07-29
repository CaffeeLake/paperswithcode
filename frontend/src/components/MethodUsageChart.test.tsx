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
});
