const DEFAULT_VIEW_WIDTH = 1024;
const SIDE_MARGIN = 16;

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
  const width = isTextElement(element) ? textWidth(element) : number(element.width);
  const height = number(element.height) ?? (isTextElement(element) ? (number(element.fontSize) ?? 20) * 1.4 : 0);
  if (width === undefined || width <= 0) return null;
  return { x, y, width, height };
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

/** Keep the default Excalidraw camera. Only recenter/shrink the top title so a
 * long heading stays visible without adding empty space around the diagram. */
export function withCenteredTitle(elements: unknown[]): unknown[] {
  const records = elements.map(asRecord);
  if (records.some((item) => item === undefined)) return elements;
  const drawn = records as Record<string, unknown>[];
  const index = titleIndex(drawn);
  if (index < 0) return elements;
  let frame: Box | null = null;
  for (let position = 0; position < drawn.length; position += 1) {
    if (position === index) continue;
    const element = drawn[position];
    if (!element || !isDrawElement(element)) continue;
    const box = elementBox(element);
    if (!box) continue;
    frame = frame ? union(frame, box) : box;
  }
  const title = { ...drawn[index] };
  let width = textWidth(title);
  const frameX = frame?.x ?? 0;
  const frameWidth = frame && frame.width > 0 ? frame.width : DEFAULT_VIEW_WIDTH;
  const maxWidth = Math.max(1, frameWidth - SIDE_MARGIN * 2);
  if (width > maxWidth) {
    const scale = maxWidth / width;
    const fontSize = number(title.fontSize) ?? 20;
    title.fontSize = fontSize * scale;
    if (typeof title.height === "number") title.height *= scale;
    width = maxWidth;
  }
  title.width = width;
  title.textAlign = "center";
  title.x = frameX + (frameWidth - width) / 2;
  return drawn.map((element, position) => (position === index ? title : element));
}
