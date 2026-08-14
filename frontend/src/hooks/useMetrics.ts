/**
 * React hooks for fetching metric definitions and directions using TanStack Query
 */

import { useQuery } from '@tanstack/react-query';
import { catalogApi } from '@/lib/api/catalog';

/**
 * Fetch metric directions mapping (optimized for quick lookup).
 *
 * Returns a map of metric names to their ranking directions:
 * - 'higher_is_better': Higher values rank better (AP, Accuracy, F1, etc.)
 * - 'lower_is_better': Lower values rank better (WER, Error Rate, Perplexity, etc.)
 *
 * This hook caches the result indefinitely since metric directions rarely change.
 */
export function useMetricDirections() {
  return useQuery({
    queryKey: ['metrics', 'directions'],
    queryFn: () => catalogApi.metricDirections(),
    staleTime: Infinity, // Metric directions rarely change, cache forever
    gcTime: Infinity, // Keep in cache forever (formerly cacheTime)
  });
}

/**
 * Get the direction for a specific metric name.
 * Defaults to 'higher_is_better' if metric is not found.
 */
export function useMetricDirection(metricName: string | undefined): 'higher_is_better' | 'lower_is_better' {
  const { data } = useMetricDirections();

  if (!metricName || !data?.directions) {
    return 'higher_is_better'; // Default assumption
  }

  return data.directions[metricName] || 'higher_is_better';
}
