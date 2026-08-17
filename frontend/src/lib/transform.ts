/**
 * Backend → v2 UI transform helpers.
 *
 * The v2 components were originally written against hardcoded fixtures in
 * `data.js` with field names like `tags`, `github`, `date`, `institution`, …
 * (see PLAN.md §4 for the full mapping). After this migration, every view
 * fetches typed `Paper` / `Task` / `Method` / `Dataset` / `Evaluation` objects
 * from the paper API client and pipes them through these helpers so the rendered
 * components keep working without surgery on every view.
 *
 * Decisions captured in PLAN.md §4.1:
 *   - `submitter`, `comments`, `institution`, `upvotes` chip are dropped
 *     entirely (no schema, no UI affordance).
 *   - `tldr` and `num_pages` schema columns exist but no ingestion yet —
 *     the UI hides those panels when null.
 */

import { format, parseISO } from "date-fns";

import type { Task } from "./api/catalog.types";
import type { Paper, Repository, TrendingPaper } from "./api/papers.types";
import { assetUrl } from "./apiUrl";

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
  /** paper.methods[*] reduced to the fields MethodChip needs */
  methods: { id?: string; name: string; slug?: string }[];
  /** Organizations displayed as compact linked logos beside the paper title. */
  organizations: { name: string; slug: string; logoUrl: string | null }[];
  citations: number;
  /** stars for the featured repo; null when no repo */
  github: number | null;
  /** url of the featured repo; null when no repo */
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
  /** label for the most popular HF artifact category, e.g. "models"; null when none */
  hfKind: "models" | "datasets" | "spaces" | null;
  /** count for the most popular HF artifact category */
  hfCount: number;
  /** link to the most popular HF artifact category; null when none */
  hfUrl: string | null;
  /** Top-3 leaderboard placements, deduped by benchmark and sorted by rank.
   *  Powers the SOTA/#2/#3 badges between the abstract and the tags. */
  sotaRanks: { name: string; slug: string | null; rank: number }[];
}

const HF_KIND_LABELS: Record<string, "models" | "datasets" | "spaces"> = {
  model: "models",
  dataset: "datasets",
  space: "spaces",
};

function summarizeHfArtifacts(paper: Paper): {
  hfKind: "models" | "datasets" | "spaces" | null;
  hfCount: number;
  hfUrl: string | null;
} {
  const summary = paper.hf_artifact_summary;
  if (!summary || !summary.best_kind || !summary.best_url || summary.best_count <= 0) {
    return { hfKind: null, hfCount: 0, hfUrl: null };
  }
  return {
    hfKind: HF_KIND_LABELS[summary.best_kind] ?? null,
    hfCount: summary.best_count,
    hfUrl: summary.best_url,
  };
}

/**
 * Pick the single repository represented by the `Code` CTA and paper-card
 * GitHub stats. Official repos take priority; if none exist, fall back to the
 * most-starred linked repo.
 */
export function summarizeRepos(repos: Repository[] | undefined): {
  github: number | null;
  githubUrl: string | null;
  velocity24h: number | null;
} {
  if (!repos || repos.length === 0) {
    return { github: null, githubUrl: null, velocity24h: null };
  }
  const official = repos.filter((r) => r.is_official);
  const pool = official.length > 0 ? official : repos;
  const top = [...pool].sort((a, b) => (b.num_stars || 0) - (a.num_stars || 0))[0];
  return {
    github: top && top.num_stars > 0 ? top.num_stars : null,
    githubUrl: top?.url || null,
    velocity24h: top?.trending_score ?? null,
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
  const { github, githubUrl, velocity24h } = summarizeRepos(paper.repositories);
  const { hfKind, hfCount, hfUrl } = summarizeHfArtifacts(paper);
  const tags = (paper.tasks || []).map((t) => t.slug || "").filter(Boolean);
  const methods = (paper.methods || []).map((m) => ({
    id: m.id,
    name: m.name,
    slug: m.slug,
  }));
  const sotaRanks = (paper.leaderboard_ranks || [])
    .filter((r) => r.best_rank >= 1 && r.best_rank <= 3)
    .map((r) => ({
      name: r.dataset_name,
      slug: r.dataset_slug || null,
      rank: r.best_rank,
    }));
  return {
    id: paper.arxiv_id || paper.id,
    dbId: paper.id,
    title: paper.title,
    abstract: paper.abstract || "",
    authors: paper.authors || [],
    tags,
    methods,
    organizations: (paper.organizations || []).map((organization) => ({
      name: organization.name,
      slug: organization.slug,
      logoUrl: assetUrl(organization.logo_url) || null,
    })),
    citations: paper.citation_count || 0,
    github,
    githubUrl,
    project: paper.project_pages?.[0]?.url || null,
    date: shortDate(paper.published),
    publishedIso: paper.published || null,
    year: isoYear(paper.published),
    thumbnailUrl: assetUrl(paper.thumbnail_url) || null,
    tldr: paper.tldr || null,
    version: paper.version || "v1",
    velocity24h,
    hfKind,
    hfCount,
    hfUrl,
    sotaRanks,
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
    methods: [],
    organizations: [],
    citations: 0,
    github: t.repository?.num_stars ?? null,
    githubUrl: t.repository?.url ?? null,
    project: null,
    date: shortDate(t.date_published),
    publishedIso: t.date_published,
    year: isoYear(t.date_published),
    thumbnailUrl: assetUrl(t.thumbnail_url) || null,
    tldr: null,
    version: "v1",
    velocity24h: t.trending?.velocity_24h ?? null,
    hfKind: null,
    hfCount: 0,
    hfUrl: null,
    sotaRanks: [],
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
  const displayOverride = TASK_DISPLAY_NAMES.get(slug.toLowerCase());
  if (displayOverride) return displayOverride;

  const acronym = slug.toUpperCase();
  if (TASK_ACRONYMS.has(acronym)) return acronym;

  return slug.replace(/[-_]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const TASK_ACRONYMS = new Set(["OCR"]);
const TASK_DISPLAY_NAMES = new Map([
  ["3d-tracking", "3D Tracking"],
  ["point-tracking", "2D Point Tracking"],
  ["3d-generation", "3D generation"],
  ["3d-understanding", "3D understanding"],
  ["3d-semantic-segmentation", "3D semantic segmentation"],
  ["3d-instance-segmentation", "3D instance segmentation"],
  ["3d-object-detection", "3D object detection"],
  ["text-to-sql", "Text-to-SQL"],
]);

export function displayTaskName(name?: string, slug?: string): string {
  const label = name || humanizeSlug(slug || "");
  const displayOverride = TASK_DISPLAY_NAMES.get(slug?.toLowerCase() || taskKey(label));
  if (displayOverride) return displayOverride;

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

function taskKey(value: string): string {
  return value.trim().toLowerCase().replace(/[\s_]+/g, "-");
}

export function tagInfoFromTask(task: Pick<Task, "name" | "slug">): TagInfo {
  const slug = task.slug || "";
  return { slug, label: task.name || humanizeSlug(slug) };
}
