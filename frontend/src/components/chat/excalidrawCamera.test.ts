import { describe, expect, it } from "vitest";

import { cameraForBounds, paddingForBounds, withFittedCamera } from "./excalidrawCamera";

describe("withFittedCamera", () => {
  it("leaves empty scenes unchanged", () => {
    expect(withFittedCamera([])).toEqual([]);
  });

  it("keeps a wide title inside a centered 4:3 camera", () => {
    const fitted = withFittedCamera([
      { id: "title", type: "text", x: 80, y: 40, width: 1180, height: 48, text: "RF-DETR: Weight-Sharing NAS for Real-Time Detection" },
      { id: "box", type: "rectangle", x: 120, y: 140, width: 400, height: 80 },
    ]);
    const camera = fitted.at(-1) as { type: string; x: number; y: number; width: number; height: number };
    expect(camera.type).toBe("cameraUpdate");
    expect(camera.width / camera.height).toBeCloseTo(4 / 3, 2);
    expect(camera.x + camera.width).toBeGreaterThanOrEqual(1260);
    expect(camera.y).toBeLessThan(40);
    expect(camera.y + camera.height).toBeGreaterThan(220);
    const leftoverTop = 40 - camera.y;
    const leftoverBottom = camera.y + camera.height - 220;
    expect(leftoverTop).toBeGreaterThan(0);
    expect(Math.abs(leftoverTop - leftoverBottom)).toBeLessThan(8);
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

  it("replaces a tight existing cameraUpdate", () => {
    const fitted = withFittedCamera([
      { type: "cameraUpdate", x: 0, y: 0, width: 1024, height: 768 },
      { id: "box", type: "rectangle", x: 10, y: 20, width: 200, height: 50 },
    ]);
    expect(fitted.filter((item) => (item as { type?: string }).type === "cameraUpdate")).toHaveLength(1);
    const camera = fitted.at(-1) as { x: number; y: number; width: number; height: number };
    expect(camera.x).toBeLessThanOrEqual(10 - paddingForBounds({ x: 10, y: 20, width: 200, height: 50 }));
    expect(camera.x + camera.width).toBeGreaterThanOrEqual(210);
  });
});
