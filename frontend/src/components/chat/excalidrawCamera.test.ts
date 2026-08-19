import { describe, expect, it } from "vitest";

import { cameraForBounds, paddingForBounds, withFittedCamera, withFramedDiagram } from "./excalidrawCamera";

describe("withFittedCamera", () => {
  it("leaves empty scenes unchanged", () => {
    expect(withFittedCamera([])).toEqual([]);
  });

  it("replaces a tight existing cameraUpdate so right-edge boxes stay in view", () => {
    const fitted = withFittedCamera([
      { type: "cameraUpdate", x: 0, y: 0, width: 800, height: 600 },
      { id: "box", type: "rectangle", x: 20, y: 90, width: 760, height: 210 },
      { id: "tail", type: "rectangle", x: 820, y: 150, width: 180, height: 60 },
    ]);
    expect(fitted.filter((item) => (item as { type?: string }).type === "cameraUpdate")).toHaveLength(1);
    const camera = fitted.at(-1) as { x: number; y: number; width: number; height: number };
    expect(camera.type).toBe("cameraUpdate");
    expect(camera.width / camera.height).toBeCloseTo(4 / 3, 2);
    expect(camera.x).toBeLessThanOrEqual(20 - paddingForBounds({ x: 20, y: 90, width: 980, height: 210 }));
    expect(camera.x + camera.width).toBeGreaterThanOrEqual(1000);
    expect(camera.y + camera.height).toBeGreaterThanOrEqual(300);
  });

  it("centers leftover space when the drawing is taller than 4:3", () => {
    const bounds = { x: 0, y: 0, width: 400, height: 800 };
    const camera = cameraForBounds(bounds);
    const pad = paddingForBounds(bounds);
    expect(camera.width / camera.height).toBeCloseTo(4 / 3, 2);
    expect(camera.y).toBe(-pad);
    expect(camera.height).toBe(800 + pad * 2);
    const leftoverLeft = -camera.x;
    const leftoverRight = camera.x + camera.width - 400;
    expect(Math.abs(leftoverLeft - leftoverRight)).toBeLessThan(2);
  });
});

describe("withFramedDiagram", () => {
  it("shrinks a long title then frames the diagram instead of clipping it", () => {
    const framed = withFramedDiagram([
      { type: "cameraUpdate", x: 0, y: 0, width: 800, height: 600 },
      { id: "title", type: "text", x: 80, y: 10, width: 1180, height: 48, fontSize: 36, text: "RF-DETR: Weight-Sharing NAS for Real-Time Detection" },
      { id: "sub", type: "text", x: 40, y: 56, width: 1100, height: 20, fontSize: 14, text: "Speculative decoding: a light draft model proposes tokens, the big target verifies them in one forward pass" },
      { id: "box", type: "rectangle", x: 20, y: 90, width: 760, height: 210 },
      { id: "note", type: "text", x: 30, y: 320, width: 900, height: 18, fontSize: 14, text: "Result: 60-85% faster per-user generation vs MTP-1 at matched throughput" },
    ]);
    const camera = framed.at(-1) as { type: string; x: number; y: number; width: number; height: number };
    const title = framed.find((item) => (item as { id?: string }).id === "title") as { x: number; width: number; fontSize: number };
    const subtitle = framed.find((item) => (item as { id?: string }).id === "sub") as { x: number; width: number };
    const note = framed.find((item) => (item as { id?: string }).id === "note") as { x: number; width: number };
    expect(camera.type).toBe("cameraUpdate");
    expect(camera.width / camera.height).toBeCloseTo(4 / 3, 2);
    expect(title.width).toBeLessThanOrEqual(760);
    expect(title.x).toBeGreaterThanOrEqual(20);
    expect(title.x + title.width).toBeLessThanOrEqual(780);
    expect(subtitle.width).toBeLessThanOrEqual(760);
    expect(note.width).toBeLessThanOrEqual(760);
    expect(camera.x).toBeLessThanOrEqual(title.x);
    expect(camera.x + camera.width).toBeGreaterThanOrEqual(title.x + title.width);
    expect(camera.y).toBeLessThanOrEqual(title.y ?? 10);
    expect(camera.y + camera.height).toBeGreaterThanOrEqual(338);
  });
});
