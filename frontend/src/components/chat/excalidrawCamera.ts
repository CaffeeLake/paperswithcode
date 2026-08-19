import { withCenteredTitle } from "./excalidrawTitle";

const MIN_PADDING = 20;
const ASPECT = 4 / 3;

type Camera = { x: number; y: number; width: number; height: number };

function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function elementBounds(element: Record<string, unknown>): Camera | null {
  const type = element.type;
  if (type === "cameraUpdate" || type === "delete" || type === "restoreCheckpoint") return null;
  const x = number(element.x);
  const y = number(element.y);
  if (x === undefined || y === undefined) return null;
  let minX = x;
  let minY = y;
  let maxX = x;
  let maxY = y;
  const width = number(element.width);
  const height = number(element.height);
  if (width !== undefined) maxX = Math.max(maxX, x + width);
  if (height !== undefined) maxY = Math.max(maxY, y + height);
  if (type === "text" && (width === undefined || width <= 0) && typeof (element.text ?? element.originalText) === "string") {
    const size = number(element.fontSize) ?? 20;
    const text = String(element.text ?? element.originalText ?? "");
    maxX = Math.max(maxX, x + text.length * size * 0.65);
    maxY = Math.max(maxY, y + size * 1.5);
  }
  if (Array.isArray(element.points)) {
    for (const point of element.points) {
      if (!Array.isArray(point) || point.length < 2) continue;
      const px = x + (number(point[0]) ?? 0);
      const py = y + (number(point[1]) ?? 0);
      minX = Math.min(minX, px);
      minY = Math.min(minY, py);
      maxX = Math.max(maxX, px);
      maxY = Math.max(maxY, py);
    }
  }
  if (maxX <= minX) return null;
  return { x: minX, y: minY, width: maxX - minX, height: Math.max(0, maxY - minY) };
}

function union(left: Camera, right: Camera): Camera {
  const x = Math.min(left.x, right.x);
  const y = Math.min(left.y, right.y);
  return {
    x,
    y,
    width: Math.max(left.x + left.width, right.x + right.width) - x,
    height: Math.max(left.y + left.height, right.y + right.height) - y,
  };
}

export function paddingForBounds(bounds: Camera): number {
  return Math.max(MIN_PADDING, Math.round(Math.max(bounds.width, bounds.height) * 0.03));
}

/** Expand padded content bounds to a centered 4:3 camera so the remote App's
 * forced 4:3 viewBox matches the host iframe. */
export function cameraForBounds(bounds: Camera): Camera {
  const pad = paddingForBounds(bounds);
  const padded = {
    x: bounds.x - pad,
    y: bounds.y - pad,
    width: bounds.width + pad * 2,
    height: bounds.height + pad * 2,
  };
  const ratio = padded.width / padded.height;
  if (Math.abs(ratio - ASPECT) < 0.01) return padded;
  if (ratio > ASPECT) {
    const height = Math.round(padded.width * 3 / 4);
    return {
      x: padded.x,
      y: padded.y - Math.round((height - padded.height) / 2),
      width: padded.width,
      height,
    };
  }
  const width = Math.round(padded.height * 4 / 3);
  return {
    x: padded.x - Math.round((width - padded.width) / 2),
    y: padded.y,
    width,
    height: padded.height,
  };
}

export function withFittedCamera(elements: unknown[]): unknown[] {
  let bounds: Camera | null = null;
  const draw: unknown[] = [];
  for (const item of elements) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    const element = item as Record<string, unknown>;
    if (element.type === "cameraUpdate") continue;
    draw.push(element);
    const box = elementBounds(element);
    if (!box) continue;
    bounds = bounds ? union(bounds, box) : box;
  }
  if (!bounds || bounds.width <= 0 || bounds.height <= 0) return elements;
  return [...draw, { type: "cameraUpdate", ...cameraForBounds(bounds) }];
}

/** Shrink overflowing labels, then fit a 4:3 camera so titles and edge text stay in view. */
export function withFramedDiagram(elements: unknown[]): unknown[] {
  return withFittedCamera(withCenteredTitle(elements));
}
