/**
 * React hooks for fetching evaluation data using TanStack Query
 */

import { useQuery } from '@tanstack/react-query';
import { getEvaluationsByPaper, getEvaluationsByDataset, getEvaluations, type Evaluation } from '@/lib/api';

/**
 * Fetch all evaluations for a specific paper
 */
export function useEvaluationsByPaper(paperId: string | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: ['evaluations', 'paper', paperId],
    queryFn: () => {
      if (!paperId) throw new Error('Paper ID is required');
      return getEvaluationsByPaper(paperId);
    },
    enabled: enabled && !!paperId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

/**
 * Fetch all evaluations for a specific dataset (for benchmark leaderboards)
 */
export function useEvaluationsByDataset(datasetId: string | undefined, enabled: boolean = true) {
  return useQuery({
    queryKey: ['evaluations', 'dataset', datasetId],
    queryFn: () => {
      if (!datasetId) throw new Error('Dataset ID is required');
      return getEvaluationsByDataset(datasetId);
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
  page?: number;
  page_size?: number;
}) {
  return useQuery({
    queryKey: ['evaluations', params],
    queryFn: () => getEvaluations(params),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}
