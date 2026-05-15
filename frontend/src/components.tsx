/**
 * Shared visual components for the v2 frontend.
 *
 * The SVG figures and DOM structure are ported verbatim from the original
 * frontend_v2 design prototype (`components.jsx`, ~1190 lines). The data
 * shapes are now backend-typed: `TagChip` takes a slug + label, `PaperCard`
 * takes the `PaperCardProps` shape produced by `lib/transform.ts`, and the
 * `Header` uses react-router `<NavLink>` instead of an App-level state machine.
 */

import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { NavLink, useLocation, useNavigate } from "react-router-dom";

import LatexTitle from "@/components/LatexTitle";
import PaperThumbnail from "@/components/PaperThumbnail";
import HfSignInButton from "@/components/HfSignInButton";
import UserMenu from "@/components/UserMenu";
import { chipColors, hueFromSlug } from "@/lib/colors";
import { apiClient } from "@/lib/api";
import type { Method } from "@/lib/api";
import { useAuth } from "@/lib/authContext";
import type { PaperCardProps } from "@/lib/transform";
import { displayTaskName, humanizeSlug } from "@/lib/transform";

// ============================================================================
// Tag chip — backend slug → deterministic-hue pastel pill
// ============================================================================

interface TagChipProps {
  slug: string;
  label?: string;
  size?: "normal" | "small";
  onClick?: (slug: string) => void;
}

export const TagChip: React.FC<TagChipProps> = ({ slug, label, onClick }) => {
  const navigate = useNavigate();
  const hue = hueFromSlug(slug);
  const c = chipColors(hue);
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onClick) {
      onClick(slug);
      return;
    }
    navigate(`/tasks/${slug}`);
  };
  return (
    <span className="tag-chip" style={{ background: c.bg, color: c.text }} onClick={handleClick}>
      <span className="dot" style={{ background: c.dot }}></span>
      {displayTaskName(label || humanizeSlug(slug), slug)}
    </span>
  );
};

// ============================================================================
// Method chip — link to /methods/:slug
// ============================================================================

interface MethodChipProps {
  method: Pick<Method, "name"> & Partial<Pick<Method, "id" | "slug">>;
  onClick?: (slug: string) => void;
}

export const MethodChip: React.FC<MethodChipProps> = ({ method, onClick }) => {
  const navigate = useNavigate();
  const slug = method.slug || method.id || "";
  if (!slug) return null;
  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onClick) {
      onClick(slug);
      return;
    }
    navigate(`/methods/${slug}`);
  };
  return (
    <span className="method-chip" onClick={handleClick}>
      {method.name}
    </span>
  );
};

// ============================================================================
// Inline icons (size-restricted SVG paths)
// ============================================================================

interface IconProps {
  name:
    | "search"
    | "arrowUp"
    | "arrowLeft"
    | "arrowRight"
    | "external"
    | "github"
    | "citation"
    | "bookmark"
    | "chart"
    | "chat"
    | "pdf"
    | "copy"
    | "sparkle"
    | "user"
    | "globe"
    | "menu"
    | "close";
  size?: number;
}

