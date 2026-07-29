import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  getOrganizations,
  submitPendingPaperEdit,
  updatePaperOrganizations,
} from "@/lib/api";
import { PendingEditNotice } from "./PendingEditNotice";
import { CurationDiff } from "./CurationDiff";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  paperId: string;
  initialOrganizationIds: number[];
  submitMode: "direct" | "pending";
  isAuthor?: boolean;
}

export const EditOrganizationsDialog = ({
  open,
  onOpenChange,
  paperId,
  initialOrganizationIds,
  submitMode,
  isAuthor,
}: Props) => {
  const [selected, setSelected] = useState<number[]>(initialOrganizationIds);
  const queryClient = useQueryClient();
  useEffect(() => {
    if (open) setSelected(initialOrganizationIds);
  }, [initialOrganizationIds, open]);
  const organizations = useQuery({
    queryKey: ["organizations", "curation"],
    queryFn: () => getOrganizations(false),
    enabled: open,
  });
  const save = useMutation({
    mutationFn: async () => {
      const removes = initialOrganizationIds.some((id) => !selected.includes(id));
      if (
        removes &&
        !window.confirm(
          "Remove one or more organizations from this paper? Destructive edits may require a fresh sign-in.",
        )
      ) {
        return;
      }
      if (submitMode === "pending") {
        await submitPendingPaperEdit({
          paper_id: Number(paperId),
          edit_type: "organizations",
          proposed_payload: { organization_ids: selected },
        });
      } else {
        await updatePaperOrganizations(paperId, selected);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["paper-arxiv"] });
      onOpenChange(false);
    },
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit organizations</DialogTitle>
          <DialogDescription>
            Associate existing organizations with this paper. Organization creation remains admin-only.
          </DialogDescription>
        </DialogHeader>
        {submitMode === "pending" && <PendingEditNotice isAuthor={isAuthor} />}
        <div className="max-h-80 space-y-2 overflow-auto">
          {organizations.data?.results.map((organization) => {
            const id = Number(organization.id);
            return (
              <label key={organization.id} className="flex items-center gap-2 rounded border p-2">
                <input
                  type="checkbox"
                  checked={selected.includes(id)}
                  onChange={(event) =>
                    setSelected((current) =>
                      event.target.checked
                        ? [...current, id]
                        : current.filter((value) => value !== id),
                    )
                  }
                />
                {organization.name}
              </label>
            );
          })}
        </div>
        <CurationDiff before={initialOrganizationIds} after={selected} />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => save.mutate()} disabled={save.isPending}>
            {submitMode === "pending" ? "Submit test edit" : "Save changes"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
