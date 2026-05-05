/**
 * API client for PapersWithCode backend
 */

const API_BASE_URL = '/api/v1';

export interface Repository {
  id: string;
  paper_id: string;
  url: string;
  owner?: string;
  name?: string;
  num_stars: number;
  is_official: boolean;
  source: string;
  created_at?: string;
  updated_at?: string;
}

export interface ProjectPage {
  id: string;
  paper_id: string;
  url: string;
  is_official: boolean;
  source: string;
  created_at?: string;
  updated_at?: string;
}

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
  repositories?: Repository[];
  project_pages?: ProjectPage[];
  tasks?: Task[];
  methods?: Method[];
}

export interface Author {
  id: string;
  name: string;
  paper_count: number;
  citation_count: number;
  h_index: number;
  semantic_scholar_id?: string;
}

export interface Area {
  id: string;
  name: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Task {
  id: string;
  name: string;
  description?: string;
  slug?: string;
  parent_id?: string;
  area_id?: string;
  level: number;
  paper_count?: number;
  image_url?: string;
  image_credit?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Method {
  id: string;
  name: string;
  slug?: string;
  full_name?: string;
  description?: string;
  area_id?: string;
  introduced_year?: number;
  source_url?: string;
  source_title?: string;
  code_snippet_url?: string;
  image_url?: string;
  image_credit?: string;
  collection_name?: string;
  collection_description?: string;
  collection_parent?: string;
  paper_count?: number;
  created_at?: string;
  updated_at?: string;
}

export interface Dataset {
  id: string;
  name: string;
  full_name?: string;
  description?: string;
  url?: string;
  hf_url?: string;
  slug?: string;
  paper_count?: number;
  created_at?: string;
  updated_at?: string;
}

export interface Evaluation {
  id: string;
  paper_id: string;
  task_id: string;
  dataset_id: string;
  model_name?: string;
  methodology?: string;
  metrics: Record<string, string | number>;
  uses_additional_data: boolean;
  best_rank?: number;
  best_metric?: string;
  evaluated_on?: string;
  external_source_url?: string;
  created_at: string;
  updated_at: string;
  paper_title?: string;
  paper_arxiv_id?: string;
  paper_published_date?: string;
  code_url?: string;
  result_url?: string;
  task_name?: string;
  dataset_name?: string;
  dataset_slug?: string;
}

export interface Metric {
  id: string;
  name: string;
  full_name?: string;
  direction: 'higher_is_better' | 'lower_is_better';
  description?: string;
  created_at: string;
  updated_at: string;
}

export interface MetricDirections {
  directions: Record<string, 'higher_is_better' | 'lower_is_better'>;
}

export interface PaginatedResponse<T> {
  count: number;
  next_page: number | null;
  previous_page: number | null;
  results: T[];
}

export interface TrendingMetrics {
  velocity_24h: number;
  trending_score: number;
  stars_gained_24h: number;
}

export interface TrendingPaper {
  paper_id: string;
  arxiv_id: string;
  title: string;
  date_published: string | null;
  thumbnail_url?: string;
  tasks?: Array<{ name: string; slug: string }>;
  repository: {
    id: string;
    url: string;
    owner: string;
    name: string;
    num_stars: number;
  };
  trending: TrendingMetrics;
  paper_age_days: number;
}

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${endpoint}`;

    console.log(`[API] Requesting: ${url}`);

    try {
      const response = await fetch(url, {
        headers: {
          'Content-Type': 'application/json',
          ...options?.headers,
        },
        ...options,
      });

      console.log(`[API] Response from ${url}:`, response.status, response.statusText);

      if (!response.ok) {
        const errorText = await response.text();
        console.error(`[API] Error response:`, errorText);
        const error: any = new Error(`API request failed: ${response.status} ${response.statusText}`);
        error.status = response.status;
        error.statusText = response.statusText;
        error.response = errorText;
        throw error;
      }

      const data = await response.json();
      console.log(`[API] Success:`, data);
      return data;
    } catch (error) {
      console.error(`[API] Request to ${url} failed:`, error);
      throw error;
    }
  }

  // Papers API
  async getPapers(params?: {
    page?: number;
    page_size?: number;
    search?: string;
    order_by?: 'date_published' | 'citation_count' | 'title' | 'trending';
    order_dir?: 'asc' | 'desc';
    published_after?: string;
    published_before?: string;
    conference?: string;
    latest_only?: boolean;
    include_resources?: boolean;
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
    if (params?.include_resources !== undefined) searchParams.append('include_resources', params.include_resources.toString());

    const endpoint = `/papers/${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Paper>>(endpoint);
  }

  async getPaper(id: string, includeResources: boolean = true): Promise<Paper> {
    const endpoint = `/papers/${id}${includeResources ? '?include_resources=true' : ''}`;
    return this.request<Paper>(endpoint);
  }

  async getPaperByArxivId(arxivId: string, includeResources: boolean = true): Promise<Paper> {
    const endpoint = `/papers/arxiv/${arxivId}${includeResources ? '?include_resources=true' : ''}`;
    return this.request<Paper>(endpoint);
  }

  async indexPaperFromArxiv(arxivId: string): Promise<Paper> {
    const endpoint = `/papers/index/${arxivId}`;
    return this.request<Paper>(endpoint, { method: 'POST' });
  }

  async updatePaperTasks(paperId: string, taskIds: number[]): Promise<Paper> {
    const searchParams = new URLSearchParams();
    taskIds.forEach(id => searchParams.append('task_ids', id.toString()));
    const endpoint = `/papers/${paperId}/tasks?${searchParams.toString()}`;
    return this.request<Paper>(endpoint, { method: 'PUT' });
  }

  async updatePaperMethods(paperId: string, methodIds: number[]): Promise<Paper> {
    const searchParams = new URLSearchParams();
    methodIds.forEach(id => searchParams.append('method_ids', id.toString()));
    const endpoint = `/papers/${paperId}/methods?${searchParams.toString()}`;
    return this.request<Paper>(endpoint, { method: 'PUT' });
  }

  async updatePaperRepositories(paperId: string, repositories: Array<{ url: string; is_official: boolean }>): Promise<Paper> {
    const endpoint = `/papers/${paperId}/repositories`;
    return this.request<Paper>(endpoint, {
      method: 'PUT',
      body: JSON.stringify({ repositories }),
    });
  }

  async getTrendingPapers(params?: {
    limit?: number;
    max_age_days?: number;
    min_velocity?: number;
  }): Promise<TrendingPaper[]> {
    const searchParams = new URLSearchParams();

    if (params?.limit) searchParams.append('limit', params.limit.toString());
    if (params?.max_age_days) searchParams.append('max_age_days', params.max_age_days.toString());
    if (params?.min_velocity !== undefined) searchParams.append('min_velocity', params.min_velocity.toString());

    const endpoint = `/papers/trending${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<TrendingPaper[]>(endpoint);
  }

  // Repositories API
  async getRepositoriesForPaper(paperId: string): Promise<Repository[]> {
    return this.request<Repository[]>(`/papers/${paperId}/repositories`);
  }

  async getRepositories(params?: {
    page?: number;
    page_size?: number;
    owner?: string;
    official_only?: boolean;
    min_stars?: number;
    source?: string;
    order_by?: string;
    order_dir?: 'asc' | 'desc';
  }): Promise<PaginatedResponse<Repository>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.owner) searchParams.append('owner', params.owner);
    if (params?.official_only) searchParams.append('official_only', params.official_only.toString());
    if (params?.min_stars) searchParams.append('min_stars', params.min_stars.toString());
    if (params?.source) searchParams.append('source', params.source);
    if (params?.order_by) searchParams.append('order_by', params.order_by);
    if (params?.order_dir) searchParams.append('order_dir', params.order_dir);

    const endpoint = `/repositories/${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Repository>>(endpoint);
  }

  // Project Pages API
  async getProjectPagesForPaper(paperId: string): Promise<ProjectPage[]> {
    return this.request<ProjectPage[]>(`/papers/${paperId}/project-pages`);
  }

  async getProjectPages(params?: {
    page?: number;
    page_size?: number;
    official_only?: boolean;
    source?: string;
    order_by?: string;
    order_dir?: 'asc' | 'desc';
  }): Promise<PaginatedResponse<ProjectPage>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.official_only) searchParams.append('official_only', params.official_only.toString());
    if (params?.source) searchParams.append('source', params.source);
    if (params?.order_by) searchParams.append('order_by', params.order_by);
    if (params?.order_dir) searchParams.append('order_dir', params.order_dir);

    const endpoint = `/project-pages/${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<ProjectPage>>(endpoint);
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

  // Areas API
  async getAreas(params?: {
    page?: number;
    page_size?: number;
    q?: string;
    name?: string;
    ordering?: string;
  }): Promise<PaginatedResponse<Area>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.q) searchParams.append('q', params.q);
    if (params?.name) searchParams.append('name', params.name);
    if (params?.ordering) searchParams.append('ordering', params.ordering);

    const endpoint = `/areas/${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Area>>(endpoint);
  }

  async getArea(id: string): Promise<Area> {
    return this.request<Area>(`/areas/${id}`);
  }

  async getAreaTasks(areaId: string, params?: {
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<Task>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());

    const endpoint = `/areas/${areaId}/tasks${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Task>>(endpoint);
  }

  // Tasks API
  async getTasks(params?: {
    page?: number;
    page_size?: number;
    q?: string;
    name?: string;
    area_id?: number;
    parent_id?: number;
    level?: number;
    ordering?: string;
  }): Promise<PaginatedResponse<Task>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.q) searchParams.append('q', params.q);
    if (params?.name) searchParams.append('name', params.name);
    if (params?.area_id) searchParams.append('area_id', params.area_id.toString());
    if (params?.parent_id) searchParams.append('parent_id', params.parent_id.toString());
    if (params?.level !== undefined) searchParams.append('level', params.level.toString());
    if (params?.ordering) searchParams.append('ordering', params.ordering);

    const endpoint = `/tasks/${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Task>>(endpoint);
  }

  async getTask(id: string): Promise<Task> {
    return this.request<Task>(`/tasks/${id}`);
  }

  async getTaskChildren(taskId: string, params?: {
    page?: number;
    page_size?: number;
  }): Promise<PaginatedResponse<Task>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());

    const endpoint = `/tasks/${taskId}/children${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Task>>(endpoint);
  }

  async getTaskParents(taskId: string): Promise<Task[]> {
    return this.request<Task[]>(`/tasks/${taskId}/parents`);
  }

  async getTaskPapers(taskId: string, params?: {
    page?: number;
    page_size?: number;
    order_by?: 'date_published' | 'citation_count' | 'title';
    order_dir?: 'asc' | 'desc';
    latest_only?: boolean;
    include_resources?: boolean;
  }): Promise<PaginatedResponse<Paper>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.order_by) searchParams.append('order_by', params.order_by);
    if (params?.order_dir) searchParams.append('order_dir', params.order_dir);
    if (params?.latest_only !== undefined) searchParams.append('latest_only', params.latest_only.toString());
    if (params?.include_resources !== undefined) searchParams.append('include_resources', params.include_resources.toString());

    const queryString = searchParams.toString();
    const endpoint = queryString ? `/tasks/${taskId}/papers?${queryString}` : `/tasks/${taskId}/papers`;

    return this.request<PaginatedResponse<Paper>>(endpoint);
  }

  // Methods API
  async getMethods(params?: {
    page?: number;
    page_size?: number;
    q?: string;
    name?: string;
    full_name?: string;
    introduced_year?: number;
    ordering?: string;
  }): Promise<PaginatedResponse<Method>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.q) searchParams.append('q', params.q);
    if (params?.name) searchParams.append('name', params.name);
    if (params?.full_name) searchParams.append('full_name', params.full_name);
    if (params?.introduced_year) searchParams.append('introduced_year', params.introduced_year.toString());
    if (params?.ordering) searchParams.append('ordering', params.ordering);

    const endpoint = `/methods/${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Method>>(endpoint);
  }

  async getMethod(id: string): Promise<Method> {
    return this.request<Method>(`/methods/${encodeURIComponent(id)}`);
  }

  async getMethodPapers(methodId: string, params?: {
    page?: number;
    page_size?: number;
    order_by?: 'date_published' | 'citation_count' | 'title';
    order_dir?: 'asc' | 'desc';
    latest_only?: boolean;
    include_resources?: boolean;
  }): Promise<PaginatedResponse<Paper>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.order_by) searchParams.append('order_by', params.order_by);
    if (params?.order_dir) searchParams.append('order_dir', params.order_dir);
    if (params?.latest_only !== undefined) searchParams.append('latest_only', params.latest_only.toString());
    if (params?.include_resources !== undefined) searchParams.append('include_resources', params.include_resources.toString());