export const Icon: React.FC<IconProps> = ({ name, size = 14 }) => {
  const paths: Record<IconProps["name"], React.ReactNode> = {
    search: <path d="M11 11l3 3M7 12.5a5.5 5.5 0 110-11 5.5 5.5 0 010 11z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />,
    arrowUp: <path d="M8 3l5 6H3l5-6z" fill="currentColor" />,
    arrowLeft: <path d="M9 3l-4 5 4 5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    arrowRight: <path d="M7 3l4 5-4 5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    external: <path d="M5 3h-2v8h8v-2M9 3h3v3M7 9l5-5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    github: <path d="M8 1a7 7 0 00-2.21 13.64c.35.06.48-.15.48-.34v-1.2c-1.95.42-2.36-.94-2.36-.94-.32-.81-.78-1.03-.78-1.03-.64-.43.05-.43.05-.43.7.05 1.07.72 1.07.72.62 1.07 1.64.76 2.04.58.06-.45.24-.76.44-.94-1.55-.18-3.18-.78-3.18-3.46 0-.76.27-1.39.72-1.88-.07-.18-.31-.89.07-1.86 0 0 .59-.19 1.92.72.56-.15 1.16-.23 1.75-.24.59 0 1.19.08 1.75.24 1.33-.9 1.92-.72 1.92-.72.38.97.14 1.68.07 1.86.45.49.72 1.12.72 1.88 0 2.69-1.64 3.28-3.19 3.45.25.22.48.65.48 1.32v1.95c0 .19.13.41.49.34A7 7 0 008 1z" fill="currentColor" />,
    citation: <path d="M3 4h3v3H3zM4 7v1.5a1.5 1.5 0 01-1.5 1.5M9 4h3v3H9zM10 7v1.5a1.5 1.5 0 01-1.5 1.5" stroke="currentColor" strokeWidth="1.2" fill="none" />,
    bookmark: <path d="M4 2h8v12l-4-3-4 3V2z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />,
    chart: <path d="M2 13h12M3 11l3-4 3 2 4-5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
    chat: <path d="M3 3h10v7H7l-3 3v-3H3V3z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />,
    pdf: <path d="M5 2h5l3 3v9H5V2z" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinejoin="round" />,
    copy: <path d="M5 5h7v8H5V5zM3 3h7v2M3 3v8h2" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinejoin="round" />,
    sparkle: <path d="M8 2l1.2 3.8L13 7l-3.8 1.2L8 12l-1.2-3.8L3 7l3.8-1.2L8 2z" fill="currentColor" />,
    user: <path d="M8 8a3 3 0 100-6 3 3 0 000 6zM2 14c0-3 2.5-5 6-5s6 2 6 5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />,
    globe: <path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM1.5 8h13M8 1.5c1.7 1.9 2.6 4.2 2.6 6.5s-.9 4.6-2.6 6.5M8 1.5C6.3 3.4 5.4 5.7 5.4 8s.9 4.6 2.6 6.5" stroke="currentColor" strokeWidth="1.2" fill="none" strokeLinecap="round" />,
    menu: <path d="M2 4h12M2 8h12M2 12h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />,
    close: <path d="M3 3l10 10M13 3L3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />,
  };
  return (
    <svg className={size === 11 ? "icon-sm" : "icon"} viewBox="0 0 16 16" width={size} height={size}>
      {paths[name]}
    </svg>
  );
};

// ============================================================================
// Header — uses react-router NavLink so the active state mirrors the URL
// ============================================================================

interface HeaderProps {
  onOpenSearch: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onOpenSearch }) => {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const closeMobile = () => setMobileOpen(false);
  const { user, logout } = useAuth();
  const location = useLocation();
  const returnTo = `${location.pathname}${location.search}` || "/";
  return (
    <>
      <header className="app-header">
        <div className="app-header-inner">
          <NavLink to="/" className="brand" onClick={closeMobile}>
            <span className="brand-mark"></span>
            <span className="brand-name">
              Papers <em>With Code</em>
            </span>
          </NavLink>
          <nav className="nav">
            <NavLink to="/" end className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
              Trending
            </NavLink>
            <NavLink to="/tasks" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
              Browse state-of-the-art
            </NavLink>
            <NavLink to="/methods" className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
              Methods
            </NavLink>
          </nav>
          <div className="header-spacer"></div>
          <button className="search-trigger" onClick={onOpenSearch}>
            <Icon name="search" size={13} />
            <span>Search papers, authors, domains…</span>
            <kbd>⌘K</kbd>
          </button>
          <button
            className="icon-btn mobile-search-btn"
            aria-label="Search"
            onClick={onOpenSearch}
          >
            <Icon name="search" size={14} />
          </button>
          <NavLink
            to="/saved"
            className="icon-btn header-bookmark-btn"
            aria-label="Saved papers"
            title="Saved papers"
          >
            <Icon name="bookmark" size={13} />
          </NavLink>
          {user ? (
            <UserMenu user={user} onLogout={logout} />
          ) : (
            <HfSignInButton returnTo={returnTo} />
          )}
          <button
            className="icon-btn mobile-menu-btn"
            aria-label="Open menu"
            onClick={() => setMobileOpen((v) => !v)}
          >
            <Icon name={mobileOpen ? "close" : "menu"} size={14} />
          </button>
        </div>
      </header>
      {mobileOpen && (
        <div className="mobile-nav-drawer" onClick={closeMobile}>
          <div className="mobile-nav-panel" onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className="mobile-nav-link mobile-nav-search"
              onClick={() => {
                closeMobile();
                onOpenSearch();
              }}
            >
              <Icon name="search" size={14} />
              <span>Search papers, authors, domains…</span>
            </button>
            <NavLink to="/" end className="mobile-nav-link" onClick={closeMobile}>
              Trending
            </NavLink>
            <NavLink to="/tasks" className="mobile-nav-link" onClick={closeMobile}>
              Browse state-of-the-art
            </NavLink>
            <NavLink to="/methods" className="mobile-nav-link" onClick={closeMobile}>
              Methods
            </NavLink>
            <NavLink to="/saved" className="mobile-nav-link" onClick={closeMobile}>
              Saved papers
            </NavLink>
            <NavLink to="/cron-dashboard" className="mobile-nav-link" onClick={closeMobile}>
              CRON dashboard
            </NavLink>
          </div>
        </div>
      )}
    </>
  );
};

