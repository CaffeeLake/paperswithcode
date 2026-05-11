import type { QueryClient } from "@tanstack/react-query";

import type { Paper } from "@/lib/api";

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
    queryClient.invalidateQueries({ queryKey: ["paper", id] });
    queryClient.invalidateQueries({ queryKey: ["paper-arxiv", id] });
  });
}
