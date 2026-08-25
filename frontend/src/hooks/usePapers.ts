import { keepPreviousData, useQuery, useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import type { Paper, PaperOrderBy, TrendingPaper } from '@/lib/api/papers.types';
import type { PaginatedResponse, PaperSearchFeedPage } from '@/lib/api/shared.types';
import { papersApi } from '@/lib/api/papers';

interface UsePapersParams {
  page?: number;
  page_size?: number;
  search?: string;
  order_by?: PaperOrderBy;
  order_dir?: 'asc' | 'desc';
  start_date?: string;
  end_date?: string;
  conference?: string;
  latest_only?: boolean;
  include_resources?: boolean;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  framework?: string;
  repository?: string;
  enabled?: boolean;
}

export function usePapers(params: UsePapersParams = {}) {
  const {
    page = 1,
    page_size = 20,
    search,
    order_by = 'date_published',
    order_dir = 'desc',
    start_date,
    end_date,
    conference,
    latest_only = true,
    include_resources = false,
    has_code = false,
    has_hf_artifacts = false,
    framework,
    repository,
    enabled = true,
  } = params;

  return useQuery<PaginatedResponse<Paper>, Error>({
    queryKey: ['papers', { page, page_size, search, order_by, order_dir, start_date, end_date, conference, latest_only, include_resources, has_code, has_hf_artifacts, framework, repository }],
    queryFn: () => papersApi.list({ page, page_size, search, order_by, order_dir, start_date, end_date, conference, latest_only, include_resources, has_code, has_hf_artifacts, framework, repository }),
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

export function usePaper(id: string, enabled: boolean = true) {
  return useQuery<Paper, Error>({
    queryKey: ['paper', id],
    queryFn: () => papersApi.get(id),
    enabled: enabled && !!id,
    staleTime: 10 * 60 * 1000, // 10 minutes
    refetchOnWindowFocus: false,
  });
}

export function usePaperByArxivId(arxivId: string, enabled: boolean = true) {
  const queryClient = useQueryClient();

  return useQuery<Paper, Error>({
    queryKey: ['paper-arxiv', arxivId],
    queryFn: () => papersApi.getByArxivId(arxivId, true), // Explicitly include resources
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
  start_date?: string;
  end_date?: string;
  conference?: string;
  latest_only?: boolean;
  include_resources?: boolean;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  framework?: string;
  repository?: string;
  enabled?: boolean;
}

export function useInfinitePapers(params: UseInfinitePapersParams = {}) {
  const {
    page_size = 20,
    search,
    order_by = 'date_published',
    order_dir = 'desc',
    start_date,
    end_date,
    conference,
    latest_only = true,
    include_resources = false,
    has_code = false,
    has_hf_artifacts = false,
    framework,
    repository,
    enabled = true,
  } = params;

  return useInfiniteQuery<PaginatedResponse<Paper>, Error>({
    queryKey: ['papers-infinite', { page_size, search, order_by, order_dir, start_date, end_date, conference, latest_only, include_resources, has_code, has_hf_artifacts, framework, repository }],
    queryFn: ({ pageParam = 1 }) =>
      papersApi.list({
        page: pageParam as number,
        page_size,
        search,
        order_by,
        order_dir,
        start_date,
        end_date,
        conference,
        latest_only,
        include_resources,
        has_code,
        has_hf_artifacts,
        framework,
        repository,
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled,
    staleTime: 5 * 60 * 1000, // 5 minutes
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

interface UseInfinitePaperSearchParams {
  q: string;
  order_by?: 'relevance' | 'date_published' | 'citation_count';
  start_date?: string;
  end_date?: string;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  enabled?: boolean;
}

export function useInfinitePaperSearch({
  q,
  order_by = 'relevance',
  start_date,
  end_date,
  has_code = false,
  has_hf_artifacts = false,
  enabled = true,
}: UseInfinitePaperSearchParams) {
  return useInfiniteQuery<PaperSearchFeedPage<Paper>, Error>({
    queryKey: ['paper-search-feed', { q, order_by, start_date, end_date, has_code, has_hf_artifacts }],
    queryFn: ({ pageParam = 1 }) => papersApi.searchFeed({
      q,
      page: pageParam as number,
      page_size: 20,
      order_by,
      start_date,
      end_date,
      has_code,
      has_hf_artifacts,
      mode: 'hybrid',
    }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: enabled && q.trim().length > 0,
    staleTime: 5 * 60 * 1000,
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
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  start_date?: string;
  end_date?: string;
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
    has_code = false,
    has_hf_artifacts = false,
    start_date,
    end_date,
    enabled = true,
  } = params;

  return useInfiniteQuery<PaginatedResponse<Paper>, Error>({
    queryKey: ['task-papers-infinite', taskId, { page_size, order_by, order_dir, latest_only, include_resources, has_code, has_hf_artifacts, start_date, end_date }],
    queryFn: ({ pageParam = 1 }) =>
      papersApi.forTask(taskId, {
        page: pageParam as number,
        page_size,
        order_by,
        order_dir,
        latest_only,
        include_resources,
        has_code,
        has_hf_artifacts,
        start_date,
        end_date,
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: enabled && !!taskId,
    staleTime: 5 * 60 * 1000, // 5 minutes
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

interface UseInfiniteConferencePapersParams {
  conferenceSlug: string;
  taskSlug?: string;
  presentation?: 'oral' | 'spotlight' | 'outstanding' | 'best_paper_finalist';
  page_size?: number;
  order_by?: 'trending' | 'date_published' | 'citation_count' | 'title';
  order_dir?: 'asc' | 'desc';
  latest_only?: boolean;
  include_resources?: boolean;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  start_date?: string;
  end_date?: string;
  enabled?: boolean;
}

export function useInfiniteConferencePapers(params: UseInfiniteConferencePapersParams) {
  const {
    conferenceSlug,
    taskSlug,
    presentation,
    page_size = 20,
    order_by = 'date_published',
    order_dir = 'desc',
    latest_only = true,
    include_resources = true,
    has_code = false,
    has_hf_artifacts = false,
    start_date,
    end_date,
    enabled = true,
  } = params;

  return useInfiniteQuery<PaginatedResponse<Paper>, Error>({
    queryKey: ['conference-papers-infinite', conferenceSlug, taskSlug, presentation, { page_size, order_by, order_dir, latest_only, include_resources, has_code, has_hf_artifacts, start_date, end_date }],
    queryFn: ({ pageParam = 1 }) =>
      papersApi.forConference(conferenceSlug, {
        task: taskSlug,
        presentation,
        page: pageParam as number,
        page_size,
        order_by,
        order_dir,
        latest_only,
        include_resources,
        has_code,
        has_hf_artifacts,
        start_date,
        end_date,
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: enabled && !!conferenceSlug,
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
    refetchOnWindowFocus: false,
  });
}

interface UseInfiniteOrganizationPapersParams {
  organizationSlug: string;
  taskSlug?: string;
  page_size?: number;
  order_by?: 'trending' | 'date_published' | 'citation_count' | 'title';
  order_dir?: 'asc' | 'desc';
  latest_only?: boolean;
  include_resources?: boolean;
  has_code?: boolean;
  has_hf_artifacts?: boolean;
  start_date?: string;
  end_date?: string;
  enabled?: boolean;
}

export function useInfiniteOrganizationPapers(params: UseInfiniteOrganizationPapersParams) {
  const {
    organizationSlug,
    taskSlug,
    page_size = 20,
    order_by = 'date_published',
    order_dir = 'desc',
    latest_only = true,
    include_resources = true,
    has_code = false,
    has_hf_artifacts = false,
    start_date,
    end_date,
    enabled = true,
  } = params;

  return useInfiniteQuery<PaginatedResponse<Paper>, Error>({
    queryKey: ['organization-papers-infinite', organizationSlug, taskSlug, { page_size, order_by, order_dir, latest_only, include_resources, has_code, has_hf_artifacts, start_date, end_date }],
    queryFn: ({ pageParam = 1 }) =>
      papersApi.forOrganization(organizationSlug, {
        task: taskSlug,
        page: pageParam as number,
        page_size,
        order_by,
        order_dir,
        latest_only,
        include_resources,
        has_code,
        has_hf_artifacts,
        start_date,
        end_date,
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: enabled && !!organizationSlug,
    staleTime: 5 * 60 * 1000,
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
    ['conference-papers-infinite'],
    ['organization-papers-infinite'],
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
    queryFn: () => papersApi.trending({ limit, max_age_days, min_velocity }),
    enabled,
    staleTime: 30 * 1000, // 30 seconds — thumbnails and velocity change frequently
    refetchInterval: 60 * 1000, // refresh while the feed stays open (thumbnails/velocity)
    refetchOnWindowFocus: true,
  });
}
