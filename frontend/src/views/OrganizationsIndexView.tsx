import React, { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";
import { apiClient, type Organization } from "@/lib/api";
import "./Organizations.css";

type SortMode = "trending" | "papers" | "name";

const parseSort = (value: string | null): SortMode =>
  value === "papers" || value === "name" ? value : "trending";

const Logo: React.FC<{ organization: Organization }> = ({ organization }) => {
  const [failed, setFailed] = useState(false);
  if (!organization.logo_url || failed) {
    return (
      <span className="organization-logo organization-logo--fallback" aria-hidden="true">
        {organization.name.slice(0, 1).toUpperCase()}
      </span>
    );
  }
  return (
    <span className="organization-logo">
      <img
        src={organization.logo_url}
        alt=""
        width={72}
        height={72}
        onError={() => setFailed(true)}
      />
    </span>
  );
};

const OrganizationsIndexView: React.FC = () => {
  const [params, setParams] = useSearchParams();
  const sort = parseSort(params.get("sort"));
  const query = params.get("q") ?? "";
  const organizationsQ = useQuery({
    queryKey: ["organizations", "featured"],
    queryFn: () => apiClient.getOrganizations(true),
    staleTime: 10 * 60 * 1000,
  });

  const setView = (next: { sort?: SortMode; query?: string }) => {
    const updated = new URLSearchParams(params);
    const nextSort = next.sort ?? sort;
    const nextQuery = next.query ?? query;
    if (nextSort === "trending") updated.delete("sort");
    else updated.set("sort", nextSort);
    if (nextQuery.trim()) updated.set("q", nextQuery);
    else updated.delete("q");
    setParams(updated);
  };

  const organizations = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase();
    const filtered = (organizationsQ.data?.results ?? []).filter((organization) =>
      [organization.name, organization.slug, organization.hf_slug ?? ""]
        .join(" ")
        .toLocaleLowerCase()
        .includes(needle),
    );
    if (sort === "papers") {
      return [...filtered].sort(
        (a, b) =>
          (b.paper_count ?? 0) - (a.paper_count ?? 0) ||
          a.name.localeCompare(b.name) ||
          a.slug.localeCompare(b.slug),
      );
    }
    if (sort === "name") {
      return [...filtered].sort(
        (a, b) => a.name.localeCompare(b.name) || a.slug.localeCompare(b.slug),
      );
    }
    return filtered;
  }, [organizationsQ.data, query, sort]);

  return (
    <div className="page organizations-page">
      <header className="organizations-hero">
        <div className="organizations-eyebrow">PAPERS WITH CODE · ORGANIZATIONS</div>
        <h1>
          The labs shaping <em>the field</em>
        </h1>
        <p>
          Explore papers from 21 leading AI organizations, ranked by sustained community
          momentum over the past 30 days.
        </p>
      </header>

      <section aria-labelledby="organizations-heading">
        <div className="organizations-section-heading">
          <h2 id="organizations-heading">
            {organizationsQ.data?.count ?? 21} organizations
          </h2>
          <span>
            {sort === "trending"
              ? "Ranked by 30-day momentum"
              : sort === "papers"
                ? "Sorted by linked papers"
                : "Sorted A–Z"}
          </span>
        </div>
        <div className="organizations-controls">
          <label>
            <span className="sr-only">Search organizations</span>
            <input
              type="search"
              value={query}
              onChange={(event) => setView({ query: event.target.value })}
              placeholder="Search organizations"
            />
          </label>
          <div className="organizations-sort" aria-label="Sort organizations">
            {(
              [
                ["trending", "Trending"],
                ["papers", "Most papers"],
                ["name", "A–Z"],
              ] as const
            ).map(([value, label]) => (
              <button
                type="button"
                key={value}
                className={sort === value ? "active" : ""}
                aria-pressed={sort === value}
                onClick={() => setView({ sort: value })}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {organizationsQ.isLoading ? (
          <div className="organizations-grid" aria-busy="true">
            {Array.from({ length: 6 }).map((_, index) => (
              <Skeleton key={index} className="organization-card-skeleton" />
            ))}
          </div>
        ) : organizationsQ.error ? (
          <Alert variant="destructive">
            <AlertDescription>
              Failed to load organizations.{" "}
              <button type="button" onClick={() => organizationsQ.refetch()}>
                Try again
              </button>
            </AlertDescription>
          </Alert>
        ) : organizations.length === 0 ? (
          <div className="organizations-empty">No organizations match “{query}”.</div>
        ) : (
          <div className="organizations-grid">
            {organizations.map((organization) => {
              const count = organization.paper_count ?? 0;
              const years =
                organization.first_paper_year && organization.latest_paper_year
                  ? organization.first_paper_year === organization.latest_paper_year
                    ? String(organization.first_paper_year)
                    : `${organization.first_paper_year}–${organization.latest_paper_year}`
                  : null;
              return (
                <Link
                  key={organization.id}
                  to={`/orgs/${organization.slug}`}
                  className="organization-card"
                  aria-label={
                    count
                      ? `Browse ${count.toLocaleString()} ${organization.name} papers`
                      : `Browse ${organization.name} papers`
                  }
                >
                  <div className="organization-card-header">
                    <Logo organization={organization} />
                    <div>
                      <h3>{organization.name}</h3>
                      <span>@{organization.hf_slug ?? organization.slug}</span>
                    </div>
                  </div>
                  <div className="organization-card-metrics">
                    <strong>{count.toLocaleString()}</strong>
                    <span>{count === 1 ? "paper" : "papers"}</span>
                    {sort === "trending" && organization.trending_rank && (
                      <span className="organization-rank">
                        #{organization.trending_rank}
                      </span>
                    )}
                  </div>
                  <div className="organization-highlight">
                    <span>Trending paper</span>
                    <strong>
                      {organization.top_trending_paper?.title ?? "No papers indexed yet"}
                    </strong>
                  </div>
                  <div className="organization-card-footer">
                    {years ? `Publishing ${years}` : "Research archive ready"}
                    <span aria-hidden="true">↗</span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
};

export default OrganizationsIndexView;
