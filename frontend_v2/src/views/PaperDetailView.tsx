import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { Icon, MethodChip, TagChip } from "@/components";
import LatexTitle, { LatexText } from "@/components/LatexTitle";
import { apiClient, indexPaperFromArxiv } from "@/lib/api";
import type { Paper } from "@/lib/api";
import { summarizeRepos } from "@/lib/transform";
import { usePaperByArxivId } from "@/hooks/usePapers";
import { useEvaluationsByPaper } from "@/hooks/useEvaluations";
import { useHuggingFaceRepos } from "@/hooks/useHuggingFaceRepos";
import { usePaperEditState } from "@/hooks/usePaperEditState";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";

import { EditTasksDialog } from "@/components/paper-detail/EditTasksDialog";
import { EditMethodsDialog } from "@/components/paper-detail/EditMethodsDialog";
import { EditRepositoriesDialog } from "@/components/paper-detail/EditRepositoriesDialog";
import { EditEvaluationsDialog } from "@/components/paper-detail/EditEvaluationsDialog";

const ABSTRACT_PREVIEW_LEN = 360;

function formatLongDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "short", day: "numeric" });
  } catch {
    return "—";
  }
}

function formatStars(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

const PaperDetailView: React.FC = () => {
  const { arxivId } = useParams<{ arxivId: string }>();
  const navigate = useNavigate();
  const { toast } = useToast();

  const { data: paper, isLoading, error, refetch } = usePaperByArxivId(arxivId || "", !!arxivId);
  const { data: hfRepos, isLoading: hfLoading } = useHuggingFaceRepos(paper?.arxiv_id);
  const { data: evaluations, isLoading: evaluationsLoading } = useEvaluationsByPaper(paper?.id, !!paper?.id);

  // Paper version dropdown (PLAN.md §7.5)
  const versionsQ = useQuery({
    queryKey: ["paper-versions", arxivId],
    queryFn: async () => {
      // Strip any vN suffix to get the canonical id.
      const raw = arxivId!.replace(/v\d+$/, "");
      const resp = await fetch(`/api/v1/papers/arxiv/${raw}/versions`);
      if (!resp.ok) return [] as Paper[];
      return (await resp.json()) as Paper[];
    },
    enabled: !!arxivId,
    staleTime: 10 * 60 * 1000,
  });

  // Related papers: same first task slug.
  const relatedQ = useQuery({
    queryKey: ["related-papers", paper?.tasks?.[0]?.id],
    queryFn: () =>
      apiClient.getTaskPapers(paper!.tasks![0]!.id, {
        page: 1,
        page_size: 5,
        order_by: "citation_count",
        order_dir: "desc",
        include_resources: false,
      }),
    enabled: !!paper?.tasks?.[0]?.id,
    staleTime: 10 * 60 * 1000,
    select: (res) => res.results.filter((p) => p.id !== paper?.id).slice(0, 4),
  });

  const [abstractExpanded, setAbstractExpanded] = useState(false);
  const [showAllAuthors, setShowAllAuthors] = useState(false);

  const {
    isEditingTasks,
    setIsEditingTasks,
    isEditingMethods,
    setIsEditingMethods,
    isEditingRepositories,
    setIsEditingRepositories,
    isEditingEvaluations,
    setIsEditingEvaluations,
  } = usePaperEditState();

  // Auto-index if missing.
  const [indexState, setIndexState] = useState<"idle" | "indexing" | "error">("idle");
  const [indexError, setIndexError] = useState<string | null>(null);

  const handleIndex = async () => {
    if (!arxivId) return;
    setIndexState("indexing");
    setIndexError(null);
    try {
      await indexPaperFromArxiv(arxivId);
      toast({ title: "Indexed", description: "Paper added to database." });
      setTimeout(() => refetch(), 1200);
      setIndexState("idle");
    } catch (e) {
      const err = e as { response?: string; message?: string };
      let msg = err.message || "Failed to index paper";
      if (err.response) {
        try {
          msg = JSON.parse(err.response).detail || msg;
        } catch {
          msg = err.response;
        }
      }
      setIndexError(msg);
      setIndexState("error");
    }
  };

  // ── render ───────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div className="page">
        <Skeleton className="h-12 w-3/4 mb-4" />
        <Skeleton className="h-6 w-1/3 mb-8" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (error || !paper) {
    return (
      <div className="page">
        <div className="breadcrumb">
          <Link to="/papers">Papers</Link>
          <span className="sep">/</span>
          <span style={{ color: "var(--ink)" }}>arXiv:{arxivId}</span>
        </div>
        <h1 className="detail-title">Paper not indexed yet</h1>
        <p style={{ fontFamily: "var(--serif)", color: "var(--ink-soft)", marginTop: 16, maxWidth: 640 }}>
          We don't have <span style={{ fontFamily: "var(--mono)" }}>arXiv:{arxivId}</span> in the database.
          You can index it from arXiv right now.
        </p>
        {indexError && (
          <Alert variant="destructive" className="mt-4 max-w-xl">
            <AlertDescription>{indexError}</AlertDescription>
          </Alert>
        )}
        <div className="action-row">
          <button className="action-btn" onClick={handleIndex} disabled={indexState === "indexing"}>
            <Icon name="sparkle" size={12} />
            {indexState === "indexing" ? "Indexing…" : "Index from arXiv"}
          </button>
          <Button variant="outline" onClick={() => navigate("/papers")}>
            Browse Papers
          </Button>
        </div>
      </div>
    );
  }

  const versions = versionsQ.data || [];
  const repoSummary = summarizeRepos(paper.repositories);
  const tldr = (paper as Paper & { tldr?: string }).tldr || null;
  const numPages = (paper as Paper & { num_pages?: number }).num_pages || null;
  const abstract = paper.abstract || "";
  const abstractShort = abstract.length > ABSTRACT_PREVIEW_LEN ? abstract.slice(0, ABSTRACT_PREVIEW_LEN) + "…" : abstract;
  const abstractView = abstractExpanded || abstract.length <= ABSTRACT_PREVIEW_LEN ? abstract : abstractShort;

  const AUTHOR_LIMIT = 12;
  const visibleAuthors =
    showAllAuthors || paper.authors.length <= AUTHOR_LIMIT ? paper.authors : paper.authors.slice(0, AUTHOR_LIMIT);

  return (
    <div className="page">
      <div className="breadcrumb">
        <Link to="/">Trending</Link>
        <span className="sep">/</span>
        <span>arXiv:{paper.arxiv_id}</span>
      </div>

      <div className="detail-grid">
        <div>
          <h1 className="detail-title">
            <LatexTitle title={paper.title} />
          </h1>
          <div className="detail-meta">
            <span>arXiv:{paper.arxiv_id}</span>
            <span>·</span>
            <span>Submitted {formatLongDate(paper.published)}</span>
            {numPages && (
              <>
                <span>·</span>
                <span>{numPages} pages</span>
              </>
            )}
            {paper.citation_count != null && (
              <>
                <span>·</span>
                <span>{paper.citation_count.toLocaleString()} citations</span>
              </>
            )}
            {paper.proceeding && (
              <>
                <span>·</span>
                <span>{paper.proceeding.replace(/\s+\d{1,2}$/, "")}</span>
              </>
            )}
            {versions.length > 1 && (
              <>
                <span>·</span>
                <select
                  className="version-select"
                  value={paper.version}
                  onChange={(e) => {
                    const v = e.target.value;
                    navigate(`/paper/${paper.arxiv_id.replace(/v\d+$/, "")}${v ? `?version=${v}` : ""}`);
                  }}
                >
                  {versions.map((v) => (
                    <option key={v.version} value={v.version}>
                      {v.version} — {formatLongDate(v.published)}
                    </option>
                  ))}
                </select>
              </>
            )}
          </div>
          <div className="detail-authors">
            {visibleAuthors.map((a, i) => (
              <React.Fragment key={i}>
                <a>{a}</a>
                {i < visibleAuthors.length - 1 ? ", " : ""}
              </React.Fragment>
            ))}
            {paper.authors.length > AUTHOR_LIMIT && (
              <button
                className="show-more-authors"
                onClick={() => setShowAllAuthors((v) => !v)}
                style={{
                  marginLeft: 8,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--accent-text)",
                  fontFamily: "var(--mono)",
                  fontSize: 12,
                }}
              >
                {showAllAuthors ? "show fewer" : `+${paper.authors.length - AUTHOR_LIMIT} more`}
              </button>
            )}
          </div>

          <div className="action-row">
            {paper.url_pdf && (
              <a className="action-btn" href={paper.url_pdf} target="_blank" rel="noopener noreferrer">
                <Icon name="pdf" size={12} /> View PDF
              </a>
            )}
            {paper.url_abs && (
              <a className="action-btn" href={paper.url_abs} target="_blank" rel="noopener noreferrer">
                <Icon name="external" size={12} /> arXiv page
              </a>
            )}
            {repoSummary.githubUrl && (
              <a className="action-btn" href={repoSummary.githubUrl} target="_blank" rel="noopener noreferrer">
                <Icon name="github" size={12} /> Code
                {repoSummary.github != null && (
                  <span style={{ opacity: 0.7, marginLeft: 4 }}>· {formatStars(repoSummary.github)} ★</span>
                )}
              </a>
            )}
            {paper.project_pages?.[0]?.url && (
              <a className="action-btn" href={paper.project_pages[0].url} target="_blank" rel="noopener noreferrer">
                <Icon name="globe" size={12} /> Project page
              </a>
            )}
            {paper.conference_url_abs && (
              <a className="action-btn" href={paper.conference_url_abs} target="_blank" rel="noopener noreferrer">
                <Icon name="external" size={12} /> Conference
              </a>
            )}
            <button className="action-btn">
              <Icon name="bookmark" size={12} /> Save
            </button>
          </div>

          {tldr && (
            <>
              <div className="section-rule">
                <span>TL;DR · AI-generated</span>
              </div>
              <div className="tldr-box">{tldr}</div>
            </>
          )}

          <div className="section-rule">
            <span>Abstract</span>
          </div>
          <p className="abstract-text" style={{ marginBottom: 8 }}>
            <LatexText text={abstractView} />
          </p>
          {abstract.length > ABSTRACT_PREVIEW_LEN && (
            <div className="read-full" onClick={() => setAbstractExpanded((v) => !v)}>
              {abstractExpanded ? "− collapse abstract" : "+ read full abstract"}
            </div>
          )}

          <div className="section-rule">
            <span>Tasks</span>
            <span className="accent">
              {paper.tasks?.length || 0} tagged
              <button
                onClick={() => setIsEditingTasks(true)}
                className="edit-link"
                style={{
                  marginLeft: 8,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--accent-text)",
                  textDecoration: "underline",
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                }}
              >
                edit
              </button>
            </span>
          </div>
          <div className="paper-tags" style={{ marginBottom: 8 }}>
            {(paper.tasks || []).map((t) => (
              <TagChip key={t.id} slug={t.slug || ""} label={t.name} />
            ))}
          </div>

          <div className="section-rule">
            <span>Methods</span>
            <span className="accent">
              {paper.methods?.length || 0} used
              <button
                onClick={() => setIsEditingMethods(true)}
                className="edit-link"
                style={{
                  marginLeft: 8,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--accent-text)",
                  textDecoration: "underline",
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                }}
              >
                edit
              </button>
            </span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
            {(paper.methods || []).map((m) => (
              <MethodChip key={m.id} method={{ slug: m.slug, name: m.name }} />
            ))}
          </div>

          <div className="section-rule">
            <span>Results</span>
            <span className="accent">
              {evaluations?.length || 0} benchmarks
              <button
                onClick={() => setIsEditingEvaluations(true)}
                className="edit-link"
                style={{
                  marginLeft: 8,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "var(--accent-text)",
                  textDecoration: "underline",
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                }}
              >
                edit
              </button>
            </span>
          </div>
          {evaluationsLoading ? (
            <Skeleton className="h-32 w-full" />
          ) : evaluations && evaluations.length > 0 ? (
            <table className="results-table">
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Benchmark</th>
                  <th>Metric</th>
                  <th>Value</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {evaluations.map((e) => (
                  <tr key={e.id}>
                    <td>
                      <span className="task-link">{e.task_name || "—"}</span>
                    </td>
                    <td className="benchmark">{e.dataset_name || "—"}</td>
                    <td className="metric">{e.best_metric}</td>
                    <td className="value">{e.metrics?.[e.best_metric || ""] ?? "—"}</td>
                    <td className="compare">
                      {e.dataset_slug && (
                        <Link to={`/benchmark/${e.dataset_slug}`}>Compare →</Link>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--ink-faint)" }}>No benchmark results recorded yet.</p>
          )}

          {(paper.repositories?.length ?? 0) > 0 && (
            <>
              <div className="section-rule">
                <span>Repositories</span>
                <span className="accent">
                  {paper.repositories?.length} repos
                  <button
                    onClick={() => setIsEditingRepositories(true)}
                    className="edit-link"
                    style={{
                      marginLeft: 8,
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      color: "var(--accent-text)",
                      textDecoration: "underline",
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                    }}
                  >
                    edit
                  </button>
                </span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 16 }}>
                {paper.repositories?.map((r) => (
                  <a
                    key={r.id}
                    href={r.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="code-line"
                    style={{ textDecoration: "none" }}
                  >
                    <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <Icon name="github" size={12} />
                      {r.owner}/{r.name}
                      {r.is_official && (
                        <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--accent-text)" }}>· Official</span>
                      )}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>★ {formatStars(r.num_stars)}</span>
                  </a>
                ))}
              </div>
            </>
          )}
        </div>

        <aside className="detail-sidebar">
          {/* Hugging Face block */}
          <div className="sidebar-card">
            <div className="sidebar-card-title">
              <span>🤗 Hugging Face</span>
            </div>
            {hfLoading ? (
              <Skeleton className="h-16 w-full" />
            ) : (
              <>
                <HfRow
                  label="Models"
                  href={`https://huggingface.co/models?other=arxiv:${paper.arxiv_id}`}
                  count={hfRepos?.models}
                  isLimited={hfRepos?.isLimited}
                />
                <HfRow
                  label="Datasets"
                  href={`https://huggingface.co/datasets?other=arxiv:${paper.arxiv_id}`}
                  count={hfRepos?.datasets}
                  isLimited={hfRepos?.isLimited}
                />
                <HfRow
                  label="Spaces"
                  href={`https://huggingface.co/spaces?other=arxiv:${paper.arxiv_id}`}
                  count={hfRepos?.spaces}
                  isLimited={hfRepos?.isLimited}
                />
                <div style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--ink-faint)", marginTop: 12 }}>
                  Cite arxiv.org/abs/{paper.arxiv_id} in a HF README to link it here.
                </div>
              </>
            )}
          </div>

          <div className="sidebar-card">
            <div className="sidebar-card-title">Citation</div>
            <pre
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10.5,
                lineHeight: 1.5,
                color: "var(--ink-soft)",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                margin: 0,
              }}
            >
{`@article{${paper.arxiv_id.replace(".", "")},
  title={{${paper.title.slice(0, 60)}${paper.title.length > 60 ? "…" : ""}}},
  author={{${paper.authors[0] || ""}${paper.authors.length > 1 ? " et al." : ""}}},
  year={{${(paper.published || "").slice(0, 4) || "—"}}},
  eprint={{${paper.arxiv_id}}},
  archivePrefix={{arXiv}}
}`}
            </pre>
          </div>

          {(relatedQ.data?.length ?? 0) > 0 && (
            <div className="sidebar-card">
              <div className="sidebar-card-title">Related papers</div>
              {relatedQ.data!.map((p) => (
                <div
                  key={p.id}
                  className="related-paper"
                  onClick={() => navigate(`/paper/${p.arxiv_id}`)}
                  style={{ cursor: "pointer" }}
                >
                  <div className="related-title">
                    <LatexTitle title={p.title} />
                  </div>
                  <div className="related-meta">
                    <span>arXiv:{p.arxiv_id}</span>
                    {p.citation_count != null && (
                      <span>{p.citation_count.toLocaleString()} cites</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>

      {/* Admin dialogs */}
      <EditTasksDialog
        open={isEditingTasks}
        onOpenChange={setIsEditingTasks}
        paperId={paper.id}
        arxivId={arxivId}
        initialTaskIds={paper.tasks?.map((t) => parseInt(t.id)) || []}
      />
      <EditMethodsDialog
        open={isEditingMethods}
        onOpenChange={setIsEditingMethods}
        paperId={paper.id}
        arxivId={arxivId}
        initialMethodIds={paper.methods?.map((m) => parseInt(m.id)) || []}
      />
      <EditRepositoriesDialog
        open={isEditingRepositories}
        onOpenChange={setIsEditingRepositories}
        paperId={paper.id}
        arxivId={arxivId}
        initialRepositories={
          paper.repositories?.map((r) => ({ url: r.url, is_official: r.is_official || false })) || []
        }
      />
      <EditEvaluationsDialog
        open={isEditingEvaluations}
        onOpenChange={setIsEditingEvaluations}
        paperId={paper.id}
        arxivId={arxivId}
        initialEvaluations={evaluations || []}
      />
    </div>
  );
};

interface HfRowProps {
  label: string;
  href: string;
  count: number | undefined;
  isLimited: boolean | undefined;
}

const HfRow: React.FC<HfRowProps> = ({ label, href, count, isLimited }) => (
  <a
    href={href}
    target="_blank"
    rel="noopener noreferrer"
    style={{
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      padding: "6px 0",
      borderBottom: "1px dashed var(--hairline)",
      fontFamily: "var(--mono)",
      fontSize: 11,
      color: "var(--ink-soft)",
      textDecoration: "none",
    }}
  >
    <span>{label}</span>
    <span style={{ fontWeight: 600, color: count ? "var(--ink)" : "var(--ink-faint)" }}>
      {count != null ? `${count}${isLimited ? "+" : ""}` : "—"}
    </span>
  </a>
);

export default PaperDetailView;
