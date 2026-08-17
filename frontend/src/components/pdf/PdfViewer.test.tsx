import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

let observedWidth = 800;
let resizeCallback: ResizeObserverCallback | undefined;

vi.mock("@/lib/pdf", () => ({
  assertPdfWorkerConfigured: vi.fn(),
}));

vi.mock("./PdfToolbar", () => ({
  PdfToolbar: () => <div>PDF toolbar</div>,
}));

vi.mock("react-pdf", () => ({
    Document: ({ children, onLoadSuccess }: {
      children: React.ReactNode;
      onLoadSuccess: (pdf: { numPages: number }) => void;
    }) => <div><button onClick={() => onLoadSuccess({ numPages: 1 })}>Load PDF</button>{children}</div>,
    Page: ({ width }: { width: number }) => <div data-testid="pdf-page" data-width={width} />,
}));

import { PdfViewer } from "./PdfViewer";

describe("PdfViewer resize rendering", () => {
  beforeEach(() => {
    observedWidth = 800;
    resizeCallback = undefined;
    Object.defineProperty(HTMLElement.prototype, "clientWidth", {
      configurable: true,
      get: () => observedWidth,
    });
    Object.defineProperty(window, "IntersectionObserver", {
      configurable: true,
      value: class {
        constructor(private readonly callback: IntersectionObserverCallback) {}
        observe(element: Element) {
          this.callback([{ isIntersecting: true, target: element } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
        }
        disconnect() {}
        unobserve() {}
        takeRecords() { return []; }
        root = null;
        rootMargin = "";
        thresholds = [];
      },
    });
    Object.defineProperty(window, "ResizeObserver", {
      configurable: true,
      value: class {
        constructor(callback: ResizeObserverCallback) { resizeCallback = callback; }
        observe() {}
        disconnect() {}
        unobserve() {}
      },
    });
  });

  it("scales the existing pages live and rerenders them only after divider dragging ends", async () => {
    const view = render(<PdfViewer
      url="https://arxiv.org/pdf/1706.03762"
      paperKey="1706.03762"
      paperTitle="Attention Is All You Need"
      paperHref="/paper/1706.03762"
    />);
    fireEvent.click(screen.getByRole("button", { name: "Load PDF" }));
    await waitFor(() => expect(screen.getByTestId("pdf-page")).toHaveAttribute("data-width", "790"));

    view.rerender(<PdfViewer
      url="https://arxiv.org/pdf/1706.03762"
      paperKey="1706.03762"
      paperTitle="Attention Is All You Need"
      paperHref="/paper/1706.03762"
      resizeActive
    />);
    observedWidth = 620;
    act(() => resizeCallback?.([], {} as ResizeObserver));
    expect(screen.getByTestId("pdf-page")).toHaveAttribute("data-width", "790");
    expect(screen.getByTestId("pdf-page").closest(".pdf-pages")).toHaveStyle({
      "--pdf-live-scale": String(610 / 790),
    });

    view.rerender(<PdfViewer
      url="https://arxiv.org/pdf/1706.03762"
      paperKey="1706.03762"
      paperTitle="Attention Is All You Need"
      paperHref="/paper/1706.03762"
    />);
    await waitFor(() => expect(screen.getByTestId("pdf-page")).toHaveAttribute("data-width", "610"));
    expect(screen.getByTestId("pdf-page").closest(".pdf-pages")).toHaveStyle({
      "--pdf-live-scale": "1",
    });
  });
});
