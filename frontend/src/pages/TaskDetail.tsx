import Header from "@/components/Header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useParams, Link } from "react-router-dom";
import { Loader2, Target, TrendingUp, FileText, Github, TrendingDown, TrendingUp as TrendingUpIcon, Minus } from "lucide-react";
import { useTask } from "@/hooks/useTasks";
import { useInfiniteTaskPapers } from "@/hooks/usePapers";
import { useTaskDatasets } from "@/hooks/useDatasets";
import { useEvaluations } from "@/hooks/useEvaluations";
import { useState, useEffect, useMemo } from "react";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import TrendingPaperCard from "@/components/TrendingPaperCard";

// Helper function to transform paper for UI (copied from Papers.tsx)
const transformPaperForUI = (paper: { id: number; title: string; abstract?: string; authors?: string[]; published?: string; tasks?: { name: string }[]; repositories?: { url?: string; is_official?: boolean; num_stars?: number }[]; thumbnail_url?: string; arxiv_id?: string }, index: number) => {
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
  const totalGithubStars = officialRepositories.reduce((total: number, repo) => {
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
    upvotes: paper.citation_count || 0,
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

const TaskDetail = () => {
  const { taskId } = useParams<{ taskId: string }>();
  const { data: task, isLoading, error } = useTask(taskId, !!taskId);
  const [sortBy, setSortBy] = useState<'date_published' | 'citation_count' | 'title'>('date_published');

  // Fetch datasets for this task
  const { data: datasetsData, isLoading: datasetsLoading } = useTaskDatasets(taskId);

  // Fetch papers for this task
  const {
    data: papersData,
    isLoading: papersLoading,
    error: papersError,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage
  } = useInfiniteTaskPapers({
    taskId: taskId || '',
    page_size: 20,
    order_by: sortBy,
    order_dir: sortBy === 'title' ? 'asc' : 'desc',
    include_resources: true,
    enabled: !!taskId
  });

  // Flatten all pages into a single array
  const allPapers = papersData?.pages.flatMap(page => page.results) || [];
  const transformedPapers = allPapers.map(transformPaperForUI);
  const totalCount = papersData?.pages[0]?.count || 0;

  // Intersection observer for infinite scroll
  const { targetRef, isIntersecting } = useIntersectionObserver({
    threshold: 0.1,
    rootMargin: '50px'
  });

  // Fetch next page when intersection observer triggers
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
          <div className="flex items-center justify-center min-h-[400px]">
            <div className="flex items-center space-x-2">
              <Loader2 className="w-6 h-6 animate-spin" />
              <span>Loading task...</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !task) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-16 text-center">
          <h1 className="text-2xl font-bold mb-4">Task not found</h1>
          <p className="text-muted-foreground mb-4">
            {error?.message || "The requested task could not be found."}
          </p>
          <Link to="/tasks">
            <Button>Back to Tasks</Button>
          </Link>
        </div>
      </div>
    );
  }

  const datasets = datasetsData?.results || [];
  const hasLeaderboards = datasets.length > 0;

  return (
    <div className="min-h-screen bg-background">
      <Header />

      {/* Hero Section */}
      <div className="container mx-auto px-4 py-8">
        <div className="flex items-start gap-8">
          {/* Task Icon */}
          <div className="w-48 h-32 bg-gradient-to-br from-blue-100 to-blue-200 rounded-lg flex items-center justify-center">
            <Target className="w-16 h-16 text-blue-600" />
          </div>

          {/* Task Info */}
          <div className="flex-1">
            <div className="flex items-center justify-between mb-4">
              <h1 className="text-4xl font-bold">{task.name}</h1>
            </div>

            <div className="flex items-center gap-6 text-lg mb-4">
              <span>
                <strong>{task.paper_count?.toLocaleString() || 0}</strong> papers
              </span>
              {hasLeaderboards && (
                <span>
                  <strong>{datasets.length}</strong> benchmark{datasets.length !== 1 ? 's' : ''}
                </span>
              )}
            </div>

            {/* Breadcrumb */}
            <div className="flex items-center space-x-2 text-sm text-muted-foreground">
              <Link to="/tasks" className="hover:text-foreground transition-colors">
                Tasks
              </Link>
              <span>/</span>
              <span className="text-foreground">{task.name}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 py-8 space-y-12">
        {/* About Section */}
        <section className="space-y-4">
          <div className="flex items-center gap-3 mb-6">
            <FileText className="w-6 h-6 text-blue-600" />
            <h2 className="text-3xl font-bold">About</h2>
          </div>
          {task.description ? (
            <Card>
              <CardContent className="p-6">
                <p className="text-muted-foreground leading-relaxed text-justify">
                  {task.description}
                </p>
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="p-6">
                <div className="text-center py-8">
                  <FileText className="w-12 h-12 mx-auto mb-4 text-muted-foreground opacity-50" />
                  <h3 className="text-lg font-semibold mb-2">No Description Available</h3>
                  <p className="text-muted-foreground">
                    A description for this task has not been added yet.
                  </p>
                </div>
              </CardContent>
            </Card>
          )}
        </section>

        {/* Leaderboards Section */}
        {hasLeaderboards && (
          <section className="space-y-4">
            <div className="flex items-center gap-3 mb-6">
              <TrendingUp className="w-6 h-6 text-green-600" />
              <h2 className="text-3xl font-bold">Leaderboards</h2>
            </div>
            {datasetsLoading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-primary" />
                <span className="ml-2 text-muted-foreground">Loading benchmarks...</span>
              </div>
            ) : (
              <LeaderboardsTable datasets={datasets} taskId={taskId || ''} />
            )}
          </section>
        )}

        {/* Papers Section */}
        <section className="space-y-4">
          <div className="flex items-center gap-3 mb-6">
            <Target className="w-6 h-6 text-purple-600" />
            <h2 className="text-3xl font-bold">Papers</h2>
          </div>

          <div className="mb-6">
            {/* Sort Buttons */}
            <div className="flex items-center gap-2 mb-6">
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
              {totalCount > 0 && (
                <div className="ml-auto text-sm text-muted-foreground">
                  {totalCount} paper{totalCount !== 1 ? 's' : ''}
                </div>
              )}
            </div>
          </div>

          {/* Loading State */}
          {papersLoading && !papersData && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-primary" />
              <span className="ml-2 text-muted-foreground">Loading papers...</span>
            </div>
          )}

          {/* Error State */}
          {papersError && (
            <div className="flex items-center justify-center py-12">
              <div className="text-center">
                <p className="text-red-500 mb-2">Failed to load papers</p>
                <p className="text-sm text-muted-foreground">{papersError.message}</p>
              </div>
            </div>
          )}

          {/* Papers List */}
          {!papersLoading && !papersError && (
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
                    {!hasNextPage && transformedPapers.length > 0 && (
                      <div className="text-sm text-muted-foreground">
                        🎉 All papers loaded!
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <Card>
                  <CardContent className="p-6">
                    <div className="text-center py-8">
                      <Target className="w-12 h-12 mx-auto mb-4 text-muted-foreground opacity-50" />
                      <h3 className="text-lg font-semibold mb-2">No Papers Yet</h3>
                      <p className="text-muted-foreground">
                        No papers have been tagged with this task yet.
                      </p>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* Pagination Info */}
          {papersData && transformedPapers.length > 0 && (
            <div className="mt-8 text-center text-sm text-muted-foreground">
              Showing {transformedPapers.length} of {totalCount} papers
              {!hasNextPage && (
                <div className="mt-2 text-xs">
                  🎉 You've reached the end! All papers loaded.
                </div>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
};

// Leaderboards Table Component
interface LeaderboardsTableProps {
  datasets: Array<{
    id: number;
    name: string;
    slug?: string;
    full_name?: string;
    description?: string;
  }>;
  taskId: string;
}

interface DatasetEvaluation {
  datasetId: number;
  datasetName: string;
  datasetSlug?: string;
  modelName: string;
  paperTitle?: string;
  paperArxivId?: string;
  codeUrl?: string;
  metrics: Record<string, string | number>;
  bestRank?: number;
  trend: 'up' | 'down' | 'stable';
}

const LeaderboardsTable = ({ datasets, taskId }: LeaderboardsTableProps) => {
  // Fetch all evaluations for this task at once (for all datasets)
  const { data: allEvaluationsData, isLoading } = useEvaluations({
    task_id: parseInt(taskId),
    page_size: 100
  });

  // Process all evaluations and get the best one for each dataset
  const leaderboardData = useMemo(() => {
    if (!allEvaluationsData?.results) return [];

    const data: DatasetEvaluation[] = [];

    // Create a map of dataset ID to dataset info for quick lookup
    const datasetMap = new Map(datasets.map(d => [d.id, d]));

    // Group evaluations by dataset ID
    const evalsByDataset = new Map<number, typeof allEvaluationsData.results>();
    allEvaluationsData.results.forEach(evaluation => {
      if (!evalsByDataset.has(evaluation.dataset_id)) {
        evalsByDataset.set(evaluation.dataset_id, []);
      }
      evalsByDataset.get(evaluation.dataset_id)!.push(evaluation);
    });

    // For each dataset, get the top evaluation
    datasets.forEach((dataset) => {
      const evaluations = evalsByDataset.get(dataset.id) || [];

      if (evaluations.length > 0) {
        // Sort by best_rank and get the top result
        const sortedEvals = [...evaluations].sort((a, b) => {
          // Handle cases where best_rank might be null/undefined
          const rankA = a.best_rank ?? Number.MAX_SAFE_INTEGER;
          const rankB = b.best_rank ?? Number.MAX_SAFE_INTEGER;
          return rankA - rankB;
        });

        const topEval = sortedEvals[0];

        data.push({
          datasetId: dataset.id,
          datasetName: dataset.name,
          datasetSlug: topEval.dataset_slug || dataset.slug,
          modelName: topEval.model_name || 'Unknown Model',
          paperTitle: topEval.paper_title,
          paperArxivId: topEval.paper_arxiv_id,
          codeUrl: topEval.code_url,
          metrics: topEval.metrics || {},
          bestRank: topEval.best_rank,
          trend: Math.random() > 0.5 ? 'up' : (Math.random() > 0.5 ? 'down' : 'stable') // Placeholder
        });
      }
    });

    return data;
  }, [datasets, allEvaluationsData]);

  const getTrendIcon = (trend: 'up' | 'down' | 'stable') => {
    switch (trend) {
      case 'up':
        return <TrendingUpIcon className="w-4 h-4 text-green-600" />;
      case 'down':
        return <TrendingDown className="w-4 h-4 text-red-600" />;
      case 'stable':
        return <Minus className="w-4 h-4 text-gray-600" />;
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-8 h-8 animate-spin text-primary" />
            <span className="ml-2 text-muted-foreground">Loading leaderboards...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (leaderboardData.length === 0) {
    return (
      <Card>
        <CardContent className="p-6">
          <div className="text-center py-12">
            <TrendingUp className="w-12 h-12 mx-auto mb-4 text-muted-foreground opacity-50" />
            <h3 className="text-lg font-semibold mb-2">No Leaderboards Available</h3>
            <p className="text-muted-foreground">
              No evaluation results have been added yet for the benchmarks in this task.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b bg-muted/30">
                <th className="p-4 text-left text-sm font-semibold text-muted-foreground uppercase tracking-wider">Trend</th>
                <th className="p-4 text-left text-sm font-semibold text-muted-foreground uppercase tracking-wider">Dataset</th>
                <th className="p-4 text-left text-sm font-semibold text-muted-foreground uppercase tracking-wider">Best Method</th>
                <th className="p-4 text-left text-sm font-semibold text-muted-foreground uppercase tracking-wider">Paper Title</th>
                <th className="p-4 text-center text-sm font-semibold text-muted-foreground uppercase tracking-wider">Paper</th>
                <th className="p-4 text-center text-sm font-semibold text-muted-foreground uppercase tracking-wider">Code</th>
                <th className="p-4 text-center text-sm font-semibold text-muted-foreground uppercase tracking-wider">Compare</th>
              </tr>
            </thead>
            <tbody>
              {leaderboardData.map((item, index) => {
                const metricsStr = Object.entries(item.metrics)
                  .map(([key, value]) => `${key}: ${typeof value === 'number' ? value.toFixed(2) : value}`)
                  .join(', ');

                return (
                  <tr key={item.datasetId} className={`border-b last:border-0 hover:bg-muted/20 transition-colors ${index % 2 === 0 ? 'bg-background' : 'bg-muted/5'}`}>
                    <td className="p-4">
                      <div className="flex items-center justify-center">
                        {getTrendIcon(item.trend)}
                      </div>
                    </td>
                    <td className="p-4">
                      <div className="font-medium text-base">{item.datasetName}</div>
                      {metricsStr && (
                        <div className="text-xs text-muted-foreground mt-1">{metricsStr}</div>
                      )}
                    </td>
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="bg-yellow-50 text-yellow-800 border-yellow-300">
                          🏆
                        </Badge>
                        <span className="font-medium">{item.modelName}</span>
                      </div>
                    </td>
                    <td className="p-4">
                      {item.paperTitle && item.paperArxivId ? (
                        <Link
                          to={`/paper/${item.paperArxivId}`}
                          className="text-blue-600 hover:text-blue-800 hover:underline"
                        >
                          {item.paperTitle}
                        </Link>
                      ) : (
                        <span className="text-muted-foreground italic">No paper linked</span>
                      )}
                    </td>
                    <td className="p-4 text-center">
                      {item.paperArxivId ? (
                        <Link to={`/paper/${item.paperArxivId}`}>
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                            <FileText className="w-4 h-4" />
                          </Button>
                        </Link>
                      ) : (
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0" disabled>
                          <FileText className="w-4 h-4 text-muted-foreground" />
                        </Button>
                      )}
                    </td>
                    <td className="p-4 text-center">
                      {item.codeUrl ? (
                        <a href={item.codeUrl} target="_blank" rel="noopener noreferrer">
                          <Button variant="ghost" size="sm" className="h-8 w-8 p-0">
                            <Github className="w-4 h-4" />
                          </Button>
                        </a>
                      ) : (
                        <Button variant="ghost" size="sm" className="h-8 w-8 p-0" disabled>
                          <Github className="w-4 h-4 text-muted-foreground" />
                        </Button>
                      )}
                    </td>
                    <td className="p-4 text-center">
                      {item.datasetSlug ? (
                        <Link to={`/benchmark/${item.datasetSlug}`}>
                          <Button variant="outline" size="sm" className="text-xs">
                            See all
                          </Button>
                        </Link>
                      ) : (
                        <Button variant="outline" size="sm" className="text-xs" disabled>
                          See all
                        </Button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
};

export default TaskDetail;
