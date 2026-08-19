import { describe, expect, it } from "vitest";

import { withCenteredTitle } from "./excalidrawTitle";

describe("withCenteredTitle", () => {
  it("leaves scenes without text unchanged", () => {
    const elements = [{ id: "box", type: "rectangle", x: 40, y: 80, width: 200, height: 50 }];
    expect(withCenteredTitle(elements)).toEqual(elements);
  });

  it("centers and shrinks a wide title over the diagram", () => {
    const fitted = withCenteredTitle([
      { id: "title", type: "text", x: 80, y: 20, width: 1180, height: 48, fontSize: 36, text: "RF-DETR: Weight-Sharing NAS for Real-Time Detection" },
      { id: "box", type: "rectangle", x: 100, y: 120, width: 800, height: 400 },
    ]);
    const title = fitted[0] as { x: number; width: number; fontSize: number; textAlign: string };
    expect(title.textAlign).toBe("center");
    expect(title.width).toBe(800 - 32);
    expect(title.x).toBe(100 + 16);
    expect(title.fontSize).toBeCloseTo(36 * ((800 - 32) / 1180), 5);
    expect(fitted[1]).toEqual({ id: "box", type: "rectangle", x: 100, y: 120, width: 800, height: 400 });
  });

  it("centers a fitting title without shrinking it", () => {
    const fitted = withCenteredTitle([
      { id: "title", type: "text", x: 0, y: 10, width: 200, height: 24, fontSize: 20, text: "DFlash" },
      { id: "box", type: "rectangle", x: 50, y: 80, width: 900, height: 200 },
    ]);
    const title = fitted[0] as { x: number; width: number; fontSize: number };
    expect(title.width).toBe(200);
    expect(title.fontSize).toBe(20);
    expect(title.x).toBe(50 + (900 - 200) / 2);
  });
});
