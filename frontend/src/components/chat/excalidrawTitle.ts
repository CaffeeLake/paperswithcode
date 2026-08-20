const DEFAULT_CAMERA = { x: 0, y: 0, width: 1024, height: 768 };
const SIDE_MARGIN = 28;
const MIN_FONT_SIZE = 12;
/** Excalifont is wider than 0.65em; underestimate caused titles to keep clipping. */
const CHAR_WIDTH = 0.9;

type Box = { x: number; y: number; width: number; height: number };

function number(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function asRecord(value: unknown): Record<string, unknown> | undefined {
  if (!value || typeof value !== "object" || Array.isArray(value)) return undefined;
  return value as Record<string, unknown>;
}

/** Repair model-generated text that escaped a line break twice inside the
 * JSON-string tool argument. This also fixes already-persisted diagrams. */
export function withDecodedLineBreaks(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(withDecodedLineBreaks);
  const object = asRecord(value);
  if (!object) return value;
  return Object.fromEntries(
    Object.entries(object).map(([key, child]) => [
      key,
      (key === "text" || key === "originalText") && typeof child === "string"
        ? child.replace(/\\r\\n|\\n|\\r/gu, "\n")
        : withDecodedLineBreaks(child),
    ]),
  );
}

function isTextElement(element: Record<string, unknown>): boolean {
  return element.type === "text" && typeof (element.text ?? element.originalText) === "string";
}

function measureWidth(element: Record<string, unknown>): number {
  const text = String(element.text ?? element.originalText ?? "");
  const size = number(element.fontSize) ?? 20;
  const measured = text.length * size * CHAR_WIDTH;
  const declared = number(element.width);
  return Math.max(declared && declared > 0 ? declared : 0, measured);
}

function cameraFrame(elements: Record<string, unknown>[]): Box {
  for (const element of elements) {
    if (element.type !== "cameraUpdate") continue;
    const width = number(element.width);
    const height = number(element.height);
    if (!width || width <= 0 || !height || height <= 0) continue;
    return {
      x: number(element.x) ?? 0,
      y: number(element.y) ?? 0,
      width,
      height,
    };
  }
  return DEFAULT_CAMERA;
}

function overflowsCamera(element: Record<string, unknown>, camera: Box): boolean {
  const x = number(element.x);
  if (x === undefined) return false;
  const width = measureWidth(element);
  const left = camera.x + SIDE_MARGIN;
  const right = camera.x + camera.width - SIDE_MARGIN;
  return x < left - 1 || x + width > right + 1;
}

function fitToCamera(element: Record<string, unknown>, camera: Box): Record<string, unknown> {
  const fitted = { ...element };
  const fontSize = number(fitted.fontSize) ?? 20;
  let width = measureWidth(fitted);
  const maxWidth = Math.max(1, camera.width - SIDE_MARGIN * 2);
  if (width > maxWidth) {
    const scale = maxWidth / width;
    fitted.fontSize = Math.max(MIN_FONT_SIZE, fontSize * scale);
    if (typeof fitted.height === "number") fitted.height *= Number(fitted.fontSize) / fontSize;
    width = Math.min(maxWidth, width * (Number(fitted.fontSize) / fontSize));
  }
  fitted.width = width;
  fitted.autoResize = false;
  fitted.textAlign = "left";
  fitted.x = camera.x + (camera.width - width) / 2;
  return fitted;
}

/** Keep the model's camera so the diagram still fills the frame. Only shrink
 * headings that would clip on the left or right of that camera. */
export function withCenteredTitle(elements: unknown[]): unknown[] {
  const decoded = withDecodedLineBreaks(elements) as unknown[];
  const records = decoded.map(asRecord);
  if (records.some((item) => item === undefined)) return elements;
  const drawn = records as Record<string, unknown>[];
  const camera = cameraFrame(drawn);
  return drawn.map((element) => {
    if (!isTextElement(element) || !overflowsCamera(element, camera)) return element;
    return fitToCamera(element, camera);
  });
}
