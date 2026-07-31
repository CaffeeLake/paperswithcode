import { describe, expect, it } from "vitest";

import { formatPageTitle, latexToPlainText } from "@/lib/latexPlainText";

describe("latexToPlainText", () => {
  it("replaces every occurrence of supported LaTeX commands and delimiters", () => {
    expect(latexToPlainText("$\\alpha + \\alpha$~and~\\'e")).toBe("α + α\u00a0and\u00a0é");
  });

  it("formats a browser title from the plain-text result", () => {
    expect(formatPageTitle("\\textbf{Vision} with $\\phi$"))
      .toBe("Vision with φ | Papers with Code");
  });
});
