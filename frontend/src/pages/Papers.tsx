import Header from "@/components/Header";
import { Sparkles, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import TrendingPaperCard from "@/components/TrendingPaperCard";
import { useInfinitePapers, useTrendingPapers } from "@/hooks/usePapers";
import { useState, useEffect, useRef } from "react";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { useSearchParams } from "react-router-dom";
import { TrendingPaper } from "@/lib/api";

// Type definitions
interface Task {
  id: string;
  name: string;
  slug?: string;
}

interface Repository {
  url?: string;
  num_stars?: number;
  is_official?: boolean;
}

interface PaperFromAPI {
  id: string;
  title: string;
  abstract: string;
  authors: string[];
  published: string;
  thumbnail_url?: string;
  arxiv_id?: string;
  tasks?: Task[];
  repositories?: Repository[];
}

// Color palette for author avatars
const authorColors = [
  "#3B82F6", "#8B5CF6", "#EF4444", "#10B981",
  "#F59E0B", "#EC4899", "#06B6D4", "#84CC16"
];

// Helper function to get author initials
const getAuthorInitials = (name: string) => {
  return name.split(' ').map(n => n[0]).join('').toUpperCase();
};

// Helper function to assign colors to authors
const assignAuthorColors = (authors: string[]) => {
  return authors.map((authorName, index) => ({
    name: authorName,
    color: authorColors[index % authorColors.length]
  }));
};

// Helper function to format date
const formatDate = (dateString: string) => {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  });
};

// Helper function to generate mock UI data from API paper
const transformPaperForUI = (paper: PaperFromAPI, index: number) => {
  const authorsWithColors = assignAuthorColors(paper.authors || []);

  // Calculate total GitHub stars from official repositories only and find the most starred one
  const repositories = paper.repositories || [];
  const officialRepositories = repositories.filter((repo: Repository) => repo.is_official);
  const totalGithubStars = officialRepositories.reduce((total: number, repo: Repository) => {
    return total + (repo.num_stars || 0);
  }, 0);

  // Find the official repository with the most stars for the GitHub link
  const mostStarredRepo = officialRepositories.length > 0
    ? officialRepositories.reduce((max: Repository, repo: Repository) =>
        (repo.num_stars || 0) > (max.num_stars || 0) ? repo : max
      )
    : null;

  // Extract task names from the paper's tasks
  // Keep the tag names in their original case for display
  const tags = paper.tasks && paper.tasks.length > 0
    ? paper.tasks.map((task: Task) => task.name)
    : [];

  // Use repository owner/name if available, otherwise undefined (no dummy data)
  let submittedBy: string | undefined = undefined;
  if (mostStarredRepo?.url) {
    // Extract owner/repo from URL like "https://github.com/owner/repo"
    const urlMatch = mostStarredRepo.url.match(/github\.com\/([^/]+)\/([^/]+)/);
    if (urlMatch) {
      submittedBy = `${urlMatch[1]}/${urlMatch[2]}`;
    }
  }

  return {
    id: paper.id,
    title: paper.title,
    abstract: paper.abstract,
    authors: authorsWithColors,
    submittedBy: submittedBy, // Use repository owner/name if available
    date: formatDate(paper.published),
    githubStars: totalGithubStars, // Real GitHub stars from official repositories
    starsPerHour: undefined, // Not available for non-trending papers
    tags: tags, // Real tags from API tasks
    thumbnailUrl: paper.thumbnail_url, // Pass through thumbnail URL from API
    arxivId: paper.arxiv_id, // Pass through arXiv ID for clickable links
    githubUrl: mostStarredRepo?.url, // Link to most starred repository
  };
};

