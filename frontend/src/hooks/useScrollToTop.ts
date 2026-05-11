import { useEffect } from "react";
import { useLocation } from "react-router-dom";

/**
 * Scroll the window to the top whenever the route changes. Mirrors the v1
 * effect in App.jsx (window.scrollTo on view change).
 */
export function useScrollToTop(): void {
  const { pathname, search } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname, search]);
}
