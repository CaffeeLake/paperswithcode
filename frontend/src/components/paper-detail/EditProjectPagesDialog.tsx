import { useEffect, useRef, useState } from "react";
import { Loader2, Check, Plus, Trash2, Globe } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updatePaperProjectPages } from "@/lib/api";
import { refreshPaperQueries } from "@/lib/queryInvalidation";

interface ProjectPage {
  url: string;
  is_official: boolean;
}

interface EditProjectPagesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialProjectPages: ProjectPage[];
  onSuccess?: () => void;
}

export function EditProjectPagesDialog({
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialProjectPages,
  onSuccess,
}: EditProjectPagesDialogProps) {
  const [editedProjectPages, setEditedProjectPages] = useState<ProjectPage[]>(initialProjectPages);
  const [newProjectPageUrl, setNewProjectPageUrl] = useState("");
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
    setEditedProjectPages(initialProjectPages);
    setNewProjectPageUrl("");
  }, [open, initialProjectPages]);

  const updateProjectPagesMutation = useMutation({
    mutationFn: ({ paperId, projectPages }: { paperId: string; projectPages: ProjectPage[] }) =>
      updatePaperProjectPages(paperId, projectPages),
    onSuccess: (updatedPaper) => {
      refreshPaperQueries(queryClient, updatedPaper, [paperId, arxivId]);
      onSuccess?.();
      onOpenChange(false);
      setNewProjectPageUrl("");
    },
  });

  const handleAddProjectPage = () => {
    const trimmedUrl = newProjectPageUrl.trim();
    if (!trimmedUrl) return;

    if (editedProjectPages.some(p => p.url === trimmedUrl)) {
      alert("This project page URL is already added");
      return;
    }

    setEditedProjectPages([...editedProjectPages, { url: trimmedUrl, is_official: false }]);
    setNewProjectPageUrl("");
  };

  const handleRemoveProjectPage = (url: string) => {
    setEditedProjectPages(editedProjectPages.filter(p => p.url !== url));
  };

  const handleToggleOfficial = (url: string) => {
    setEditedProjectPages(
      editedProjectPages.map(p =>
        p.url === url ? { ...p, is_official: !p.is_official } : p
      )
    );
  };

  const handleSave = () => {
    updateProjectPagesMutation.mutate({ paperId, projectPages: editedProjectPages });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[600px]">
        <DialogHeader>
          <DialogTitle>Edit Paper Project Pages</DialogTitle>
          <DialogDescription>
            Add or remove project page URLs (e.g. authors' demo or landing pages) associated with this paper. Mark pages as official if they are created by the paper authors.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2">
          <label className="text-sm font-medium">Add Project Page URL</label>
          <div className="flex space-x-2">
            <Input
              type="url"
              placeholder="https://example.com/project"
              value={newProjectPageUrl}
              onChange={(e) => setNewProjectPageUrl(e.target.value)}
              onKeyPress={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddProjectPage();
                }
              }}
              className="flex-1"
            />
            <Button onClick={handleAddProjectPage} size="sm" disabled={!newProjectPageUrl.trim()}>
              <Plus className="w-4 h-4 mr-1" />
              Add
            </Button>
          </div>
        </div>

        <div className="py-4 overflow-y-auto max-h-[350px]">
          {editedProjectPages.length > 0 ? (
            <div className="space-y-2">
              {editedProjectPages.map((page, index) => (
                <div key={index} className="flex items-center space-x-2 p-3 bg-muted/30 rounded-lg hover:bg-muted/50 transition-colors">
                  <Globe className="w-4 h-4 text-muted-foreground flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center space-x-2">
                      <span className="text-sm font-medium text-paper-blue truncate">
                        {page.url}
                      </span>
                      {page.is_official && (
                        <Badge variant="secondary" className="text-xs">Official</Badge>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center space-x-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleToggleOfficial(page.url)}
                      className="h-8 px-2"
                      title={page.is_official ? "Mark as unofficial" : "Mark as official"}
                    >
                      <Check className={`w-4 h-4 ${page.is_official ? 'text-green-600' : 'text-muted-foreground'}`} />
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRemoveProjectPage(page.url)}
                      className="h-8 px-2 text-destructive hover:text-destructive"
                      title="Remove project page"
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Globe className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No project pages added yet</p>
              <p className="text-xs mt-1">Add a project page URL above to get started</p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={updateProjectPagesMutation.isPending}>
            {updateProjectPagesMutation.isPending ? (
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
