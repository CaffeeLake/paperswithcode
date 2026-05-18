/**
 * Bookmark hooks for the signed-in HF user.
 *
 * `useBookmarkIds` returns a memoised `Set<number>` of paper IDs the user has
 * bookmarked, gated on a valid auth session. `useToggleBookmark` POSTs/DELETEs
 * `/api/v1/me/bookmarks/{id}` and optimistically updates the IDs cache so the
 * Save button flips state without a round-trip.
 *
 * If the user is not signed in, `toggle()` redirects to the HF OAuth login
 * (same pattern as `HfSignInButton`) so the user lands back on the page they
 * came from.
 */

import React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiClient, type BookmarkIdsResponse } from "@/lib/api";
import { apiUrl, isAuthDisabled } from "@/lib/apiUrl";
import { useAuth } from "@/lib/authContext";

const BOOKMARK_IDS_KEY = ["my-bookmark-ids"] as const;

export function useBookmarkIds() {
  const { user } = useAuth();

  const query = useQuery<BookmarkIdsResponse, Error>({
    queryKey: BOOKMARK_IDS_KEY,
    queryFn: () => apiClient.getMyBookmarkIds(),
    enabled: !!user,
    staleTime: 60 * 1000,
    refetchOnWindowFocus: false,
  });

  const idSet = React.useMemo(
    () => new Set<number>(query.data?.paper_ids ?? []),
    [query.data?.paper_ids],
  );

  return {
    ids: query.data?.paper_ids ?? [],
    idSet,
    isLoading: query.isLoading,
    isError: query.isError,
  };
}

interface ToggleArgs {
  paperId: string | number;
  isBookmarked: boolean;
}

export function useToggleBookmark() {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const mutation = useMutation<void, Error, ToggleArgs, { previous?: BookmarkIdsResponse }>(
    {
      mutationFn: async ({ paperId, isBookmarked }) => {
        if (isBookmarked) {
          await apiClient.removeBookmark(paperId);
        } else {
          await apiClient.addBookmark(paperId);
        }
      },
      onMutate: async ({ paperId, isBookmarked }) => {
        await queryClient.cancelQueries({ queryKey: BOOKMARK_IDS_KEY });
        const previous = queryClient.getQueryData<BookmarkIdsResponse>(BOOKMARK_IDS_KEY);
        const numericId = typeof paperId === "string" ? Number(paperId) : paperId;
        const currentIds = previous?.paper_ids ?? [];
        const nextIds = isBookmarked
          ? currentIds.filter((id) => id !== numericId)
          : [numericId, ...currentIds.filter((id) => id !== numericId)];
        queryClient.setQueryData<BookmarkIdsResponse>(BOOKMARK_IDS_KEY, {
          paper_ids: nextIds,
        });
        return { previous };
      },
      onError: (_err, _vars, context) => {
        if (context?.previous) {
          queryClient.setQueryData(BOOKMARK_IDS_KEY, context.previous);
        }
      },
      onSettled: () => {
        queryClient.invalidateQueries({ queryKey: BOOKMARK_IDS_KEY });
        queryClient.invalidateQueries({ queryKey: ["my-bookmarks"] });
      },
    },
  );

  const toggle = React.useCallback(
    (paperId: string | number, isBookmarked: boolean) => {
      if (!user) {
        if (isAuthDisabled()) return;
        const returnTo =
          typeof window !== "undefined"
            ? window.location.pathname + window.location.search
            : "/";
        window.location.href = apiUrl(
          `/api/v1/auth/hf/login?return_to=${encodeURIComponent(returnTo)}`,
        );
        return;
      }
      mutation.mutate({ paperId, isBookmarked });
    },
    [mutation, user],
  );

  return { toggle, isPending: mutation.isPending };
}
