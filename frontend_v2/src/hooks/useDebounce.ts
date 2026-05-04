import { useEffect, useState } from "react";

/**
 * Standard string debounce. 300ms by default — matches the v1 PaperSearch
 * component (PLAN.md §6).
 */
export function useDebounce<T>(value: T, delayMs = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);

  return debounced;
}
