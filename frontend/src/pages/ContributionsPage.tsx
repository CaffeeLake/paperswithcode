import { useInfiniteQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { apiClient } from "@/lib/api";
import { useAuth } from "@/lib/authContext";

const ContributionsPage = () => {
  const { user } = useAuth();
  const query = useInfiniteQuery({
    queryKey: ["contributions", user?.username],
    queryFn: ({ pageParam }) => apiClient.getMyContributions(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: !!user?.can_contribute,
  });
  const events = query.data?.pages.flatMap((page) => page.events) ?? [];

  if (!user?.can_contribute) {
    return (
      <div className="page">
        <h1>Contributions</h1>
        <p>This history is available to project contributors and admins.</p>
      </div>
    );
  }
  return (
    <div className="page max-w-5xl mx-auto px-4 py-8">
      <h1 className="text-3xl font-bold">My contributions</h1>
      <p className="mt-2 text-sm text-muted-foreground">
        Private history for catalog changes made through your contributor account.
      </p>
      {query.isLoading && <p className="mt-8">Loading contributions…</p>}
      {query.error && (
        <p className="mt-8 text-destructive">Could not load contribution history.</p>
      )}
      <div className="mt-6 space-y-3">
        {events.map((event) => (
          <article key={event.id} className="rounded-md border p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <strong>
                {event.operation} {event.entity_type}
              </strong>
              <time className="text-xs text-muted-foreground">
                {new Date(event.created_at).toLocaleString()}
              </time>
            </div>
            <p className="mt-1 font-mono text-xs text-muted-foreground">
              {event.entity_id} · {event.id}
            </p>
            <details className="mt-3 text-xs">
              <summary>Before / after</summary>
              <pre className="mt-2 overflow-auto rounded bg-muted p-3">
                {JSON.stringify(
                  { before: event.before, after: event.after },
                  null,
                  2,
                )}
              </pre>
            </details>
          </article>
        ))}
        {query.data && events.length === 0 && (
          <p className="text-sm text-muted-foreground">No direct edits yet.</p>
        )}
        {query.hasNextPage && (
          <Button
            variant="outline"
            onClick={() => query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
          >
            {query.isFetchingNextPage ? "Loading…" : "Load older contributions"}
          </Button>
        )}
      </div>
    </div>
  );
};

export default ContributionsPage;
