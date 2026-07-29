import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/**
 * Scroll the window to the top whenever the pathname changes. Query-string
 * updates represent in-page state such as feed filters and sorting, so they
 * deliberately preserve the current scroll position.
 *
 * Skipped when the URL carries a hash (e.g. `/paper/98456#results`) so route
 * navigation doesn't fight intentional deep links: the page's own hash-scroll
 * logic is responsible for landing on the anchored section instead.
 */
export function useScrollToTop(): void {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (hash) return;
    window.scrollTo(0, 0);
  }, [pathname, hash]);
}