// ============================================================================
// Domain (task) glyph — abstract line-art icon keyed by slug
// ============================================================================

interface DomainIconProps {
  slug: string;
  size?: number;
}

export const DomainIcon: React.FC<DomainIconProps> = ({ slug, size = 32 }) => {
  const props = {
    stroke: "currentColor",
    strokeWidth: 1.4,
    fill: "none",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };
  const glyphs: Record<string, React.ReactNode> = {
    "language-modeling": (
      <>
        <path d="M5 7c0-1.1.9-2 2-2h18c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H14l-5 4v-4H7c-1.1 0-2-.9-2-2V7z" {...props} />
        <line x1="9" y1="11" x2="23" y2="11" {...props} />
        <line x1="9" y1="15" x2="19" y2="15" {...props} />
      </>
    ),
    "image-classification": (
      <>
        <rect x="5" y="6" width="22" height="16" rx="1.5" {...props} />
        <circle cx="11" cy="12" r="2" {...props} />
        <path d="M5 19l6-5 5 4 5-3 6 4" {...props} />
      </>
    ),
    "object-detection": (
      <>
        <rect x="4" y="5" width="24" height="22" rx="0.5" strokeDasharray="1.5 1" {...props} />
        <rect x="7" y="9" width="10" height="9" {...props} />
        <rect x="18" y="14" width="9" height="10" {...props} />
      </>
    ),
    robotics: (
      <>
        <rect x="4" y="22" width="12" height="4" rx="0.5" {...props} />
        <circle cx="10" cy="22" r="1.5" {...props} />
        <line x1="10" y1="20.5" x2="18" y2="11" {...props} />
        <circle cx="18" cy="11" r="1.5" {...props} />
      </>
    ),
    "speech-recognition": (
      <>
        <line x1="4" y1="16" x2="28" y2="16" {...props} />
        <line x1="7" y1="13" x2="7" y2="19" {...props} />
        <line x1="11" y1="9" x2="11" y2="23" {...props} />
        <line x1="15" y1="11" x2="15" y2="21" {...props} />
        <line x1="19" y1="7" x2="19" y2="25" {...props} />
        <line x1="23" y1="13" x2="23" y2="19" {...props} />
      </>
    ),
    "time-series": (
      <>
        <line x1="5" y1="26" x2="28" y2="26" {...props} />
        <line x1="5" y1="6" x2="5" y2="26" {...props} />
        <path d="M7 22l4-3 3 2 4-7 3 4 4-2 3 1" {...props} />
      </>
    ),
  };
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      {glyphs[slug] || <circle cx="16" cy="16" r="6" {...props} />}
    </svg>
  );
};

// ============================================================================
// Hand-drawn PDF preview (fallback when no real thumbnail exists)
// ============================================================================

const seedRand = (seed: string): (() => number) => {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 16777619);
  }
  return () => {
    h = Math.imul(h ^ (h >>> 15), 2246822507);
    h = Math.imul(h ^ (h >>> 13), 3266489909);
    h ^= h >>> 16;
    return ((h >>> 0) % 10000) / 10000;
  };
};

