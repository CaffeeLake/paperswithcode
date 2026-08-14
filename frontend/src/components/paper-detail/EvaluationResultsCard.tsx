import { useMemo } from "react";
import { Loader2, Edit, Trophy, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { type Dataset, type Evaluation as APIEvaluation } from "@/lib/api";
import { catalogApi } from "@/lib/api/catalog";
import { formatMetricValue } from "@/lib/utils";

interface TaskEvaluationsGroup {
  taskId: string;
  taskName: string;
  taskSlug?: string;
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

const getNameCharLimits = (metricCount: number) => {
  if (metricCount <= 2) {
    return { dataset: Number.POSITIVE_INFINITY, model: Number.POSITIVE_INFINITY };
  }

  if (metricCount <= 4) {
    return { dataset: 60, model: 60 };
  }

  if (metricCount === 5) {
    return { dataset: 48, model: 48 };
  }

  return { dataset: 40, model: 40 };
};

const truncateText = (text: string | null | undefined, maxChars: number) => {
  if (!text) {
    return text ?? "";
  }

  if (!Number.isFinite(maxChars) || text.length <= maxChars) {
    return text;
  }

  if (maxChars <= 3) {
    return `${text.slice(0, maxChars)}...`;
  }

  return `${text.slice(0, maxChars - 3).trimEnd()}...`;
};

export function EvaluationResultsCard({ evaluations, isLoading, onEdit }: EvaluationResultsCardProps) {
  // Dataset names/slugs are served on each evaluation when available, but we keep
  // this lookup as a last-resort fallback for stale rows that pre-date the
  // `dataset_name`/`dataset_slug` fields on the evaluation payload.
  const { data: allDatasetsData } = useQuery({
    queryKey: ['datasets-for-evals'],
    queryFn: () => catalogApi.listDatasets({ page_size: 100 }),
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
      const taskName = group.evaluations[0]?.task_name || `Task ${taskId}`;
      const taskSlug = group.evaluations[0]?.task_slug || undefined;

      const sortedMetrics = Array.from(group.metrics).sort();
      const visibleMetrics = sortedMetrics.slice(0, MAX_VISIBLE_METRICS);

      const taskGroup: TaskEvaluationsGroup = {
        taskId,
        taskName,
        taskSlug,
        evaluations: group.evaluations,
        metrics: visibleMetrics,
        totalMetricsCount: sortedMetrics.length,
      };

      return taskGroup;
    }).sort((a, b) => a.taskName.localeCompare(b.taskName));
  }, [evaluations]);

  // Calculate column widths for a specific number of metrics
const calculateColumnWidths = (metricCount: number) => {
    const rankWidth = 8;
    const benchmarkWidth = 12;

    const datasetWidth =
    metricCount <= 2 ? 26 :
    metricCount <= 4 ? 22 :
    metricCount <= 5 ? 19 :
    18;

    const modelWidth = datasetWidth;

    const reservedWidth = datasetWidth + modelWidth + rankWidth + benchmarkWidth;
    const remainingWidth = Math.max(0, 100 - reservedWidth);
    const metricWidth = metricCount > 0 ? remainingWidth / metricCount : remainingWidth;

    return {
      dataset: datasetWidth,
      model: modelWidth,
      rank: rankWidth,
      benchmark: benchmarkWidth,
      metric: metricWidth,
    datasetMinWidth:
      metricCount <= 2 ? '220px' :
      metricCount <= 4 ? '170px' :
      metricCount <= 5 ? '150px' :
      '140px',
    modelMinWidth:
      metricCount <= 2 ? '220px' :
      metricCount <= 4 ? '170px' :
      metricCount <= 5 ? '150px' :
      '140px',
    metricMinWidth:
      metricCount <= 2 ? '120px' :
      metricCount <= 4 ? '105px' :
      metricCount <= 5 ? '95px' :
      '90px',
    rankMinWidth: '72px',
    benchmarkMinWidth: '118px',
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
                const columnWidths = calculateColumnWidths(taskMetricCount);
                const nameCharLimits = getNameCharLimits(taskMetricCount);

                return (
                  <div key={taskGroup.taskId} className={taskGroupIdx > 0 ? 'mt-8' : ''}>
                    {/* Task Heading — links to /tasks/{slug} when we know the canonical slug. */}
                    <h3 className="text-lg font-semibold mb-4 text-foreground">
                      {taskGroup.taskSlug ? (
                        <Link
                          to={`/tasks/${taskGroup.taskSlug}`}
                          className="hover:text-primary hover:underline underline-offset-4"
                        >
                          {taskGroup.taskName}
                        </Link>
                      ) : (
                        taskGroup.taskName
                      )}
                    </h3>

                    {/* Evaluation Table with fixed layout for column alignment */}
                    <div className="overflow-x-auto w-full">
                      <table className="w-full table-fixed">
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
                            <th className="text-left py-3 px-4 font-medium text-muted-foreground whitespace-nowrap">
                              Dataset
                            </th>
                            <th className="text-left py-3 px-4 font-medium text-muted-foreground whitespace-nowrap">
                              Model
                            </th>
                            {/* Render actual metric columns only */}
                            {taskMetrics.map((metricName, metricIndex) => {
                              const headerClassName = `py-3 px-3 font-medium text-muted-foreground whitespace-normal break-words leading-tight text-right ${
                                taskMetricCount <= 2 ? '' : 'text-xs'
                              }`;
                              return (
                                <th
                                  key={`metric-header-${metricIndex}`}
                                  className={headerClassName}
                                >
                                  {metricName}
                                </th>
                              );
                            })}
                            <th className="text-center py-3 px-4 font-medium text-muted-foreground whitespace-nowrap">
                              Rank
                            </th>
                            <th className="text-right py-3 px-4 font-medium text-muted-foreground whitespace-nowrap">
                              Benchmark
                            </th>
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

                            // Use the canonical task slug from the grouped header (sourced
                            // from the evaluation payload itself); fall back to the task ID
                            // only if no slug is available, which would also break the link.
                            const taskSlug = taskGroup.taskSlug || evaluation.task_id;

                            return (
                              <tr key={evaluation.id} className={`${idx < taskGroup.evaluations.length - 1 ? 'border-b border-border' : ''} hover:bg-muted/20`}>
                                <td className="py-4 px-4 text-sm">
                                  <div className="truncate" title={datasetName}>
                                    {truncateText(datasetName, nameCharLimits.dataset)}
                                  </div>
                                </td>
                                <td className="py-4 px-4 font-medium text-sm">
                                  <div className="truncate" title={evaluation.model_name || 'N/A'}>
                                    {evaluation.hf_model_url ? (
                                      <a
                                        href={evaluation.hf_model_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-primary hover:underline"
                                        title={`Open ${evaluation.model_name || 'model'} on Hugging Face`}
                                      >
                                        {truncateText(evaluation.model_name || 'N/A', nameCharLimits.model)}
                                      </a>
                                    ) : (
                                      truncateText(evaluation.model_name || 'N/A', nameCharLimits.model)
                                    )}
                                  </div>
                                </td>
                                {/* Render actual metric values only */}
                                {taskMetrics.map((metricName, metricIndex) => {
                                  const value = evaluation.metrics?.[metricName];
                                  const hasValue = value !== undefined && value !== null && value !== '';

                                  return (
                                    <td
                                      key={`metric-cell-${evaluation.id}-${metricIndex}`}
                                      className={`py-3 px-3 text-right whitespace-nowrap ${taskMetricCount <= 2 ? '' : 'text-sm'}`}
                                    >
                                      {metricName && hasValue ? (
                                        <span className={`font-semibold ${taskMetricCount <= 2 ? '' : 'text-sm'}`}>
                                          {formatMetricValue(value)}
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
                                      className="bg-emerald-500 hover:bg-emerald-600 text-white rounded-full px-3"
                                      asChild
                                    >
                                      <Link to={`/benchmark/${datasetSlug}?task=${taskSlug}`}>
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
