import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Header from "@/components/Header";
import { ArrowLeft, Trophy, Calendar, Github, ExternalLink, CheckCircle, Loader2, ChevronDown } from "lucide-react";
import { useParams, Link } from "react-router-dom";
import { useDatasetBySlug } from "@/hooks/useDatasets";
import { useEvaluationsByDataset } from "@/hooks/useEvaluations";
import { useMetricDirections } from "@/hooks/useMetrics";
import { getTasks, getPaper, type Task, type Paper, type Evaluation } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState, useEffect } from "react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Dot } from 'recharts';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

interface EvaluationWithPaperAndTask extends Evaluation {
  paper?: Paper;
  task?: Task;
}

const Benchmark = () => {
  const { datasetSlug } = useParams<{ datasetSlug: string }>();

  // Filter states
  const [selectedMetric, setSelectedMetric] = useState<string>('');
  const [sortBy, setSortBy] = useState<string>('rank');
  const [modelFilter, setModelFilter] = useState<string>('all');

  // Fetch dataset by slug
  const { data: dataset, isLoading: datasetLoading, error: datasetError } = useDatasetBySlug(datasetSlug);

  // Fetch evaluations for this dataset
  const { data: evaluations, isLoading: evaluationsLoading } = useEvaluationsByDataset(
    dataset?.id,
    !!dataset?.id
  );

  // Fetch metric directions for correct sorting
  const { data: metricDirectionsData } = useMetricDirections();
  const metricDirections = metricDirectionsData?.directions || {};

  // Fetch tasks to display task names
  const { data: tasksData } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => getTasks({ page_size: 100 }),
  });

  // Create a map of task IDs to task names
  const taskMap = useMemo(() => {
    if (!tasksData?.results) return {};
    return Object.fromEntries(
      tasksData.results.map((task: Task) => [task.id, task.name])
    );
  }, [tasksData]);

  // Get available metrics across all evaluations (these will be our table columns)
  const availableMetrics = useMemo(() => {
    if (!evaluations || evaluations.length === 0) return [];
    const metricsSet = new Set<string>();
    evaluations.forEach(e => {
      Object.keys(e.metrics || {}).forEach(metric => metricsSet.add(metric));
    });
    // Sort metrics alphabetically for consistent column order
    return Array.from(metricsSet).sort();
  }, [evaluations]);

  // Set default selected metric for sorting (use best_metric from first evaluation)
  useEffect(() => {
    if (availableMetrics.length > 0 && !selectedMetric) {
      setSelectedMetric(evaluations?.[0]?.best_metric || availableMetrics[0]);
    }
  }, [availableMetrics, selectedMetric, evaluations]);

  // Process evaluations to include paper info and sort by selected metric
  const processedEvaluations = useMemo(() => {
    if (!evaluations) return [];

    // Get the metric to sort by
    const sortMetric = selectedMetric || evaluations[0]?.best_metric || availableMetrics[0];

    // Get the metric direction (default to higher_is_better if not found)
    const metricDirection = sortMetric ? (metricDirections[sortMetric] || 'higher_is_better') : 'higher_is_better';

    // Sort by selected metric or rank
    return evaluations
      .map(e => {
        // Get value for the selected sort metric
        const sortValue = sortMetric && e.metrics[sortMetric]
          ? parseFloat(String(e.metrics[sortMetric]))
          : 0;

        return {
          ...e,
          sortValue,
          year: e.evaluated_on
            ? new Date(e.evaluated_on).getFullYear()
            : e.paper_published_date
              ? new Date(e.paper_published_date).getFullYear()
              : null
        };
      })
      .sort((a, b) => {
        if (sortBy === 'rank') {
          // Sort by best_rank (ascending - lower rank is better)
          // Items without a rank go to the end
          const rankA = a.best_rank ?? Number.MAX_SAFE_INTEGER;
          const rankB = b.best_rank ?? Number.MAX_SAFE_INTEGER;
          if (rankA !== rankB) {
            return rankA - rankB;
          }
          // If ranks are equal, use sort metric value as tiebreaker (respecting direction)
          if (metricDirection === 'lower_is_better') {
            return a.sortValue - b.sortValue; // Lower is better
          } else {
            return b.sortValue - a.sortValue; // Higher is better
          }
        }
        if (sortBy === 'date') {
          const dateA = a.evaluated_on || a.paper_published_date || 0;
          const dateB = b.evaluated_on || b.paper_published_date || 0;
          return new Date(dateB).getTime() - new Date(dateA).getTime();
        }
        // Default: sort by selected metric value based on direction
        if (metricDirection === 'lower_is_better') {
          // For metrics like WER, lower is better (ascending sort)
          return a.sortValue - b.sortValue;
        } else {
          // For metrics like AP/Accuracy, higher is better (descending sort)
          return b.sortValue - a.sortValue;
        }
      });
  }, [evaluations, selectedMetric, sortBy, availableMetrics, metricDirections]);

  // Prepare chart data - show best result per paper over time
  const chartData = useMemo(() => {
    if (!processedEvaluations.length) return [];

    // Filter evaluations with valid dates
    const evaluationsWithDates = processedEvaluations
      .filter(e => e.evaluated_on || e.paper_published_date)
      .map(e => {
        const dateStr = e.evaluated_on || e.paper_published_date;
        const dateTimestamp = new Date(dateStr!).getTime();
        return {
          date: dateTimestamp,
          dateStr: new Date(dateTimestamp).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
          value: e.sortValue,
          model: e.model_name || 'Unknown',
          paperId: e.paper_id,
          evaluation: e
        };
      });

    // Group evaluations by paper_id and keep only the best result per paper
    const paperBestResults = new Map<string, typeof evaluationsWithDates[0]>();

    for (const point of evaluationsWithDates) {
      const existing = paperBestResults.get(point.paperId);
      if (!existing || point.value > existing.value) {
        paperBestResults.set(point.paperId, point);
      }
    }

    // Convert to array, sort by date, and build chart data
    const bestResultsPerPaper = Array.from(paperBestResults.values())
      .sort((a, b) => a.date - b.date)
      .map(point => ({
        date: point.date,
        dateStr: point.dateStr,
        value: point.value,
        model: point.model,
        isTop: true
      }));

    return bestResultsPerPaper;
  }, [processedEvaluations]);

  // Get the best evaluation (SOTA)
  const sotaEvaluation = processedEvaluations.find(e => e.best_rank === 1) || processedEvaluations[0];

  if (datasetLoading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <main className="container mx-auto px-4 py-8">
          <div className="flex items-center justify-center min-h-[400px]">
            <div className="flex items-center space-x-2">
              <Loader2 className="w-6 h-6 animate-spin" />
              <span>Loading benchmark...</span>
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (datasetError || !dataset) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <main className="container mx-auto px-4 py-8">
          <div className="flex items-center justify-center min-h-[400px]">
            <div className="text-center">
              <h2 className="text-2xl font-bold mb-2">Dataset Not Found</h2>
              <p className="text-muted-foreground mb-4">
                The requested benchmark dataset could not be found.
              </p>
              <Link to="/papers">
                <Button>Browse Papers</Button>
              </Link>
            </div>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        {/* Breadcrumb */}
        <div className="flex items-center space-x-2 text-sm text-muted-foreground mb-6">
          <Link to="/papers" className="hover:text-foreground transition-colors flex items-center space-x-1">
            <ArrowLeft className="w-4 h-4" />
            <span>Back to papers</span>
          </Link>
          <span>/</span>
          <span className="text-foreground">Benchmark Results</span>
        </div>

        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center space-x-3 mb-4">
            <Trophy className="w-6 h-6 text-yellow-600" />
            <h1 className="text-3xl font-bold">{dataset.full_name || dataset.name}</h1>
          </div>

          <div className="flex items-center space-x-4 text-sm text-muted-foreground">
            <Badge variant="secondary" className="bg-blue-500 text-white px-3 py-1">
              State-of-the-Art Leaderboard
            </Badge>
            <div className="flex items-center space-x-1">
              <Calendar className="w-4 h-4" />
              <span>Updated {dataset.updated_at ? new Date(dataset.updated_at).toLocaleDateString('en-US', { day: 'numeric', month: 'numeric', year: 'numeric' }) : new Date().toLocaleDateString('en-US', { day: 'numeric', month: 'numeric', year: 'numeric' })}</span>
            </div>
          </div>

          {dataset.description && (
            <p className="mt-4 text-sm text-muted-foreground max-w-3xl">
              {dataset.description}
            </p>
          )}
        </div>

        {/* Leaderboard Chart */}
        {!evaluationsLoading && processedEvaluations.length > 0 && (
          <Card className="mb-8">
            <CardHeader>
              <div className="flex flex-col space-y-4">
                <CardTitle>Leaderboard</CardTitle>

                {/* Filter Controls */}
                <div className="flex items-center space-x-6 text-sm">
                  <div className="flex items-center space-x-2">
                    <span className="text-muted-foreground">Sort by</span>
                    <Select value={selectedMetric || availableMetrics[0]} onValueChange={setSelectedMetric}>
                      <SelectTrigger className="w-[200px] h-8">
                        <SelectValue placeholder="Select metric" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableMetrics.map(metric => (
                          <SelectItem key={metric} value={metric}>
                            {metric}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="flex items-center space-x-2">
                    <span className="text-muted-foreground">Order</span>
                    <Select value={sortBy} onValueChange={setSortBy}>
                      <SelectTrigger className="w-[120px] h-8">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="rank">Rank</SelectItem>
                        <SelectItem value="score">Score</SelectItem>
                        <SelectItem value="date">Date</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="flex items-center space-x-2">
                    <span className="text-muted-foreground">Filter</span>
                    <Select value={modelFilter} onValueChange={setModelFilter}>
                      <SelectTrigger className="w-[140px] h-8">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="all">All models</SelectItem>
                        <SelectItem value="top">Top models</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <LineChart data={chartData} margin={{ top: 20, right: 30, bottom: 40, left: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                  <XAxis
                    dataKey="date"
                    type="number"
                    domain={['dataMin', 'dataMax']}
                    tick={{ fontSize: 12 }}
                    tickLine={{ stroke: '#e5e7eb' }}
                    axisLine={{ stroke: '#e5e7eb' }}
                    tickFormatter={(value) => {
                      return new Date(value).toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
                    }}
                  />
                  <YAxis
                    label={{
                      value: selectedMetric || 'Score',
                      angle: -90,
                      position: 'insideLeft',
                      style: { textAnchor: 'middle', fontSize: 12 }
                    }}
                    tick={{ fontSize: 12 }}
                    tickLine={{ stroke: '#e5e7eb' }}
                    axisLine={{ stroke: '#e5e7eb' }}
                    domain={['auto', 'auto']}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-background border border-border rounded-lg shadow-lg p-3">
                            <p className="font-semibold text-sm">{data.model}</p>
                            <p className="text-xs text-muted-foreground">{data.dateStr}</p>
                            <p className="text-sm mt-1">
                              <span className="font-medium">{selectedMetric}:</span> {data.value.toFixed(2)}
                            </p>
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#0ea5e9"
                    strokeWidth={2}
                    dot={(props: { cx: number; cy: number; payload: unknown }) => {
                      const { cx, cy } = props;
                      return (
                        <Dot
                          cx={cx}
                          cy={cy}
                          r={6}
                          fill="#0ea5e9"
                          stroke="#fff"
                          strokeWidth={2}
                        />
                      );
                    }}
                    activeDot={{ r: 8 }}
                  />
                </LineChart>
              </ResponsiveContainer>

              {/* Legend */}
              <div className="flex items-center justify-center space-x-6 mt-4 text-xs">
                <div className="flex items-center space-x-2">
                  <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                  <span className="text-muted-foreground">
                    Best result per paper
                  </span>
                </div>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Current Rankings Table */}
        <Card>
          <CardHeader>
            <CardTitle>Leaderboard</CardTitle>
          </CardHeader>
          <CardContent>
            {evaluationsLoading ? (
              <div className="flex items-center justify-center py-8">
                <Loader2 className="w-6 h-6 animate-spin mr-2" />
                <span>Loading evaluations...</span>
              </div>
            ) : processedEvaluations.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-2 font-medium text-muted-foreground">Rank</th>
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground min-w-[200px]">Model</th>
                    {/* Dynamic metric columns */}
                    {availableMetrics.map(metric => (
                      <th key={metric} className="text-left py-3 px-4 font-medium text-muted-foreground whitespace-nowrap">
                        {metric}
                        {metric === selectedMetric && (
                          <span className="text-primary ml-1">↓</span>
                        )}
                      </th>
                    ))}
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">Paper</th>
                    <th className="text-center py-3 px-4 font-medium text-muted-foreground">Code</th>
                    <th className="text-center py-3 px-4 font-medium text-muted-foreground">Year</th>
                  </tr>
                </thead>
                <tbody>
                    {processedEvaluations.map((evaluation, index) => {
                      const rank = evaluation.best_rank || index + 1;

                      return (
                        <tr key={evaluation.id} className="border-b border-border hover:bg-muted/20">
                        <td className="py-4 px-2">
                          <div className="text-center font-medium">{rank}</div>
                        </td>
                        <td className="py-4 px-4">
                          <div className="font-medium">{evaluation.model_name || 'Unknown Model'}</div>
                        </td>
                        {/* Dynamic metric value columns */}
                        {availableMetrics.map(metric => {
                          const value = evaluation.metrics[metric];
                          return (
                            <td key={metric} className="py-4 px-4">
                              {value !== undefined && value !== null ? (
                                <div className="font-semibold">
                                  {typeof value === 'number' ? value.toFixed(2) : value}
                                </div>
                              ) : (
                                <span className="text-muted-foreground">-</span>
                              )}
                            </td>
                          );
                        })}
                        <td className="py-4 px-4">
                          {evaluation.paper_title && evaluation.paper_arxiv_id ? (
                            <Link
                              to={`/paper/${evaluation.paper_arxiv_id}`}
                              className="text-primary hover:underline text-sm"
                            >
                              {evaluation.paper_title.length > 50
                                ? `${evaluation.paper_title.substring(0, 50)}...`
                                : evaluation.paper_title}
                            </Link>
                          ) : evaluation.paper_arxiv_id ? (
                            <Link
                              to={`/paper/${evaluation.paper_arxiv_id}`}
                              className="text-primary hover:underline inline-flex items-center space-x-1 text-sm"
                            >
                              <ExternalLink className="w-3 h-3" />
                              <span>View</span>
                            </Link>
                          ) : (
                            <span className="text-muted-foreground text-sm">N/A</span>
                          )}
                        </td>
                        <td className="py-4 px-4 text-center">
                          {evaluation.code_url ? (
                            <a
                              href={evaluation.code_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center justify-center w-8 h-8 rounded hover:bg-muted transition-colors"
                              title="View code repository"
                            >
                              <Github className="w-4 h-4 text-muted-foreground hover:text-foreground" />
                            </a>
                          ) : (
                            <span className="text-muted-foreground text-xs">-</span>
                          )}
                        </td>
                        <td className="py-4 px-4 text-center">
                          <span className="text-muted-foreground">
                            {evaluation.year || (evaluation.evaluated_on ? new Date(evaluation.evaluated_on).getFullYear() : '-')}
                          </span>
                        </td>
                      </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Trophy className="w-12 h-12 mx-auto mb-3 opacity-30" />
                <p>No evaluation results available for this dataset yet.</p>
              </div>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  );
};

export default Benchmark;
