import { MessageCircle, Calendar, ExternalLink, BookOpen, Database, Zap, Bookmark, Trophy, Edit, Loader2, Globe, X, Check, Search, Plus, Trash2, Github, Quote } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Link, useParams } from "react-router-dom";
import Header from "@/components/Header";
import { usePaperByArxivId } from "@/hooks/usePapers";
import { useHuggingFaceRepos } from "@/hooks/useHuggingFaceRepos";
import { useEvaluationsByPaper } from "@/hooks/useEvaluations";
import PaperResources from "@/components/PaperResources";
import { getTasks, getMethods, getDatasets, updatePaperTasks, updatePaperMethods, updatePaperRepositories, createEvaluation, updateEvaluation, deleteEvaluation, type Task as APITask, type Method as APIMethod, type Dataset, type Evaluation as APIEvaluation } from "@/lib/api";
import { useState, useEffect, useMemo } from "react";
import { useQueryClient, useQuery, useMutation } from "@tanstack/react-query";
import { LatexTitle, LatexText } from "@/components/LatexTitle";

// Type definitions
interface Task {
  id: string;
  name: string;
  slug?: string;
}

interface TaskEvaluationsGroup {
  taskId: string;
  taskName: string;
  evaluations: APIEvaluation[];
  metrics: string[];
  totalMetricsCount: number;
}

const MAX_VISIBLE_METRICS = 6;

