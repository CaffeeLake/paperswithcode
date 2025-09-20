/**
 * API client for PapersWithCode backend
 */

const API_BASE_URL = 'http://167.235.148.241:8000/api/v1';

export interface Paper {
  id: string;
  arxiv_id: string;
  url_abs: string;
  url_pdf: string;
  thumbnail_url?: string;
  title: string;
  abstract: string;
  authors: string[];
  published: string;
  conference?: string;
  conference_url_abs?: string;
  conference_url_pdf?: string;
  proceeding?: string;
  version: string;
  is_latest_version: boolean;
  citation_count: number;
  semantic_scholar_id?: string;
}

export interface Author {
  id: string;
  name: string;
  paper_count: number;
  citation_count: number;
  h_index: number;
  semantic_scholar_id?: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next_page: number | null;
  previous_page: number | null;
  results: T[];
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        ...options,
      });

      if (!response.ok) {
        throw new Error(`API request failed: ${response.status} ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error(`API request to ${url} failed:`, error);
      throw error;
    }
  }

  // Papers API
  async getPapers(params?: {
    page?: number;
    page_size?: number;
    search?: string;
    order_by?: 'date_published' | 'citation_count' | 'title';
    order_dir?: 'asc' | 'desc';
    published_after?: string;
    published_before?: string;
    conference?: string;
    latest_only?: boolean;
  }): Promise<PaginatedResponse<Paper>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.search) searchParams.append('search', params.search);
    if (params?.order_by) searchParams.append('order_by', params.order_by);
    if (params?.order_dir) searchParams.append('order_dir', params.order_dir);
    if (params?.published_after) searchParams.append('published_after', params.published_after);
    if (params?.published_before) searchParams.append('published_before', params.published_before);
    if (params?.conference) searchParams.append('conference', params.conference);
    if (params?.latest_only !== undefined) searchParams.append('latest_only', params.latest_only.toString());

    const endpoint = `/papers/${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Paper>>(endpoint);
  }

  async getPaper(id: string): Promise<Paper> {
    return this.request<Paper>(`/papers/${id}`);
  }

  // Authors API
  async getAuthors(params?: {
    limit?: number;
    offset?: number;
    search?: string;
    sort_by?: 'name' | 'paper_count' | 'citation_count' | 'h_index';
    sort_order?: 'asc' | 'desc';
  }): Promise<PaginatedResponse<Author>> {
    const searchParams = new URLSearchParams();

    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.offset) searchParams.append('offset', params.offset.toString());
    if (params?.search) searchParams.append('search', params.search);
    if (params?.sort_by) searchParams.append('sort_by', params.sort_by);
    if (params?.sort_order) searchParams.append('sort_order', params.sort_order);

    const endpoint = `/authors${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Author>>(endpoint);
  }

  async getAuthor(id: string): Promise<Author> {
    return this.request<Author>(`/authors/${id}`);
  }

  // Thumbnails API
  async generateThumbnail(paperId: string): Promise<{ thumbnail_url?: string; status: string; message: string }> {
    const url = `http://167.235.148.241:8000/api/thumbnails/generate/${paperId}`;
    const response = await fetch(url, { method: 'POST' });
    if (!response.ok) {
      throw new Error(`Thumbnail generation failed: ${response.status}`);
    }
    return await response.json();
  }

  async getThumbnailStatus(paperId: string): Promise<{ has_thumbnail: boolean; thumbnail_url?: string; arxiv_id?: string; version?: string }> {
    const url = `http://167.235.148.241:8000/api/thumbnails/status/${paperId}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Thumbnail status check failed: ${response.status}`);
    }
    return await response.json();
  }

  // Health check
  async healthCheck(): Promise<{ status: string; service: string }> {
    const url = `http://167.235.148.241:8000/health`; // Use VPS IP for health check
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Health check failed: ${response.status}`);
    }
    return await response.json();
  }
}

// Create and export a singleton instance
export const apiClient = new ApiClient();

// Export individual API functions for convenience
export const {
  getPapers,
  getPaper,
  getAuthors,
  getAuthor,
  generateThumbnail,
  getThumbnailStatus,
  healthCheck,
} = apiClient;
