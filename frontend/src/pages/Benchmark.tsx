import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import Header from "@/components/Header";
import { ArrowLeft, Trophy, Calendar, Github, ExternalLink, CheckCircle, Loader2 } from "lucide-react";
import { useParams, Link } from "react-router-dom";
import { useDatasetBySlug } from "@/hooks/useDatasets";
import { useEvaluationsByDataset } from "@/hooks/useEvaluations";
import { getTasks, getPaper, type Task, type Paper, type Evaluation } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ZAxis } from 'recharts';

interface EvaluationWithPaperAndTask extends Evaluation {
  paper?: Paper;
  task?: Task;
}

const Benchmark = () => {
  const { datasetSlug } = useParams<{ datasetSlug: string }>();

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

  // Process evaluations to include paper info and sort by metric value
  const processedEvaluations = useMemo(() => {
    if (!evaluations) return [];

    // Get primary metric from first evaluation
    const firstEval = evaluations[0];
    const primaryMetric = firstEval?.best_metric || Object.keys(firstEval?.metrics || {})[0];

    // Sort by metric value (descending)
    return evaluations
      .map(e => ({
        ...e,
        primaryMetric,
        primaryValue: parseFloat(String(e.metrics[primaryMetric] || 0))
      }))
      .sort((a, b) => b.primaryValue - a.primaryValue);
  }, [evaluations]);

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
            <Badge variant="secondary" className="bg-primary/10 text-primary">
              Benchmark Leaderboard
            </Badge>
            <div className="flex items-center space-x-1">
              <Calendar className="w-4 h-4" />
              <span>Updated {new Date().toLocaleDateString()}</span>
            </div>
            {evaluations && (
              <span>{evaluations.length} evaluation{evaluations.length !== 1 ? 's' : ''}</span>
            )}
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
              <CardTitle>Performance Chart</CardTitle>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <ScatterChart margin={{ top: 20, right: 30, bottom: 60, left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis
                    type="category"
                    dataKey="index"
                    name="Rank"
                    label={{ value: 'Rank', position: 'insideBottom', offset: -10 }}
                    domain={[0, processedEvaluations.length + 1]}
                  />
                  <YAxis
                    type="number"
                    dataKey="primaryValue"
                    name={processedEvaluations[0]?.primaryMetric || 'Score'}
                    label={{ value: processedEvaluations[0]?.primaryMetric || 'Score', angle: -90, position: 'insideLeft' }}
                    domain={['auto', 'auto']}
                  />
                  <ZAxis range={[100, 400]} />
                  <Tooltip
                    cursor={{ strokeDasharray: '3 3' }}
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload;
                        return (
                          <div className="bg-background border border-border rounded-lg shadow-lg p-3">
                            <p className="font-semibold text-sm">{data.model_name || 'Unknown Model'}</p>
                            <p className="text-xs text-muted-foreground">Rank #{data.index}</p>
                            <p className="text-sm mt-1">
                              <span className="font-medium">{data.primaryMetric}:</span> {data.primaryValue.toFixed(2)}
                            </p>
                            {data.uses_additional_data && (
                              <Badge variant="secondary" className="text-xs mt-1">Extra data</Badge>
                            )}
                          </div>
                        );
                      }
                      return null;
                    }}
                  />
                  <Scatter
                    data={processedEvaluations.map((e, idx) => ({
                      ...e,
                      index: idx + 1
                    }))}
                    fill="#3b82f6"
                  >
                    {processedEvaluations.map((evaluation, index) => (
                      <Cell
                        key={`cell-${index}`}
                        fill={evaluation.best_rank === 1 ? '#eab308' : '#3b82f6'}
                        opacity={0.8}
                      />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
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
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-3 px-2 font-medium text-muted-foreground">Rank</th>
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">Model</th>
                      <th className="text-left py-3 px-4 font-medium text-muted-foreground">
                        {processedEvaluations[0]?.primaryMetric || 'Metric'}
                      </th>
                    <th className="text-left py-3 px-4 font-medium text-muted-foreground">Paper</th>
                      <th className="text-left py-3 px-4 font-medium text-muted-foreground">Task</th>
                      <th className="text-center py-3 px-2 font-medium text-muted-foreground">Additional Data</th>
                      <th className="text-left py-3 px-4 font-medium text-muted-foreground">Date</th>
                  </tr>
                </thead>
                <tbody>
                    {processedEvaluations.map((evaluation, index) => {
                      const rank = evaluation.best_rank || index + 1;
                      const taskName = taskMap[evaluation.task_id] || `Task ${evaluation.task_id}`;

                      return (
                        <tr key={evaluation.id} className="border-b border-border hover:bg-muted/20">
                        <td className="py-4 px-2">
                            <div className={`flex items-center justify-center w-8 h-8 rounded-full ${
                              rank === 1 ? 'bg-yellow-500/20 text-yellow-700 font-bold' : 'bg-muted'
                            } text-sm font-medium`}>
                              {rank}
                          </div>
                        </td>
                        <td className="py-4 px-4">
                            <div className="font-semibold">{evaluation.model_name || 'Unknown Model'}</div>
                            {evaluation.methodology && (
                              <div className="text-xs text-muted-foreground mt-1">
                                {evaluation.methodology.substring(0, 50)}
                                {evaluation.methodology.length > 50 ? '...' : ''}
                              </div>
                            )}
                        </td>
                        <td className="py-4 px-4">
                            <div className="font-semibold text-lg">{evaluation.primaryValue.toFixed(2)}</div>
                        </td>
                        <td className="py-4 px-4">
                          <Link
                              to={`/paper/${evaluation.paper_id}`}
                              className="text-primary hover:underline text-sm"
                            >
                              Paper {evaluation.paper_id}
                            </Link>
                          </td>
                          <td className="py-4 px-4 text-sm text-muted-foreground">
                            {taskName}
                        </td>
                        <td className="py-4 px-2 text-center">
                            {evaluation.uses_additional_data && (
                              <Badge variant="secondary" className="text-xs">Extra data</Badge>
                          )}
                        </td>
                          <td className="py-4 px-4 text-muted-foreground text-sm">
                            {evaluation.evaluated_on ? new Date(evaluation.evaluated_on).toLocaleDateString() : '-'}
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
