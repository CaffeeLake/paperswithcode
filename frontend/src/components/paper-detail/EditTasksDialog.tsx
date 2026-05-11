import { useState } from "react";
import { Loader2, Search, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getTasks, updatePaperTasks, type Task as APITask } from "@/lib/api";
import { refreshPaperQueries } from "@/lib/queryInvalidation";

interface EditTasksDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialTaskIds: number[];
  onSuccess?: () => void;
}

export function EditTasksDialog({
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialTaskIds,
  onSuccess,
}: EditTasksDialogProps) {
  const [selectedTaskIds, setSelectedTaskIds] = useState<number[]>(initialTaskIds);
  const [searchQuery, setSearchQuery] = useState("");
  const queryClient = useQueryClient();

  // Reset state when dialog opens
  const handleOpenChange = (newOpen: boolean) => {
    if (newOpen) {
      setSelectedTaskIds(initialTaskIds);
      setSearchQuery("");
    }
    onOpenChange(newOpen);
  };

  // Fetch all tasks
  const { data: allTasksData } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => getTasks({ page_size: 100 }),
    enabled: open,
  });

  // Mutation for updating tasks
  const updateTasksMutation = useMutation({
    mutationFn: ({ paperId, taskIds }: { paperId: string; taskIds: number[] }) =>
      updatePaperTasks(paperId, taskIds),
    onSuccess: (updatedPaper) => {
      refreshPaperQueries(queryClient, updatedPaper, [paperId, arxivId]);
      onSuccess?.();
      onOpenChange(false);
    },
  });

  // Filter tasks based on search query
  const filteredTasks = allTasksData?.results?.filter((task: APITask) => {
    const searchLower = searchQuery.toLowerCase();
    return (
      task.name.toLowerCase().includes(searchLower) ||
      (task.description && task.description.toLowerCase().includes(searchLower))
    );
  });

  const handleSave = () => {
    updateTasksMutation.mutate({ paperId, taskIds: selectedTaskIds });
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
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
              <p>No tasks found matching "{searchQuery}"</p>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin" />
              <p>Loading tasks...</p>
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
