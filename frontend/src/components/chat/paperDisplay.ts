/**
 * Display helpers deriving UI strings from the chat hit contract
 * (`ChatPaperHit`): author line, venue line, and a short visual excerpt of
 * `content` (the contract carries no snippet and no relevance score).
 */

import type { ChatPaperHit, ChatPaperMetadata } from "@/lib/chat";

export function authorsLine(m: ChatPaperMetadata): string {
  if (!m.authors.length) return "";
  const names = m.authors.slice(0, 3).map((a) => a.name).join(", ");
  return m.authors.length > 3 ? `${names}, et al.` : names;
}

/** "CVPR 2024", "arXiv 2025", or the external source's host. */
export function venueLine(m: ChatPaperMetadata): string {
  if (m.conference) return m.conference;
  const year = m.published?.slice(0, 4);
  if (m.arxiv_id) return year ? `arXiv ${year}` : "arXiv";
  if (m.source_url) {
    try {
      return new URL(m.source_url).hostname.replace(/^www\./, "");
    } catch {
      /* fall through */
    }
  }
  return year ?? "external";
}

export function excerpt(hit: ChatPaperHit, max = 240): string {
  const text = hit.content.trim();
  if (text.length <= max) return text;
  return `${text.slice(0, max).trimEnd()}…`;
}
