import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/**
 * Scroll the window to the top whenever the route changes. Mirrors the v1
 * effect in App.jsx (window.scrollTo on view change).
 *
 * Skipped when the URL carries a hash (e.g. `/paper/98456#results`) so route
 * navigation doesn't fight intentional deep links: the page's own hash-scroll
 * logic is responsible for landing on the anchored section instead.
 */
export function useScrollToTop(): void {
  const { pathname, search, hash } = useLocation();
  useEffect(() => {
    if (hash) return;
    window.scrollTo(0, 0);
  }, [pathname, search, hash]);
}
