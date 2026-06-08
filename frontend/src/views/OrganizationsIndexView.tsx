import React from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";

const sectionHeaderStyle = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  gap: 24,
  paddingBottom: 12,
  borderBottom: "1px solid var(--hairline-strong)",
} as const;

const OrganizationsIndexView: React.FC = () => {
  const organizationsQ = useQuery({
    queryKey: ["organizations"],
    queryFn: () => apiClient.getOrganizations(),
    staleTime: 10 * 60 * 1000,
  });

  if (organizationsQ.error) {
    return (
      <div className="page">
        <Alert variant="destructive">
          <AlertDescription>Failed to load organizations. Please try again.</AlertDescription>
        </Alert>
      </div>
    );
  }

  const organizations = organizationsQ.data?.results ?? [];
  const totalPapers = organizations.reduce((s, o) => s + (o.paper_count ?? 0), 0);

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            All <em>Organizations</em>
          </h1>
          <div className="feed-subtitle">
            Browse research papers grouped by the labs and companies behind them.
          </div>
        </div>
      </div>

      {organizationsQ.isLoading ? (
        <div className="tag-grid">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : (
        <section style={{ marginBottom: 48 }}>
          <div style={sectionHeaderStyle}>
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
                Organizations
              </h2>
            </div>
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11,
                color: "var(--ink-faint)",
                whiteSpace: "nowrap",
              }}
            >
              {organizations.length} {organizations.length === 1 ? "organization" : "organizations"} ·{" "}
              {totalPapers.toLocaleString()} papers
            </div>
          </div>
          <div className="tag-grid">
            {organizations.map((org) => (
              <Link key={org.id} to={`/${org.slug}`} className="tag-cell">
                <div
                  className="name"
                  style={{ display: "flex", alignItems: "center", gap: 10 }}
                >
                  {org.logo_url && (
                    <img
                      src={org.logo_url}
                      alt=""
                      width={24}
                      height={24}
                      style={{ borderRadius: 4, objectFit: "contain", flexShrink: 0 }}
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                    />
                  )}
                  {org.name}
                </div>
                <div className="meta">
                  <span>{(org.paper_count ?? 0).toLocaleString()} papers</span>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
};

export default OrganizationsIndexView;