export const PdfThumbnail: React.FC<{ paperId: string }> = ({ paperId }) => {
  const rand = seedRand(paperId);
  const W = 160;
  const H = 220;
  const titleLines = [0.85 + rand() * 0.1, 0.55 + rand() * 0.25];
  const authorW = 0.45 + rand() * 0.3;
  const colLines: number[] = [];
  const numLines = 9 + Math.floor(rand() * 3);
  for (let i = 0; i < numLines; i++) colLines.push(0.55 + rand() * 0.4);
  const hasFigure = rand() > 0.3;
  const figureType = Math.floor(rand() * 3);
  const rightLines: number[] = [];
  const rightCount = 6 + Math.floor(rand() * 3);
  for (let i = 0; i < rightCount; i++) rightLines.push(0.5 + rand() * 0.45);

  const lineColor = "#9A9588";
  const titleColor = "#3A352D";
  const padding = 5;
  const colWidth = (W - padding * 2 - 2) / 2;
  const colLeft = padding;
  const colRight = padding + colWidth + 2;

  let y = padding + 2;
  const titleY = y;
  y += 4 + 2;
  const authorsY = y + 1;
  y += 5;
  const stampY = y;
  y += 3;
  const bodyTop = y + 1;

  return (
    <div
      style={{
        width: W,
        height: H,
        background: "#FDFCF9",
        border: "1px solid var(--hairline-strong)",
        borderRadius: 2,
        boxShadow: "0 1px 0 rgba(0,0,0,0.04), 0 4px 8px -4px rgba(0,0,0,0.08)",
        flexShrink: 0,
        overflow: "hidden",
        position: "relative",
      }}
    >
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }}>
        {titleLines.map((w, i) => (
          <rect
            key={`t${i}`}
            x={padding + ((W - padding * 2) * (1 - w)) / 2}
            y={titleY + i * 2.4}
            width={(W - padding * 2) * w}
            height={1.4}
            fill={titleColor}
            rx={0.3}
          />
        ))}
        <rect
          x={padding + ((W - padding * 2) * (1 - authorW)) / 2}
          y={authorsY}
          width={(W - padding * 2) * authorW}
          height={0.9}
          fill={lineColor}
          opacity={0.7}
          rx={0.2}
        />
        <rect x={padding} y={stampY} width={6} height={1} fill={titleColor} opacity={0.6} />
        {colLines.map((w, i) => {
          const ly = bodyTop + i * 2.1;
          if (ly > H - padding - 1) return null;
          return (
            <rect
              key={`l${i}`}
              x={colLeft}
              y={ly}
              width={colWidth * w}
              height={0.8}
              fill={lineColor}
              opacity={0.55}
              rx={0.2}
            />
          );
        })}
        {hasFigure && (
          <g>
            <rect
              x={colRight}
              y={bodyTop}
              width={colWidth}
              height={14}
              fill="#F0EBE0"
              stroke={lineColor}
              strokeWidth={0.3}
              opacity={0.9}
            />
            {figureType === 0 && (
              <g stroke={titleColor} strokeWidth={0.4} fill="none" opacity={0.6}>
                <polyline
                  points={`${colRight + 2},${bodyTop + 11} ${colRight + 6},${bodyTop + 8} ${colRight + 10},${bodyTop + 9} ${colRight + 14},${bodyTop + 5} ${colRight + 18},${bodyTop + 6} ${colRight + 22},${bodyTop + 3}`}
                />
              </g>
            )}
            {figureType === 1 && (
              <g opacity={0.55}>
                <circle cx={colRight + colWidth / 2} cy={bodyTop + 7} r={3.5} fill={titleColor} />
                <rect x={colRight + 2} y={bodyTop + 11} width={colWidth - 4} height={1.5} fill={lineColor} />
              </g>
            )}
            {figureType === 2 && (
              <g opacity={0.55}>
                <rect x={colRight + 3} y={bodyTop + 5} width={colWidth - 6} height={1} fill={titleColor} />
                <rect x={colRight + 6} y={bodyTop + 8} width={colWidth - 12} height={0.8} fill={titleColor} />
              </g>
            )}
          </g>
        )}
        {rightLines.map((w, i) => {
          const ly = bodyTop + (hasFigure ? 16 : 0) + i * 2.1;
          if (ly > H - padding - 1) return null;
          return (
            <rect
              key={`r${i}`}
              x={colRight}
              y={ly}
              width={colWidth * w}
              height={0.8}
              fill={lineColor}
              opacity={0.55}
              rx={0.2}
            />
          );
        })}
      </svg>
    </div>
  );
};

/**
 * Real paper thumbnail wrapper. Prefers the backend-supplied thumbnail_url;
 * falls back to PdfThumbnail when no image is available.
 *
 * PLAN.md §9 thumbnail bullet: keep PdfThumbnail as a *fallback*, prefer real
 * thumbnails first.
 */
