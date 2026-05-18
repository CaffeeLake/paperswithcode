import { useEffect, useRef, useState } from "react";
import { Loader2, Check, Plus, Trash2, Github } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updatePaperRepositories } from "@/lib/api";
import { refreshPaperQueries } from "@/lib/queryInvalidation";

interface Repository {
  url: string;
  is_official: boolean;
}

interface EditRepositoriesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialRepositories: Repository[];
  onSuccess?: () => void;
}

export function EditRepositoriesDialog({
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialRepositories,
  onSuccess,
}: EditRepositoriesDialogProps) {
  const [editedRepositories, setEditedRepositories] = useState<Repository[]>(initialRepositories);
  const [newRepositoryUrl, setNewRepositoryUrl] = useState("");
  const queryClient = useQueryClient();

  // Only seed local state on the false→true transition of `open` so background
  // refetches of the paper don't wipe pending edits while the dialog is open.
  const hasSeededRef = useRef(false);
  useEffect(() => {
    if (!open) {
      hasSeededRef.current = false;
      return;
    }
    if (hasSeededRef.current) return;
    hasSeededRef.current = true;
    setEditedRepositories(initialRepositories);
    setNewRepositoryUrl("");
  }, [open, initialRepositories]);

  const updateRepositoriesMutation = useMutation({
    mutationFn: ({ paperId, repositories }: { paperId: string; repositories: Repository[] }) =>
      updatePaperRepositories(paperId, repositories),
    onSuccess: (updatedPaper) => {
      refreshPaperQueries(queryClient, updatedPaper, [paperId, arxivId]);
      onSuccess?.();
      onOpenChange(false);
      setNewRepositoryUrl("");
    },
  });

  // Returns the repositories to commit, optionally folding in the typed-but-not-yet-added URL.
  // Returns null when the typed URL is a duplicate so callers can abort.
  const getRepositoriesForSubmission = (): Repository[] | null => {
    const trimmedUrl = newRepositoryUrl.trim();
    if (!trimmedUrl) return editedRepositories;

    if (editedRepositories.some(r => r.url === trimmedUrl)) {
      alert("This repository URL is already added");
      return null;
    }

    return [...editedRepositories, { url: trimmedUrl, is_official: false }];
  };

  const handleAddRepository = () => {
    const next = getRepositoriesForSubmission();
    if (next === null) return;
    if (next.length === editedRepositories.length) return;

    setEditedRepositories(next);
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

  const handleSave = () => {
    const next = getRepositoriesForSubmission();
    if (next === null) return;
    updateRepositoriesMutation.mutate({ paperId, repositories: next });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={updateRepositoriesMutation.isPending}>
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
  );
}
