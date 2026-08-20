type Range = { start: number; end: number };

function codeRanges(markdown: string): Range[] {
  const ranges: Range[] = [];
  let offset = 0;
  let fence: { marker: string; length: number; start: number } | null = null;

  for (const line of markdown.match(/.*(?:\n|$)/g) ?? []) {
    if (!line) continue;
    const body = line.endsWith("\n") ? line.slice(0, -1) : line;

    if (fence) {
      const closing = body.match(/^ {0,3}(`+|~+)[ \t]*$/);
      if (
        closing
        && closing[1][0] === fence.marker
        && closing[1].length >= fence.length
      ) {
        ranges.push({ start: fence.start, end: offset + line.length });
        fence = null;
      }
      offset += line.length;
      continue;
    }

    const opening = body.match(/^ {0,3}(`{3,}|~{3,})/);
    if (opening) {
      fence = {
        marker: opening[1][0],
        length: opening[1].length,
        start: offset,
      };
      offset += line.length;
      continue;
    }

    let cursor = 0;
    while (cursor < body.length) {
      const start = body.indexOf("`", cursor);
      if (start === -1) break;
      let length = 1;
      while (body[start + length] === "`") length += 1;
      const delimiter = "`".repeat(length);
      let end = body.indexOf(delimiter, start + length);
      while (
        end !== -1
        && (body[end - 1] === "`" || body[end + length] === "`")
      ) {
        end = body.indexOf(delimiter, end + length);
      }
      if (end === -1) {
        cursor = start + length;
        continue;
      }
      ranges.push({ start: offset + start, end: offset + end + length });
      cursor = end + length;
    }
    offset += line.length;
  }

  if (fence) ranges.push({ start: fence.start, end: markdown.length });
  return ranges;
}

function isInside(ranges: Range[], index: number): boolean {
  return ranges.some((range) => index >= range.start && index < range.end);
}

function isUnescapedDelimiter(markdown: string, index: number): boolean {
  let precedingSlashes = 0;
  for (let cursor = index - 1; cursor >= 0 && markdown[cursor] === "\\"; cursor -= 1) {
    precedingSlashes += 1;
  }
  return precedingSlashes % 2 === 0;
}

function delimiterPairs(
  markdown: string,
  open: string,
  close: string,
  excluded: Range[],
): Range[] {
  const pairs: Range[] = [];
  let cursor = 0;

  while (cursor < markdown.length) {
    const start = markdown.indexOf(open, cursor);
    if (start === -1) break;
    if (isInside(excluded, start) || !isUnescapedDelimiter(markdown, start)) {
      cursor = start + open.length;
      continue;
    }

    let end = markdown.indexOf(close, start + open.length);
    while (
      end !== -1
      && (isInside(excluded, end) || !isUnescapedDelimiter(markdown, end))
    ) {
      end = markdown.indexOf(close, end + close.length);
    }
    if (end === -1) break;
    pairs.push({ start, end: end + close.length });
    cursor = end + close.length;
  }
  return pairs;
}

/**
 * remark-math accepts dollar delimiters but not LaTeX's common \(...\) and
 * \[...\] forms. Convert complete pairs before Markdown parsing, excluding
 * code where delimiter-looking text must remain literal.
 */
export function normalizeChatMath(markdown: string): string {
  const code = codeRanges(markdown);
  const display = delimiterPairs(markdown, "\\[", "\\]", code);
  const inline = delimiterPairs(markdown, "\\(", "\\)", [...code, ...display]);
  const replacements = new Map<number, { length: number; value: string }>();

  for (const range of display) {
    replacements.set(range.start, { length: 2, value: "$$" });
    replacements.set(range.end - 2, { length: 2, value: "$$" });
  }
  for (const range of inline) {
    replacements.set(range.start, { length: 2, value: "$" });
    replacements.set(range.end - 2, { length: 2, value: "$" });
  }

  if (replacements.size === 0) return markdown;
  let normalized = "";
  for (let cursor = 0; cursor < markdown.length;) {
    const replacement = replacements.get(cursor);
    if (replacement) {
      normalized += replacement.value;
      cursor += replacement.length;
    } else {
      normalized += markdown[cursor];
      cursor += 1;
    }
  }
  return normalized;
}
