import { apiUrl } from "@/lib/apiUrl";

export interface GitHubRepo {
  owner: string;
  repository: string;
  repoId: string;
  url: string;
}

export interface GitHubRepoPreview {
  description: string | null;
  stars: number;
  forks: number;
  language: string | null;
  archived: boolean;
  avatarUrl: string;
}

const GITHUB_HOSTS = new Set(["github.com", "www.github.com"]);

export function parseGitHubRepoUrl(value: string): GitHubRepo | null {
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  if (url.protocol !== "https:" || !GITHUB_HOSTS.has(url.hostname)) return null;

  const parts = url.pathname.split("/").filter(Boolean);
  if (parts.length !== 2) return null;

  let owner: string;
  let repository: string;
  try {
    owner = decodeURIComponent(parts[0]);
    repository = decodeURIComponent(parts[1]).replace(/\.git$/, "");
  } catch {
    return null;
  }
  if (
    !/^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,38})$/.test(owner) ||
    !/^[a-zA-Z0-9._-]{1,100}$/.test(repository)
  ) {
    return null;
  }

  const repoId = `${owner}/${repository}`;
  const encodedRepoId = [owner, repository].map(encodeURIComponent).join("/");
  return {
    owner,
    repository,
    repoId,
    url: `https://github.com/${encodedRepoId}`,
  };
}

export async function fetchGitHubRepoPreview(
  repo: GitHubRepo,
  signal?: AbortSignal,
): Promise<GitHubRepoPreview> {
  const encodedRepoId = [repo.owner, repo.repository]
    .map(encodeURIComponent)
    .join("/");
  const response = await fetch(
    apiUrl(`/api/v1/github/repositories/${encodedRepoId}/preview`),
    { signal },
  );
  if (!response.ok) throw new Error(`GitHub repository lookup failed: ${response.status}`);

  const payload = await response.json() as Record<string, unknown>;
  return {
    description: typeof payload.description === "string" ? payload.description : null,
    stars: typeof payload.stars === "number" ? payload.stars : 0,
    forks: typeof payload.forks === "number" ? payload.forks : 0,
    language: typeof payload.language === "string" ? payload.language : null,
    archived: payload.archived === true,
    avatarUrl: typeof payload.avatar_url === "string" ? payload.avatar_url : "",
  };
}

/** Canonical GitHub repo URL (owner/repo only, lowercase) for deduping. */
export function normalizeGithubUrl(url: string): string | null {
  const trimmed = url.trim();
  if (!trimmed) return null;

  let href = trimmed;
  if (!href.startsWith("http://") && !href.startsWith("https://")) {
    href = `https://${href}`;
  }

  try {
    const parsed = new URL(href);
    if (parsed.hostname.toLowerCase() !== "github.com") return null;
    const parts = parsed.pathname.split("/").filter(Boolean);
    if (parts.length < 2) return null;
    const owner = parts[0].toLowerCase();
    let name = parts[1].toLowerCase();
    if (name.endsWith(".git")) {
      name = name.slice(0, -4);
    }
    return `https://github.com/${owner}/${name}`;
  } catch {
    return null;
  }
}

export function githubUrlsMatch(a: string, b: string): boolean {
  const normA = normalizeGithubUrl(a);
  const normB = normalizeGithubUrl(b);
  if (normA && normB) return normA === normB;
  return a.trim() === b.trim();
}
