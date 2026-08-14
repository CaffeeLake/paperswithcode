import { useQuery } from '@tanstack/react-query';
import type { Dataset } from '@/lib/api/catalog.types';
import { catalogApi } from '@/lib/api/catalog';

export function useTaskDatasets(taskId: string | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: ['datasets', 'task', taskId],
    queryFn: () => catalogApi.listDatasets({ task: taskId, page_size: 100 }),
    enabled: !!taskId && enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useDataset(datasetId: string | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: ['dataset', datasetId],
    queryFn: () => catalogApi.getDataset(datasetId!),
    enabled: !!datasetId && enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useDatasetBySlug(slug: string | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: ['dataset', 'slug', slug],
    queryFn: () => catalogApi.getDatasetBySlug(slug!),
    enabled: !!slug && enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export type { Dataset };