export const PaperPreview: React.FC<{ paperId: string; title: string; thumbnailUrl: string | null }> = ({
  paperId,
  title,
  thumbnailUrl,
}) => {
  const [errored, setErrored] = React.useState(false);
  if (thumbnailUrl && !errored) {
    return (
      <div
        style={{
          width: 160,
          height: 220,
          background: "#FDFCF9",
          border: "1px solid var(--hairline-strong)",
          borderRadius: 2,
          boxShadow: "0 1px 0 rgba(0,0,0,0.04), 0 4px 8px -4px rgba(0,0,0,0.08)",
          flexShrink: 0,
          overflow: "hidden",
          position: "relative",
        }}
      >
        <img
          src={thumbnailUrl}
          alt={`Thumbnail for ${title}`}
          style={{ width: "100%", height: "100%", objectFit: "contain", display: "block" }}
          onError={() => setErrored(true)}
        />
      </div>
    );
  }
  return <PdfThumbnail paperId={paperId} />;
};

// ============================================================================
// Paper card — list item used by FeedView, TagBrowseView, MethodDetailView
// ============================================================================

interface PaperCardComponentProps {
  paper: PaperCardProps;
  rank?: number | null;
  showInstitution?: boolean;
  onClickTag?: (slug: string) => void;
}

export const PaperCard: React.FC<PaperCardComponentProps> = ({ paper, rank, onClickTag }) => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const handleOpen = () => navigate(`/paper/${paper.id}`);
  const prefetchPaper = React.useCallback(() => {
    queryClient.prefetchQuery({
      queryKey: ["paper-arxiv", paper.id],
      queryFn: () => apiClient.getPaperByArxivId(paper.id, true),
      staleTime: 10 * 60 * 1000,
    });
  }, [paper.id, queryClient]);
  const visibleAuthors = paper.authors.slice(0, 3).join(", ");
  const totalAuthors = paper.authors.length;
  return (
    <article className="paper-card">
      {rank != null && (
        <div
          className="paper-thumb-wrap"
          onClick={handleOpen}
          onFocus={prefetchPaper}
          onMouseEnter={prefetchPaper}
          style={{ cursor: "pointer" }}
        >
          <PaperPreview paperId={paper.id} title={paper.title} thumbnailUrl={paper.thumbnailUrl} />
        </div>
      )}
      <div className="paper-body">
        <div className="paper-body-main">
          <h3 className="paper-title" onClick={handleOpen} onFocus={prefetchPaper} onMouseEnter={prefetchPaper}>
            <LatexTitle title={paper.title} />
          </h3>
          <div className="paper-authors">
            {visibleAuthors}
            {totalAuthors > 3 && (
              <span>
                {", "}+{totalAuthors - 3} authors
              </span>
            )}
            {paper.date && (
              <>
                {" · "}
                <span>{paper.date}</span>
              </>
            )}
            {paper.citations > 0 && (
              <>
                {" · "}
                <span>{paper.citations.toLocaleString()} citations</span>
              </>
            )}
          </div>
          {paper.abstract && <p className="paper-abstract">{paper.abstract}</p>}
          {paper.tags.length > 0 && (
            <div className="paper-tags">
              {paper.tags.map((slug) => (
                <TagChip key={slug} slug={slug} onClick={onClickTag} />
              ))}
            </div>
          )}
        </div>
        {paper.github != null && (() => {
          const statsContent = (
            <>
              <div className="gh-stat-block">
                <div className="gh-value-row">
                  <Icon name="github" size={12} />
                  <span className="gh-stars">{formatStars(paper.github)}</span>
                </div>
                <div className="gh-stars-label">stars</div>
              </div>
              {paper.velocity24h != null && paper.velocity24h > 0 && (
                <div className="gh-stat-block">
                  <div className="gh-value-row">
                    <span className="gh-rate-arrow">↑</span>
                    <span className="gh-rate">{formatStarsPerHour(paper.velocity24h)}</span>
                  </div>
                  <div className="gh-stars-label">stars / hr</div>
                </div>
              )}
            </>
          );
          if (paper.githubUrl) {
            return (
              <a
                className="paper-github-stats is-link"
                href={paper.githubUrl}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`Open GitHub repository (${formatStars(paper.github)} stars)`}
                onClick={(e) => e.stopPropagation()}
              >
                {statsContent}
              </a>
            );
          }
          return <aside className="paper-github-stats">{statsContent}</aside>;
        })()}
      </div>
    </article>
  );
};

function formatStars(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function formatStarsPerHour(n: number): string {
  return n.toFixed(1);
}
