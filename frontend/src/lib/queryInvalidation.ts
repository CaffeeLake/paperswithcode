import type { QueryClient } from "@tanstack/react-query";

import type { Paper } from "@/lib/api";

/**
 * Reconcile React Query caches after a paper edit mutation.
 *
 * Callers (e.g. `EditTasksDialog`) typically apply an optimistic update to the
 * paper detail caches in `onMutate`, so the user's change is already visible
 * by the time this runs. Here we only need to:
 *
 *   1. Replace the active `["paper", id]` / `["paper-arxiv", id]` entries with
 *      the canonical server response. We deliberately skip
 *      `invalidateQueries` for those keys: invalidation would trigger a
 *      redundant detail refetch that round-trips to the backend again and
 *      delayed the visible "Tasks updated" change by the duration of that
 *      extra request (the symptom that made tag removal feel like 10s+).
 *   2. Mark paginated paper lists stale without forcing an immediate refetch,
 *      so they pick up the updated tags/methods/repositories the next time
 *      they're mounted (no point refetching long lists while the user is
 *      reading the detail page).
 */
export function refreshPaperQueries(
  queryClient: QueryClient,
  updatedPaper: Paper,
  identifiers: Array<string | undefined>,
) {
  const queryIds = new Set(
    [...identifiers, updatedPaper.id, updatedPaper.arxiv_id].filter(
      (id): id is string => Boolean(id),
    ),
  );

  queryIds.forEach((id) => {
    queryClient.setQueryData(["paper", id], updatedPaper);
    queryClient.setQueryData(["paper-arxiv", id], updatedPaper);
  });

  queryClient.invalidateQueries({ queryKey: ["papers"], refetchType: "none" });
  queryClient.invalidateQueries({
    queryKey: ["papers-infinite"],
    refetchType: "none",
  });
  queryClient.invalidateQueries({
    queryKey: ["task-papers-infinite"],
    refetchType: "none",
  });
}
