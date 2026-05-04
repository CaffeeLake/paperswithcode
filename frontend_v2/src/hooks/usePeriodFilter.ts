import { useMemo, useState } from "react";
import { startOfDay, startOfMonth, startOfWeek } from "date-fns";

/**
 * Period switcher (Today / This Week / This Month / All Time) for the FeedView
 * and /papers list. Boundary semantics live in the visitor's local TZ — see
 * PLAN.md §7.1.
 *
 *   - Today      = startOfDay(now) local
 *   - This Week  = startOfWeek(now, { weekStartsOn: 1 }) — ISO Mon 00:00 local
 *   - This Month = startOfMonth(now) local
 *   - All Time   = no filter
 *
 * Boundaries are computed once per mount; they only roll over at local
 * midnight / Monday / 1st-of-month, which is fine because the cache key
 * includes `publishedAfter` and a stale key just means a sub-second extra
 * fetch when the boundary actually moves.
 */
export type Period = "Today" | "This Week" | "This Month" | "All Time";

export const PERIODS: Period[] = ["Today", "This Week", "This Month", "All Time"];

interface PeriodFilter {
  period: Period;
  setPeriod: (p: Period) => void;
  /** ISO UTC string suitable for `published_after` query param, or undefined */
  publishedAfter: string | undefined;
}

export function usePeriodFilter(initial: Period = "All Time"): PeriodFilter {
  const [period, setPeriod] = useState<Period>(initial);

  const publishedAfter = useMemo(() => {
    const now = new Date();
    let cutoff: Date | null = null;
    if (period === "Today") cutoff = startOfDay(now);
    else if (period === "This Week") cutoff = startOfWeek(now, { weekStartsOn: 1 });
    else if (period === "This Month") cutoff = startOfMonth(now);
    return cutoff ? cutoff.toISOString() : undefined;
  }, [period]);

  return { period, setPeriod, publishedAfter };
}
