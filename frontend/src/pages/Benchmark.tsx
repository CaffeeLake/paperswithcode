import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Header from "@/components/Header";
import { ArrowLeft, Trophy, Calendar, Github, ExternalLink, CheckCircle, Loader2, ChevronDown } from "lucide-react";
import { useParams, Link } from "react-router-dom";
import { useDatasetBySlug } from "@/hooks/useDatasets";
import { useEvaluationsByDataset } from "@/hooks/useEvaluations";
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
  const [sortBy, setSortBy] = useState<string>('date');
  const [modelFilter, setModelFilter] = useState<string>('all');

  // Fetch dataset by slug
  const { data: dataset, isLoading: datasetLoading, error: datasetError } = useDatasetBySlug(datasetSlug);

  // Fetch evaluations for this dataset
  const { data: evaluations, isLoading: evaluationsLoading } = useEvaluationsByDataset(
    dataset?.id,
    !!dataset?.id
  );

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

  // Get available metrics
  const availableMetrics = useMemo(() => {
    if (!evaluations || evaluations.length === 0) return [];
    const firstEval = evaluations[0];
    return Object.keys(firstEval?.metrics || {});
  }, [evaluations]);

  // Set default metric
  useEffect(() => {
    if (availableMetrics.length > 0 && !selectedMetric) {
      setSelectedMetric(evaluations?.[0]?.best_metric || availableMetrics[0]);
    }
  }, [availableMetrics, selectedMetric, evaluations]);

  // Process evaluations to include paper info and sort by metric value
  const processedEvaluations = useMemo(() => {
    if (!evaluations) return [];

    // Get primary metric
    const primaryMetric = selectedMetric || evaluations[0]?.best_metric || Object.keys(evaluations[0]?.metrics || {})[0];

    // Sort by metric value (descending)
    return evaluations
      .map(e => ({
        ...e,
        primaryMetric,
        primaryValue: parseFloat(String(e.metrics[primaryMetric] || 0)),
        year: e.evaluated_on ? new Date(e.evaluated_on).getFullYear() : null
      }))
      .sort((a, b) => {
        if (sortBy === 'date') {
          return new Date(b.evaluated_on || 0).getTime() - new Date(a.evaluated_on || 0).getTime();
        }
        return b.primaryValue - a.primaryValue;
      });
  }, [evaluations, selectedMetric, sortBy]);

  // Get top models for chart (models with best scores)
  const topModels = useMemo(() => {
    const sorted = [...processedEvaluations].sort((a, b) => b.primaryValue - a.primaryValue);
    return sorted.slice(0, Math.min(10, sorted.length));
  }, [processedEvaluations]);

  // Prepare chart data - group by date and show top performers
  const chartData = useMemo(() => {
    if (!topModels.length) return [];

    // Group evaluations by paper_id to ensure same date for results from the same paper
    const paperDates = new Map<string, number>();
    topModels
      .filter(e => e.evaluated_on && e.paper_id)
      .forEach(e => {
        const paperId = e.paper_id;
        const date = new Date(e.evaluated_on!).getTime();
        if (!paperDates.has(paperId) || paperDates.get(paperId)! > date) {
          // Use the earliest evaluated_on date for this paper
          paperDates.set(paperId, date);
        }
      });

    return topModels
      .filter(e => e.evaluated_on)
      .map(e => {
        // Use the paper's date if available, otherwise use the evaluation's own date
        const dateTimestamp = e.paper_id && paperDates.has(e.paper_id)
          ? paperDates.get(e.paper_id)!
          : new Date(e.evaluated_on!).getTime();

        return {
          date: dateTimestamp,
          dateStr: new Date(dateTimestamp).toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
          value: e.primaryValue,
          model: e.model_name || 'Unknown',
          isTop: true
        };
      })
      .sort((a, b) => a.date - b.date);
  }, [topModels]);

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
                    <span className="text-muted-foreground">View</span>
                    <Select value={selectedMetric} onValueChange={setSelectedMetric}>
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
                    <span className="text-muted-foreground">by</span>
                    <Select value={sortBy} onValueChange={setSortBy}>
                      <SelectTrigger className="w-[120px] h-8">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="date">Date</SelectItem>
                        <SelectItem value="score">Score</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="flex items-center space-x-2">
                    <span className="text-muted-foreground">for</span>
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
                    dot={(props: any) => {
                      const { cx, cy, payload } = props;
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
                  <div className="w-3 h-3 rounded-full bg-gray-300"></div>
                  <span className="text-muted-foreground">Other models</span>
                </div>
                <div className="flex items-center space-x-2">
                  <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                  <span className="text-muted-foreground">Models with highest {selectedMetric || 'metric'}</span>
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
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">Model</th>
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">
                      {selectedMetric || processedEvaluations[0]?.primaryMetric || 'Metric'}
                    </th>
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">Paper</th>
                    <th className="text-center py-3 px-4 font-medium text-muted-foreground">Code</th>
                    <th className="text-center py-3 px-4 font-medium text-muted-foreground">Result</th>
                    <th className="text-center py-3 px-4 font-medium text-muted-foreground">Year</th>
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">Tags</th>
                  </tr>
                </thead>
                <tbody>
                    {processedEvaluations.map((evaluation, index) => {
                      const rank = evaluation.best_rank || index + 1;
                      const taskName = taskMap[evaluation.task_id] || '';

                      return (
                        <tr key={evaluation.id} className="border-b border-border hover:bg-muted/20">
                        <td className="py-4 px-2">
                          <div className="text-center font-medium">{rank}</div>
                        </td>
                        <td className="py-4 px-4">
                          <div className="font-medium">{evaluation.model_name || 'Unknown Model'}</div>
                        </td>
                        <td className="py-4 px-4">
                          <div className="font-semibold">{evaluation.primaryValue.toFixed(2)}</div>
                        </td>
                        <td className="py-4 px-4">
                          {evaluation.paper_title && evaluation.paper_arxiv_id ? (
                            <Link
                              to={`/paper/${evaluation.paper_arxiv_id}`}
                              className="text-primary hover:underline text-sm"
                            >
                              {evaluation.paper_title.length > 60
                                ? `${evaluation.paper_title.substring(0, 60)}...`
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
                          {evaluation.result_url ? (
                            <a
                              href={evaluation.result_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="inline-flex items-center justify-center text-primary hover:underline"
                              title="View results"
                            >
                              <CheckCircle className="w-4 h-4" />
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
                        <td className="py-4 px-4">
                          <div className="flex flex-wrap gap-1">
                            {taskName && (
                              <Badge variant="secondary" className="text-xs">
                                {taskName}
                              </Badge>
                            )}
                            {evaluation.uses_additional_data && (
                              <Badge variant="secondary" className="text-xs bg-orange-100 text-orange-700">
                                Extra data
                              </Badge>
                            )}
                          </div>
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
