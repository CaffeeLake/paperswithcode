import React, { useEffect, useMemo } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { PaperCard } from "@/components";
import { apiClient } from "@/lib/api";
import { displayTaskName, transformPaperForCard } from "@/lib/transform";
import { useInfiniteOrganizationPapers } from "@/hooks/usePapers";
import { useIntersectionObserver } from "@/hooks/useIntersectionObserver";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import NotFound from "@/pages/NotFound";

type OrderBy = "trending" | "date_published" | "citation_count";
const SORT_OPTIONS: Array<[OrderBy, string]> = [
  ["trending", "trending"],
  ["date_published", "newest"],
  ["citation_count", "most cited"],
];

const parseOrderBy = (value: string | null): OrderBy => {
  if (value === "trending" || value === "date_published" || value === "citation_count") {
    return value;
  }
  return "trending";
};

const OrganizationTaskView: React.FC = () => {
  const { orgSlug, taskSlug } = useParams<{ orgSlug: string; taskSlug: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const orderBy = parseOrderBy(searchParams.get("order_by"));
  const setOrderBy = (next: OrderBy) => {
    const params = new URLSearchParams(searchParams);
    params.set("order_by", next);
    setSearchParams(params);
  };

  const isAllPapers = taskSlug === "all";
  const apiTaskSlug = isAllPapers ? undefined : taskSlug;

  const organizationQ = useQuery({
    queryKey: ["organization", orgSlug],
    queryFn: () => apiClient.getOrganization(orgSlug!),
    enabled: !!orgSlug,
    staleTime: 10 * 60 * 1000,
  });

  const taskQ = useQuery({
    queryKey: ["task", taskSlug],
    queryFn: () => apiClient.getTask(taskSlug!),
    enabled: !!taskSlug && !isAllPapers,
    staleTime: 10 * 60 * 1000,
  });

  const papersQ = useInfiniteOrganizationPapers({
    organizationSlug: orgSlug || "",
    taskSlug: apiTaskSlug,
    page_size: 12,
    order_by: orderBy,
    order_dir: "desc",
    include_resources: true,
    enabled: !!orgSlug,
  });

  const { targetRef: sentinelRef, isIntersecting } = useIntersectionObserver({ rootMargin: "200px" });

  useEffect(() => {
    if (isIntersecting && papersQ.hasNextPage && !papersQ.isFetchingNextPage) {
      papersQ.fetchNextPage();
    }
  }, [isIntersecting, papersQ.hasNextPage, papersQ.isFetchingNextPage]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [orgSlug, taskSlug]);

  const cards = useMemo(() => {
    const pages = papersQ.data?.pages ?? [];
    return pages.flatMap((page) => page.results.map(transformPaperForCard));
  }, [papersQ.data]);

  const taskName = isAllPapers
    ? "All papers"
    : displayTaskName(taskQ.data?.name || taskSlug || "", taskQ.data?.slug || taskSlug);

  const totalCount = papersQ.data?.pages[0]?.count ?? organizationQ.data?.paper_count ?? 0;
  const orgName = organizationQ.data?.name ?? orgSlug;

  if (organizationQ.error || taskQ.error || papersQ.error) {
    if ((organizationQ.error as { status?: number } | null)?.status === 404) {
      return <NotFound />;
    }
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Failed to load organization papers. Please try again.</AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="page">
      <nav className="breadcrumb" aria-label="Breadcrumb">
        <Link to="/">Home</Link>
        <span> / </span>
        <Link to="/organizations">Organizations</Link>
        <span> / </span>
        <Link to={`/${orgSlug}`}>{orgName}</Link>
        <span> / </span>
        <span>{taskName}</span>
      </nav>

      <div style={{ marginTop: 16, marginBottom: 28 }}>
        <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent-text)", letterSpacing: "0.1em", marginBottom: 8 }}>
          {isAllPapers ? "BROWSE PAPERS" : "TASK"}
        </div>
        <h1 className="domain-mega-title">{taskName}</h1>
        {organizationQ.data && (
          <div className="task-quickstats" style={{ marginTop: 12 }}>
            <span>
              <span className="num">{totalCount.toLocaleString()}</span>PAPERS
            </span>
            <span>{organizationQ.data.name}</span>
          </div>
        )}
      </div>

      <div className="task-section-head">
        <div className="task-section-eyebrow">Organization papers · sort below</div>
        <div className="task-section-title">
          Papers <span className="meta">[{totalCount.toLocaleString()}]</span>
        </div>
      </div>

      <div className="sort-bar">
        <div className="sort-options">
          {SORT_OPTIONS.map(([k, l]) => (
            <button
              key={k}
              className={`sort-btn ${orderBy === k ? "active" : ""}`}
              onClick={() => setOrderBy(k)}
            >
              {l}
            </button>
          ))}
        </div>
        <div className="results-count">
          {cards.length} loaded in <span>{taskName}</span>
        </div>
      </div>

      {papersQ.isLoading ? (
        <div className="paper-list">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-40 w-full" />
          ))}
        </div>
      ) : cards.length === 0 ? (
        <div className="no-results">No papers found for this selection.</div>
      ) : (
        <>
          <div className="paper-list">
            {cards.map((p, i) => (
              <PaperCard key={p.id} paper={p} rank={i + 1} />
            ))}
          </div>
          <div ref={sentinelRef} style={{ height: 1 }} />
          {papersQ.isFetchingNextPage && (
            <div style={{ padding: "20px 0", textAlign: "center", color: "var(--ink-faint)" }}>
              Loading more…
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default OrganizationTaskView;
