import { describe, expect, it, vi } from "vitest";

vi.mock("react-pdf", () => ({
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" }, version: "4.8.69" },
}));

import { assertPdfWorkerConfigured, pdfjs } from "./pdf";

describe("PDF runtime", () => {
  it("uses the bundled worker matching the pinned runtime", () => {
    expect(() => assertPdfWorkerConfigured()).not.toThrow();
    expect(pdfjs.version).toBe("4.8.69");
    expect(pdfjs.GlobalWorkerOptions.workerSrc).toContain("pdf.worker.min");
    expect(pdfjs.GlobalWorkerOptions.workerSrc).not.toMatch(/^https?:/);
  });
});
