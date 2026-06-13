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
