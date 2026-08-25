import { describe, expect, it } from "vitest";

import { queryCenteredExcerpt } from "@/lib/paperSearchPresentation";

describe("queryCenteredExcerpt", () => {
  it("centers late literal matches and retains complete LaTeX delimiters", () => {
    const abstract = `${"background ".repeat(80)}$x_i = y$ hostile <img onerror=alert(1)> needle ${"tail ".repeat(80)}`;
    const excerpt = queryCenteredExcerpt(abstract, "needle");
    expect(excerpt).toContain("needle");
    expect(excerpt.startsWith("…")).toBe(true);
    expect((excerpt.match(/\$/g) || []).length % 2).toBe(0);
    expect(excerpt).toContain("<img onerror=alert(1)>");
  });

  it("keeps the beginning for semantic-only matches", () => {
    const abstract = "opening ".repeat(100);
    expect(queryCenteredExcerpt(abstract, "absent")).toBe(abstract);
  });
});
