import { keepPreviousData, useQuery, useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient, Paper, PaginatedResponse, PaperOrderBy, PaperTimeWindow, TrendingPaper } from '@/lib/api';

interface UsePapersParams {
  page?: number;
  page_size?: number;
  search?: string;
  order_by?: PaperOrderBy;
  order_dir?: 'asc' | 'desc';
  time?: PaperTimeWindow;
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
    time,
    published_after,
    published_before,
    conference,
    latest_only = true,
    include_resources = false,
    enabled = true,
  } = params;

  return useQuery<PaginatedResponse<Paper>, Error>({
    queryKey: ['papers', { page, page_size, search, order_by, order_dir, time, published_after, published_before, conference, latest_only, include_resources }],
    queryFn: () => apiClient.getPapers({ page, page_size, search, order_by, order_dir, time, published_after, published_before, conference, latest_only, include_resources }),
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
    placeholderData: keepPreviousData,
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
  const queryClient = useQueryClient();

  return useQuery<Paper, Error>({
    queryKey: ['paper-arxiv', arxivId],
    queryFn: () => apiClient.getPaperByArxivId(arxivId, true), // Explicitly include resources
    enabled: enabled && !!arxivId,
    staleTime: 10 * 60 * 1000, // 10 minutes
    placeholderData: () => {
      const cachedPaper = findPaperInCachedQueries(queryClient, arxivId);
      return cachedPaper;
    },
    refetchOnWindowFocus: false,
  });
}

interface UseInfinitePapersParams {
  page_size?: number;
  search?: string;
  order_by?: PaperOrderBy;
  order_dir?: 'asc' | 'desc';
  time?: PaperTimeWindow;
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
    time,
    published_after,
    published_before,
    conference,
    latest_only = true,
    include_resources = false,
    enabled = true,
  } = params;

  return useInfiniteQuery<PaginatedResponse<Paper>, Error>({
    queryKey: ['papers-infinite', { page_size, search, order_by, order_dir, time, published_after, published_before, conference, latest_only, include_resources }],
    queryFn: ({ pageParam = 1 }) =>
      apiClient.getPapers({
        page: pageParam as number,
        page_size,
        search,
        order_by,
        order_dir,
        time,
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
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

interface UseInfiniteTaskPapersParams {
  taskId: string;
  page_size?: number;
  order_by?: 'trending' | 'date_published' | 'citation_count' | 'title';
  order_dir?: 'asc' | 'desc';
  latest_only?: boolean;
  include_resources?: boolean;
  enabled?: boolean;
}

export function useInfiniteTaskPapers(params: UseInfiniteTaskPapersParams) {
  const {
    taskId,
    page_size = 20,
    order_by = 'date_published',
    order_dir = 'desc',
    latest_only = true,
    include_resources = true,
    enabled = true,
  } = params;

  return useInfiniteQuery<PaginatedResponse<Paper>, Error>({
    queryKey: ['task-papers-infinite', taskId, { page_size, order_by, order_dir, latest_only, include_resources }],
    queryFn: ({ pageParam = 1 }) =>
      apiClient.getTaskPapers(taskId, {
        page: pageParam as number,
        page_size,
        order_by,
        order_dir,
        latest_only,
        include_resources
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: enabled && !!taskId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

interface UseTrendingPapersParams {
  limit?: number;
  max_age_days?: number;
  min_velocity?: number;
  enabled?: boolean;
}

function findPaperInCachedQueries(
  queryClient: ReturnType<typeof useQueryClient>,
  arxivId: string,
): Paper | undefined {
  const queryPrefixes = [
    ['papers'],
    ['papers-infinite'],
    ['task-papers-infinite'],
    ['method-papers-infinite'],
  ];

  for (const queryKey of queryPrefixes) {
    for (const [, data] of queryClient.getQueriesData({ queryKey })) {
      const paper = findPaperInQueryData(data, arxivId);
      if (paper) return paper;
    }
  }

  return undefined;
}

function findPaperInQueryData(data: unknown, arxivId: string): Paper | undefined {
  if (!data || typeof data !== 'object') return undefined;

  const paginated = data as Partial<PaginatedResponse<Paper>>;
  const match = paginated.results?.find((paper) => paper.arxiv_id === arxivId);
  if (match) return match;

  const infinite = data as { pages?: Array<Partial<PaginatedResponse<Paper>>> };
  return infinite.pages
    ?.flatMap((page) => page?.results ?? [])
    .find((paper) => paper.arxiv_id === arxivId);
}

export function useTrendingPapers(params: UseTrendingPapersParams = {}) {
  const {
    limit = 20,
    max_age_days = 180,
    min_velocity,
    enabled = true,
  } = params;

  return useQuery<TrendingPaper[], Error>({
    queryKey: ['trending-papers', { limit, max_age_days, min_velocity }],
    queryFn: () => apiClient.getTrendingPapers({ limit, max_age_days, min_velocity }),
    enabled,
    staleTime: 30 * 1000, // 30 seconds — thumbnails and velocity change frequently
    refetchOnWindowFocus: true,
  });
}
