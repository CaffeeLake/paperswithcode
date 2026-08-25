const EXCERPT_LENGTH = 360;

function firstLiteralMatch(text: string, query: string): number {
  const lower = text.toLocaleLowerCase();
  return query.trim().split(/\s+/).filter(Boolean).reduce((best, term) => {
    const index = lower.indexOf(term.toLocaleLowerCase());
    return index >= 0 && (best < 0 || index < best) ? index : best;
  }, -1);
}

function outsideMathBoundary(text: string, boundary: number, direction: "start" | "end"): number {
  const dollarsBefore = (text.slice(0, boundary).match(/\$/g) || []).length;
  if (dollarsBefore % 2 === 0) return boundary;
  if (direction === "start") return text.lastIndexOf("$", boundary) + 1;
  const next = text.indexOf("$", boundary);
  return next >= 0 ? next + 1 : boundary;
}

/** Show the beginning for semantic-only hits and a safe, literal-match excerpt otherwise. */
export function queryCenteredExcerpt(abstract: string, query: string): string {
  if (abstract.length <= EXCERPT_LENGTH) return abstract;
  const match = firstLiteralMatch(abstract, query);
  if (match < 0 || match < EXCERPT_LENGTH * 0.6) return abstract;
  let start = Math.max(0, match - Math.floor(EXCERPT_LENGTH * 0.35));
  let end = Math.min(abstract.length, start + EXCERPT_LENGTH);
  start = outsideMathBoundary(abstract, start, "start");
  end = outsideMathBoundary(abstract, end, "end");
  return `${start > 0 ? "…" : ""}${abstract.slice(start, end).trim()}${end < abstract.length ? "…" : ""}`;
}
