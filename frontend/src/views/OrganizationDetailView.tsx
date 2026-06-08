import React, { useMemo } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import MarkdownText from "@/components/MarkdownText";
import { apiClient } from "@/lib/api";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { displayTaskName } from "@/lib/transform";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import NotFound from "@/pages/NotFound";

const taskKey = (value?: string) => value?.trim().toLowerCase().replace(/[\s_]+/g, "-") ?? "";

const OrganizationDetailView: React.FC = () => {
  const { orgSlug } = useParams<{ orgSlug: string }>();

  const taxonomyQ = useQuery({
    queryKey: ["organization-areas-with-tasks", orgSlug],
    queryFn: () => apiClient.getOrganizationAreasWithTasks(orgSlug!),
    enabled: !!orgSlug,
    staleTime: 10 * 60 * 1000,
  });

  const visibleAreas = useMemo(() => {
    if (!taxonomyQ.data) return [];

    const AREA_ORDER: Record<string, number> = {
      general: 0,
      vision: 1,
      video: 2,
      language: 3,
      audio: 4,
      other: 5,
    };
    const rank = (name: string) => AREA_ORDER[taskKey(name)] ?? 999;

    return [...taxonomyQ.data.results].sort((a, b) => {
      const ra = rank(a.name);
      const rb = rank(b.name);
      if (ra !== rb) return ra - rb;
      return a.name.localeCompare(b.name);
    });
  }, [taxonomyQ.data]);

  const organization = taxonomyQ.data?.organization;
  const totalPapers = taxonomyQ.data?.total_paper_count ?? 0;
  const totalTasks = visibleAreas.reduce((s, area) => s + area.tasks.length, 0);

  if (taxonomyQ.error) {
    // Unknown top-level slug (e.g. /not-an-org) resolves here via the alias
    // route; fall through to the standard not-found page on a 404.
    if ((taxonomyQ.error as { status?: number }).status === 404) {
      return <NotFound />;
    }
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Failed to load organization. Please try again.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const orgName = organization?.name;

  return (
    <div className="page">
      <div>
        <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--accent-text)", letterSpacing: "0.1em", marginBottom: 8 }}>
          ORGANIZATION
        </div>
        <h1 className="feed-title" style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {organization?.logo_url && (
            <img
              src={organization.logo_url}
              alt=""
              style={{ height: "0.9em", width: "auto", borderRadius: 4, objectFit: "contain" }}
              onError={(e) => {
                e.currentTarget.style.display = "none";
              }}
            />
          )}
          {orgName ?? <Skeleton className="h-10 w-64 inline-block" />}
        </h1>
        <div className="feed-subtitle" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <span>{totalPapers.toLocaleString()} papers</span>
          {organization?.website_url && (
            <a href={organization.website_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent-text)" }}>
              {organization.website_url.replace(/^https?:\/\//, "").replace(/\/$/, "")}
            </a>
          )}
          {organization?.github_url && (
            <a href={organization.github_url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent-text)" }}>
              {organization.github_url.replace(/^https?:\/\//, "").replace(/\/$/, "")}
            </a>
          )}
          {organization?.hf_url && (
            <a
              className="bm-action-btn"
              href={organization.hf_url}
              target="_blank"
              rel="noopener noreferrer"
              style={{ alignSelf: "flex-start", marginTop: 4 }}
            >
              <span aria-hidden="true">🤗</span> View on Hugging Face
            </a>
          )}
        </div>
        {organization?.description && (
          <MarkdownText className="method-description" text={organization.description} />
        )}
      </div>

      {!taxonomyQ.isLoading && totalPapers > 0 && (
        <section style={{ marginTop: 48, marginBottom: 48 }}>
          <div
            style={{
              display: "flex",
              alignItems: "baseline",
              justifyContent: "space-between",
              gap: 24,
              paddingBottom: 12,
              borderBottom: "1px solid var(--hairline-strong)",
            }}
          >
            <div>
              <h2
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 26,
                  fontWeight: 500,
                  letterSpacing: "-0.02em",
                  marginBottom: 4,
                }}
              >
                Browse papers
              </h2>
              <div
                style={{
                  fontFamily: "var(--serif)",
                  fontStyle: "italic",
                  fontSize: 13,
                  color: "var(--ink-soft)",
                }}
              >
                All papers attributed to this organization.
              </div>
            </div>
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11,
                color: "var(--ink-faint)",
                whiteSpace: "nowrap",
              }}
            >
              {totalPapers.toLocaleString()} papers
            </div>
          </div>
          <div className="tag-grid">
            <Link to={`/${orgSlug}/all`} className="tag-cell">
              <div className="name">
                <span className="dot" style={{ background: "var(--accent)" }}></span>
                All papers
              </div>
              <div className="meta">
                <span>{totalPapers.toLocaleString()} papers</span>
              </div>
            </Link>
          </div>
        </section>
      )}

      {taxonomyQ.isLoading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i}>
              <Skeleton className="h-8 w-1/3 mb-4" />
              <div className="tag-grid">
                {Array.from({ length: 6 }).map((__, j) => (
                  <Skeleton key={j} className="h-24" />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        visibleAreas.map((area) => {
          const tasks = area.tasks;
          if (tasks.length === 0) return null;
          const areaPaperCount = tasks.reduce((s, t) => s + (t.paper_count || 0), 0);
          return (
            <section key={area.id} style={{ marginBottom: 48 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  gap: 24,
                  paddingBottom: 12,
                  borderBottom: "1px solid var(--hairline-strong)",
                }}
              >
                <div>
                  <h2
                    style={{
                      fontFamily: "var(--serif)",
                      fontSize: 26,
                      fontWeight: 500,
                      letterSpacing: "-0.02em",
                      marginBottom: 4,
                    }}
                  >
                    {area.name}
                  </h2>
                  {area.description && (
                    <div
                      style={{
                        fontFamily: "var(--serif)",
                        fontStyle: "italic",
                        fontSize: 13,
                        color: "var(--ink-soft)",
                      }}
                    >
                      {area.description}
                    </div>
                  )}
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "var(--ink-faint)",
                    whiteSpace: "nowrap",
                  }}
                >
                  {tasks.length} {tasks.length === 1 ? "task" : "tasks"} · {areaPaperCount.toLocaleString()} papers
                </div>
              </div>
              <div className="tag-grid">
                {tasks.map((t) => {
                  const slug = t.slug || "";
                  const c = chipColors(hueFromSlug(slug));
                  return (
                    <Link
                      key={t.id}
                      to={`/${orgSlug}/${slug}`}
                      className="tag-cell"
                    >
                      <div className="name">
                        <span className="dot" style={{ background: c.dot }}></span>
                        {displayTaskName(t.name, slug)}
                      </div>
                      <div className="meta">
                        <span>{(t.paper_count ?? 0).toLocaleString()} papers</span>
                      </div>
                    </Link>
                  );
                })}
              </div>
            </section>
          );
        })
      )}

      {totalTasks > 0 && (
        <div style={{ fontFamily: "var(--mono)", fontSize: 11, color: "var(--ink-faint)", marginTop: 24 }}>
          {totalTasks} tasks across {visibleAreas.filter((area) => area.tasks.length > 0).length} areas.
        </div>
      )}
    </div>
  );
};

export default OrganizationDetailView;
