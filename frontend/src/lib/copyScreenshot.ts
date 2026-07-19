/**
 * Render a DOM node to a PNG and write it to the system clipboard.
 *
 * Used by benchmark cards so users can paste a snapshot of a SOTA chart or
 * leaderboard into Slack/Twitter/etc. We always paint a solid background
 * before capture because the surrounding CSS variables (`--bg-elevated`)
 * resolve to a translucent value in some themes, which produces an image
 * that looks broken when pasted outside the site.
 */
import { toBlob } from "html-to-image";

const DEFAULT_BACKGROUND = "#ffffff";

function readThemeBackground(): string {
  if (typeof window === "undefined") return DEFAULT_BACKGROUND;
  return (
    window
      .getComputedStyle(document.documentElement)
      .getPropertyValue("--bg-elevated")
      .trim() || DEFAULT_BACKGROUND
  );
}

function readBackgroundColor(node: HTMLElement): string {
  if (typeof window === "undefined") return DEFAULT_BACKGROUND;
  const computed = window.getComputedStyle(node).backgroundColor;
  if (!computed || computed === "rgba(0, 0, 0, 0)" || computed === "transparent") {
    return readThemeBackground();
  }
  return computed;
}

export async function copyNodeAsPng(node: HTMLElement): Promise<void> {
  if (typeof window === "undefined" || !window.navigator?.clipboard?.write) {
    throw new Error("Clipboard image copy is not supported in this browser.");
  }
  if (typeof window.ClipboardItem === "undefined") {
    throw new Error("Clipboard image copy is not supported in this browser.");
  }

  // 2x pixel ratio keeps charts and table text crisp when pasted into chat
  // clients that render images at native resolution.
  const blob = await toBlob(node, {
    pixelRatio: 2,
    cacheBust: true,
    backgroundColor: readBackgroundColor(node),
  });

  if (!blob) {
    throw new Error("Failed to render screenshot.");
  }

  await window.navigator.clipboard.write([
    new window.ClipboardItem({ "image/png": blob }),
  ]);
}
