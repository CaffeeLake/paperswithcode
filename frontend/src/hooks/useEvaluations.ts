/**
 * React hooks for fetching evaluation data using TanStack Query
 */

import { useQuery } from '@tanstack/react-query';
import { evaluationsApi } from '@/lib/api/evaluations';

/**
 * Fetch all evaluations for a specific paper
 */
export function useEvaluationsByPaper(paperId: string | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: ['evaluations', 'paper', paperId],
    queryFn: () => {
      if (!paperId) throw new Error('Paper ID is required');
      return evaluationsApi.byPaper(paperId);
    },
    enabled: enabled && !!paperId,
    staleTime: 0,
    refetchOnMount: 'always',
  });
}

/**
 * Fetch all evaluations for a specific dataset (for benchmark leaderboards)
 */
export function useEvaluationsByDataset(
  datasetId: string | undefined,
  bestMetric?: string,
  enabled: boolean = true
) {
  return useQuery({
    queryKey: ['evaluations', 'dataset', datasetId, bestMetric],
    queryFn: () => {
      if (!datasetId) throw new Error('Dataset ID is required');
      return evaluationsApi.byDataset(datasetId, bestMetric);
    },
    enabled: enabled && !!datasetId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch evaluations with custom filters
 */
export function useEvaluations(params?: {
  paper_id?: number;
  task_id?: number;
  dataset_id?: number;
  external?: boolean;
  page?: number;
  page_size?: number;
}) {
  return useQuery({
    queryKey: ['evaluations', params],
    queryFn: () => evaluationsApi.list(params),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch evaluations for a specific task and dataset (for leaderboards)
 */
export function useTaskDatasetEvaluations(
  taskId: string | number | undefined,
  datasetId: string | number | undefined,
  enabled: boolean = true
) {
  return useQuery({
    queryKey: ['evaluations', 'task', taskId, 'dataset', datasetId],
    queryFn: () => {
      const params: { task_id?: number; dataset_id?: number; page_size: number } = {
        page_size: 100,
      };
      if (taskId) params.task_id = typeof taskId === 'string' ? parseInt(taskId) : taskId;
      if (datasetId) params.dataset_id = typeof datasetId === 'string' ? parseInt(datasetId) : datasetId;
      return evaluationsApi.list(params);
    },
    enabled: enabled && !!taskId && !!datasetId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
