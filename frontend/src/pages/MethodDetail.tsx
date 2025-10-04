import Header from "@/components/Header";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useParams, Link } from "react-router-dom";
import { Loader2, ExternalLink } from "lucide-react";
import { useQuery, useInfiniteQuery } from "@tanstack/react-query";
import { getMethod, getMethodPapers, type Method, type Paper } from "@/lib/api";
import { useState, useEffect } from "react";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import TrendingPaperCard from "@/components/TrendingPaperCard";
import ReactMarkdown from 'react-markdown';
import remarkMath from 'remark-math';
import remarkGfm from 'remark-gfm';
import rehypeKatex from 'rehype-katex';

// Helper function to transform paper for UI
const transformPaperForUI = (paper: Paper, index: number) => {
  const authorColors = [
    "#3B82F6", "#8B5CF6", "#EF4444", "#10B981",
    "#F59E0B", "#EC4899", "#06B6D4", "#84CC16"
  ];

  const assignAuthorColors = (authors: string[]) => {
    return authors.map((authorName, idx) => ({
      name: authorName,
      color: authorColors[idx % authorColors.length]
    }));
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  const authorsWithColors = assignAuthorColors(paper.authors || []);
  const repositories = paper.repositories || [];
  const officialRepositories = repositories.filter((repo) => repo.is_official);
  const totalGithubStars = officialRepositories.reduce((total, repo) => {
    return total + (repo.num_stars || 0);
  }, 0);

  const mostStarredRepo = officialRepositories.length > 0
    ? officialRepositories.reduce((max, repo) =>
        (repo.num_stars || 0) > (max.num_stars || 0) ? repo : max
      )
    : null;

  const tags = paper.tasks && paper.tasks.length > 0
    ? paper.tasks.map((task) => task.name)
    : [];

  return {
    id: paper.id,
    title: paper.title,
    abstract: paper.abstract,
    authors: authorsWithColors,
    submittedBy: `user${paper.id}`,
    date: formatDate(paper.published),
    upvotes: Math.floor(Math.random() * 200) + 10,
    comments: Math.floor(Math.random() * 5),
    category: "Machine Learning",
    isUpvoted: Math.random() > 0.7,
    githubStars: totalGithubStars,
    tags: tags,
    thumbnailUrl: paper.thumbnail_url,
    arxivId: paper.arxiv_id,
    githubUrl: mostStarredRepo?.url,
  };
};

const MethodDetail = () => {
  const { methodId } = useParams<{ methodId: string }>();
  const [sortBy, setSortBy] = useState<'date_published' | 'citation_count' | 'title'>('date_published');

  // Fetch method details
  const { data: method, isLoading, error } = useQuery({
    queryKey: ['method', methodId],
    queryFn: () => getMethod(methodId!),
    enabled: !!methodId,
    staleTime: 5 * 60 * 1000,
  });

  // Fetch papers for this method using infinite query
  const {
    data: papersData,
    isLoading: papersLoading,
    error: papersError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage
  } = useInfiniteQuery({
    queryKey: ['method-papers', methodId, sortBy],
    queryFn: ({ pageParam = 1 }) => getMethodPapers(methodId!, {
      page: pageParam,
      page_size: 20,
      order_by: sortBy,
      order_dir: sortBy === 'title' ? 'asc' : 'desc',
      include_resources: true,
    }),
    enabled: !!methodId,
    getNextPageParam: (lastPage) => lastPage.next_page || undefined,
    initialPageParam: 1,
    staleTime: 5 * 60 * 1000,
  });

  // Flatten all pages into a single array
  const allPapers = papersData?.pages.flatMap(page => page.results) || [];
  const transformedPapers = allPapers.map(transformPaperForUI);
  const totalCount = papersData?.pages[0]?.count || 0;

  // Intersection observer for infinite scroll
  const { targetRef, isIntersecting } = useIntersectionObserver({
    threshold: 0.1,
  });

  useEffect(() => {
    if (isIntersecting && hasNextPage && !isFetchingNextPage) {
      fetchNextPage();
    }
  }, [isIntersecting, hasNextPage, isFetchingNextPage, fetchNextPage]);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !method) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <Card className="p-6">
            <p className="text-red-500">Failed to load method details. Please try again later.</p>
          </Card>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        {/* Method Header */}
        <div className="mb-8">
          <div className="flex items-start justify-between mb-4">
            <div className="flex-1">
              <h1 className="text-4xl font-bold mb-2">{method.name}</h1>
              {method.full_name && method.full_name !== method.name && (
                <p className="text-xl text-muted-foreground mb-4">{method.full_name}</p>
              )}
            </div>
          </div>

          {/* Method Metadata */}
          <div className="flex flex-wrap gap-4 mb-6">
            {method.introduced_year && (
              <Badge variant="outline" className="text-sm">
                Introduced: {method.introduced_year}
              </Badge>
            )}
            {method.paper_count !== undefined && (
              <Badge variant="outline" className="text-sm">
                {method.paper_count} papers
              </Badge>
            )}
            {method.collection_name && (
              <Badge variant="secondary" className="text-sm">
                Collection: {method.collection_name}
              </Badge>
            )}
          </div>

          {/* Method Description */}
          {method.description && (
            <Card className="p-6 mb-6">
              <h2 className="text-lg font-semibold mb-3">Description</h2>
              <div className="prose prose-slate dark:prose-invert max-w-none">
                <ReactMarkdown
                  remarkPlugins={[remarkMath, remarkGfm]}
                  rehypePlugins={[rehypeKatex]}
                >
                  {method.description}
                </ReactMarkdown>
              </div>
            </Card>
          )}

          {/* Additional Information */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
            {method.source_url && (
              <Card className="p-4">
                <h3 className="text-sm font-semibold mb-2">Source</h3>
                <a
                  href={method.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline flex items-center gap-1"
                >
                  {method.source_title || method.source_url}
                  <ExternalLink className="w-3 h-3" />
                </a>
              </Card>
            )}
            {method.code_snippet_url && (
              <Card className="p-4">
                <h3 className="text-sm font-semibold mb-2">Code Snippet</h3>
                <a
                  href={method.code_snippet_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline flex items-center gap-1"
                >
                  View Code
                  <ExternalLink className="w-3 h-3" />
                </a>
              </Card>
            )}
          </div>
        </div>

        {/* Papers Section */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold">
              Papers using {method.name}
              {totalCount > 0 && <span className="text-muted-foreground ml-2">({totalCount})</span>}
            </h2>

            <div className="flex items-center gap-2">
              <label htmlFor="sort-select" className="text-sm text-muted-foreground">
                Sort by:
              </label>
              <select
                id="sort-select"
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
                className="border rounded-md px-3 py-1 text-sm bg-background"
              >
                <option value="date_published">Most Recent</option>
                <option value="citation_count">Most Cited</option>
                <option value="title">Title (A-Z)</option>
              </select>
            </div>
          </div>

          {papersLoading && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
            </div>
          )}

          {papersError && (
            <Card className="p-6">
              <p className="text-red-500">Failed to load papers. Please try again later.</p>
            </Card>
          )}

          {!papersLoading && !papersError && transformedPapers.length === 0 && (
            <Card className="p-6">
              <p className="text-muted-foreground">No papers found using this method.</p>
            </Card>
          )}

          {!papersLoading && !papersError && transformedPapers.length > 0 && (
            <div className="space-y-6">
              {transformedPapers.map((paper) => (
                <TrendingPaperCard key={paper.id} {...paper} />
              ))}

              {/* Infinite scroll trigger */}
              {hasNextPage && (
                <div ref={targetRef} className="flex items-center justify-center py-8">
                  {isFetchingNextPage && (
                    <Loader2 className="w-6 h-6 animate-spin text-primary" />
                  )}
                </div>
              )}

              {!hasNextPage && transformedPapers.length > 0 && (
                <div className="text-center text-muted-foreground py-4">
                  All papers loaded ({totalCount} total)
                </div>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
};

export default MethodDetail;
