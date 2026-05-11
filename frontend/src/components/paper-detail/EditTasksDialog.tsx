import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Search, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getTasks, updatePaperTasks, type Paper, type Task as APITask } from "@/lib/api";
import { refreshPaperQueries } from "@/lib/queryInvalidation";
import { useToast } from "@/hooks/use-toast";

interface EditTasksDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialTaskIds: number[];
  // Minimal Task objects already attached to the paper. Used to render the
  // currently-selected chips even when they don't match the active search,
  // so the user can always uncheck a tag without first having to find it.
  initialTasks?: Array<Pick<APITask, "id" | "name" | "slug" | "description">>;
  onSuccess?: () => void;
}

const SEARCH_DEBOUNCE_MS = 250;
// `page_size` cap from /api/v1/tasks/ is 100; the server-side q search and
// ordering pick up everything past the alphabetical first page for us.
const SEARCH_PAGE_SIZE = 100;

export function EditTasksDialog({
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialTaskIds,
  initialTasks,
  onSuccess,
}: EditTasksDialogProps) {
  const [selectedTaskIds, setSelectedTaskIds] = useState<number[]>(initialTaskIds);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  // Pool of Task records we have full data for. Seeded with `initialTasks`
  // and grown as search results stream in, so we can always render a chip
  // for any id in `selectedTaskIds`.
  const [knownTasks, setKnownTasks] = useState<Map<number, APITask>>(new Map());
  const queryClient = useQueryClient();
  const { toast } = useToast();
  // Track whether we've already seeded state for the current "open" session.
  // The parent passes `initialTaskIds`/`initialTasks` as freshly-built arrays
  // on every render, so a naive `useEffect` that listed them as deps would
  // re-run on every background refetch and wipe the user's pending selection.
  // We only want to reset state on the false→true transition of `open`.
  const hasSeededRef = useRef(false);

  useEffect(() => {
    if (!open) {
      hasSeededRef.current = false;
      return;
    }
    if (hasSeededRef.current) return;
    hasSeededRef.current = true;
    setSelectedTaskIds(initialTaskIds);
    setSearchQuery("");
    setDebouncedQuery("");
    const seeded = new Map<number, APITask>();
    (initialTasks || []).forEach((t) => {
      const id = parseInt(t.id);
      if (!Number.isNaN(id)) {
        seeded.set(id, t as APITask);
      }
    });
    setKnownTasks(seeded);
  }, [open, initialTaskIds, initialTasks]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedQuery(searchQuery.trim());
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [searchQuery]);

  const { data: searchData, isFetching: searchLoading } = useQuery({
    queryKey: ["tasks-search", debouncedQuery],
    queryFn: () =>
      getTasks({
        page_size: SEARCH_PAGE_SIZE,
        ...(debouncedQuery ? { q: debouncedQuery } : {}),
      }),
    enabled: open,
  });

  useEffect(() => {
    if (!searchData?.results?.length) return;
    setKnownTasks((prev) => {
      const next = new Map(prev);
      searchData.results.forEach((t) => {
        const id = parseInt(t.id);
        if (!Number.isNaN(id)) next.set(id, t);
      });
      return next;
    });
  }, [searchData]);

  const displayedTasks = useMemo(() => {
    const results = searchData?.results || [];
    const seen = new Set<number>();
    const ordered: APITask[] = [];
    // Pin currently-selected tasks at the top so they can always be unchecked.
    selectedTaskIds.forEach((id) => {
      if (seen.has(id)) return;
      const task = knownTasks.get(id);
      if (task) {
        ordered.push(task);
        seen.add(id);
      }
    });
    results.forEach((t) => {
      const id = parseInt(t.id);
      if (Number.isNaN(id) || seen.has(id)) return;
      ordered.push(t);
      seen.add(id);
    });
    return ordered;
  }, [searchData, selectedTaskIds, knownTasks]);

  const updateTasksMutation = useMutation({
    mutationFn: ({ paperId, taskIds }: { paperId: string; taskIds: number[] }) =>
      updatePaperTasks(paperId, taskIds),
    // Apply the new task list to the paper detail cache *before* the network
    // round-trip so the chip the user just unchecked disappears immediately.
    // The dialog also closes here, then the canonical server response
    // reconciles the cache in `onSuccess` (or rolls back on `onError`).
    onMutate: async ({ taskIds }) => {
      const optimisticTasks = taskIds
        .map((id) => knownTasks.get(id))
        .filter((t): t is APITask => Boolean(t))
        .map((t) => ({ id: t.id, name: t.name, slug: t.slug }))
        .sort((a, b) => a.name.localeCompare(b.name));
      const ids = Array.from(
        new Set(
          [paperId, arxivId].filter((v): v is string => Boolean(v)),
        ),
      );

      await Promise.all(
        ids.flatMap((id) => [
          queryClient.cancelQueries({ queryKey: ["paper", id] }),
          queryClient.cancelQueries({ queryKey: ["paper-arxiv", id] }),
        ]),
      );

      const snapshots: Array<{ key: readonly unknown[]; data: Paper | undefined }> = [];
      ids.forEach((id) => {
        (["paper", "paper-arxiv"] as const).forEach((prefix) => {
          const key = [prefix, id] as const;
          const data = queryClient.getQueryData<Paper>(key);
          snapshots.push({ key, data });
          if (data) {
            queryClient.setQueryData<Paper>(key, {
              ...data,
              tasks: optimisticTasks as unknown as Paper["tasks"],
            });
          }
        });
      });

      toast({
        title: "Tasks updated",
        description: `Saved ${taskIds.length} task${
          taskIds.length === 1 ? "" : "s"
        } for this paper.`,
      });
      onSuccess?.();
      onOpenChange(false);

      return { snapshots };
    },
    onSuccess: (updatedPaper) => {
      refreshPaperQueries(queryClient, updatedPaper, [paperId, arxivId]);
    },
    onError: (err: unknown, _vars, context) => {
      context?.snapshots?.forEach(({ key, data }) => {
        queryClient.setQueryData(key as unknown[], data);
      });

      const e = err as { response?: string; message?: string };
      let description = e.message || "Failed to update paper tasks.";
      if (e.response) {
        try {
          const parsed = JSON.parse(e.response);
          if (typeof parsed?.detail === "string") {
            description = parsed.detail;
          } else if (Array.isArray(parsed?.detail) && parsed.detail[0]?.msg) {
            description = parsed.detail[0].msg;
          }
        } catch {
          description = e.response;
        }
      }
      toast({
        title: "Could not save tasks",
        description,
        variant: "destructive",
      });
    },
  });

  const handleSave = () => {
    updateTasksMutation.mutate({ paperId, taskIds: selectedTaskIds });
  };

  const toggleTask = (taskId: number, checked: boolean) => {
    setSelectedTaskIds((prev) => {
      if (checked) {
        return prev.includes(taskId) ? prev : [...prev, taskId];
      }
      return prev.filter((id) => id !== taskId);
    });
  };

  const clearSearch = () => setSearchQuery("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 pr-9"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={clearSearch}
              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-muted-foreground hover:text-foreground"
              aria-label="Clear search"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
        <div className="py-4 overflow-y-auto max-h-[400px]">
          {displayedTasks.length > 0 ? (
            <div className="space-y-2">
              {displayedTasks.map((task) => {
                const taskId = parseInt(task.id);
                const isSelected = selectedTaskIds.includes(taskId);
                return (
                  <div key={task.id} className="flex items-center space-x-2 p-2 hover:bg-muted/50 rounded-md">
                    <Checkbox
                      id={`task-${task.id}`}
                      checked={isSelected}
                      onCheckedChange={(checked) => toggleTask(taskId, checked === true)}
                    />
                    <label
                      htmlFor={`task-${task.id}`}
                      className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer flex-1"
                    >
                      {task.name}
                      {task.description && (
                        <span className="block text-xs text-muted-foreground font-normal mt-1">
                          {task.description.substring(0, 100)}{task.description.length > 100 ? "..." : ""}
                        </span>
                      )}
                    </label>
                  </div>
                );
              })}
            </div>
          ) : searchLoading ? (
            <div className="text-center py-8 text-muted-foreground">
              <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin" />
              <p>Loading tasks...</p>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>
                {debouncedQuery
                  ? `No tasks found matching "${debouncedQuery}"`
                  : "No tasks available"}
              </p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={updateTasksMutation.isPending}>
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
  );
}
