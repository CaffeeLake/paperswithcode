import { useMemo } from "react";
import { Loader2, Edit, Trophy, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getTasks, getDatasets, type Task as APITask, type Dataset, type Evaluation as APIEvaluation } from "@/lib/api";

interface TaskEvaluationsGroup {
  taskId: string;
  taskName: string;
  evaluations: APIEvaluation[];
  metrics: string[];
  totalMetricsCount: number;
}

interface EvaluationResultsCardProps {
  evaluations: APIEvaluation[] | undefined;
  isLoading: boolean;
  onEdit: () => void;
}

const MAX_VISIBLE_METRICS = 6;

export function EvaluationResultsCard({ evaluations, isLoading, onEdit }: EvaluationResultsCardProps) {
  // Fetch tasks and datasets to display names instead of IDs
  const { data: allTasksDataForEvals } = useQuery({
    queryKey: ['tasks-for-evals'],
    queryFn: () => getTasks({ page_size: 100 }),
    enabled: !!evaluations && evaluations.length > 0,
  });

  const { data: allDatasetsData } = useQuery({
    queryKey: ['datasets-for-evals'],
    queryFn: () => getDatasets({ page_size: 100 }),
    enabled: !!evaluations && evaluations.length > 0,
  });

  // Group evaluations by task
  const evaluationsByTask = useMemo<TaskEvaluationsGroup[]>(() => {
    if (!evaluations) return [];

    const grouped = new Map<string, { evaluations: APIEvaluation[]; metrics: Set<string> }>();

    evaluations.forEach(evaluation => {
      const taskId = evaluation.task_id;
      if (!grouped.has(taskId)) {
        grouped.set(taskId, { evaluations: [], metrics: new Set<string>() });
      }

      const taskGroup = grouped.get(taskId)!;
      taskGroup.evaluations.push(evaluation);

      if (evaluation.metrics) {
        Object.keys(evaluation.metrics).forEach(metric => taskGroup.metrics.add(metric));
      }
    });

    return Array.from(grouped.entries()).map(([taskId, group]) => {
      const taskName = group.evaluations[0]?.task_name ||
        allTasksDataForEvals?.results?.find((t: APITask) => t.id === taskId)?.name ||
        `Task ${taskId}`;

      const sortedMetrics = Array.from(group.metrics).sort();
      const visibleMetrics = sortedMetrics.slice(0, MAX_VISIBLE_METRICS);

      const taskGroup = {
        taskId,
        taskName,
        evaluations: group.evaluations,
        metrics: visibleMetrics,
        totalMetricsCount: sortedMetrics.length,
      };

      return taskGroup;
    }).sort((a, b) => a.taskName.localeCompare(b.taskName));
  }, [evaluations, allTasksDataForEvals]);

  // Determine the maximum number of metric columns across all task groups
  const maxMetricCount = useMemo(() => {
    if (!evaluationsByTask.length) {
      return 0;
    }

    return evaluationsByTask.reduce(
      (max, group) => (group.metrics.length > max ? group.metrics.length : max),
      0
    );
  }, [evaluationsByTask]);

  // Calculate column widths for a specific number of metrics
  const calculateColumnWidths = (metricCount: number) => {
    const totalColumns = metricCount + 4; // dataset, model, rank, benchmark
    const columnWidth = totalColumns > 0 ? 100 / totalColumns : 25; // default evenly spread

    return {
      dataset: columnWidth,
      model: columnWidth,
      rank: columnWidth,
      benchmark: columnWidth,
      metric: columnWidth,
      datasetMinWidth: '140px',
      modelMinWidth: '140px',
      metricMinWidth: '90px',
      rankMinWidth: '70px',
      benchmarkMinWidth: '120px',
    };
  };

  return (
    <Card className="mb-8">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="text-xl font-semibold">Results from the paper</CardTitle>
          <Button
            variant="ghost"
            size="sm"
            className="flex items-center space-x-1 text-muted-foreground"
            onClick={onEdit}
          >
            <Edit className="w-4 h-4" />
            <span>Edit</span>
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="w-6 h-6 animate-spin mr-2" />
            <span>Loading evaluation results...</span>
          </div>
        ) : evaluations && evaluations.length > 0 ? (
          <>
            {/* SOTA Badge - show if any evaluation has best_rank === 1 */}
            {evaluations.some(e => e.best_rank === 1) && (
              <div className="bg-muted/30 rounded-lg p-4 mb-6">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <Trophy className="w-5 h-5 text-yellow-600" />
                    <span className="font-semibold">State-of-the-Art results achieved</span>
                  </div>
                </div>
              </div>
            )}

            {/* Evaluation Tables - One per Task */}
            <div className="w-full">
              {evaluationsByTask.map((taskGroup, taskGroupIdx) => {
                const taskMetrics = taskGroup.metrics;
                const taskMetricCount = taskMetrics.length;
                const columnWidths = calculateColumnWidths(maxMetricCount);

                return (
                  <div key={taskGroup.taskId} className={taskGroupIdx > 0 ? 'mt-8' : ''}>
                    {/* Task Heading */}
                    <h3 className="text-lg font-semibold mb-4 text-foreground">{taskGroup.taskName}</h3>

                    {/* Evaluation Table with fixed layout for column alignment */}
                    <div className="overflow-x-auto w-full">
                      <table className="w-full" style={{ tableLayout: 'fixed', width: '100%' }}>
                        <colgroup>
                          <col style={{ width: `${columnWidths.dataset}%`, minWidth: columnWidths.datasetMinWidth }} />
                          <col style={{ width: `${columnWidths.model}%`, minWidth: columnWidths.modelMinWidth }} />
                          {taskMetrics.map((_, metricIndex) => (
                            <col
                              key={`metric-col-${metricIndex}`}
                              style={{ width: `${columnWidths.metric}%`, minWidth: columnWidths.metricMinWidth }}
                            />
                          ))}
                          <col style={{ width: `${columnWidths.rank}%`, minWidth: columnWidths.rankMinWidth }} />
                          <col style={{ width: `${columnWidths.benchmark}%`, minWidth: columnWidths.benchmarkMinWidth }} />
                        </colgroup>
                        <thead>
                          <tr className="border-b border-border">
                            <th className="text-left py-3 px-4 font-medium text-muted-foreground">Dataset</th>
                            <th className="text-left py-3 px-4 font-medium text-muted-foreground">Model</th>
                            {/* Render actual metric columns only */}
                            {taskMetrics.map((metricName, metricIndex) => (
                              <th
                                key={`metric-header-${metricIndex}`}
                                className={`py-3 px-3 font-medium text-muted-foreground whitespace-normal break-words leading-tight text-right ${taskMetricCount <= 2 ? '' : 'text-xs'}`}
                              >
                                {metricName}
                              </th>
                            ))}
                            <th className="text-center py-3 px-4 font-medium text-muted-foreground">Rank</th>
                            <th className="text-right py-3 px-4 font-medium text-muted-foreground">Benchmark</th>
                          </tr>
                        </thead>
                        <tbody>
                          {taskGroup.evaluations.map((evaluation, idx) => {
                            // Get dataset name and slug - prefer from evaluation, fallback to lookup
                            const datasetName = evaluation.dataset_name || (() => {
                              const dataset = allDatasetsData?.results?.find(
                                (d: Dataset) => d.id === evaluation.dataset_id
                              );
                              return dataset?.name || `Dataset ${evaluation.dataset_id}`;
                            })();

                            // Get dataset slug - now available directly from evaluation
                            const datasetSlug = evaluation.dataset_slug || (() => {
                              const dataset = allDatasetsData?.results?.find(
                                (d: Dataset) => d.id === evaluation.dataset_id
                              );
                              return dataset?.slug || `dataset-${evaluation.dataset_id}`;
                            })();

                            return (
                              <tr key={evaluation.id} className={`${idx < taskGroup.evaluations.length - 1 ? 'border-b border-border' : ''} hover:bg-muted/20`}>
                                <td className="py-4 px-4">{datasetName}</td>
                                <td className="py-4 px-4 font-medium">{evaluation.model_name || 'N/A'}</td>
                                {/* Render actual metric values only */}
                                {taskMetrics.map((metricName, metricIndex) => {
                                  const value = evaluation.metrics?.[metricName];
                                  const hasValue = value !== undefined && value !== null && value !== '';

                                  return (
                                    <td
                                      key={`metric-cell-${evaluation.id}-${metricIndex}`}
                                      className={`py-3 px-3 text-right ${taskMetricCount <= 2 ? '' : 'text-sm'}`}
                                    >
                                      {hasValue ? (
                                        <span className={`font-semibold ${taskMetricCount <= 2 ? '' : 'text-sm'}`}>
                                          {typeof value === 'number' ? value.toFixed(2) : value}
                                        </span>
                                      ) : (
                                        <span className="text-muted-foreground">-</span>
                                      )}
                                    </td>
                                  );
                                })}
                                <td className="py-4 px-4 font-semibold text-center">
                                  {evaluation.best_rank ? `# ${evaluation.best_rank}` : '-'}
                                </td>
                                <td className="py-4 px-4 min-w-[120px]">
                                  <div className="flex justify-end">
                                    <Button
                                      size="sm"
                                      className="bg-emerald-500 hover:bg-emerald-600 text-white rounded-full px-4"
                                      asChild
                                    >
                                      <Link to={`/benchmark/${datasetSlug}`}>
                                        See all
                                      </Link>
                                    </Button>
                                  </div>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                      {taskGroup.totalMetricsCount > MAX_VISIBLE_METRICS && (
                        <p className="text-xs text-muted-foreground mt-2">
                          Showing up to {MAX_VISIBLE_METRICS} metrics here. Visit the benchmark for the full list.
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            <Database className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>No evaluation results available for this paper yet.</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
