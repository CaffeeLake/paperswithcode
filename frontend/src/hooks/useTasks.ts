/**
 * React Query hooks for task data
 */

import { useQuery } from '@tanstack/react-query';
import { getTask, getTasks, getTaskChildren, getTaskParents } from '@/lib/api';

/**
 * Hook to fetch a single task by ID or slug
 */
export const useTask = (taskId: string | undefined, enabled: boolean = true) => {
  return useQuery({
    queryKey: ['task', taskId],
    queryFn: () => {
      if (!taskId) throw new Error('Task ID is required');
      return getTask(taskId);
    },
    enabled: enabled && !!taskId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};

/**
 * Hook to fetch all tasks with optional filtering
 */
export const useTasks = (params?: {
  page?: number;
  page_size?: number;
  q?: string;
  name?: string;
  area_id?: number;
  parent_id?: number;
  level?: number;
  ordering?: string;
}) => {
  return useQuery({
    queryKey: ['tasks', params],
    queryFn: () => getTasks(params),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};

/**
 * Hook to fetch child tasks of a specific task
 */
export const useTaskChildren = (
  taskId: string | undefined,
  params?: {
    page?: number;
    page_size?: number;
  }
) => {
  return useQuery({
    queryKey: ['task-children', taskId, params],
    queryFn: () => {
      if (!taskId) throw new Error('Task ID is required');
      return getTaskChildren(taskId, params);
    },
    enabled: !!taskId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};

/**
 * Hook to fetch parent tasks of a specific task
 */
export const useTaskParents = (taskId: string | undefined) => {
  return useQuery({
    queryKey: ['task-parents', taskId],
    queryFn: () => {
      if (!taskId) throw new Error('Task ID is required');
      return getTaskParents(taskId);
    },
    enabled: !!taskId,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};
