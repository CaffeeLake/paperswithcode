/**
 * React hooks for fetching dataset data using TanStack Query
 */

import { useQuery } from '@tanstack/react-query';
import { getDatasets, getDataset, getDatasetBySlug, type Dataset } from '@/lib/api';

/**
 * Fetch a single dataset by ID
 */
export function useDataset(datasetId: string | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: ['dataset', datasetId],
    queryFn: () => {
      if (!datasetId) throw new Error('Dataset ID is required');
      return getDataset(datasetId);
    },
    enabled: enabled && !!datasetId,
    staleTime: 10 * 60 * 1000, // 10 minutes (datasets rarely change)
  });
}

/**
 * Fetch a single dataset by slug (for URL routing)
 */
export function useDatasetBySlug(slug: string | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: ['dataset', 'slug', slug],
    queryFn: () => {
      if (!slug) throw new Error('Dataset slug is required');
      return getDatasetBySlug(slug);
    },
    enabled: enabled && !!slug,
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}

/**
 * Fetch datasets with filters and pagination
 */
export function useDatasets(params?: {
  page?: number;
  page_size?: number;
  q?: string;
  name?: string;
  task?: string;
}) {
  return useQuery({
    queryKey: ['datasets', params],
    queryFn: () => getDatasets(params),
    staleTime: 10 * 60 * 1000, // 10 minutes
  });
}
