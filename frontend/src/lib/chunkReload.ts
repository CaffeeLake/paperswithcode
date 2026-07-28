const CHUNK_RELOAD_KEY = "pwc:chunk-reload-at";
const CHUNK_RELOAD_COOLDOWN_MS = 60_000;

export function shouldReloadChunk(
  previousReload: string | null,
  now: number,
): boolean {
  if (!previousReload) return true;
  const timestamp = Number(previousReload);
  return !Number.isFinite(timestamp) || now - timestamp >= CHUNK_RELOAD_COOLDOWN_MS;
}

/**
 * Recover when an immutable deployment rotates out a lazy-loaded chunk that an
 * already-open tab still references. Vite emits `vite:preloadError` before the
 * rejected dynamic import reaches React, giving the page one safe opportunity
 * to fetch the current no-store HTML shell.
 */
export function installChunkReloadRecovery(): () => void {
  if (typeof window === "undefined") return () => undefined;

  const onPreloadError = (event: Event) => {
    const now = Date.now();
    if (!shouldReloadChunk(sessionStorage.getItem(CHUNK_RELOAD_KEY), now)) return;

    event.preventDefault();
    sessionStorage.setItem(CHUNK_RELOAD_KEY, String(now));
    window.location.reload();
  };

  window.addEventListener("vite:preloadError", onPreloadError);
  const cooldown = window.setTimeout(
    () => sessionStorage.removeItem(CHUNK_RELOAD_KEY),
    CHUNK_RELOAD_COOLDOWN_MS,
  );

  return () => {
    window.removeEventListener("vite:preloadError", onPreloadError);
    window.clearTimeout(cooldown);
  };
}
