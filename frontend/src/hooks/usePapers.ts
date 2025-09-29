import { useQuery, useInfiniteQuery } from '@tanstack/react-query';
import { apiClient, Paper, PaginatedResponse } from '@/lib/api';

interface UsePapersParams {
  page?: number;
  page_size?: number;
  search?: string;
  order_by?: 'date_published' | 'citation_count' | 'title';
  order_dir?: 'asc' | 'desc';
  published_after?: string;
  published_before?: string;
  conference?: string;
  latest_only?: boolean;
  include_resources?: boolean;
  enabled?: boolean;
}

export function usePapers(params: UsePapersParams = {}) {
  const {
    page = 1,
    page_size = 20,
    search,
    order_by = 'date_published',
    order_dir = 'desc',
    published_after,
    published_before,
    conference,
    latest_only = true,
    include_resources = false,
    enabled = true,
  } = params;

  return useQuery<PaginatedResponse<Paper>, Error>({
    queryKey: ['papers', { page, page_size, search, order_by, order_dir, published_after, published_before, conference, latest_only, include_resources }],
    queryFn: () => apiClient.getPapers({ page, page_size, search, order_by, order_dir, published_after, published_before, conference, latest_only, include_resources }),
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
  });
}

export function usePaper(id: string, enabled: boolean = true) {
  return useQuery<Paper, Error>({
    queryKey: ['paper', id],
    queryFn: () => apiClient.getPaper(id),
    enabled: enabled && !!id,
    staleTime: 10 * 60 * 1000, // 10 minutes
    refetchOnWindowFocus: false,
  });
}

export function usePaperByArxivId(arxivId: string, enabled: boolean = true) {
  return useQuery<Paper, Error>({
    queryKey: ['paper-arxiv', arxivId],
    queryFn: () => apiClient.getPaperByArxivId(arxivId, true), // Explicitly include resources
    enabled: enabled && !!arxivId,
    staleTime: 10 * 60 * 1000, // 10 minutes
    refetchOnWindowFocus: false,
  });
}

interface UseInfinitePapersParams {
  page_size?: number;
  search?: string;
  order_by?: 'date_published' | 'citation_count' | 'title';
  order_dir?: 'asc' | 'desc';
  published_after?: string;
  published_before?: string;
  conference?: string;
  latest_only?: boolean;
  include_resources?: boolean;
  enabled?: boolean;
}

export function useInfinitePapers(params: UseInfinitePapersParams = {}) {
  const {
    page_size = 20,
    search,
    order_by = 'date_published',
    order_dir = 'desc',
    published_after,
    published_before,
    conference,
    latest_only = true,
    include_resources = false,
    enabled = true,
  } = params;

  return useInfiniteQuery<PaginatedResponse<Paper>, Error>({
    queryKey: ['papers-infinite', { page_size, search, order_by, order_dir, published_after, published_before, conference, latest_only, include_resources }],
    queryFn: ({ pageParam = 1 }) =>
      apiClient.getPapers({
        page: pageParam as number,
        page_size,
        search,
        order_by,
        order_dir,
        published_after,
        published_before,
        conference,
        latest_only,
        include_resources
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
    refetchOnWindowFocus: false,
  });
}
