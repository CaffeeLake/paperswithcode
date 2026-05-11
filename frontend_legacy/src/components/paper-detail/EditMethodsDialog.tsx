import { useState } from "react";
import { Loader2, Search, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getMethods, updatePaperMethods, type Method as APIMethod } from "@/lib/api";

interface EditMethodsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialMethodIds: number[];
  onSuccess?: () => void;
}

export function EditMethodsDialog({
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialMethodIds,
  onSuccess,
}: EditMethodsDialogProps) {
  const [selectedMethodIds, setSelectedMethodIds] = useState<number[]>(initialMethodIds);
  const [searchQuery, setSearchQuery] = useState("");
  const queryClient = useQueryClient();

  // Reset state when dialog opens
  const handleOpenChange = (newOpen: boolean) => {
    if (newOpen) {
      setSelectedMethodIds(initialMethodIds);
      setSearchQuery("");
    }
    onOpenChange(newOpen);
  };

  // Fetch all methods
  const { data: allMethodsData } = useQuery({
    queryKey: ['methods'],
    queryFn: () => getMethods({ page_size: 100 }),
    enabled: open,
  });

  // Mutation for updating methods
  const updateMethodsMutation = useMutation({
    mutationFn: ({ paperId, methodIds }: { paperId: string; methodIds: number[] }) =>
      updatePaperMethods(paperId, methodIds),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['paper-arxiv', arxivId] });
      onSuccess?.();
      onOpenChange(false);
    },
  });

  // Filter methods based on search query
  const filteredMethods = allMethodsData?.results?.filter((method: APIMethod) => {
    const searchLower = searchQuery.toLowerCase();
    return (
      method.name.toLowerCase().includes(searchLower) ||
      (method.full_name && method.full_name.toLowerCase().includes(searchLower)) ||
      (method.description && method.description.toLowerCase().includes(searchLower))
    );
  });

  const handleSave = () => {
    updateMethodsMutation.mutate({ paperId, methodIds: selectedMethodIds });
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
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
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
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
              <p>No methods found matching "{searchQuery}"</p>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Loader2 className="w-8 h-8 mx-auto mb-2 animate-spin" />
              <p>Loading methods...</p>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={updateMethodsMutation.isPending}>
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
  );
}
