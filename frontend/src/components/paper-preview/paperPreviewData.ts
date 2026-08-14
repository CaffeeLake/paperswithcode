import type { Paper } from "@/lib/api/papers.types";

export interface PaperPreviewData {
  routeId: string;
  title: string;
  arxivId: string | null;
  source: "arxiv" | "external";
  sourceUrl: string | null;
  thumbnailUrl: string | null;
  authors: string[];
  published: string | null;
  conference: string | null;
  citationCount: number | null;
  tasks: { name: string; slug: string }[];
}

export function paperToPreviewData(
  paper: Paper,
  routeId = paper.arxiv_id ?? paper.id,
): PaperPreviewData {
  return {
    routeId,
    title: paper.title,
    arxivId: paper.arxiv_id,
    source: paper.source ?? (paper.arxiv_id ? "arxiv" : "external"),
    sourceUrl: paper.source_url ?? paper.url_abs,
    thumbnailUrl: paper.thumbnail_url ?? null,
    authors: paper.authors,
    published: paper.published ?? null,
    conference: paper.conference_name ?? paper.conference ?? null,
    citationCount: paper.citation_count,
    tasks: (paper.tasks ?? []).map((task) => ({
      name: task.name,
      slug: task.slug ?? "",
    })),
  };
}

export function authorsLine(data: PaperPreviewData): string {
  if (!data.authors.length) return "";
  const names = data.authors.slice(0, 3).join(", ");
  return data.authors.length > 3 ? `${names}, et al.` : names;
}

export function venueLine(data: PaperPreviewData): string {
  if (data.conference) return data.conference;
  const year = data.published?.slice(0, 4);
  if (data.arxivId) return year ? `arXiv ${year}` : "arXiv";
  if (data.sourceUrl) {
    try {
      return new URL(data.sourceUrl).hostname.replace(/^www\./, "");
    } catch {
      // Fall through to the date or generic external label.
    }
  }
  return year ?? "external";
}
