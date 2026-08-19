const DEFAULT_VIEW_WIDTH = 1024;
const SIDE_MARGIN = 16;
const MIN_FONT_SIZE = 11;

type Box = { x: number; y: number; width: number; height: number };

function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

function isDrawElement(element: Record<string, unknown>): boolean {
  return element.type !== "cameraUpdate" && element.type !== "delete" && element.type !== "restoreCheckpoint";
}

function isTextElement(element: Record<string, unknown>): boolean {
  return element.type === "text" && typeof (element.text ?? element.originalText) === "string";
}

function textWidth(element: Record<string, unknown>): number {
  const width = number(element.width);
  if (width !== undefined && width > 0) return width;
  const text = String(element.text ?? element.originalText ?? "");
  const size = number(element.fontSize) ?? 20;
  return text.length * size * 0.65;
}

function elementBox(element: Record<string, unknown>): Box | null {
  const x = number(element.x);
  const y = number(element.y);
  if (x === undefined || y === undefined) return null;
  let minX = x;
  let minY = y;
  let maxX = x;
  let maxY = y;
  const width = isTextElement(element) ? textWidth(element) : number(element.width);
  const height = number(element.height) ?? (isTextElement(element) ? (number(element.fontSize) ?? 20) * 1.4 : 0);
  if (width !== undefined && width > 0) maxX = Math.max(maxX, x + width);
  if (height !== undefined && height > 0) maxY = Math.max(maxY, y + height);
  if (Array.isArray(element.points)) {
    for (const point of element.points) {
      if (!Array.isArray(point) || point.length < 2) continue;
      minX = Math.min(minX, x + (number(point[0]) ?? 0));
      minY = Math.min(minY, y + (number(point[1]) ?? 0));
      maxX = Math.max(maxX, x + (number(point[0]) ?? 0));
      maxY = Math.max(maxY, y + (number(point[1]) ?? 0));
    }
  }
  if (maxX <= minX) return null;
  return { x: minX, y: minY, width: maxX - minX, height: Math.max(0, maxY - minY) };
}

function union(left: Box, right: Box): Box {
  const x = Math.min(left.x, right.x);
  const y = Math.min(left.y, right.y);
  return {
    x,
    y,
    width: Math.max(left.x + left.width, right.x + right.width) - x,
    height: Math.max(left.y + left.height, right.y + right.height) - y,
  };
}

function structureBox(elements: Record<string, unknown>[]): Box | null {
  let frame: Box | null = null;
  for (const element of elements) {
    if (!isDrawElement(element) || isTextElement(element)) continue;
    const box = elementBox(element);
    if (!box) continue;
    frame = frame ? union(frame, box) : box;
  }
  return frame;
}

function titleIndex(elements: Record<string, unknown>[]): number {
  let best = -1;
  let bestY = Infinity;
  let bestSize = -1;
  elements.forEach((element, index) => {
    if (!isTextElement(element)) return;
    const y = number(element.y);
    if (y === undefined) return;
    const size = number(element.fontSize) ?? textWidth(element);
    if (y < bestY - 8 || (Math.abs(y - bestY) <= 8 && size > bestSize)) {
      best = index;
      bestY = y;
      bestSize = size;
    }
  });
  return best;
}

function fitText(
  element: Record<string, unknown>,
  frame: Box,
  center: boolean,
): Record<string, unknown> {
  const fitted = { ...element };
  let width = textWidth(fitted);
  const maxWidth = Math.max(1, frame.width - SIDE_MARGIN * 2);
  const fontSize = number(fitted.fontSize) ?? 20;
  if (width > maxWidth) {
    const scale = Math.max(MIN_FONT_SIZE / fontSize, maxWidth / width);
    fitted.fontSize = fontSize * scale;
    if (typeof fitted.height === "number") fitted.height *= scale;
    width = Math.min(maxWidth, width * scale);
  }
  fitted.width = width;
  if (center) {
    fitted.textAlign = "center";
    fitted.x = frame.x + (frame.width - width) / 2;
  } else {
    const x = number(fitted.x) ?? frame.x;
    const minX = frame.x + SIDE_MARGIN;
    const maxX = frame.x + frame.width - SIDE_MARGIN - width;
    fitted.x = Math.min(Math.max(x, minX), Math.max(minX, maxX));
  }
  return fitted;
}

/** Recenter/shrink headings and other overflowing labels so they stay over the
 * drawn diagram instead of clipping at the default Excalidraw camera. */
export function withCenteredTitle(elements: unknown[]): unknown[] {
  const records = elements.map(asRecord);
  if (records.some((item) => item === undefined)) return elements;
  const drawn = records as Record<string, unknown>[];
  const index = titleIndex(drawn);
  let frame = structureBox(drawn);
  if (!frame) {
    if (index < 0) return elements;
    for (let position = 0; position < drawn.length; position += 1) {
      if (position === index) continue;
      const element = drawn[position];
      if (!element || !isDrawElement(element)) continue;
      const box = elementBox(element);
      if (!box) continue;
      frame = frame ? union(frame, box) : box;
    }
  }
  const frameX = frame?.x ?? 0;
  const frameWidth = frame && frame.width > 0 ? frame.width : DEFAULT_VIEW_WIDTH;
  const usable: Box = { x: frameX, y: frame?.y ?? 0, width: frameWidth, height: frame?.height ?? 0 };
  return drawn.map((element, position) => {
    if (!isTextElement(element)) return element;
    const box = elementBox(element);
    const above = box !== null && box.y + box.height <= usable.y + 8;
    const tooWide = textWidth(element) > usable.width - SIDE_MARGIN * 2;
    if (position === index || above || tooWide) {
      return fitText(element, usable, position === index || above);
    }
    return element;
  });
}
