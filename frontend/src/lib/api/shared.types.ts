import type { Task } from "./catalog.types";

export interface PaginatedResponse<T> {
  count: number;
  next_page: number | null;
  previous_page: number | null;
  results: T[];
  scope?: {
    kind: 'framework' | 'repository';
    repository?: string | null;
    framework_slug?: string | null;
    framework_name?: string | null;
    github_url?: string | null;
    num_stars?: number | null;
    introducing_paper_arxiv_id?: string | null;
    recommended_tasks?: Task[];
  } | null;
}

export interface SearchPage<T> {
  next_page: number | null;
  previous_page: number | null;
  results: T[];
}

export interface PaperSearchFeedPage<T> extends SearchPage<T> {
  applied_filters: Record<string, string>;
  requested_mode: 'keyword' | 'semantic' | 'hybrid';
  applied_mode: 'keyword' | 'semantic' | 'hybrid';
  order_by: 'relevance' | 'date_published' | 'citation_count';
  cap: number;
  cap_reached: boolean;
  exhausted: boolean;
}
