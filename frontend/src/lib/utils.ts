import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Format a metric value for display: at most 2 decimal places, with fewer
// decimals for larger magnitudes so headline numbers stay readable. Accepts
// strings (as returned by the evaluations API) and falls back to the raw value
// when it isn't a finite number.
export function formatMetricValue(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (!Number.isFinite(n)) return String(v);
  if (Math.abs(n) >= 100) return n.toFixed(0);
  if (Math.abs(n) >= 10) return n.toFixed(1);
  return n.toFixed(2);
}
