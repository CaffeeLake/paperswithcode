import Header from "@/components/Header";
import { Search, Sparkles, Github, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import PaperCard from "@/components/PaperCard";
import TrendingPaperCard from "@/components/TrendingPaperCard";
import { useInfinitePapers } from "@/hooks/usePapers";
import { useState, useEffect } from "react";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { useSearchParams } from "react-router-dom";

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
const transformPaperForUI = (paper: any, index: number) => {
  const authorsWithColors = assignAuthorColors(paper.authors || []);

  return {
    id: paper.id,
    title: paper.title,
    abstract: paper.abstract,
    authors: authorsWithColors,
    submittedBy: `user${paper.id}`, // Mock submitted by
    date: formatDate(paper.published),
    upvotes: Math.floor(Math.random() * 200) + 10, // Mock upvotes
    comments: Math.floor(Math.random() * 5), // Mock comments
    category: "Machine Learning", // Mock category
    isUpvoted: Math.random() > 0.7, // Mock upvote status
    githubStars: paper.citation_count * 10 + Math.floor(Math.random() * 1000), // Mock GitHub stars
    tags: ["machine learning", "artificial intelligence", "research"], // Mock tags
    thumbnailUrl: paper.thumbnail_url, // Pass through thumbnail URL from API
  };
};

const Papers = () => {
  const [searchParams] = useSearchParams();
  const urlSearch = searchParams.get('search') || '';

  const [searchTerm, setSearchTerm] = useState(urlSearch);
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState(urlSearch);
  const [sortBy, setSortBy] = useState<'date_published' | 'citation_count' | 'title'>('date_published');

  // Update search term when URL changes
  useEffect(() => {
    const newSearch = searchParams.get('search') || '';
    setSearchTerm(newSearch);
    setDebouncedSearchTerm(newSearch);
  }, [searchParams]);

  // Debounce search term to avoid too many API calls
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm);
    }, 500); // 500ms delay

    return () => clearTimeout(timer);
  }, [searchTerm]);

  // Fetch papers from API with infinite scroll
  const {
    data,
    isLoading,
    error,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage
  } = useInfinitePapers({
    page_size: 20,
    search: debouncedSearchTerm || undefined,
    order_by: sortBy,
    order_dir: sortBy === 'title' ? 'asc' : 'desc'
  });

  // Flatten all pages into a single array
  const allPapers = data?.pages.flatMap(page => page.results) || [];
  const transformedPapers = allPapers.map(transformPaperForUI);
  const totalCount = data?.pages[0]?.count || 0;

  // Debug logging (temporary)
  console.log('📊 Papers State:', {
    totalPages: data?.pages.length || 0,
    totalPapers: allPapers.length,
    hasNextPage,
    isFetchingNextPage,
    isLoading,
    sortBy,
    searchTerm: debouncedSearchTerm
  });

  // Intersection observer for infinite scroll
  const { targetRef, isIntersecting } = useIntersectionObserver({
    threshold: 0.1,
    rootMargin: '50px'
  });

  // Fetch next page when intersection observer triggers
  useEffect(() => {
    if (isIntersecting && hasNextPage && !isFetchingNextPage) {
      console.log('🔄 Fetching next page...', {
        isIntersecting,
        hasNextPage,
        isFetchingNextPage,
        currentPapers: transformedPapers.length
      });
      fetchNextPage();
    }
  }, [isIntersecting, hasNextPage, isFetchingNextPage, fetchNextPage]);

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <div className="container mx-auto px-4 py-8 max-w-7xl">
        {/* Header Section */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h1 className="text-4xl font-bold mb-2">Trending Papers</h1>
              <div className="flex items-center text-muted-foreground">
                <span className="mr-2">by</span>
                <div className="flex items-center space-x-1 mr-2">
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
          <div className="flex items-center gap-4 mb-6">
            <div className="relative flex-1 max-w-md">
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
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className={sortBy === 'date_published' ? "bg-muted" : ""}
              onClick={() => setSortBy('date_published')}
            >
              Recent
            </Button>
            <Button
              variant="outline"
              size="sm"
              className={sortBy === 'citation_count' ? "bg-muted" : ""}
              onClick={() => setSortBy('citation_count')}
            >
              Most Cited
            </Button>
            <Button
              variant="outline"
              size="sm"
              className={sortBy === 'title' ? "bg-muted" : ""}
              onClick={() => setSortBy('title')}
            >
              A-Z
            </Button>
            <div className="ml-auto">
              <Button variant="default" size="sm" className="bg-orange-500 hover:bg-orange-600">
                Trending Papers
              </Button>
            </div>
          </div>
        </div>


        {/* Loading State */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
            <span className="ml-2 text-muted-foreground">Loading papers...</span>
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
        {!isLoading && !error && (
          <div className="space-y-6">
            {transformedPapers.length > 0 ? (
              <>
                {transformedPapers.map((paper) => (
                  <TrendingPaperCard key={paper.id} {...paper} />
                ))}

                {/* Intersection Observer Target */}
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
              </>
            ) : (
              <div className="text-center py-12">
                <p className="text-muted-foreground">No papers found</p>
                <p className="text-xs text-muted-foreground mt-2">
                  Search: "{debouncedSearchTerm}" | Papers: {allPapers.length} | Total: {totalCount}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Pagination Info */}
        {data && (
          <div className="mt-8 text-center text-sm text-muted-foreground">
            Showing {transformedPapers.length} of {totalCount} papers
            {!hasNextPage && transformedPapers.length > 0 && (
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