    const queryString = searchParams.toString();
    const endpoint = queryString ? `/methods/${encodeURIComponent(methodId)}/papers?${queryString}` : `/methods/${encodeURIComponent(methodId)}/papers`;

    return this.request<PaginatedResponse<Paper>>(endpoint);
  }

  // Datasets API
  async getDatasets(params?: {
    page?: number;
    page_size?: number;
    q?: string;
    name?: string;
    full_name?: string;
    task?: string;
    task_id?: number;
    ordering?: string;
  }): Promise<PaginatedResponse<Dataset>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.q) searchParams.append('q', params.q);
    if (params?.name) searchParams.append('name', params.name);
    if (params?.full_name) searchParams.append('full_name', params.full_name);
    if (params?.task) searchParams.append('task', params.task);
    if (params?.task_id) searchParams.append('task', params.task_id.toString());
    if (params?.ordering) searchParams.append('ordering', params.ordering);

    const endpoint = `/datasets/${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Dataset>>(endpoint);
  }

  async getDataset(id: string): Promise<Dataset> {
    return this.request<Dataset>(`/datasets/${id}`);
  }

  async getDatasetBySlug(slug: string): Promise<Dataset> {
    // Use the datasets/{slug} endpoint which supports both ID and slug lookups
    return this.request<Dataset>(`/datasets/${slug}`);
  }

  async getDatasetTasks(datasetId: string): Promise<Task[]> {
    const response = await this.request<PaginatedResponse<Task>>(`/datasets/${datasetId}/tasks/`);
    return response.results;
  }

  // Evaluations API
  async getEvaluations(params?: {
    page?: number;
    page_size?: number;
    q?: string;
    paper_id?: number;
    task_id?: number;
    dataset_id?: number;
    best_metric?: string;
    ordering?: string;
  }): Promise<PaginatedResponse<Evaluation>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.q) searchParams.append('q', params.q);
    if (params?.paper_id) searchParams.append('paper_id', params.paper_id.toString());
    if (params?.task_id) searchParams.append('task_id', params.task_id.toString());
    if (params?.dataset_id) searchParams.append('dataset_id', params.dataset_id.toString());
    if (params?.best_metric) searchParams.append('best_metric', params.best_metric);
    if (params?.ordering) searchParams.append('ordering', params.ordering);

    const endpoint = `/evaluations/${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Evaluation>>(endpoint);
  }

  async getEvaluation(id: string): Promise<Evaluation> {
    return this.request<Evaluation>(`/evaluations/${id}`);
  }

  async getEvaluationsByPaper(paperId: string): Promise<Evaluation[]> {
    const response = await this.getEvaluations({ paper_id: parseInt(paperId), page_size: 100 });
    return response.results;
  }

  async getEvaluationsByDataset(datasetId: string, bestMetric?: string): Promise<Evaluation[]> {
    const response = await this.getEvaluations({
      dataset_id: parseInt(datasetId),
      best_metric: bestMetric,
      page_size: 100,
      ordering: 'best_rank'  // Sort by rank ascending (rank 1 first)
    });
    return response.results;
  }

  async createEvaluation(data: {
    paper_id: number;
    task_id: number;
    dataset_id: number;
    model_name?: string;
    methodology?: string;
    metrics: Record<string, string | number>;
    uses_additional_data?: boolean;
    best_rank?: number;
    best_metric?: string;
    evaluated_on?: string;
    external_source_url?: string;
  }): Promise<Evaluation> {
    const endpoint = '/evaluations/';
    return this.request<Evaluation>(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async updateEvaluation(evaluationId: string, data: {
    task_id?: number;
    dataset_id?: number;
    model_name?: string;
    methodology?: string;
    metrics?: Record<string, string | number>;
    uses_additional_data?: boolean;
    best_rank?: number;
    best_metric?: string;
    evaluated_on?: string;
    external_source_url?: string;
  }): Promise<Evaluation> {
    const endpoint = `/evaluations/${evaluationId}`;
    return this.request<Evaluation>(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }

  async deleteEvaluation(evaluationId: string): Promise<void> {
    const endpoint = `/evaluations/${evaluationId}`;
    return this.request<void>(endpoint, {
      method: 'DELETE',
    });
  }

  // Thumbnails API
  async generateThumbnail(paperId: string): Promise<{ thumbnail_url?: string; status: string; message: string }> {
    const url = `/api/thumbnails/generate/${paperId}`;
    const response = await fetch(url, { method: 'POST' });
    if (!response.ok) {
      throw new Error(`Thumbnail generation failed: ${response.status}`);
    }
    return await response.json();
  }

  async getThumbnailStatus(paperId: string): Promise<{ has_thumbnail: boolean; thumbnail_url?: string; arxiv_id?: string; version?: string }> {
    const url = `/api/thumbnails/status/${paperId}`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Thumbnail status check failed: ${response.status}`);
    }
    return await response.json();
  }

  // Health check
  async healthCheck(): Promise<{ status: string; service: string }> {
    const url = `/health`;
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`Health check failed: ${response.status}`);
    }
    return await response.json();
  }

  // Metrics
  async getMetrics(params?: {
    page?: number;
    page_size?: number;
    q?: string;
    direction?: 'higher_is_better' | 'lower_is_better';
    ordering?: string;
  }): Promise<PaginatedResponse<Metric>> {
    const searchParams = new URLSearchParams();

    if (params?.page) searchParams.append('page', params.page.toString());
    if (params?.page_size) searchParams.append('page_size', params.page_size.toString());
    if (params?.q) searchParams.append('q', params.q);
    if (params?.direction) searchParams.append('direction', params.direction);
    if (params?.ordering) searchParams.append('ordering', params.ordering);

    const endpoint = `/metrics/${searchParams.toString() ? `?${searchParams.toString()}` : ''}`;
    return this.request<PaginatedResponse<Metric>>(endpoint);
  }

  async getMetric(metricName: string): Promise<Metric> {
    return this.request<Metric>(`/metrics/${metricName}`);
  }

  async getMetricDirections(): Promise<MetricDirections> {
    return this.request<MetricDirections>('/metrics/directions');
  }
}

// Create and export a singleton instance
export const apiClient = new ApiClient();

// Export individual API functions for convenience (with proper binding)
export const getPapers = apiClient.getPapers.bind(apiClient);
export const getPaper = apiClient.getPaper.bind(apiClient);
export const getPaperByArxivId = apiClient.getPaperByArxivId.bind(apiClient);
export const indexPaperFromArxiv = apiClient.indexPaperFromArxiv.bind(apiClient);
export const updatePaperTasks = apiClient.updatePaperTasks.bind(apiClient);
export const updatePaperMethods = apiClient.updatePaperMethods.bind(apiClient);
export const updatePaperRepositories = apiClient.updatePaperRepositories.bind(apiClient);
export const getTrendingPapers = apiClient.getTrendingPapers.bind(apiClient);
export const getRepositoriesForPaper = apiClient.getRepositoriesForPaper.bind(apiClient);
export const getRepositories = apiClient.getRepositories.bind(apiClient);
export const getProjectPagesForPaper = apiClient.getProjectPagesForPaper.bind(apiClient);
export const getProjectPages = apiClient.getProjectPages.bind(apiClient);
export const getAuthors = apiClient.getAuthors.bind(apiClient);
export const getAuthor = apiClient.getAuthor.bind(apiClient);
export const getAreas = apiClient.getAreas.bind(apiClient);
export const getArea = apiClient.getArea.bind(apiClient);
export const getAreaTasks = apiClient.getAreaTasks.bind(apiClient);
export const getTasks = apiClient.getTasks.bind(apiClient);
export const getTask = apiClient.getTask.bind(apiClient);
export const getTaskChildren = apiClient.getTaskChildren.bind(apiClient);
export const getTaskParents = apiClient.getTaskParents.bind(apiClient);
export const getTaskPapers = apiClient.getTaskPapers.bind(apiClient);
export const getMethods = apiClient.getMethods.bind(apiClient);
export const getMethod = apiClient.getMethod.bind(apiClient);
export const getMethodPapers = apiClient.getMethodPapers.bind(apiClient);
export const getDatasets = apiClient.getDatasets.bind(apiClient);
export const getDataset = apiClient.getDataset.bind(apiClient);
export const getDatasetBySlug = apiClient.getDatasetBySlug.bind(apiClient);
export const getDatasetTasks = apiClient.getDatasetTasks.bind(apiClient);
export const getEvaluations = apiClient.getEvaluations.bind(apiClient);
export const getEvaluation = apiClient.getEvaluation.bind(apiClient);
export const getEvaluationsByPaper = apiClient.getEvaluationsByPaper.bind(apiClient);
export const getEvaluationsByDataset = apiClient.getEvaluationsByDataset.bind(apiClient);
export const createEvaluation = apiClient.createEvaluation.bind(apiClient);
export const updateEvaluation = apiClient.updateEvaluation.bind(apiClient);
export const deleteEvaluation = apiClient.deleteEvaluation.bind(apiClient);
export const generateThumbnail = apiClient.generateThumbnail.bind(apiClient);
export const getThumbnailStatus = apiClient.getThumbnailStatus.bind(apiClient);
export const getMetrics = apiClient.getMetrics.bind(apiClient);
export const getMetric = apiClient.getMetric.bind(apiClient);
export const getMetricDirections = apiClient.getMetricDirections.bind(apiClient);
export const healthCheck = apiClient.healthCheck.bind(apiClient);
