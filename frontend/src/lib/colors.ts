/**
 * Deterministic hue derived from a string slug. Used by `TagChip` to keep the v2
 * "domain hue" affordance after we drop the hand-curated `DOMAINS[i].hue` table.
 *
 * Output is in the 0..360 hue range. The hash is FNV-1a, the same family of
 * deterministic non-crypto hashes the v2 source uses elsewhere (see `seedRand`
 * in components.tsx). Same input ⇒ same hue forever.
 */
export function hueFromSlug(slug: string): number {
  let h = 2166136261;
  const s = slug || "";
  for (let i = 0; i < s.length; i++) {
    h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  }
  return Math.abs(h) % 360;
}

/**
 * v2 "tag chip" palette: a soft pastel in oklch space at the given hue, with
 * a darker text and dot for contrast.
 */
export function chipColors(hue: number) {
  return {
    bg: `oklch(0.94 0.04 ${hue})`,
    text: `oklch(0.35 0.10 ${hue})`,
    dot: `oklch(0.55 0.12 ${hue})`,
  };
}
