import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Check, Plus, Trash2, Database } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getTasks, getDatasets, createEvaluation, updateEvaluation, deleteEvaluation, type Task as APITask, type Dataset, type Evaluation as APIEvaluation } from "@/lib/api";

interface EditableEvaluation {
  id?: string;
  task_id: string;
  dataset_id: string;
  model_name: string;
  harness: string;
  metric_name: string;
  metric_value: string;
  best_rank?: string;
  operation?: 'create' | 'update' | 'delete' | 'unchanged';
}

interface EditEvaluationsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialEvaluations: APIEvaluation[];
  onSuccess?: () => void;
}

function mapApiEvaluationsToEditable(evaluations: APIEvaluation[]): EditableEvaluation[] {
  return evaluations.map(e => {
    const metricName = e.best_metric || Object.keys(e.metrics)[0];
    const metricValue = e.metrics[metricName];
    return {
      id: e.id,
      task_id: e.task_id,
      dataset_id: e.dataset_id,
      model_name: e.model_name || '',
      harness: e.harness || '',
      metric_name: metricName || '',
      metric_value: String(metricValue || ''),
      best_rank: e.best_rank ? String(e.best_rank) : '',
      operation: 'unchanged' as const,
    };
  });
}

export function EditEvaluationsDialog({
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialEvaluations,
  onSuccess,
}: EditEvaluationsDialogProps) {
  const [editedEvaluations, setEditedEvaluations] = useState<EditableEvaluation[]>([]);
  const queryClient = useQueryClient();

  // Seed local state from props once per open session. The parent controls
  // `open`, so initialization can't depend on Radix's `onOpenChange` callback
  // firing (it doesn't when the parent flips `open` itself). `hasSeededRef`
  // becomes true after a non-empty seed so background refetches of
  // `initialEvaluations` don't clobber the form; `hasUserEditedRef` extends
  // that protection to in-progress edits even if seeding hasn't run with
  // non-empty data yet. The dialog still late-seeds once if it was opened
  // before evaluations finished loading.
  const hasSeededRef = useRef(false);
  const hasUserEditedRef = useRef(false);

  useEffect(() => {
    if (!open) {
      hasSeededRef.current = false;
      hasUserEditedRef.current = false;
      return;
    }
    if (hasSeededRef.current) return;
    if (hasUserEditedRef.current) return;
    if (initialEvaluations.length === 0) return;
    hasSeededRef.current = true;
    setEditedEvaluations(mapApiEvaluationsToEditable(initialEvaluations));
  }, [open, initialEvaluations]);

  // Fetch all tasks and datasets for evaluation editing
  const { data: allTasksForEvals } = useQuery({
    queryKey: ['tasks-for-eval-edit'],
    queryFn: () => getTasks({ page_size: 100 }),
    enabled: open,
  });

  const { data: allDatasetsForEvals } = useQuery({
    queryKey: ['datasets-for-eval-edit'],
    queryFn: () => getDatasets({ page_size: 100 }),
    enabled: open,
  });

  // Create a map of task_id -> datasets using React Query
  const uniqueTaskIds = useMemo(() => {
    return Array.from(new Set(editedEvaluations.map(e => e.task_id).filter(id => id && id !== '')));
  }, [editedEvaluations]);

  // Fetch datasets for each unique task
  const taskDatasetsQueries = useQuery({
    queryKey: ['datasets-by-tasks', uniqueTaskIds, open],
    queryFn: async () => {
      if (!open) return {};

      const datasetsMap: Record<string, Dataset[]> = {};

      // Fetch datasets for each task in parallel
      await Promise.all(
        uniqueTaskIds.map(async (taskId) => {
          if (taskId) {
            try {
              const response = await getDatasets({ task_id: parseInt(taskId), page_size: 100 });
              datasetsMap[taskId] = response.results;
            } catch (error) {
              console.error(`Error fetching datasets for task ${taskId}:`, error);
              datasetsMap[taskId] = [];
            }
          }
        })
      );

      return datasetsMap;
    },
    enabled: open && uniqueTaskIds.length > 0,
  });

  // Function to get filtered datasets for a specific task
  const getFilteredDatasetsForTask = (taskId: string): Dataset[] => {
    // If no task is selected, return all datasets
    if (!taskId) {
      return allDatasetsForEvals?.results || [];
    }

    // If we have task-specific datasets from our query, use those
    if (taskDatasetsQueries.data && taskDatasetsQueries.data[taskId]) {
      return taskDatasetsQueries.data[taskId];
    }

    // Fallback to all datasets if the query hasn't loaded yet
    return allDatasetsForEvals?.results || [];
  };

  const selectedDatasetSupportsHarness = (taskId: string, datasetId: string): boolean => {
    if (!taskId || !datasetId) return false;
    const dataset = getFilteredDatasetsForTask(taskId).find((d) => d.id === datasetId);
    return Boolean(dataset?.supports_harness);
  };

  // Mutation for saving evaluations (handles create, update, delete)
  const saveEvaluationsMutation = useMutation({
    mutationFn: async ({ paperId, evaluations }: { paperId: string; evaluations: EditableEvaluation[] }) => {
      // Process each evaluation based on its operation
      for (const evalItem of evaluations) {
        if (evalItem.operation === 'delete' && evalItem.id) {
          try {
            await deleteEvaluation(evalItem.id);
          } catch (error: unknown) {
            // If the evaluation doesn't exist (404), that's fine - it's already gone
            const status = typeof error === 'object' && error !== null && 'status' in error
              ? (error as { status?: number }).status
              : undefined;
            if (status !== 404) {
              throw error;
            }
            console.log(`Evaluation ${evalItem.id} already deleted or not found`);
          }
        } else if (evalItem.operation === 'create') {
          const supportsHarness = selectedDatasetSupportsHarness(evalItem.task_id, evalItem.dataset_id);
          await createEvaluation({
            paper_id: parseInt(paperId),
            task_id: parseInt(evalItem.task_id),
            dataset_id: parseInt(evalItem.dataset_id),
            model_name: evalItem.model_name || undefined,
            harness: supportsHarness ? evalItem.harness || undefined : undefined,
            metrics: { [evalItem.metric_name]: evalItem.metric_value },
            best_metric: evalItem.metric_name,
            best_rank: evalItem.best_rank ? parseInt(evalItem.best_rank) : undefined,
          });
        } else if (evalItem.operation === 'update' && evalItem.id) {
          const supportsHarness = selectedDatasetSupportsHarness(evalItem.task_id, evalItem.dataset_id);
          await updateEvaluation(evalItem.id, {
            task_id: parseInt(evalItem.task_id),
            dataset_id: parseInt(evalItem.dataset_id),
            model_name: evalItem.model_name || undefined,
            harness: supportsHarness ? evalItem.harness || null : null,
            metrics: { [evalItem.metric_name]: evalItem.metric_value },
            best_metric: evalItem.metric_name,
            best_rank: evalItem.best_rank ? parseInt(evalItem.best_rank) : undefined,
          });
        }
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-arxiv', arxivId] });
      queryClient.invalidateQueries({ queryKey: ['evaluations', 'paper', paperId] });
      onSuccess?.();
      onOpenChange(false);
    },
  });

  const handleAddEvaluation = () => {
    hasUserEditedRef.current = true;
    setEditedEvaluations([
      ...editedEvaluations,
      {
        task_id: '',
        dataset_id: '',
        model_name: '',
        harness: '',
        metric_name: '',
        metric_value: '',
        best_rank: '',
        operation: 'create',
      },
    ]);
  };

  const handleDeleteEvaluation = (index: number) => {
    hasUserEditedRef.current = true;
    const evaluation = editedEvaluations[index];
    if (evaluation.id) {
      // Mark existing evaluation for deletion
      setEditedEvaluations(
        editedEvaluations.map((e, i) =>
          i === index ? { ...e, operation: 'delete' as const } : e
        )
      );
    } else {
      // Remove new evaluation from list
      setEditedEvaluations(editedEvaluations.filter((_, i) => i !== index));
    }
  };

  const handleUpdateEvaluationField = (
    index: number,
    field: keyof EditableEvaluation,
    value: string
  ) => {
    hasUserEditedRef.current = true;
    setEditedEvaluations(
      editedEvaluations.map((e, i) => {
        if (i !== index) return e;
        const updated = { ...e, [field]: value };

        // If task changes, reset the dataset selection
        if (field === 'task_id') {
          updated.dataset_id = '';
          updated.harness = '';
        }

        if (
          field === 'dataset_id' &&
          value &&
          !selectedDatasetSupportsHarness(updated.task_id, value)
        ) {
          updated.harness = '';
        }

        // Mark as updated if it was previously unchanged
        if (e.operation === 'unchanged') {
          updated.operation = 'update';
        }
        return updated;
      })
    );
  };

  const handleSave = () => {
    // Filter out evaluations marked for deletion that are shown in UI
    const evaluationsToSave = editedEvaluations.filter(
      e => e.operation !== 'delete' || e.id
    );
    saveEvaluationsMutation.mutate({
      paperId,
      evaluations: evaluationsToSave,
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl max-h-[800px]">
        <DialogHeader>
          <DialogTitle>Edit Evaluation Results</DialogTitle>
          <DialogDescription>
            Add, edit, or remove evaluation results for this paper. Each row represents a benchmark result.
          </DialogDescription>
        </DialogHeader>

        <div className="py-4 overflow-y-auto max-h-[600px]">
          {editedEvaluations.filter(e => e.operation !== 'delete').length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left py-2 px-2 font-medium text-sm">Task</th>
                    <th className="text-left py-2 px-2 font-medium text-sm">Dataset</th>
                    <th className="text-left py-2 px-2 font-medium text-sm">Model</th>
                    <th className="text-left py-2 px-2 font-medium text-sm">Harness</th>
                    <th className="text-left py-2 px-2 font-medium text-sm">Metric</th>
                    <th className="text-left py-2 px-2 font-medium text-sm">Value</th>
                    <th className="text-left py-2 px-2 font-medium text-sm w-16">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {editedEvaluations.map((evaluation, index) => {
                    if (evaluation.operation === 'delete') return null;

                    return (
                      <tr key={index} className="border-b border-border">
                        <td className="py-2 px-2">
                          <select
                            className="w-full px-2 py-1 text-sm border border-border rounded-md bg-background"
                            value={evaluation.task_id}
                            onChange={(e) => handleUpdateEvaluationField(index, 'task_id', e.target.value)}
                          >
                            <option value="">Select Task</option>
                            {allTasksForEvals?.results?.map((task: APITask) => (
                              <option key={task.id} value={task.id}>
                                {task.name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="py-2 px-2">
                          <select
                            className="w-full px-2 py-1 text-sm border border-border rounded-md bg-background"
                            value={evaluation.dataset_id}
                            onChange={(e) => handleUpdateEvaluationField(index, 'dataset_id', e.target.value)}
                          >
                            <option value="">Select Dataset</option>
                            {getFilteredDatasetsForTask(evaluation.task_id).map((dataset: Dataset) => (
                              <option key={dataset.id} value={dataset.id}>
                                {dataset.name}
                              </option>
                            ))}
                          </select>
                        </td>
                        <td className="py-2 px-2">
                          <Input
                            type="text"
                            className="w-full text-sm"
                            placeholder="Model name"
                            value={evaluation.model_name}
                            onChange={(e) => handleUpdateEvaluationField(index, 'model_name', e.target.value)}
                          />
                        </td>
                        <td className="py-2 px-2">
                          {selectedDatasetSupportsHarness(evaluation.task_id, evaluation.dataset_id) ? (
                            <Input
                              type="text"
                              className="w-full text-sm"
                              placeholder="Claude Code, Terminus, ..."
                              value={evaluation.harness}
                              onChange={(e) => handleUpdateEvaluationField(index, 'harness', e.target.value)}
                            />
                          ) : (
                            <span className="text-xs text-muted-foreground">
                              Not supported
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-2">
                          <Input
                            type="text"
                            className="w-full text-sm"
                            placeholder="AP, mAP, etc."
                            value={evaluation.metric_name}
                            onChange={(e) => handleUpdateEvaluationField(index, 'metric_name', e.target.value)}
                          />
                        </td>
                        <td className="py-2 px-2">
                          <Input
                            type="text"
                            className="w-full text-sm"
                            placeholder="44.9"
                            value={evaluation.metric_value}
                            onChange={(e) => handleUpdateEvaluationField(index, 'metric_value', e.target.value)}
                          />
                        </td>
                        <td className="py-2 px-2">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDeleteEvaluation(index)}
                            className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                            title="Delete row"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Database className="w-12 h-12 mx-auto mb-3 opacity-30" />
              <p>No evaluation results yet</p>
              <p className="text-sm mt-2">Click "Add Row" below to add a new evaluation</p>
            </div>
          )}

          <div className="mt-4">
            <Button
              variant="outline"
              size="sm"
              onClick={handleAddEvaluation}
              className="flex items-center space-x-2"
            >
              <Plus className="w-4 h-4" />
              <span>Add Row</span>
            </Button>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            disabled={saveEvaluationsMutation.isPending}
          >
            {saveEvaluationsMutation.isPending ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Saving...
              </>
            ) : (
              <>
                <Check className="w-4 h-4 mr-2" />
                Save Changes
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