// Helper function to transform trending paper to UI format
const transformTrendingPaperForUI = (paper: TrendingPaper, index: number) => {
  // Generate mock authors for now (trending endpoint doesn't include authors)
  const mockAuthors = ['John Doe', 'Jane Smith'];
  const authorsWithColors = assignAuthorColors(mockAuthors);

  return {
    id: paper.paper_id,
    title: paper.title,
    abstract: '', // Trending endpoint doesn't include abstract
    authors: authorsWithColors,
    submittedBy: `${paper.repository.owner}/${paper.repository.name}`,
    date: paper.date_published ? formatDate(paper.date_published) : 'Unknown',
    githubStars: paper.repository.num_stars,
    starsPerHour: paper.trending.velocity_24h,
    tags: paper.tasks || [], // Use tasks from API response
    thumbnailUrl: paper.thumbnail_url, // Pass through thumbnail URL from API
    arxivId: paper.arxiv_id,
    githubUrl: paper.repository.url,
  };
};

const Papers = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const urlSearch = searchParams.get('search') || '';
  const urlSort = searchParams.get('sort') || 'trending';

  const [searchTerm, setSearchTerm] = useState(urlSearch);
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState(urlSearch);
  const [sortBy, setSortBy] = useState<'date_published' | 'citation_count' | 'title' | 'trending'>(
    urlSort as 'date_published' | 'citation_count' | 'title' | 'trending'
  );

  // Update search term and sort when URL changes
  useEffect(() => {
    const newSearch = searchParams.get('search') || '';
    const newSort = searchParams.get('sort') || 'trending';
    setSearchTerm(newSearch);
    setDebouncedSearchTerm(newSearch);
    setSortBy(newSort as 'date_published' | 'citation_count' | 'title' | 'trending');
  }, [searchParams]);

  // Debounce search term to avoid too many API calls
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm);
    }, 500); // 500ms delay

    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Track sorting transitions to prevent showing stale data
  const [isTransitioning, setIsTransitioning] = useState(false);
  const previousSortRef = useRef(sortBy);

  // Helper function to update sort and URL
  const handleSortChange = (newSort: 'date_published' | 'citation_count' | 'title' | 'trending') => {
    if (newSort !== sortBy) {
      setIsTransitioning(true);
      previousSortRef.current = sortBy;
    }
    setSortBy(newSort);
    const params = new URLSearchParams(searchParams);
    params.set('sort', newSort);
    setSearchParams(params);
  };

  // Use trending endpoint when sortBy is 'trending' and no search term
  const useTrendingEndpoint = sortBy === 'trending' && !debouncedSearchTerm;

  // Fetch trending papers using dedicated endpoint
  const {
    data: trendingData,
    isLoading: trendingLoading,
    error: trendingError,
  } = useTrendingPapers({
    limit: 50,
    max_age_days: 180,
    enabled: useTrendingEndpoint,
  });

  // Fetch papers from API with infinite scroll (for non-trending or when searching)
  const {
    data: infiniteData,
    isLoading: infiniteLoading,
    error: infiniteError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage
  } = useInfinitePapers({
    page_size: 20,
    search: debouncedSearchTerm || undefined,
    order_by: sortBy === 'trending' ? 'date_published' : sortBy, // Fallback for trending with search
    order_dir: sortBy === 'title' ? 'asc' : 'desc',
    include_resources: true,
    enabled: !useTrendingEndpoint,
  });

  // Clear transition state once data is loaded
  useEffect(() => {
    if (isTransitioning) {
      const hasData = useTrendingEndpoint ? !!trendingData : !!(infiniteData && infiniteData.pages.length > 0);
      const isStillLoading = useTrendingEndpoint ? trendingLoading : infiniteLoading;

      if (hasData && !isStillLoading) {
        setIsTransitioning(false);
      }
    }
  }, [isTransitioning, useTrendingEndpoint, trendingData, infiniteData, trendingLoading, infiniteLoading]);

  // Combine data based on which endpoint is active
  // IMPORTANT: Only use data from the currently active endpoint to prevent showing stale data
  const isLoading = useTrendingEndpoint ? trendingLoading : infiniteLoading;
  const error = useTrendingEndpoint ? trendingError : infiniteError;

  let transformedPapers;
  let totalCount;

  // Don't show any data while transitioning to prevent stale data flash
  if (isTransitioning) {
    transformedPapers = [];
    totalCount = 0;
  } else if (useTrendingEndpoint) {
    // Only show trending data when trending endpoint is active and has data
    if (trendingData) {
      transformedPapers = trendingData.map(transformTrendingPaperForUI);
      totalCount = trendingData.length;
    } else {
      transformedPapers = [];
      totalCount = 0;
    }
  } else {
    // Only show infinite scroll data when that endpoint is active and has data
    if (infiniteData && infiniteData.pages.length > 0) {
      const allPapers = infiniteData.pages.flatMap(page => page.results);
      transformedPapers = allPapers.map(transformPaperForUI);
      totalCount = infiniteData.pages[0]?.count || 0;
    } else {
      transformedPapers = [];
      totalCount = 0;
    }
  }

  // Debug logging (temporary)
  console.log('📊 Papers State:', {
    sortBy,
    useTrendingEndpoint,
    isTransitioning,
    totalPages: infiniteData?.pages.length || 0,
    totalPapers: transformedPapers.length,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    trendingLoading,
    infiniteLoading,
    hasTrendingData: !!trendingData,
    hasInfiniteData: !!(infiniteData && infiniteData.pages.length > 0),
    searchTerm: debouncedSearchTerm
  });

  // Intersection observer for infinite scroll
  const { targetRef, isIntersecting } = useIntersectionObserver({
    threshold: 0.1,
    rootMargin: '50px'
  });

  // Fetch next page when intersection observer triggers (only for non-trending)
  useEffect(() => {
    if (!useTrendingEndpoint && isIntersecting && hasNextPage && !isFetchingNextPage) {
      console.log('🔄 Fetching next page...', {
        isIntersecting,
        hasNextPage,
        isFetchingNextPage,
        currentPapers: transformedPapers.length
      });
      fetchNextPage();
    }
  }, [useTrendingEndpoint, isIntersecting, hasNextPage, isFetchingNextPage, fetchNextPage, transformedPapers.length]);

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <div className="container mx-auto px-3 py-6 sm:px-4 sm:py-8 max-w-7xl">
        {/* Header Section */}
        <div className="mb-8">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-6">
            <div className="space-y-2">
              <h1 className="text-3xl sm:text-4xl font-bold">
                {sortBy === 'trending' && '🔥 Trending Papers'}
                {sortBy === 'date_published' && 'Recent Papers'}
                {sortBy === 'citation_count' && 'Most Cited Papers'}
                {sortBy === 'title' && 'Papers A-Z'}
              </h1>
              <div className="flex flex-wrap items-center gap-2 text-muted-foreground text-sm sm:text-base">
                <span>by</span>
                <div className="flex items-center space-x-1">
                  <Avatar className="w-6 h-6">
                    <AvatarFallback className="text-xs bg-blue-500 text-white">AK</AvatarFallback>
                  </Avatar>
                  <Avatar className="w-6 h-6">
                    <AvatarFallback className="text-xs bg-green-500 text-white">HF</AvatarFallback>
                  </Avatar>
                </div>
                <span>AK and the research community</span>
              </div>
            </div>
            <Button variant="outline" size="sm" className="hidden md:flex">
              + Submit a paper
            </Button>
          </div>

          {/* Search Bar */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4 mb-6">
            <div className="relative w-full sm:flex-1 sm:max-w-md">
              <Sparkles className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground w-4 h-4" />
              <Input
                className="pl-10 bg-muted/50 border focus-visible:ring-1 focus-visible:ring-primary"
                placeholder="Search any paper with AI"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              {isLoading && (
                <Loader2 className="absolute right-3 top-1/2 transform -translate-y-1/2 w-4 h-4 animate-spin text-muted-foreground" />
              )}
            </div>
            {debouncedSearchTerm && (
              <div className="text-sm text-muted-foreground">
                Searching for: "{debouncedSearchTerm}"
              </div>
            )}
          </div>

          {/* Time Filter Tabs */}
          <div className="flex gap-2 overflow-x-auto pb-2 sm:pb-0 sm:flex-wrap">
            <Button
              variant="outline"
              size="sm"
              className={`${sortBy === 'trending' ? "bg-muted" : ""} whitespace-nowrap`}
              onClick={() => handleSortChange('trending')}
            >
              🔥 Trending
            </Button>
            <Button
              variant="outline"
              size="sm"
              className={`${sortBy === 'date_published' ? "bg-muted" : ""} whitespace-nowrap`}
              onClick={() => handleSortChange('date_published')}
            >
              Recent
            </Button>
            <Button
              variant="outline"
              size="sm"
              className={`${sortBy === 'citation_count' ? "bg-muted" : ""} whitespace-nowrap`}
              onClick={() => handleSortChange('citation_count')}
            >
              Most Cited
            </Button>
            <Button
              variant="outline"
              size="sm"
              className={`${sortBy === 'title' ? "bg-muted" : ""} whitespace-nowrap`}
              onClick={() => handleSortChange('title')}
            >
              A-Z
            </Button>
          </div>
        </div>


        {/* Loading State */}
        {(isLoading || isTransitioning) && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
            <span className="ml-2 text-muted-foreground">
              {isTransitioning ? 'Switching view...' : 'Loading papers...'}
            </span>
          </div>
        )}

        {/* Error State */}
        {error && (
          <div className="flex items-center justify-center py-12">
            <div className="text-center">
              <p className="text-red-500 mb-2">Failed to load papers</p>
              <p className="text-sm text-muted-foreground">{error.message}</p>
            </div>
          </div>
        )}

        {/* Papers List */}
        {!isLoading && !isTransitioning && !error && (
          <div className="space-y-4 sm:space-y-6">
            {transformedPapers.length > 0 ? (
              <>
                {transformedPapers.map((paper) => (
                  <TrendingPaperCard key={paper.id} {...paper} />
                ))}

                {/* Intersection Observer Target - Only show for non-trending with pagination */}
                {!useTrendingEndpoint && (
                  <div
                    ref={targetRef}
                    className="h-32 flex items-center justify-center border-2 border-dashed border-gray-200 bg-gray-50/50 rounded-lg my-4"
                    style={{ minHeight: '100px' }}
                  >
                    {isFetchingNextPage && (
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Loading more papers...</span>
                      </div>
                    )}
                    {hasNextPage && !isFetchingNextPage && (
                      <div className="flex flex-col items-center gap-3">
                        <div className="text-sm text-muted-foreground text-center">
                          📜 Scroll here to load more papers automatically<br/>
                          <span className="text-xs">or click the button below</span>
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => fetchNextPage()}
                          className="text-xs"
                        >
                          Load More Papers
                        </Button>
                      </div>
                    )}
                    {!hasNextPage && (
                      <div className="text-sm text-muted-foreground">
                        🎉 All papers loaded!
                      </div>
                    )}
                  </div>
                )}

                {/* End indicator for trending papers */}
                {useTrendingEndpoint && (
                  <div className="text-center py-8 text-muted-foreground">
                    🔥 Showing top {transformedPapers.length} trending papers
                  </div>
                )}
              </>
            ) : (
              <div className="text-center py-12">
                <p className="text-muted-foreground">No papers found</p>
                <p className="text-xs text-muted-foreground mt-2">
                  {debouncedSearchTerm && `Search: "${debouncedSearchTerm}" | `}
                  Papers: {transformedPapers.length} | Total: {totalCount}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Pagination Info */}
        {(infiniteData || trendingData) && (
          <div className="mt-8 text-center text-sm text-muted-foreground">
            Showing {transformedPapers.length} of {totalCount} papers
            {!useTrendingEndpoint && !hasNextPage && transformedPapers.length > 0 && (
              <div className="mt-2 text-xs">
                🎉 You've reached the end! All papers loaded.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

export default Papers;
