import type { QueryClient } from "@tanstack/react-query";

import type { Evaluation, PaginatedResponse, Paper } from "@/lib/api";

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
 *   3. Patch cached evaluation rows that reference this paper so benchmark
 *      leaderboards and the paper's evaluation list show the updated title
 *      (and any other paper-level fields surfaced on `Evaluation`) without
 *      waiting for the 5-minute stale window. The backend resolves
 *      `paper_title` from `papers.title` on every request, so a refetch would
 *      return the fresh value as well, but in-place patching avoids a network
 *      round-trip for already-mounted views.
 */
type EvaluationCacheData =
  | Evaluation[]
  | PaginatedResponse<Evaluation>
  | undefined
  | null;

function patchEvaluationsForPaper(
  oldData: EvaluationCacheData,
  paperId: string,
  newTitle: string,
): EvaluationCacheData {
  if (!oldData) return oldData;

  const replaceTitleIfMatch = (entry: Evaluation): Evaluation => {
    if (entry.paper_id !== paperId) return entry;
    if (entry.paper_title === newTitle) return entry;
    return { ...entry, paper_title: newTitle };
  };

  if (Array.isArray(oldData)) {
    const next = oldData.map(replaceTitleIfMatch);
    const changed = next.some((entry, i) => entry !== oldData[i]);
    return changed ? next : oldData;
  }

  if (Array.isArray(oldData.results)) {
    const nextResults = oldData.results.map(replaceTitleIfMatch);
    const changed = nextResults.some(
      (entry, i) => entry !== oldData.results[i],
    );
    return changed ? { ...oldData, results: nextResults } : oldData;
  }

  return oldData;
}

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

  const paperIdKey = String(updatedPaper.id);
  const patcher = (oldData: unknown) =>
    patchEvaluationsForPaper(
      oldData as EvaluationCacheData,
      paperIdKey,
      updatedPaper.title,
    );

  queryClient.setQueriesData({ queryKey: ["evaluations"] }, patcher);
  queryClient.setQueriesData({ queryKey: ["dataset-evals"] }, patcher);

  queryClient.invalidateQueries({
    queryKey: ["evaluations"],
    refetchType: "none",
  });
  queryClient.invalidateQueries({
    queryKey: ["dataset-evals"],
    refetchType: "none",
  });
}