const PaperDetail = () => {
  const { arxivId } = useParams<{ arxivId: string }>();
  const { data: paper, isLoading, error } = usePaperByArxivId(arxivId || "", !!arxivId);
  const { data: hfRepos, isLoading: hfLoading } = useHuggingFaceRepos(paper?.arxiv_id);
  const { data: evaluations, isLoading: evaluationsLoading } = useEvaluationsByPaper(paper?.id, !!paper?.id);
  const queryClient = useQueryClient();

  // Fetch tasks and datasets to display names instead of IDs
  const { data: allTasksDataForEvals } = useQuery({
    queryKey: ['tasks-for-evals'],
    queryFn: () => getTasks({ page_size: 100 }),
    enabled: !!evaluations && evaluations.length > 0,
  });

  const { data: allDatasetsData } = useQuery({
    queryKey: ['datasets-for-evals'],
    queryFn: async () => {
      const { getDatasets } = await import('@/lib/api');
      return getDatasets({ page_size: 100 });
    },
    enabled: !!evaluations && evaluations.length > 0,
  });

  // Author display state
  const [showAllAuthors, setShowAllAuthors] = useState(false);
  const AUTHOR_DISPLAY_LIMIT = 30;

  // Admin editing state
  const [isEditingTasks, setIsEditingTasks] = useState(false);
  const [isEditingMethods, setIsEditingMethods] = useState(false);
  const [isEditingRepositories, setIsEditingRepositories] = useState(false);
  const [selectedTaskIds, setSelectedTaskIds] = useState<number[]>([]);
  const [selectedMethodIds, setSelectedMethodIds] = useState<number[]>([]);
  const [taskSearchQuery, setTaskSearchQuery] = useState("");
  const [methodSearchQuery, setMethodSearchQuery] = useState("");

  // Repository editing state (different from tasks/methods - we manage URLs directly)
  const [editedRepositories, setEditedRepositories] = useState<Array<{ url: string; is_official: boolean }>>([]);
  const [newRepositoryUrl, setNewRepositoryUrl] = useState("");

  // Evaluation editing state
  const [isEditingEvaluations, setIsEditingEvaluations] = useState(false);

  // Extended evaluation type to track operation (create/update/delete)
  interface EditableEvaluation {
    id?: string;
    task_id: string;
    dataset_id: string;
    model_name: string;
    metric_name: string;
    metric_value: string;
    best_rank?: string;
    operation?: 'create' | 'update' | 'delete' | 'unchanged';
  }

  const [editedEvaluations, setEditedEvaluations] = useState<EditableEvaluation[]>([]);

  // Fetch all tasks (using max allowed page_size of 100)
  const { data: allTasksData } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => getTasks({ page_size: 100 }),
    enabled: isEditingTasks,
  });

  // Fetch all methods (using max allowed page_size of 100)
  const { data: allMethodsData } = useQuery({
    queryKey: ['methods'],
    queryFn: () => getMethods({ page_size: 100 }),
    enabled: isEditingMethods,
  });

  // Fetch all tasks and datasets for evaluation editing
  const { data: allTasksForEvals } = useQuery({
    queryKey: ['tasks-for-eval-edit'],
    queryFn: () => getTasks({ page_size: 100 }),
    enabled: isEditingEvaluations,
  });

  const { data: allDatasetsForEvals } = useQuery({
    queryKey: ['datasets-for-eval-edit'],
    queryFn: () => getDatasets({ page_size: 100 }),
    enabled: isEditingEvaluations,
  });

  // Mutation for updating tasks
  const updateTasksMutation = useMutation({
    mutationFn: ({ paperId, taskIds }: { paperId: string; taskIds: number[] }) =>
      updatePaperTasks(paperId, taskIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-arxiv', arxivId] });
      setIsEditingTasks(false);
    },
  });

  // Mutation for updating methods
  const updateMethodsMutation = useMutation({
    mutationFn: ({ paperId, methodIds }: { paperId: string; methodIds: number[] }) =>
      updatePaperMethods(paperId, methodIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-arxiv', arxivId] });
      setIsEditingMethods(false);
    },
  });

  // Mutation for updating repositories (now sends URLs instead of IDs)
  const updateRepositoriesMutation = useMutation({
    mutationFn: ({ paperId, repositories }: { paperId: string; repositories: Array<{ url: string; is_official: boolean }> }) =>
      updatePaperRepositories(paperId, repositories),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-arxiv', arxivId] });
      setIsEditingRepositories(false);
      setNewRepositoryUrl("");
    },
  });

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
          await createEvaluation({
            paper_id: parseInt(paperId),
            task_id: parseInt(evalItem.task_id),
            dataset_id: parseInt(evalItem.dataset_id),
            model_name: evalItem.model_name || undefined,
            metrics: { [evalItem.metric_name]: evalItem.metric_value },
            best_metric: evalItem.metric_name,
            best_rank: evalItem.best_rank ? parseInt(evalItem.best_rank) : undefined,
          });
        } else if (evalItem.operation === 'update' && evalItem.id) {
          await updateEvaluation(evalItem.id, {
            task_id: parseInt(evalItem.task_id),
            dataset_id: parseInt(evalItem.dataset_id),
            model_name: evalItem.model_name || undefined,
            metrics: { [evalItem.metric_name]: evalItem.metric_value },
            best_metric: evalItem.metric_name,
            best_rank: evalItem.best_rank ? parseInt(evalItem.best_rank) : undefined,
          });
        }
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-arxiv', arxivId] });
      queryClient.invalidateQueries({ queryKey: ['evaluations', 'paper', paper?.id] });
      setIsEditingEvaluations(false);
    },
  });

  // Generate colors for authors (similar to the original hardcoded approach)
  const getAuthorColor = (index: number) => {
    const colors = ["#3B82F6", "#8B5CF6", "#EF4444", "#10B981", "#F59E0B", "#EC4899", "#06B6D4", "#84CC16", "#F97316"];
    return colors[index % colors.length];
  };

  // Initialize selected items when opening dialog
  const handleEditTasks = () => {
    if (paper?.tasks) {
      setSelectedTaskIds(paper.tasks.map((t: Task) => parseInt(t.id)));
    }
    setTaskSearchQuery("");
    setIsEditingTasks(true);
  };

  const handleEditMethods = () => {
    if (paper?.methods) {
      setSelectedMethodIds(paper.methods.map((m: { id: string }) => parseInt(m.id)));
    }
    setMethodSearchQuery("");
    setIsEditingMethods(true);
  };

  const handleEditRepositories = () => {
    if (paper?.repositories) {
      // Initialize with current repositories
      setEditedRepositories(
        paper.repositories.map((r) => ({
          url: r.url,
          is_official: r.is_official || false,
        }))
      );
    } else {
      setEditedRepositories([]);
    }
    setNewRepositoryUrl("");
    setIsEditingRepositories(true);
  };

  // Save handlers
  const handleSaveTasks = () => {
    if (paper?.id) {
      updateTasksMutation.mutate({ paperId: paper.id, taskIds: selectedTaskIds });
    }
  };

  const handleSaveMethods = () => {
    if (paper?.id) {
      updateMethodsMutation.mutate({ paperId: paper.id, methodIds: selectedMethodIds });
    }
  };

  const handleSaveRepositories = () => {
    if (paper?.id) {
      updateRepositoriesMutation.mutate({ paperId: paper.id, repositories: editedRepositories });
    }
  };

  const handleAddRepository = () => {
    const trimmedUrl = newRepositoryUrl.trim();
    if (!trimmedUrl) return;

    // Check if URL already exists
    if (editedRepositories.some(r => r.url === trimmedUrl)) {
      alert("This repository URL is already added");
      return;
    }

    setEditedRepositories([...editedRepositories, { url: trimmedUrl, is_official: false }]);
    setNewRepositoryUrl("");
  };

  const handleRemoveRepository = (url: string) => {
    setEditedRepositories(editedRepositories.filter(r => r.url !== url));
  };

  const handleToggleOfficial = (url: string) => {
    setEditedRepositories(
      editedRepositories.map(r =>
        r.url === url ? { ...r, is_official: !r.is_official } : r
      )
    );
  };

  // Evaluation editing handlers
  const handleEditEvaluations = () => {
    if (evaluations && evaluations.length > 0) {
      // Convert existing evaluations to editable format
      const editable: EditableEvaluation[] = evaluations.map(e => {
        const metricName = e.best_metric || Object.keys(e.metrics)[0];
        const metricValue = e.metrics[metricName];
        return {
          id: e.id,
          task_id: e.task_id,
          dataset_id: e.dataset_id,
          model_name: e.model_name || '',
          metric_name: metricName || '',
          metric_value: String(metricValue || ''),
          best_rank: e.best_rank ? String(e.best_rank) : '',
          operation: 'unchanged' as const,
        };
      });
      setEditedEvaluations(editable);
    } else {
      setEditedEvaluations([]);
    }
    setIsEditingEvaluations(true);
  };

  const handleAddEvaluation = () => {
    setEditedEvaluations([
      ...editedEvaluations,
      {
        task_id: '',
        dataset_id: '',
        model_name: '',
        metric_name: '',
        metric_value: '',
        best_rank: '',
        operation: 'create',
      },
    ]);
  };

  const handleDeleteEvaluation = (index: number) => {
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
    setEditedEvaluations(
      editedEvaluations.map((e, i) => {
        if (i !== index) return e;
        const updated = { ...e, [field]: value };

        // If task changes, reset the dataset selection
        if (field === 'task_id') {
          updated.dataset_id = '';
        }

        // Mark as updated if it was previously unchanged
        if (e.operation === 'unchanged') {
          updated.operation = 'update';
        }
        return updated;
      })
    );
  };

  const handleSaveEvaluations = () => {
    if (paper?.id) {
      // Filter out evaluations marked for deletion that are shown in UI
      const evaluationsToSave = editedEvaluations.filter(
        e => e.operation !== 'delete' || e.id
      );
      saveEvaluationsMutation.mutate({
        paperId: paper.id,
        evaluations: evaluationsToSave,
      });
    }
  };

  // Filter tasks based on search query
  const filteredTasks = allTasksData?.results?.filter((task: APITask) => {
    const searchLower = taskSearchQuery.toLowerCase();
    return (
      task.name.toLowerCase().includes(searchLower) ||
      (task.description && task.description.toLowerCase().includes(searchLower))
    );
  });

  // Filter methods based on search query
  const filteredMethods = allMethodsData?.results?.filter((method: APIMethod) => {
    const searchLower = methodSearchQuery.toLowerCase();
    return (
      method.name.toLowerCase().includes(searchLower) ||
      (method.full_name && method.full_name.toLowerCase().includes(searchLower)) ||
      (method.description && method.description.toLowerCase().includes(searchLower))
    );
  });

  // Create a map of task_id -> datasets using React Query
  // We'll fetch datasets for each unique task_id in the evaluations
  const uniqueTaskIds = useMemo(() => {
    return Array.from(new Set(editedEvaluations.map(e => e.task_id).filter(id => id && id !== '')));
  }, [editedEvaluations]);

  // Fetch datasets for each unique task
  const taskDatasetsQueries = useQuery({
    queryKey: ['datasets-by-tasks', uniqueTaskIds, isEditingEvaluations],
    queryFn: async () => {
      if (!isEditingEvaluations) return {};

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
    enabled: isEditingEvaluations && uniqueTaskIds.length > 0,
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

  // Determine the maximum number of metric columns across all task groups.
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

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="flex items-center justify-center min-h-[400px]">
            <div className="flex items-center space-x-2">
              <Loader2 className="w-6 h-6 animate-spin" />
              <span>Loading paper...</span>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (error || !paper) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <div className="container mx-auto px-4 py-8">
          <div className="flex items-center justify-center min-h-[400px]">
            <div className="text-center">
              <h2 className="text-2xl font-bold mb-2">Paper Not Found</h2>
              <p className="text-muted-foreground mb-4">
                {error?.message || "The requested paper could not be found."}
              </p>
              <Link to="/papers">
                <Button>Browse Papers</Button>
              </Link>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Format the publication date
  const formatDate = (dateString: string | null) => {
    if (!dateString) return "Unknown";
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  // Format proceeding by removing trailing number (e.g., "ICCV 2023 1" -> "ICCV 2023")
  const formatProceeding = (proceeding: string | null | undefined) => {
    if (!proceeding) return null;
    // Remove trailing space and 1-2 digit number (e.g., " 1", " 11")
    // Only matches 1-2 digits to avoid removing years (4 digits)
    return proceeding.replace(/\s+\d{1,2}$/, '');
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <div className="container mx-auto px-4 py-8">
        {/* Breadcrumb */}
        <div className="flex items-center space-x-2 text-sm text-muted-foreground mb-6">
          <Link to="/papers" className="hover:text-foreground transition-colors">Papers</Link>
          <span>/</span>
          <span className="text-foreground">{paper.arxiv_id || paper.id}</span>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* Main Content */}
          <div className="lg:col-span-3">
            {/* Paper Header */}
            <div className="mb-8">
              <div className="flex items-start justify-between mb-4">
                <h1 className="text-3xl font-bold leading-tight pr-8"><LatexTitle title={paper.title} /></h1>
                <div className="flex items-center space-x-2 px-4 py-2 bg-primary/5 border border-primary/20 rounded-md">
                  <Quote className="w-4 h-4 text-muted-foreground" />
                  <span className="text-sm">Citations:</span>
                  <span className="font-semibold">{paper.citation_count || 0}</span>
                </div>
              </div>

              {/* Metadata */}
              <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground mb-6">
                <div className="flex items-center space-x-1">
                  <span>Published on {formatDate(paper.published?.toString() || null)}</span>
                </div>
                {formatProceeding(paper.proceeding) && (
                  <div className="flex items-center space-x-1">
                    <span>Conference: {formatProceeding(paper.proceeding)}</span>
                  </div>
                )}
              </div>

              {/* Authors */}
              <div className="mb-6">
                <span className="text-sm font-semibold text-foreground">Authors: </span>
                <span className="text-sm">
                  {(showAllAuthors ? paper.authors : paper.authors.slice(0, AUTHOR_DISPLAY_LIMIT)).map((author, index) => (
                    <span key={index}>
                      <button className="text-paper-blue hover:underline font-medium">
                        {author}
                      </button>
                      {index < (showAllAuthors ? paper.authors.length : Math.min(AUTHOR_DISPLAY_LIMIT, paper.authors.length)) - 1 && ", "}
                    </span>
                  ))}
                  {paper.authors.length > AUTHOR_DISPLAY_LIMIT && (
                    <button
                      onClick={() => setShowAllAuthors(!showAllAuthors)}
                      className="ml-2 text-paper-blue hover:underline font-medium text-sm"
                    >
                      {showAllAuthors
                        ? "Show less"
                        : `+${paper.authors.length - AUTHOR_DISPLAY_LIMIT} more authors`
                      }
                    </button>
                  )}
                </span>
              </div>
            </div>

            {/* Abstract */}
            <Card className="mb-8">
              <CardHeader>
                <CardTitle className="flex items-center space-x-2">
                  <BookOpen className="w-5 h-5" />
                  <span>Abstract</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-sm">
                  <p className="leading-relaxed text-justify text-foreground">
                    <LatexText text={paper.abstract} />
                  </p>
                </div>
              </CardContent>
            </Card>

            {/* Actions */}
            <div className="flex items-center space-x-4 mb-12">
              {paper.url_abs && (
                <Button variant="outline" className="flex items-center space-x-2" asChild>
                  <a href={paper.url_abs} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="w-4 h-4" />
                    <span>View on arXiv</span>
                  </a>
                </Button>
              )}
              {paper.url_pdf && (
                <Button variant="outline" className="flex items-center space-x-2" asChild>
                  <a href={paper.url_pdf} target="_blank" rel="noopener noreferrer">
                    <BookOpen className="w-4 h-4" />
                    <span>PDF</span>
                  </a>
                </Button>
              )}
              {paper.conference_url_abs && (
                <Button variant="outline" className="flex items-center space-x-2" asChild>
                  <a href={paper.conference_url_abs} target="_blank" rel="noopener noreferrer">
                    <ExternalLink className="w-4 h-4" />
                    <span>Conference page</span>
                  </a>
                </Button>
              )}
              {/* Project Pages */}
              {paper.project_pages && paper.project_pages.length > 0 && (
                paper.project_pages.map((page, index) => (
                  <Button key={page.id} variant="outline" className="flex items-center space-x-2" asChild>
                    <a href={page.url} target="_blank" rel="noopener noreferrer">
                      <Globe className="w-4 h-4" />
                      <span>Project page{paper.project_pages!.length > 1 ? ` ${index + 1}` : ''}</span>
                    </a>
                  </Button>
                ))
              )}
              <Button variant="outline" className="flex items-center space-x-2">
                <Bookmark className="w-4 h-4" />
                <span>Save</span>
              </Button>
            </div>

            {/* Code, Tasks, and Methods */}
            <PaperResources
              repositories={paper.repositories || []}
              tasks={paper.tasks || []}
              methods={paper.methods || []}
              onEditTasks={handleEditTasks}
              onEditMethods={handleEditMethods}
              onEditRepositories={handleEditRepositories}
            />

            {/* Evaluation Results */}
            <Card className="mb-8">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-xl font-semibold">Results from the paper</CardTitle>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="flex items-center space-x-1 text-muted-foreground"
                    onClick={handleEditEvaluations}
                  >
                    <Edit className="w-4 h-4" />
                    <span>Edit</span>
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {evaluationsLoading ? (
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
          </div>

          {/* Sidebar */}
          <div className="lg:col-span-1">
            <div className="space-y-6">
              {/* Linked Hugging Face models */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center space-x-2">
                    <Zap className="w-4 h-4" />
                    <span>🤗 Models</span>
                    {paper.arxiv_id && (
                      <a
                        href={`https://huggingface.co/models?other=arxiv:${paper.arxiv_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:opacity-80 transition-opacity"
                      >
                        <Badge variant="secondary">
                          {hfLoading ? '...' :
                           (hfRepos?.models !== undefined ?
                            (hfRepos.isLimited ? `${hfRepos.models}+` : hfRepos.models) :
                            0
                           )
                          }
                        </Badge>
                      </a>
                    )}
                    {!paper.arxiv_id && <Badge variant="secondary">0</Badge>}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {hfLoading ? 'Loading...' :
                     (hfRepos?.models ?
                      `${hfRepos.isLimited ? `${hfRepos.models}+` : hfRepos.models} model${hfRepos.models !== 1 ? 's' : ''} linking this paper` :
                      'No model linking this paper'
                     )
                    }
                  </p>
                  {paper.arxiv_id && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Cite arxiv.org/abs/{paper.arxiv_id} in a model README.md to link it to this page.
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Linked Hugging Face datasets */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center space-x-2">
                    <Database className="w-4 h-4" />
                    <span>🤗 Datasets</span>
                    {paper.arxiv_id && (
                      <a
                        href={`https://huggingface.co/datasets?other=arxiv:${paper.arxiv_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:opacity-80 transition-opacity"
                      >
                        <Badge variant="secondary">
                          {hfLoading ? '...' :
                           (hfRepos?.datasets !== undefined ?
                            (hfRepos.isLimited ? `${hfRepos.datasets}+` : hfRepos.datasets) :
                            0
                           )
                          }
                        </Badge>
                      </a>
                    )}
                    {!paper.arxiv_id && <Badge variant="secondary">0</Badge>}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {hfLoading ? 'Loading...' :
                     (hfRepos?.datasets ?
                      `${hfRepos.isLimited ? `${hfRepos.datasets}+` : hfRepos.datasets} dataset${hfRepos.datasets !== 1 ? 's' : ''} linking this paper` :
                      'No dataset linking this paper'
                     )
                    }
                  </p>
                  {paper.arxiv_id && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Cite arxiv.org/abs/{paper.arxiv_id} in a dataset README.md to link it to this page.
                    </p>
                  )}
                </CardContent>
              </Card>

              {/* Linked Hugging Face Spaces */}
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle className="text-base flex items-center space-x-2">
                    <Zap className="w-4 h-4" />
                    <span>🤗 Spaces</span>
                    {paper.arxiv_id && (
                      <a
                        href={`https://huggingface.co/spaces?other=arxiv:${paper.arxiv_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:opacity-80 transition-opacity"
                      >
                        <Badge variant="secondary">
                          {hfLoading ? '...' :
                           (hfRepos?.spaces !== undefined ?
                            (hfRepos.isLimited ? `${hfRepos.spaces}+` : hfRepos.spaces) :
                            0
                           )
                          }
                        </Badge>
                      </a>
                    )}
                    {!paper.arxiv_id && <Badge variant="secondary">0</Badge>}
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {hfLoading ? 'Loading..' :
                     (hfRepos?.spaces ?
                      `${hfRepos.isLimited ? `${hfRepos.spaces}+` : hfRepos.spaces} Space${hfRepos.spaces !== 1 ? 's' : ''} linking this paper` :
                      'No Space linking this paper'
                     )
                    }
                  </p>
                  {paper.arxiv_id && (
                    <p className="text-xs text-muted-foreground mt-2">
                      Cite arxiv.org/abs/{paper.arxiv_id} in a Space README.md to link it to this page.
                    </p>
                  )}
                </CardContent>
              </Card>

            </div>
          </div>
        </div>
      </div>

      {/* Edit Tasks Dialog */}
      <Dialog open={isEditingTasks} onOpenChange={setIsEditingTasks}>
        <DialogContent className="max-w-2xl max-h-[600px]">
          <DialogHeader>
            <DialogTitle>Edit Paper Tasks</DialogTitle>
            <DialogDescription>
              Select the tasks that this paper addresses. You can select multiple tasks.
            </DialogDescription>
          </DialogHeader>
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search tasks..."
              value={taskSearchQuery}
              onChange={(e) => setTaskSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <div className="py-4 overflow-y-auto max-h-[400px]">
            {filteredTasks && filteredTasks.length > 0 ? (
              <div className="space-y-2">
                {filteredTasks.map((task: APITask) => (
                  <div key={task.id} className="flex items-center space-x-2 p-2 hover:bg-muted/50 rounded-md">
                    <Checkbox
                      id={`task-${task.id}`}
                      checked={selectedTaskIds.includes(parseInt(task.id))}
                      onCheckedChange={(checked) => {
                        const taskId = parseInt(task.id);
                        if (checked) {
                          setSelectedTaskIds([...selectedTaskIds, taskId]);
                        } else {
                          setSelectedTaskIds(selectedTaskIds.filter(id => id !== taskId));
                        }
                      }}
                    />
                    <label
                      htmlFor={`task-${task.id}`}
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer flex-1"
                    >
                      {task.name}
                      {task.description && (
                        <span className="block text-xs text-muted-foreground font-normal mt-1">
                          {task.description.substring(0, 100)}{task.description.length > 100 ? '...' : ''}
                        </span>
                      )}
                    </label>
                  </div>
                ))}
              </div>
            ) : allTasksData?.results ? (
              <div className="text-center py-8 text-muted-foreground">
                <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>No tasks found matching "{taskSearchQuery}"</p>
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin" />
                <p>Loading tasks...</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditingTasks(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveTasks} disabled={updateTasksMutation.isPending}>
              {updateTasksMutation.isPending ? (
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

      {/* Edit Methods Dialog */}
      <Dialog open={isEditingMethods} onOpenChange={setIsEditingMethods}>
        <DialogContent className="max-w-2xl max-h-[600px]">
          <DialogHeader>
            <DialogTitle>Edit Paper Methods</DialogTitle>
            <DialogDescription>
              Select the methods and techniques used in this paper. You can select multiple methods.
            </DialogDescription>
          </DialogHeader>
          <div className="relative mb-4">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search methods..."
              value={methodSearchQuery}
              onChange={(e) => setMethodSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <div className="py-4 overflow-y-auto max-h-[400px]">
            {filteredMethods && filteredMethods.length > 0 ? (
              <div className="space-y-2">
                {filteredMethods.map((method: APIMethod) => (
                  <div key={method.id} className="flex items-center space-x-2 p-2 hover:bg-muted/50 rounded-md">
                    <Checkbox
                      id={`method-${method.id}`}
                      checked={selectedMethodIds.includes(parseInt(method.id))}
                      onCheckedChange={(checked) => {
                        const methodId = parseInt(method.id);
                        if (checked) {
                          setSelectedMethodIds([...selectedMethodIds, methodId]);
                        } else {
                          setSelectedMethodIds(selectedMethodIds.filter(id => id !== methodId));
                        }
                      }}
                    />
                    <label
                      htmlFor={`method-${method.id}`}
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer flex-1"
                    >
                      {method.name}
                      {method.full_name && method.full_name !== method.name && (
                        <span className="block text-xs text-muted-foreground font-normal">
                          {method.full_name}
                        </span>
                      )}
                      {method.description && (
                        <span className="block text-xs text-muted-foreground font-normal mt-1">
                          {method.description.substring(0, 100)}{method.description.length > 100 ? '...' : ''}
                        </span>
                      )}
                    </label>
                  </div>
                ))}
              </div>
            ) : allMethodsData?.results ? (
              <div className="text-center py-8 text-muted-foreground">
                <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p>No methods found matching "{methodSearchQuery}"</p>
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin" />
                <p>Loading methods...</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditingMethods(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveMethods} disabled={updateMethodsMutation.isPending}>
              {updateMethodsMutation.isPending ? (
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

      {/* Edit Repositories Dialog */}
      <Dialog open={isEditingRepositories} onOpenChange={setIsEditingRepositories}>
        <DialogContent className="max-w-2xl max-h-[600px]">
          <DialogHeader>
            <DialogTitle>Edit Paper Repositories</DialogTitle>
            <DialogDescription>
              Add or remove GitHub repository URLs associated with this paper. Mark repositories as official if they are created by the paper authors.
            </DialogDescription>
          </DialogHeader>

          {/* Add new repository */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Add Repository URL</label>
            <div className="flex space-x-2">
              <Input
                type="url"
                placeholder="https://github.com/owner/repo"
                value={newRepositoryUrl}
                onChange={(e) => setNewRepositoryUrl(e.target.value)}
                onKeyPress={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleAddRepository();
                  }
                }}
                className="flex-1"
              />
              <Button onClick={handleAddRepository} size="sm" disabled={!newRepositoryUrl.trim()}>
                <Plus className="w-4 h-4 mr-1" />
                Add
              </Button>
            </div>
          </div>

          {/* List of repositories */}
          <div className="py-4 overflow-y-auto max-h-[350px]">
            {editedRepositories.length > 0 ? (
              <div className="space-y-2">
                {editedRepositories.map((repo, index) => (
                  <div key={index} className="flex items-center space-x-2 p-3 bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors">
                    <Github className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center space-x-2">
                        <span className="text-sm font-medium text-paper-blue truncate">
                          {repo.url}
                        </span>
                        {repo.is_official && (
                          <Badge variant="secondary" className="text-xs">Official</Badge>
                        )}
                      </div>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleToggleOfficial(repo.url)}
                        className="h-8 px-2"
                        title={repo.is_official ? "Mark as unofficial" : "Mark as official"}
                      >
                        <Check className={`w-4 h-4 ${repo.is_official ? 'text-green-600' : 'text-muted-foreground'}`} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveRepository(repo.url)}
                        className="h-8 px-2 text-destructive hover:text-destructive"
                        title="Remove repository"
                      >
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                <Github className="w-8 h-8 mx-auto mb-2 opacity-50" />
                <p className="text-sm">No repositories added yet</p>
                <p className="text-xs mt-1">Add a repository URL above to get started</p>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setIsEditingRepositories(false)}>
              Cancel
            </Button>
            <Button onClick={handleSaveRepositories} disabled={updateRepositoriesMutation.isPending}>
              {updateRepositoriesMutation.isPending ? (
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

      {/* Edit Evaluations Dialog */}
      <Dialog open={isEditingEvaluations} onOpenChange={setIsEditingEvaluations}>
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
            <Button variant="outline" onClick={() => setIsEditingEvaluations(false)}>
              Cancel
            </Button>
            <Button
              onClick={handleSaveEvaluations}
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
    </div>
  );
};

export default PaperDetail;
