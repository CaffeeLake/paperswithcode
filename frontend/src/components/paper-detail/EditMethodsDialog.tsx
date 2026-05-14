import { useEffect, useMemo, useRef, useState } from "react";
import { Loader2, Search, Check, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getMethods, updatePaperMethods, type Method as APIMethod } from "@/lib/api";
import { refreshPaperQueries } from "@/lib/queryInvalidation";
import { useToast } from "@/hooks/use-toast";

interface EditMethodsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  arxivId?: string;
  initialMethodIds: number[];
  // Minimal Method objects already attached to the paper, used to render
  // selected chips even when they don't match the active search.
  initialMethods?: Array<Pick<APIMethod, "id" | "name" | "slug" | "full_name" | "description">>;
  onSuccess?: () => void;
}

const SEARCH_DEBOUNCE_MS = 250;
// /api/v1/methods/ caps page_size at 100; the q-search ordering covers the
// long tail (193+ methods) which the previous client-side filter missed.
const SEARCH_PAGE_SIZE = 100;

export function EditMethodsDialog({
  open,
  onOpenChange,
  paperId,
  arxivId,
  initialMethodIds,
  initialMethods,
  onSuccess,
}: EditMethodsDialogProps) {
  const [selectedMethodIds, setSelectedMethodIds] = useState<number[]>(initialMethodIds);
  const [searchQuery, setSearchQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [knownMethods, setKnownMethods] = useState<Map<number, APIMethod>>(new Map());
  const queryClient = useQueryClient();
  const { toast } = useToast();
  // The parent rebuilds `initialMethodIds`/`initialMethods` on every render,
  // so we gate the seeding effect with a ref and only reset on the
  // false→true transition of `open`. Otherwise a background parent re-render
  // would wipe the user's pending selection mid-dialog.
  const hasSeededRef = useRef(false);

  useEffect(() => {
    if (!open) {
      hasSeededRef.current = false;
      return;
    }
    if (hasSeededRef.current) return;
    hasSeededRef.current = true;
    setSelectedMethodIds(initialMethodIds);
    setSearchQuery("");
    setDebouncedQuery("");
    const seeded = new Map<number, APIMethod>();
    (initialMethods || []).forEach((m) => {
      const id = parseInt(m.id);
      if (!Number.isNaN(id)) {
        seeded.set(id, m as APIMethod);
      }
    });
    setKnownMethods(seeded);
  }, [open, initialMethodIds, initialMethods]);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedQuery(searchQuery.trim());
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [searchQuery]);

  const { data: searchData, isFetching: searchLoading } = useQuery({
    queryKey: ["methods-search", debouncedQuery],
    queryFn: () =>
      getMethods({
        page_size: SEARCH_PAGE_SIZE,
        ...(debouncedQuery ? { q: debouncedQuery } : {}),
      }),
    enabled: open,
  });

  useEffect(() => {
    if (!searchData?.results?.length) return;
    setKnownMethods((prev) => {
      const next = new Map(prev);
      searchData.results.forEach((m) => {
        const id = parseInt(m.id);
        if (!Number.isNaN(id)) next.set(id, m);
      });
      return next;
    });
  }, [searchData]);

  const displayedMethods = useMemo(() => {
    const results = searchData?.results || [];
    const seen = new Set<number>();
    const ordered: APIMethod[] = [];
    selectedMethodIds.forEach((id) => {
      if (seen.has(id)) return;
      const method = knownMethods.get(id);
      if (method) {
        ordered.push(method);
        seen.add(id);
      }
    });
    results.forEach((m) => {
      const id = parseInt(m.id);
      if (Number.isNaN(id) || seen.has(id)) return;
      ordered.push(m);
      seen.add(id);
    });
    return ordered;
  }, [searchData, selectedMethodIds, knownMethods]);

  const updateMethodsMutation = useMutation({
    mutationFn: ({ paperId, methodIds }: { paperId: string; methodIds: number[] }) =>
      updatePaperMethods(paperId, methodIds),
    onSuccess: (updatedPaper) => {
      refreshPaperQueries(queryClient, updatedPaper, [paperId, arxivId]);
      toast({
        title: "Methods updated",
        description: `Saved ${selectedMethodIds.length} method${
          selectedMethodIds.length === 1 ? "" : "s"
        } for this paper.`,
      });
      onSuccess?.();
      onOpenChange(false);
    },
    onError: (err: unknown) => {
      const e = err as { response?: string; message?: string };
      let description = e.message || "Failed to update paper methods.";
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
        title: "Could not save methods",
        description,
        variant: "destructive",
      });
    },
  });

  const handleSave = () => {
    updateMethodsMutation.mutate({ paperId, methodIds: selectedMethodIds });
  };

  const toggleMethod = (methodId: number, checked: boolean) => {
    setSelectedMethodIds((prev) => {
      if (checked) {
        return prev.includes(methodId) ? prev : [...prev, methodId];
      }
      return prev.filter((id) => id !== methodId);
    });
  };

  const clearSearch = () => setSearchQuery("");

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
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
          {displayedMethods.length > 0 ? (
            <div className="space-y-2">
              {displayedMethods.map((method) => {
                const methodId = parseInt(method.id);
                const isSelected = selectedMethodIds.includes(methodId);
                return (
                  <div key={method.id} className="flex items-center space-x-2 p-2 hover:bg-muted/50 rounded-md">
                    <Checkbox
                      id={`method-${method.id}`}
                      checked={isSelected}
                      onCheckedChange={(checked) => toggleMethod(methodId, checked === true)}
                      className="!border !border-black data-[state=checked]:!bg-black data-[state=checked]:!text-white"
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
                          {method.description.substring(0, 100)}{method.description.length > 100 ? "..." : ""}
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
              <p>Loading methods...</p>
            </div>
          ) : (
            <div className="text-center py-8 text-muted-foreground">
              <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p>
                {debouncedQuery
                  ? `No methods found matching "${debouncedQuery}"`
                  : "No methods available"}
              </p>
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
