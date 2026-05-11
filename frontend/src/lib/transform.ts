/**
 * Backend → v2 UI transform helpers.
 *
 * The v2 components were originally written against hardcoded fixtures in
 * `data.js` with field names like `tags`, `github`, `date`, `institution`, …
 * (see PLAN.md §4 for the full mapping). After this migration, every view
 * fetches typed `Paper` / `Task` / `Method` / `Dataset` / `Evaluation` objects
 * from `lib/api.ts` and pipes them through these helpers so the rendered
 * components keep working without surgery on every view.
 *
 * Decisions captured in PLAN.md §4.1:
 *   - `submitter`, `comments`, `institution`, `upvotes` chip are dropped
 *     entirely (no schema, no UI affordance).
 *   - `tldr` and `num_pages` schema columns exist but no ingestion yet —
 *     the UI hides those panels when null.
 */

import { format, parseISO } from "date-fns";

import type { Paper, Repository, Task, TrendingPaper } from "./api";

export interface PaperCardProps {
  /** source-aware route id: arxiv_id for ArXiv rows, DB id for external rows */
  id: string;
  /** numeric DB id (used by write APIs) */
  dbId: string;
  title: string;
  abstract: string;
  authors: string[];
  /** paper.tasks[*].slug, used by TagChip */
  tags: string[];
  citations: number;
  /** sum of stars across official repos; null when no repo */
  github: number | null;
  /** url of most-starred official repo; null when no repo */
  githubUrl: string | null;
  /** project_pages[0]?.url; null when none */
  project: string | null;
  /** "Apr 26" short label; null when published is null */
  date: string | null;
  /** ISO date string; null when published is null */
  publishedIso: string | null;
  /** ISO publication year, or null */
  year: number | null;
  /** /api/thumbnails url or paper-supplied thumbnail; null otherwise */
  thumbnailUrl: string | null;
  /** AI-generated TL;DR; null until the generation pipeline ships */
  tldr: string | null;
  /** number of arxiv versions; null until version-list is loaded */
  version: string;
  /** /api/v1/papers/trending velocity_24h, when known */
  velocity24h: number | null;
}

/**
 * Roll up multiple `Repository` rows into the single (stars, url) tuple the
 * `PaperCard` aside renders. Mirrors the legacy `Papers.tsx` logic: official
 * repos take priority; if none, fall back to most-starred unofficial.
 */
export function summarizeRepos(repos: Repository[] | undefined): {
  github: number | null;
  githubUrl: string | null;
} {
  if (!repos || repos.length === 0) {
    return { github: null, githubUrl: null };
  }
  const official = repos.filter((r) => r.is_official);
  const pool = official.length > 0 ? official : repos;
  const totalStars = pool.reduce((s, r) => s + (r.num_stars || 0), 0);
  const top = [...pool].sort((a, b) => (b.num_stars || 0) - (a.num_stars || 0))[0];
  return {
    github: totalStars > 0 ? totalStars : null,
    githubUrl: top?.url || null,
  };
}

function shortDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    const d = typeof iso === "string" ? parseISO(iso) : (iso as Date);
    return format(d, "MMM d, yyyy");
  } catch {
    return null;
  }
}

function isoYear(iso: string | null | undefined): number | null {
  if (!iso) return null;
  try {
    return parseISO(iso).getFullYear();
  } catch {
    return null;
  }
}

/**
 * Turn a backend `Paper` into the props the `PaperCard` component needs.
 */
export function transformPaperForCard(paper: Paper): PaperCardProps {
  const { github, githubUrl } = summarizeRepos(paper.repositories);
  const tags = (paper.tasks || []).map((t) => t.slug || "").filter(Boolean);
  return {
    id: paper.arxiv_id || paper.id,
    dbId: paper.id,
    title: paper.title,
    abstract: paper.abstract || "",
    authors: paper.authors || [],
    tags,
    citations: paper.citation_count || 0,
    github,
    githubUrl,
    project: paper.project_pages?.[0]?.url || null,
    date: shortDate(paper.published),
    publishedIso: paper.published || null,
    year: isoYear(paper.published),
    thumbnailUrl: paper.thumbnail_url || null,
    tldr: (paper as any).tldr || null,
    version: paper.version || "v1",
    velocity24h: null,
  };
}

/**
 * Turn the lightweight `/papers/trending` row into the same `PaperCard` shape.
 * Velocity comes from `trending.velocity_24h` directly (PLAN.md §4.6).
 */
export function transformTrendingForCard(t: TrendingPaper): PaperCardProps {
  return {
    id: t.arxiv_id || t.paper_id,
    dbId: t.paper_id,
    title: t.title,
    abstract: t.abstract || "",
    authors: t.authors || [],
    tags: (t.tasks || []).map((x) => x.slug).filter(Boolean),
    citations: 0,
    github: t.repository?.num_stars ?? null,
    githubUrl: t.repository?.url ?? null,
    project: null,
    date: shortDate(t.date_published),
    publishedIso: t.date_published,
    year: isoYear(t.date_published),
    thumbnailUrl: t.thumbnail_url || null,
    tldr: null,
    version: "v1",
    velocity24h: t.trending?.velocity_24h ?? null,
  };
}

/**
 * Rough TagChip props — `name` falls back to a humanized slug if the backend
 * task has no display name.
 */
export interface TagInfo {
  slug: string;
  label: string;
}

export function humanizeSlug(slug: string): string {
  const acronym = slug.toUpperCase();
  if (TASK_ACRONYMS.has(acronym)) return acronym;

  return slug.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const TASK_ACRONYMS = new Set(["OCR"]);

export function displayTaskName(name?: string, slug?: string): string {
  const label = name || humanizeSlug(slug || "");
  const normalizedSlug = slug?.toUpperCase();
  const normalizedLabel = label.toUpperCase();
  const isAcronymLabel = /^[A-Z0-9][A-Z0-9-]{1,}$/.test(label);

  if (
    isAcronymLabel ||
    (normalizedSlug && TASK_ACRONYMS.has(normalizedSlug)) ||
    TASK_ACRONYMS.has(normalizedLabel)
  ) {
    return normalizedLabel;
  }

  return label
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function tagInfoFromTask(task: Pick<Task, "name" | "slug">): TagInfo {
  const slug = task.slug || "";
  return { slug, label: task.name || humanizeSlug(slug) };
}
