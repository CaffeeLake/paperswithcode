import { describe, expect, it } from "vitest";

import { withCenteredTitle, withDecodedLineBreaks } from "./excalidrawTitle";

describe("withDecodedLineBreaks", () => {
  it("repairs double-escaped line breaks in labels and standalone text", () => {
    expect(withDecodedLineBreaks([
      { type: "rectangle", label: { text: "first\\nsecond" } },
      { type: "text", text: "third\\r\\nfourth", originalText: "third\\r\\nfourth" },
    ])).toEqual([
      { type: "rectangle", label: { text: "first\nsecond" } },
      { type: "text", text: "third\nfourth", originalText: "third\nfourth" },
    ]);
  });
});

describe("withCenteredTitle", () => {
  it("leaves scenes without text unchanged", () => {
    const elements = [{ id: "box", type: "rectangle", x: 40, y: 80, width: 200, height: 50 }];
    expect(withCenteredTitle(elements)).toEqual(elements);
  });

  it("keeps the model camera and shrinks a wide title to fit inside it", () => {
    const camera = { type: "cameraUpdate", x: 0, y: 0, width: 800, height: 600 };
    const fitted = withCenteredTitle([
      camera,
      { id: "title", type: "text", x: 150, y: 10, fontSize: 24, text: "RF-DETR: Weight-Sharing NAS for Real-Time Detection" },
      { id: "box", type: "rectangle", x: 20, y: 90, width: 760, height: 210 },
    ]);
    expect(fitted[0]).toEqual(camera);
    const title = fitted[1] as { x: number; width: number; fontSize: number; textAlign: string; autoResize: boolean };
    expect(title.textAlign).toBe("left");
    expect(title.autoResize).toBe(false);
    expect(title.width).toBeLessThanOrEqual(800 - 56);
    expect(title.x).toBeGreaterThanOrEqual(28);
    expect(title.x + title.width).toBeLessThanOrEqual(772);
    expect(title.fontSize).toBeLessThan(24);
    expect(fitted[2]).toEqual({ id: "box", type: "rectangle", x: 20, y: 90, width: 760, height: 210 });
  });

  it("leaves a short title that already fits the camera", () => {
    const fitted = withCenteredTitle([
      { type: "cameraUpdate", x: 0, y: 0, width: 800, height: 600 },
      { id: "title", type: "text", x: 200, y: 10, fontSize: 20, text: "DFlash" },
      { id: "box", type: "rectangle", x: 50, y: 80, width: 700, height: 200 },
    ]);
    const title = fitted[1] as { x: number; fontSize: number; text?: string };
    expect(title.x).toBe(200);
    expect(title.fontSize).toBe(20);
  });

  it("shrinks a long subtitle that would clip the camera", () => {
    const fitted = withCenteredTitle([
      { type: "cameraUpdate", x: 0, y: 0, width: 800, height: 600 },
      { id: "sub", type: "text", x: 120, y: 48, fontSize: 15, text: "Speculative decoding: a light draft model proposes tokens, the big target verifies them in one pass" },
    ]);
    const subtitle = fitted[1] as { x: number; width: number; textAlign: string };
    expect(subtitle.textAlign).toBe("left");
    expect(subtitle.x).toBeGreaterThanOrEqual(28);
    expect(subtitle.x + subtitle.width).toBeLessThanOrEqual(772);
  });
});
