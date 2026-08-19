import { describe, expect, it } from "vitest";

import { EXCALIDRAW_CAMERA_PADDING, withFittedCamera } from "./excalidrawCamera";

describe("withFittedCamera", () => {
  it("leaves empty scenes unchanged", () => {
    expect(withFittedCamera([])).toEqual([]);
  });

  it("fits a wide title that would overflow the default 1024px camera", () => {
    const fitted = withFittedCamera([
      { id: "title", type: "text", x: 80, y: 40, width: 1180, height: 48, text: "RF-DETR: Weight-Sharing NAS for Real-Time Detection" },
      { id: "box", type: "rectangle", x: 120, y: 140, width: 400, height: 80 },
    ]);
    const camera = fitted.at(-1) as { type: string; x: number; y: number; width: number; height: number };
    expect(camera.type).toBe("cameraUpdate");
    expect(camera.x).toBe(80 - EXCALIDRAW_CAMERA_PADDING);
    expect(camera.y).toBe(40 - EXCALIDRAW_CAMERA_PADDING);
    expect(camera.width).toBe(1180 + EXCALIDRAW_CAMERA_PADDING * 2);
    expect(camera.height).toBe(140 + 80 - 40 + EXCALIDRAW_CAMERA_PADDING * 2);
  });

  it("replaces a tight existing cameraUpdate", () => {
    const fitted = withFittedCamera([
      { type: "cameraUpdate", x: 0, y: 0, width: 1024, height: 768 },
      { id: "box", type: "rectangle", x: 10, y: 20, width: 200, height: 50 },
    ]);
    expect(fitted.filter((item) => (item as { type?: string }).type === "cameraUpdate")).toHaveLength(1);
    const camera = fitted.at(-1) as { x: number; width: number };
    expect(camera.x).toBe(10 - EXCALIDRAW_CAMERA_PADDING);
    expect(camera.width).toBe(200 + EXCALIDRAW_CAMERA_PADDING * 2);
  });
});
