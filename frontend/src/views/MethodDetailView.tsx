import React, { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { keepPreviousData, useInfiniteQuery, useQuery } from "@tanstack/react-query";

import { MethodChip, PaperCard } from "@/components";
import { MethodFigure } from "@/components/MethodFigure";
import MarkdownText from "@/components/MarkdownText";
import { apiClient } from "@/lib/api";
import { transformPaperForCard } from "@/lib/transform";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";

type SortKey = "new" | "cited";
const SORT_OPTIONS: Array<[SortKey, string]> = [
  ["new", "newest"],
  ["cited", "most cited"],
];

const MethodDetailView: React.FC = () => {
  const { methodSlug } = useParams<{ methodSlug: string }>();
  const [sortBy, setSortBy] = useState<SortKey>("new");

  const methodQ = useQuery({
    queryKey: ["method", methodSlug],
    queryFn: () => apiClient.getMethod(methodSlug!),
    enabled: !!methodSlug,
    staleTime: 10 * 60 * 1000,
  });

  const orderBy = sortBy === "cited" ? "citation_count" : "date_published";
  const papersQ = useInfiniteQuery({
    queryKey: ["method-papers-infinite", methodSlug, orderBy],
    queryFn: ({ pageParam = 1 }) =>
      apiClient.getMethodPapers(methodSlug!, {
        page: pageParam as number,
        page_size: 20,
        order_by: orderBy,
        order_dir: "desc",
        include_resources: true,
      }),
    getNextPageParam: (lastPage) => lastPage.next_page,
    initialPageParam: 1,
    enabled: !!methodSlug,
    staleTime: 5 * 60 * 1000,
    placeholderData: keepPreviousData,
  });

  // Related methods: same area_id.
  const relatedQ = useQuery({
    queryKey: ["methods-by-area", methodQ.data?.area_id],
    queryFn: () =>
      apiClient.getMethods({
        // Backend uses ordering on -paper_count to surface popular ones.
        ordering: "-paper_count",
        page_size: 100,
      }),
    enabled: !!methodQ.data?.area_id,
    staleTime: 10 * 60 * 1000,
    select: (res) =>
      res.results
        .filter((m) => m.area_id === methodQ.data?.area_id && m.id !== methodQ.data?.id)
        .slice(0, 8),
  });

  const cards = useMemo(() => {
    const all = papersQ.data?.pages.flatMap((p) => p.results) || [];
    return all.map(transformPaperForCard);
  }, [papersQ.data]);

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "200px" });
  useEffect(() => {
    if (isIntersecting && papersQ.hasNextPage && !papersQ.isFetchingNextPage) {
      papersQ.fetchNextPage();
    }
  }, [isIntersecting, papersQ.hasNextPage, papersQ.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  if (methodQ.isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-1/2 mb-4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (methodQ.error || !methodQ.data) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Method not found.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const m = methodQ.data;

  return (
    <div className="page">
      <div className="breadcrumb">
        <Link to="/methods">Methods</Link>
        <span className="sep">/</span>
        <span style={{ color: "var(--ink)" }}>{m.name}</span>
      </div>

      <div className="tag-hero method-hero-grid">
        <div>
          <div className="tag-hero-eyebrow">METHOD</div>
          <h1 className="tag-hero-title" style={{ fontFamily: "var(--mono)", fontSize: 48, letterSpacing: "-0.01em" }}>
            {m.name}
          </h1>
          {m.full_name && m.full_name !== m.name && (
            <div style={{ fontFamily: "var(--serif)", fontSize: 16, fontStyle: "italic", color: "var(--ink-soft)", marginTop: 8 }}>
              {m.full_name}
            </div>
          )}
          {m.description && (
            <MarkdownText className="method-description" text={m.description} />
          )}
          {m.source_url && m.source_title && (
            <div className="method-source">
              <span className="method-source-label">Source</span>
              <a className="method-source-link" href={m.source_url} target="_blank" rel="noopener noreferrer">
                <span className="method-source-title">{m.source_title}</span>
                {m.introduced_year && <span className="method-source-meta">{m.introduced_year}</span>}
              </a>
            </div>
          )}
          <div className="tag-hero-meta">
            <div className="stat">
              <span className="label">Papers using</span>
              <span className="value">{(m.paper_count ?? 0).toLocaleString()}</span>
            </div>
            {m.introduced_year != null && (
              <div className="stat">
                <span className="label">Introduced</span>
                <span className="value">{m.introduced_year}</span>
              </div>
            )}
          </div>
        </div>
        <figure className="method-figure-card">
          <div className="method-figure-svg">
            <MethodFigure method={m} />
          </div>
          <figcaption>
            Figure · schematic of {m.name}
            {m.image_credit && (
              <>
                <br />
                <span style={{ fontSize: 10, fontFamily: "var(--mono)", color: "var(--ink-faint)" }}>{m.image_credit}</span>
              </>
            )}
          </figcaption>
        </figure>
      </div>

      {(relatedQ.data?.length ?? 0) > 0 && (
        <div className="filter-row">
          <span className="label">Related methods</span>
          {relatedQ.data!.map((rm) => (
            <MethodChip key={rm.id} method={{ slug: rm.slug, name: rm.name }} />
          ))}
        </div>
      )}

      <div className="sort-bar">
        <div className="sort-options">
          {SORT_OPTIONS.map(([k, l]) => (
            <button
              key={k}
              className={`sort-btn ${sortBy === k ? "active" : ""}`}
              onClick={() => setSortBy(k)}
            >
              {l}
            </button>
          ))}
        </div>
        <div className="results-count">{cards.length} papers using {m.name}</div>
      </div>

      {papersQ.isLoading ? (
        <div className="paper-list">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : cards.length === 0 ? (
        <div className="no-results">No papers tagged with this method yet.</div>
      ) : (
        <>
          <div className="paper-list">
            {cards.map((p, i) => (
              <PaperCard key={p.id} paper={p} rank={i + 1} />
            ))}
          </div>
          <div ref={sentinelRef} style={{ height: 1 }} />
          {papersQ.isFetchingNextPage && (
            <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>Loading more…</div>
          )}
        </>
      )}
    </div>
  );
};

export default MethodDetailView;
