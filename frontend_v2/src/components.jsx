// Shared UI components
import React from 'react';
import {
  DOMAINS,
  METHODS,
  METHOD_CATEGORIES,
  getDomain,
  getMethod,
  getMethodCategory,
} from './data.js';

const TagChip = ({ tagId, size = 'normal', onClick }) => {
  const domain = getDomain(tagId);
  if (!domain) return null;
  const bg = `oklch(0.94 0.04 ${domain.hue})`;
  const text = `oklch(0.35 0.10 ${domain.hue})`;
  const dot = `oklch(0.55 0.12 ${domain.hue})`;
  return (
    <span
      className="tag-chip"
      style={{ background: bg, color: text }}
      onClick={(e) => { e.stopPropagation(); onClick && onClick(tagId); }}
    >
      <span className="dot" style={{ background: dot }}></span>
      {domain.label}
    </span>
  );
};

const Icon = ({ name, size = 14 }) => {
  const paths = {
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
  };
  return (
    <svg className={size === 11 ? 'icon-sm' : 'icon'} viewBox="0 0 16 16" width={size} height={size}>
      {paths[name]}
    </svg>
  );
};

// Domain glyphs — abstract, line-style icons for each task/domain. 32×32 viewBox.
// Stroke: currentColor; fill: none. Designed to read at ~28-36px.
const DomainIcon = ({ id, size = 32 }) => {
  const props = { stroke: 'currentColor', strokeWidth: 1.4, fill: 'none', strokeLinecap: 'round', strokeLinejoin: 'round' };
  const glyphs = {
    // Speech bubble with text-baseline strokes
    'language-modeling': (
      <>
        <path d="M5 7c0-1.1.9-2 2-2h18c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H14l-5 4v-4H7c-1.1 0-2-.9-2-2V7z" {...props} />
        <line x1="9" y1="11" x2="23" y2="11" {...props} />
        <line x1="9" y1="15" x2="19" y2="15" {...props} />
      </>
    ),
    // Reward signal: agent dot + curved arrow back to environment box
    'reinforcement-learning': (
      <>
        <rect x="4" y="13" width="10" height="10" rx="1" {...props} />
        <circle cx="22" cy="10" r="3" {...props} />
        <path d="M14 16c4-3 6-3 8-3" {...props} />
        <path d="M22 18c-3 2-5 4-8 4" {...props} />
        <path d="M12 22l2 0M14 22l-1.5 1.5M14 22l-1.5-1.5" {...props} />
      </>
    ),
    // Image with content + small label tag
    'image-classification': (
      <>
        <rect x="5" y="6" width="22" height="16" rx="1.5" {...props} />
        <circle cx="11" cy="12" r="2" {...props} />
        <path d="M5 19l6-5 5 4 5-3 6 4" {...props} />
        <path d="M20 24l4 0 2 2" {...props} />
        <circle cx="22" cy="24" r="0.6" fill="currentColor" />
      </>
    ),
    // Robot arm with end-effector
    'robotics': (
      <>
        <rect x="4" y="22" width="12" height="4" rx="0.5" {...props} />
        <circle cx="10" cy="22" r="1.5" {...props} />
        <line x1="10" y1="20.5" x2="18" y2="11" {...props} />
        <circle cx="18" cy="11" r="1.5" {...props} />
        <line x1="18" y1="9.5" x2="24" y2="6" {...props} />
        <path d="M24 6l1.5-2M24 6l-2-1.5M24 6l3 1" {...props} />
      </>
    ),
    // Diffusion: noise grid → clean
    'diffusion-models': (
      <>
        <rect x="4" y="9" width="10" height="14" rx="1" {...props} />
        <rect x="18" y="9" width="10" height="14" rx="1" {...props} />
        {[6, 8.5, 11].flatMap((y, yi) =>
          [6, 8, 10, 12].map((x, xi) => (
            <circle key={`n-${yi}-${xi}`} cx={x} cy={y + 4} r="0.6" fill="currentColor" />
          ))
        )}
        <path d="M14.5 16h3" {...props} />
        <path d="M17.5 16l-1-0.8M17.5 16l-1 0.8" {...props} />
        <circle cx="23" cy="16" r="3" {...props} />
      </>
    ),
    // Multimodal: text + image + audio overlapping
    'multimodal': (
      <>
        <circle cx="11" cy="12" r="6" {...props} />
        <circle cx="20" cy="14" r="6" {...props} />
        <circle cx="15" cy="20" r="6" {...props} />
      </>
    ),
    // Agent: figure with thought-arrow loop
    'agents': (
      <>
        <circle cx="16" cy="11" r="3" {...props} />
        <path d="M9 25c0-4 3-7 7-7s7 3 7 7" {...props} />
        <path d="M5 6 a8 8 0 0 1 8-3" {...props} />
        <path d="M5 6l-1-2M5 6l2.5-0.5" {...props} />
      </>
    ),
    // Speech: waveform peaks
    'speech-recognition': (
      <>
        <line x1="4" y1="16" x2="28" y2="16" {...props} />
        <line x1="7" y1="13" x2="7" y2="19" {...props} />
        <line x1="11" y1="9" x2="11" y2="23" {...props} />
        <line x1="15" y1="11" x2="15" y2="21" {...props} />
        <line x1="19" y1="7" x2="19" y2="25" {...props} />
        <line x1="23" y1="13" x2="23" y2="19" {...props} />
        <line x1="26" y1="14.5" x2="26" y2="17.5" {...props} />
      </>
    ),
    // Graph: nodes + edges
    'graph-neural-networks': (
      <>
        <circle cx="8" cy="8" r="2.5" {...props} />
        <circle cx="24" cy="9" r="2.5" {...props} />
        <circle cx="16" cy="16" r="2.5" {...props} />
        <circle cx="7" cy="22" r="2.5" {...props} />
        <circle cx="24" cy="23" r="2.5" {...props} />
        <line x1="10" y1="9" x2="14" y2="14.5" {...props} />
        <line x1="22" y1="10.5" x2="18" y2="14.5" {...props} />
        <line x1="14" y1="18" x2="9" y2="20" {...props} />
        <line x1="18" y1="18" x2="22" y2="21" {...props} />
        <line x1="9" y1="22" x2="22" y2="23" {...props} />
      </>
    ),
    // Interpretability: lens over network
    'interpretability': (
      <>
        <circle cx="20" cy="13" r="6" {...props} />
        <line x1="24.5" y1="17.5" x2="28" y2="22" {...props} />
        <circle cx="17" cy="12" r="1" fill="currentColor" />
        <circle cx="22" cy="11" r="1" fill="currentColor" />
        <circle cx="20" cy="15" r="1" fill="currentColor" />
        <line x1="17" y1="12" x2="20" y2="15" {...props} />
        <line x1="22" y1="11" x2="20" y2="15" {...props} />
        <path d="M5 24l4-3 3 2" {...props} />
      </>
    ),
    // Video: filmstrip with play
    'video-generation': (
      <>
        <rect x="4" y="8" width="24" height="16" rx="1" {...props} />
        <line x1="4" y1="12" x2="28" y2="12" {...props} />
        <line x1="4" y1="20" x2="28" y2="20" {...props} />
        {[7, 12, 17, 22].map(x => (
          <React.Fragment key={x}>
            <rect x={x - 0.7} y="9.4" width="1.4" height="1.4" {...props} />
            <rect x={x - 0.7} y="20.6" width="1.4" height="1.4" {...props} />
          </React.Fragment>
        ))}
        <path d="M14 14l5 2-5 2z" fill="currentColor" />
      </>
    ),
    // Code: angle brackets + slash
    'code-generation': (
      <>
        <path d="M11 9l-6 7 6 7" {...props} />
        <path d="M21 9l6 7-6 7" {...props} />
        <line x1="18" y1="7" x2="14" y2="25" {...props} />
      </>
    ),
    // Medical: cross + heartbeat
    'medical-imaging': (
      <>
        <circle cx="16" cy="16" r="11" {...props} />
        <line x1="16" y1="10" x2="16" y2="22" {...props} />
        <line x1="10" y1="16" x2="22" y2="16" {...props} />
        <path d="M5 16h3l1.5-3 2 6 1.5-3h2" {...props} />
      </>
    ),
    // 3D reconstruction: wireframe cube
    '3d-reconstruction': (
      <>
        <path d="M16 5l10 5v12l-10 5L6 22V10z" {...props} />
        <path d="M6 10l10 5 10-5" {...props} />
        <line x1="16" y1="15" x2="16" y2="27" {...props} />
        <path d="M11 7.5l10 5M21 7.5l-10 5" strokeDasharray="1.5 1.5" {...props} />
      </>
    ),
    // Alignment: balance scale
    'alignment': (
      <>
        <line x1="16" y1="6" x2="16" y2="24" {...props} />
        <line x1="9" y1="24" x2="23" y2="24" {...props} />
        <line x1="7" y1="10" x2="25" y2="10" {...props} />
        <path d="M7 10l-3 6h6z" {...props} />
        <path d="M25 10l-3 6h6z" {...props} />
        <circle cx="16" cy="6" r="1" fill="currentColor" />
      </>
    ),
    // Object detection: bounding boxes
    'object-detection': (
      <>
        <rect x="4" y="5" width="24" height="22" rx="0.5" strokeDasharray="1.5 1" {...props} />
        <rect x="7" y="9" width="10" height="9" {...props} />
        <rect x="18" y="14" width="9" height="10" {...props} />
        <line x1="7" y1="9" x2="9" y2="7" {...props} />
        <line x1="18" y1="14" x2="20" y2="12" {...props} />
      </>
    ),
    // Time series: line chart with grid
    'time-series': (
      <>
        <line x1="5" y1="26" x2="28" y2="26" {...props} />
        <line x1="5" y1="6" x2="5" y2="26" {...props} />
        <path d="M7 22l4-3 3 2 4-7 3 4 4-2 3 1" {...props} />
        {[10, 15, 20, 25].map(x => <line key={x} x1={x} y1="25" x2={x} y2="27" {...props} />)}
      </>
    ),
    // Evaluation: checklist with checkmark
    'evaluation': (
      <>
        <rect x="6" y="5" width="20" height="22" rx="1" {...props} />
        <rect x="11" y="3" width="10" height="4" rx="0.5" {...props} />
        <path d="M9 13l2 2 4-4" {...props} />
        <path d="M9 20l2 2 4-4" {...props} />
        <line x1="17" y1="14" x2="23" y2="14" {...props} />
        <line x1="17" y1="21" x2="23" y2="21" {...props} />
      </>
    ),
  };
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      {glyphs[id] || <circle cx="16" cy="16" r="6" {...props} />}
    </svg>
  );
};

const Header = ({ currentView, onNavigate, onOpenSearch }) => {
  return (
    <header className="app-header">
      <div className="app-header-inner">
        <div className="brand" onClick={() => onNavigate('feed')}>
          <span className="brand-mark"></span>
          <span className="brand-name">Papers <em>With Code</em></span>
        </div>
        <nav className="nav">
          <a className={`nav-item ${currentView === 'feed' ? 'active' : ''}`} onClick={() => onNavigate('feed')}>Trending</a>
          <a className={`nav-item ${currentView === 'tags' ? 'active' : ''}`} onClick={() => onNavigate('tags')}>Browse state-of-the-art</a>
          <a className={`nav-item ${currentView === 'methods' ? 'active' : ''}`} onClick={() => onNavigate('methods')}>Methods</a>
        </nav>
        <div className="header-spacer"></div>
        <button className="search-trigger" onClick={onOpenSearch}>
          <Icon name="search" size={13} />
          <span>Search papers, authors, domains…</span>
          <kbd>⌘K</kbd>
        </button>
        <button className="icon-btn"><Icon name="bookmark" size={13} /></button>
        <button className="icon-btn"><Icon name="user" size={13} /></button>
      </div>
    </header>
  );
};

const Banner = () => (
  <div className="banner">
    <span className="banner-tag">NEW</span>
    <span>Get a daily digest of trending research in your inbox.</span>
    <a className="banner-link">Subscribe →</a>
  </div>
);

// Deterministic pseudo-random from string seed
const seedRand = (seed) => {
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

const PdfThumbnail = ({ paper }) => {
  const rand = seedRand(paper.id);
  const W = 160, H = 220;
  // Title: 2 lines; vary widths
  const titleLines = [0.85 + rand() * 0.1, 0.55 + rand() * 0.25];
  // Authors line
  const authorW = 0.45 + rand() * 0.3;
  // Abstract: a left column of 8-10 short lines; varies
  const colLines = [];
  const numLines = 9 + Math.floor(rand() * 3);
  for (let i = 0; i < numLines; i++) {
    colLines.push(0.55 + rand() * 0.4);
  }
  // Optional figure box on right column
  const hasFigure = rand() > 0.3;
  const figureType = Math.floor(rand() * 3); // 0: chart, 1: image, 2: equation
  // Right column lines (after figure)
  const rightLines = [];
  const rightCount = 6 + Math.floor(rand() * 3);
  for (let i = 0; i < rightCount; i++) {
    rightLines.push(0.5 + rand() * 0.45);
  }

  const lineColor = '#9A9588';
  const titleColor = '#3A352D';
  const padding = 5;
  const colWidth = (W - padding * 2 - 2) / 2;
  const colLeft = padding;
  const colRight = padding + colWidth + 2;

  let y = padding + 2;
  const titleY = y;
  y += 4 + 2; // title block
  // authors
  const authorsY = y + 1;
  y += 5;
  // arxiv id stamp
  const stampY = y;
  y += 3;
  // start two-column body around y
  const bodyTop = y + 1;

  return (
    <div style={{
      width: W,
      height: H,
      background: '#FDFCF9',
      border: '1px solid var(--hairline-strong)',
      borderRadius: 2,
      boxShadow: '0 1px 0 rgba(0,0,0,0.04), 0 4px 8px -4px rgba(0,0,0,0.08)',
      flexShrink: 0,
      overflow: 'hidden',
      position: 'relative',
    }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
        {/* Title lines */}
        {titleLines.map((w, i) => (
          <rect
            key={`t${i}`}
            x={padding + (W - padding * 2) * (1 - w) / 2}
            y={titleY + i * 2.4}
            width={(W - padding * 2) * w}
            height={1.4}
            fill={titleColor}
            rx={0.3}
          />
        ))}
        {/* Authors */}
        <rect
          x={padding + (W - padding * 2) * (1 - authorW) / 2}
          y={authorsY}
          width={(W - padding * 2) * authorW}
          height={0.9}
          fill={lineColor}
          opacity={0.7}
          rx={0.2}
        />
        {/* Abstract heading bar */}
        <rect
          x={padding}
          y={stampY}
          width={6}
          height={1}
          fill={titleColor}
          opacity={0.6}
        />
        {/* Left column lines */}
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
        {/* Right column: figure + lines */}
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
                <polyline points={`${colRight + 2},${bodyTop + 11} ${colRight + 6},${bodyTop + 8} ${colRight + 10},${bodyTop + 9} ${colRight + 14},${bodyTop + 5} ${colRight + 18},${bodyTop + 6} ${colRight + 22},${bodyTop + 3}`} />
                <line x1={colRight + 1.5} y1={bodyTop + 12.5} x2={colRight + colWidth - 1} y2={bodyTop + 12.5} strokeWidth={0.3} />
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
                <rect x={colRight + 4} y={bodyTop + 10.5} width={colWidth - 8} height={0.8} fill={titleColor} />
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
        {/* Page number */}
        <text
          x={W / 2}
          y={H - 1.5}
          fontSize={2}
          fill={lineColor}
          opacity={0.6}
          textAnchor="middle"
          fontFamily="serif"
        >1</text>
      </svg>
    </div>
  );
};

// Stars/hour — deterministic synthetic rate. Higher for trending (more upvotes,
// fewer days-since-publish). Returns a small int like 12, 47, 134.
const computeStarsPerHour = (paper) => {
  const upv = paper.upvotes || 0;
  // Map "Apr 26" / "Apr 21" etc. to a day-of-month, treat newest = Apr 26.
  const m = (paper.date || '').match(/(\d+)/);
  const day = m ? parseInt(m[1], 10) : 26;
  const daysAgo = Math.max(1, 26 - day + 1); // 1..6 across the seeded dataset
  // Base rate: upvotes per hour scaled, then weight by recency.
  const raw = (upv / daysAgo) * 0.9;
  // Add a deterministic per-paper jitter from id hash so values aren't all multiples.
  let h = 0;
  for (let i = 0; i < paper.id.length; i++) h = (h * 31 + paper.id.charCodeAt(i)) | 0;
  const jitter = (Math.abs(h) % 17) - 8; // -8..+8
  return Math.max(2, Math.round(raw + jitter));
};

const PaperCard = ({ paper, rank, onOpenPaper, onClickTag, upvoted, onUpvote }) => {
  const handleTitleClick = () => onOpenPaper(paper.id);
  return (
    <article className="paper-card">
      {rank != null && (
        <div
          className="paper-thumb-wrap"
          onClick={handleTitleClick}
          style={{ cursor: 'pointer' }}
        >
          <PdfThumbnail paper={paper} />
        </div>
      )}
      <div className="paper-body">
        <div className="paper-body-main">
          <h3 className="paper-title" onClick={handleTitleClick}>{paper.title}</h3>
          <div className="paper-authors">
            {paper.authors.slice(0, 3).join(', ')}
            {paper.authors.length > 3 && <span>, {paper.authors[paper.authors.length - 1]}</span>}
            {' · '}
            <span className="institution">{paper.institution}</span>
          </div>
          <p className="paper-abstract">{paper.abstract}</p>
          <div className="paper-tags">
            {paper.tags.map(t => <TagChip key={t} tagId={t} onClick={onClickTag} />)}
          </div>
        </div>
        {paper.github != null && (
          <aside className="paper-github-stats">
            <div className="gh-stat-block">
              <div className="gh-value-row">
                <Icon name="github" size={12} />
                <span className="gh-stars">{(paper.github / 1000).toFixed(1)}k</span>
              </div>
              <div className="gh-stars-label">stars</div>
            </div>
            <div className="gh-stat-block">
              <div className="gh-value-row">
                <span className="gh-rate-arrow">↑</span>
                <span className="gh-rate">{computeStarsPerHour(paper)}</span>
              </div>
              <div className="gh-stars-label">stars / hr</div>
            </div>
          </aside>
        )}
      </div>
    </article>
  );
};

// === MethodFigure: small illustrative diagram per method ===
// Palette echoes the canonical Vaswani-style box colors: muted pastels.
const MF_COLORS = {
  pink: '#F8D7D9',     pinkS: '#D9B0B3',
  yellow: '#FBEFC2',   yellowS: '#C9B97D',
  orange: '#F8D7B3',   orangeS: '#C99466',
  blue: '#CDE2EE',     blueS: '#7FA4BA',
  purple: '#D4D2EA',   purpleS: '#8E8AC0',
  green: '#CCE2C5',    greenS: '#7DA475',
  ink: '#1A1814',      faint: '#8E8678',
};
const C = MF_COLORS;

// Reusable rounded labeled box
const MFBox = ({ x, y, w, h, fill, stroke, label, fontSize = 10, multiline }) => (
  <g>
    <rect x={x} y={y} width={w} height={h} rx="3" ry="3" fill={fill} stroke={stroke} strokeWidth="1" />
    {multiline ? (
      <>
        <text x={x + w / 2} y={y + h / 2 - 2} fontSize={fontSize} fontFamily="var(--sans)" fill={C.ink} textAnchor="middle" dominantBaseline="middle">{multiline[0]}</text>
        <text x={x + w / 2} y={y + h / 2 + fontSize - 1} fontSize={fontSize} fontFamily="var(--sans)" fill={C.ink} textAnchor="middle" dominantBaseline="middle">{multiline[1]}</text>
      </>
    ) : (
      <text x={x + w / 2} y={y + h / 2} fontSize={fontSize} fontFamily="var(--sans)" fill={C.ink} textAnchor="middle" dominantBaseline="middle">{label}</text>
    )}
  </g>
);

// — Transformer (Vaswani-style two-stack) —
const TransformerFig = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: 'block' }}>
    <text x="180" y="14" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Output Probabilities</text>
    <path d="M180 22 L180 32" stroke={C.ink} strokeWidth="1.2" />
    <MFBox x={150} y={32} w={60} h={20} fill={C.green} stroke={C.greenS} label="Softmax" />
    <path d="M180 52 L180 62" stroke={C.ink} strokeWidth="1.2" />
    <MFBox x={150} y={62} w={60} h={20} fill={C.purple} stroke={C.purpleS} label="Linear" />
    <path d="M180 82 L180 92" stroke={C.ink} strokeWidth="1.2" />

    {/* Encoder stack (left) */}
    <rect x="50" y="170" width="120" height="120" rx="4" fill="#EFEBE0" stroke={C.faint} strokeWidth="1" strokeDasharray="3 2" />
    <text x="20" y="232" fontSize="11" fontFamily="var(--serif)" fill={C.faint}>N×</text>
    <MFBox x={70} y={180} w={80} h={18} fill={C.yellow} stroke={C.yellowS} label="Add & Norm" />
    <MFBox x={70} y={200} w={80} h={28} fill={C.blue} stroke={C.blueS} multiline={["Feed", "Forward"]} />
    <MFBox x={70} y={236} w={80} h={18} fill={C.yellow} stroke={C.yellowS} label="Add & Norm" />
    <MFBox x={70} y={256} w={80} h={28} fill={C.orange} stroke={C.orangeS} multiline={["Multi-Head", "Attention"]} />

    {/* Decoder stack (right) */}
    <rect x="190" y="92" width="120" height="200" rx="4" fill="#EFEBE0" stroke={C.faint} strokeWidth="1" strokeDasharray="3 2" />
    <text x="320" y="195" fontSize="11" fontFamily="var(--serif)" fill={C.faint}>N×</text>
    <MFBox x={210} y={102} w={80} h={18} fill={C.yellow} stroke={C.yellowS} label="Add & Norm" />
    <MFBox x={210} y={122} w={80} h={28} fill={C.blue} stroke={C.blueS} multiline={["Feed", "Forward"]} />
    <MFBox x={210} y={158} w={80} h={18} fill={C.yellow} stroke={C.yellowS} label="Add & Norm" />
    <MFBox x={210} y={178} w={80} h={28} fill={C.orange} stroke={C.orangeS} multiline={["Multi-Head", "Attention"]} />
    <MFBox x={210} y={216} w={80} h={18} fill={C.yellow} stroke={C.yellowS} label="Add & Norm" />
    <MFBox x={210} y={236} w={80} h={28} fill={C.orange} stroke={C.orangeS} multiline={["Masked MH", "Attention"]} />

    {/* Cross attention link */}
    <path d="M150 220 L195 192" stroke={C.ink} strokeWidth="1.2" fill="none" />
    <path d="M150 220 L195 200" stroke={C.ink} strokeWidth="1.2" fill="none" />

    {/* Positional encodings */}
    <text x="35" y="320" fontSize="9" fontFamily="var(--serif)" fill={C.faint} textAnchor="middle">Positional</text>
    <text x="35" y="332" fontSize="9" fontFamily="var(--serif)" fill={C.faint} textAnchor="middle">Encoding</text>
    <circle cx="78" cy="318" r="6" fill="none" stroke={C.ink} />
    <path d="M73 318 q5 -5 10 0" stroke={C.ink} fill="none" />
    <text x="100" y="322" fontSize="14" fill={C.ink} textAnchor="middle">+</text>
    <path d="M100 312 L100 305" stroke={C.ink} />
    <path d="M100 322 L100 335" stroke={C.ink} />

    <text x="325" y="320" fontSize="9" fontFamily="var(--serif)" fill={C.faint} textAnchor="middle">Positional</text>
    <text x="325" y="332" fontSize="9" fontFamily="var(--serif)" fill={C.faint} textAnchor="middle">Encoding</text>
    <circle cx="282" cy="318" r="6" fill="none" stroke={C.ink} />
    <path d="M277 318 q5 -5 10 0" stroke={C.ink} fill="none" />
    <text x="260" y="322" fontSize="14" fill={C.ink} textAnchor="middle">+</text>
    <path d="M260 312 L260 305" stroke={C.ink} />
    <path d="M260 322 L260 335" stroke={C.ink} />

    {/* Embeddings */}
    <MFBox x={70} y={340} w={80} h={26} fill={C.pink} stroke={C.pinkS} multiline={["Input", "Embedding"]} />
    <MFBox x={210} y={340} w={80} h={26} fill={C.pink} stroke={C.pinkS} multiline={["Output", "Embedding"]} />
    <path d="M110 366 L110 380" stroke={C.ink} />
    <path d="M250 366 L250 380" stroke={C.ink} />
    <text x="110" y="395" fontSize="11" fontFamily="var(--serif)" fill={C.ink} textAnchor="middle">Inputs</text>
    <text x="250" y="395" fontSize="9" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Outputs (shifted right)</text>
    <text x="250" y="408" fontSize="11" fontFamily="var(--serif)" fill={C.ink} textAnchor="middle"></text>

    {/* Encoder right-output to decoder cross-attn (dashed) */}
    <path d="M150 270 q40 -40 60 -80" stroke={C.ink} strokeDasharray="3 3" fill="none" strokeWidth="1" />
  </svg>
);

// — Attention (scaled dot-product) —
const AttentionFig = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: 'block' }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Scaled Dot-Product Attention</text>
    <MFBox x={140} y={40} w={80} h={26} fill={C.yellow} stroke={C.yellowS} label="MatMul" fontSize={11} />
    <path d="M180 66 L180 80" stroke={C.ink} />
    <MFBox x={140} y={80} w={80} h={26} fill={C.green} stroke={C.greenS} label="SoftMax" fontSize={11} />
    <path d="M180 106 L180 120" stroke={C.ink} />
    <MFBox x={140} y={120} w={80} h={26} fill={C.purple} stroke={C.purpleS} label="Mask (opt.)" fontSize={11} />
    <path d="M180 146 L180 160" stroke={C.ink} />
    <MFBox x={140} y={160} w={80} h={26} fill={C.blue} stroke={C.blueS} label="Scale ÷√dₖ" fontSize={11} />
    <path d="M180 186 L180 200" stroke={C.ink} />
    <MFBox x={140} y={200} w={80} h={26} fill={C.yellow} stroke={C.yellowS} label="MatMul" fontSize={11} />
    <path d="M156 226 L120 270" stroke={C.ink} />
    <path d="M180 226 L180 270" stroke={C.ink} />
    <path d="M204 226 L240 270" stroke={C.ink} />
    <MFBox x={100} y={270} w={40} h={24} fill={C.pink} stroke={C.pinkS} label="Q" fontSize={13} />
    <MFBox x={160} y={270} w={40} h={24} fill={C.pink} stroke={C.pinkS} label="K" fontSize={13} />
    <MFBox x={220} y={270} w={40} h={24} fill={C.pink} stroke={C.pinkS} label="V" fontSize={13} />
    <text x="180" y="330" fontSize="14" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
      softmax(QK<tspan fontSize="9" baselineShift="super">⊤</tspan> / √d) V
    </text>
  </svg>
);

// — CNN: stack of conv layers —
const CNNFig = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: 'block' }}>
    {[0,1,2,3].map(i => {
      const x = 30 + i * 75;
      const w = 60 - i * 8;
      const h = 240 - i * 30;
      return (
        <g key={i}>
          <rect x={x} y={(420 - h)/2} width={w} height={h} rx="2" fill={[C.blue,C.green,C.orange,C.purple][i]} stroke={[C.blueS,C.greenS,C.orangeS,C.purpleS][i]} strokeWidth="1" />
          {/* grid */}
          {[...Array(Math.floor(h / 16))].map((_, j) => (
            <line key={j} x1={x} y1={(420 - h)/2 + j * 16} x2={x + w} y2={(420 - h)/2 + j * 16} stroke="rgba(0,0,0,0.08)" />
          ))}
        </g>
      );
    })}
    <text x="60" y="395" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">conv</text>
    <text x="135" y="395" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">conv</text>
    <text x="210" y="395" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">conv</text>
    <text x="285" y="395" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">fc</text>
    {[105,180,255].map(x => <path key={x} d={`M${x} 210 L${x+15} 210`} stroke={C.ink} markerEnd="url(#arrh)" />)}
    <defs>
      <marker id="arrh" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
        <path d="M0,0 L6,3 L0,6 z" fill={C.ink} />
      </marker>
    </defs>
  </svg>
);

// — U-Net: encoder-decoder with skip connections —
const UNetFig = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: 'block' }}>
    {/* encoder: left going down */}
    {[0,1,2,3].map(i => {
      const x = 50;
      const y = 60 + i * 80;
      const w = 100 - i * 12;
      const h = 50 - i * 6;
      return <rect key={`e${i}`} x={x} y={y} width={w} height={h} rx="2" fill={C.blue} stroke={C.blueS} strokeWidth="1" />;
    })}
    {/* bottleneck */}
    <rect x="155" y="320" width="50" height="40" rx="2" fill={C.purple} stroke={C.purpleS} />
    {/* decoder: right going up */}
    {[0,1,2,3].map(i => {
      const x = 210;
      const y = 60 + i * 80;
      const w = 100 - i * 12;
      const h = 50 - i * 6;
      return <rect key={`d${i}`} x={x} y={y} width={w} height={h} rx="2" fill={C.green} stroke={C.greenS} strokeWidth="1" />;
    })}
    {/* skip connections (gray dashed arrows) */}
    {[0,1,2,3].map(i => {
      const y = 60 + i * 80 + (50 - i * 6) / 2;
      const xL = 50 + (100 - i * 12);
      const xR = 210;
      return <path key={`s${i}`} d={`M${xL} ${y} L${xR} ${y}`} stroke={C.faint} strokeDasharray="4 3" />;
    })}
    {/* downsample arrows */}
    <path d="M100 105 L100 145" stroke={C.ink} markerEnd="url(#arrhU)" />
    <path d="M94 185 L94 225" stroke={C.ink} markerEnd="url(#arrhU)" />
    <path d="M88 265 L88 305" stroke={C.ink} markerEnd="url(#arrhU)" />
    <path d="M180 360 L180 380 L210 380" stroke={C.ink} fill="none" markerEnd="url(#arrhU)" />
    <text x="100" y="40" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">encoder</text>
    <text x="260" y="40" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">decoder</text>
    <text x="180" y="395" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">skip connections preserve high-res features</text>
    <defs>
      <marker id="arrhU" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
        <path d="M0,0 L6,3 L0,6 z" fill={C.ink} />
      </marker>
    </defs>
  </svg>
);

// — ViT: image patches → transformer —
const ViTFig = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: 'block' }}>
    {/* image grid 3x3 */}
    {[0,1,2].map(r => [0,1,2].map(c => (
      <rect key={`${r}-${c}`} x={20 + c*40} y={40 + r*40} width="38" height="38" fill={['#F8D7D9','#FBEFC2','#CDE2EE','#CCE2C5','#D4D2EA','#F8D7B3','#F8D7D9','#FBEFC2','#CDE2EE'][r*3+c]} stroke={C.faint} />
    )))}
    {/* arrow + linear projection */}
    <path d="M150 100 L185 100" stroke={C.ink} markerEnd="url(#arrhV)" />
    <text x="170" y="92" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">flatten</text>
    {/* Patch embeddings sequence */}
    {[0,1,2,3,4,5,6,7,8].map(i => (
      <rect key={i} x={20 + i*36} y={170} width="32" height="20" rx="2" fill={['#F8D7D9','#FBEFC2','#CDE2EE','#CCE2C5','#D4D2EA','#F8D7B3','#F8D7D9','#FBEFC2','#CDE2EE'][i]} stroke={C.faint} strokeWidth="0.6" />
    ))}
    <text x="180" y="160" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">linear projection of flattened patches</text>
    <text x="36" y="183" fontSize="11" fontFamily="var(--serif)" fill={C.ink} textAnchor="middle" dominantBaseline="middle" fontStyle="italic">[CLS]</text>
    {/* + position embedding */}
    {[0,1,2,3,4,5,6,7,8].map(i => (
      <text key={i} x={36 + i*36} y={210} fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">{i}</text>
    ))}
    {/* arrow down */}
    <path d="M180 220 L180 240" stroke={C.ink} markerEnd="url(#arrhV)" />
    {/* Transformer encoder block */}
    <rect x="40" y="245" width="280" height="120" rx="4" fill="#EFEBE0" stroke={C.faint} strokeDasharray="3 2" />
    <MFBox x={70} y={258} w={220} h={20} fill={C.yellow} stroke={C.yellowS} label="Norm" />
    <MFBox x={70} y={282} w={220} h={28} fill={C.orange} stroke={C.orangeS} label="Multi-Head Attention" />
    <MFBox x={70} y={314} w={220} h={20} fill={C.yellow} stroke={C.yellowS} label="Norm" />
    <MFBox x={70} y={338} w={220} h={20} fill={C.blue} stroke={C.blueS} label="MLP" />
    <text x="180" y="385" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">Transformer Encoder · L×</text>
    <defs>
      <marker id="arrhV" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
        <path d="M0,0 L6,3 L0,6 z" fill={C.ink} />
      </marker>
    </defs>
  </svg>
);

// — Mixture of Experts: router + experts —
const MoEFig = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: 'block' }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Sparse routing of tokens to k of N experts</text>
    {/* input */}
    <MFBox x={140} y={40} w={80} h={28} fill={C.pink} stroke={C.pinkS} label="Token x" fontSize={11} />
    <path d="M180 68 L180 90" stroke={C.ink} markerEnd="url(#arrhM)" />
    {/* router */}
    <MFBox x={120} y={90} w={120} h={30} fill={C.yellow} stroke={C.yellowS} label="Router (softmax)" fontSize={11} />
    {/* lines to experts */}
    {[0,1,2,3,4].map(i => {
      const x = 50 + i * 65;
      const active = i === 1 || i === 3;
      return (
        <g key={i}>
          <path d={`M180 120 L${x + 25} 180`} stroke={active ? C.ink : C.faint} strokeWidth={active ? 1.6 : 0.8} strokeDasharray={active ? null : '3 3'} markerEnd={active ? 'url(#arrhM)' : null} />
          <rect x={x} y={185} width="50" height="60" rx="3" fill={active ? C.green : '#F2EFE8'} stroke={active ? C.greenS : C.faint} strokeWidth="1" />
          <text x={x + 25} y={210} fontSize="10" fontFamily="var(--mono)" fill={C.ink} textAnchor="middle">FFN</text>
          <text x={x + 25} y={228} fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">E{i+1}</text>
          <path d={`M${x + 25} 245 L180 290`} stroke={active ? C.ink : C.faint} strokeWidth={active ? 1.6 : 0.6} strokeDasharray={active ? null : '3 3'} />
        </g>
      );
    })}
    <circle cx="180" cy="295" r="10" fill={C.bg} stroke={C.ink} />
    <text x="180" y="299" fontSize="11" fill={C.ink} textAnchor="middle">Σ</text>
    <path d="M180 305 L180 325" stroke={C.ink} markerEnd="url(#arrhM)" />
    <MFBox x={140} y={325} w={80} h={28} fill={C.purple} stroke={C.purpleS} label="Output y" fontSize={11} />
    <defs>
      <marker id="arrhM" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
        <path d="M0,0 L6,3 L0,6 z" fill={C.ink} />
      </marker>
    </defs>
  </svg>
);

// — Diffusion: noising schedule with images x_T → x_0 —
const DiffusionFig = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: 'block' }}>
    <text x="180" y="50" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Reverse process: pure noise → sample</text>
    {[0,1,2,3,4,5].map(i => {
      const x = 25 + i * 56;
      // noise level from low (i=0 noise) to high (i=5 clean): leftmost is noisy
      const noiseLevel = (5 - i) / 5;
      return (
        <g key={i}>
          <rect x={x} y={90} width={50} height={50} rx="3" fill={`oklch(${0.85 - noiseLevel * 0.1} 0.04 250)`} stroke={C.faint} />
          {/* render dots/noise as dense scatter */}
          {[...Array(Math.floor(60 * noiseLevel) + 8)].map((_, j) => {
            const px = x + 4 + ((j * 17) % 42);
            const py = 94 + ((j * 31) % 42);
            return <circle key={j} cx={px} cy={py} r={Math.max(0.5, 1.5 * noiseLevel)} fill={`rgba(0,0,0,${0.15 + 0.5 * noiseLevel})`} />;
          })}
          {/* Underlying shape becomes visible at low noise */}
          {noiseLevel < 0.4 && (
            <circle cx={x + 25} cy={115} r={12 - noiseLevel * 16} fill={C.orange} opacity={1 - noiseLevel * 1.5} />
          )}
          <text x={x + 25} y={158} fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
            x<tspan baselineShift="sub" fontSize="8">{i === 0 ? 'T' : (i === 5 ? '0' : `T-${i}`)}</tspan>
          </text>
        </g>
      );
    })}
    {[0,1,2,3,4].map(i => {
      const x = 75 + i * 56;
      return <path key={i} d={`M${x} 115 L${x + 6} 115`} stroke={C.ink} strokeWidth="1.4" markerEnd="url(#arrhD)" />;
    })}
    <text x="180" y="195" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">denoise (learned ε-prediction)</text>
    {/* Loss */}
    <rect x="60" y="240" width="240" height="120" rx="4" fill="#FFF9EE" stroke={C.faint} />
    <text x="180" y="260" fontSize="11" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">TRAINING OBJECTIVE</text>
    <text x="180" y="295" fontSize="14" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
      L = E[‖ε − ε_θ(x_t, t)‖²]
    </text>
    <text x="180" y="325" fontSize="10" fontFamily="var(--serif)" fill={C.faint} textAnchor="middle">predict noise added at random step t</text>
    <defs>
      <marker id="arrhD" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
        <path d="M0,0 L6,3 L0,6 z" fill={C.ink} />
      </marker>
    </defs>
  </svg>
);

// — GAN: G + D adversarial —
const GANFig = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: 'block' }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Generator vs. Discriminator</text>
    {/* z noise */}
    <circle cx="50" cy="120" r="22" fill={C.purple} stroke={C.purpleS} />
    <text x="50" y="125" fontSize="14" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">z</text>
    <path d="M75 120 L110 120" stroke={C.ink} markerEnd="url(#arrhG)" />
    {/* G */}
    <rect x="110" y="92" width="80" height="56" rx="3" fill={C.blue} stroke={C.blueS} />
    <text x="150" y="124" fontSize="14" fontFamily="var(--mono)" fill={C.ink} textAnchor="middle">G</text>
    <path d="M190 120 L225 120" stroke={C.ink} markerEnd="url(#arrhG)" />
    {/* fake image */}
    <rect x="225" y="100" width="40" height="40" rx="3" fill={C.orange} stroke={C.orangeS} />
    <text x="245" y="155" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">G(z)</text>
    {/* real image */}
    <rect x="225" y="195" width="40" height="40" rx="3" fill={C.green} stroke={C.greenS} />
    <text x="245" y="250" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">x ~ p_data</text>
    {/* Discriminator */}
    <path d="M270 120 L290 145" stroke={C.ink} markerEnd="url(#arrhG)" />
    <path d="M270 215 L290 175" stroke={C.ink} markerEnd="url(#arrhG)" />
    <rect x="290" y="140" width="50" height="50" rx="3" fill={C.pink} stroke={C.pinkS} />
    <text x="315" y="170" fontSize="14" fontFamily="var(--mono)" fill={C.ink} textAnchor="middle">D</text>
    <path d="M315 195 L315 245" stroke={C.ink} markerEnd="url(#arrhG)" />
    <text x="315" y="265" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">real / fake?</text>
    {/* loss */}
    <rect x="40" y="305" width="280" height="60" rx="4" fill="#FFF9EE" stroke={C.faint} />
    <text x="180" y="325" fontSize="11" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">MINIMAX OBJECTIVE</text>
    <text x="180" y="350" fontSize="13" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
      min_G max_D  E[log D(x)] + E[log(1 − D(G(z)))]
    </text>
    <defs>
      <marker id="arrhG" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
        <path d="M0,0 L6,3 L0,6 z" fill={C.ink} />
      </marker>
    </defs>
  </svg>
);

// — VAE: encoder → μ,σ → decoder —
const VAEFig = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: 'block' }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Variational Autoencoder</text>
    <rect x="30" y="100" width="40" height="40" rx="3" fill={C.green} stroke={C.greenS} />
    <text x="50" y="155" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">x</text>
    <path d="M75 120 L100 120" stroke={C.ink} markerEnd="url(#arrhVA)" />
    <rect x="100" y="92" width="60" height="56" rx="3" fill={C.blue} stroke={C.blueS} />
    <text x="130" y="124" fontSize="11" fontFamily="var(--mono)" fill={C.ink} textAnchor="middle">Encoder</text>
    <text x="130" y="138" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">q(z|x)</text>
    {/* μ, σ */}
    <path d="M160 110 L195 90" stroke={C.ink} />
    <path d="M160 130 L195 150" stroke={C.ink} />
    <rect x="195" y="78" width="36" height="22" rx="3" fill={C.yellow} stroke={C.yellowS} />
    <text x="213" y="93" fontSize="13" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">μ</text>
    <rect x="195" y="142" width="36" height="22" rx="3" fill={C.yellow} stroke={C.yellowS} />
    <text x="213" y="157" fontSize="13" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">σ</text>
    {/* z */}
    <path d="M231 89 L260 110" stroke={C.ink} />
    <path d="M231 153 L260 130" stroke={C.ink} />
    <circle cx="270" cy="120" r="14" fill={C.purple} stroke={C.purpleS} />
    <text x="270" y="124" fontSize="13" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">z</text>
    <text x="270" y="155" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">μ + σ⊙ε</text>
    {/* arrow down to decoder */}
    <path d="M270 138 L270 220 L160 220" stroke={C.ink} fill="none" markerEnd="url(#arrhVA)" />
    <rect x="100" y="200" width="60" height="56" rx="3" fill={C.orange} stroke={C.orangeS} />
    <text x="130" y="232" fontSize="11" fontFamily="var(--mono)" fill={C.ink} textAnchor="middle">Decoder</text>
    <text x="130" y="246" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">p(x|z)</text>
    <path d="M75 230 L100 230" stroke={C.ink} fill="none" />
    <rect x="30" y="210" width="40" height="40" rx="3" fill={C.pink} stroke={C.pinkS} />
    <text x="50" y="265" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">x̂</text>
    <rect x="40" y="295" width="280" height="80" rx="4" fill="#FFF9EE" stroke={C.faint} />
    <text x="180" y="315" fontSize="11" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">EVIDENCE LOWER BOUND</text>
    <text x="180" y="345" fontSize="13" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
      L = E[log p(x|z)] − KL(q(z|x) ‖ p(z))
    </text>
    <text x="180" y="365" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">reconstruction      regularization</text>
    <defs>
      <marker id="arrhVA" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
        <path d="M0,0 L6,3 L0,6 z" fill={C.ink} />
      </marker>
    </defs>
  </svg>
);

// — RLHF: reward model + PPO loop —
const RLHFFig = () => (
  <svg viewBox="0 0 360 420" width="100%" height="100%" style={{ display: 'block' }}>
    <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Three-stage post-training pipeline</text>
    {/* Step 1: SFT */}
    <text x="20" y="58" fontSize="9" fontFamily="var(--mono)" fill={C.faint}>1.</text>
    <MFBox x={40} y={45} w={280} h={36} fill={C.green} stroke={C.greenS} label="Supervised fine-tuning on demonstrations" fontSize={11} />
    {/* Step 2: RM */}
    <text x="20" y="118" fontSize="9" fontFamily="var(--mono)" fill={C.faint}>2.</text>
    <MFBox x={40} y={105} w={120} h={36} fill={C.blue} stroke={C.blueS} label="Pairwise preferences" fontSize={10} />
    <path d="M165 123 L195 123" stroke={C.ink} markerEnd="url(#arrhR)" />
    <MFBox x={200} y={105} w={120} h={36} fill={C.yellow} stroke={C.yellowS} label="Reward model rθ" fontSize={11} />
    {/* Step 3: PPO loop */}
    <text x="20" y="178" fontSize="9" fontFamily="var(--mono)" fill={C.faint}>3.</text>
    <MFBox x={40} y={165} w={100} h={40} fill={C.pink} stroke={C.pinkS} label="Policy πφ (LLM)" fontSize={11} />
    <path d="M145 175 L175 175" stroke={C.ink} markerEnd="url(#arrhR)" />
    <text x="160" y="170" fontSize="9" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">y</text>
    <MFBox x={180} y={165} w={70} h={40} fill={C.orange} stroke={C.orangeS} label="Sample y" fontSize={10} />
    <path d="M255 185 L290 215" stroke={C.ink} markerEnd="url(#arrhR)" />
    <MFBox x={250} y={220} w={70} h={40} fill={C.yellow} stroke={C.yellowS} label="rθ(y)" fontSize={11} />
    <path d="M250 240 L155 240 L155 215" stroke={C.ink} fill="none" markerEnd="url(#arrhR)" />
    <text x="80" y="255" fontSize="10" fontFamily="var(--mono)" fill={C.faint}>PPO update</text>
    <text x="80" y="268" fontSize="10" fontFamily="var(--mono)" fill={C.faint}>− β·KL(π‖π_ref)</text>

    <rect x="40" y="295" width="280" height="80" rx="4" fill="#FFF9EE" stroke={C.faint} />
    <text x="180" y="315" fontSize="11" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">PPO OBJECTIVE</text>
    <text x="180" y="345" fontSize="13" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
      max E[rθ(y)] − β·KL(πφ ‖ π_ref)
    </text>
    <defs>
      <marker id="arrhR" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
        <path d="M0,0 L6,3 L0,6 z" fill={C.ink} />
      </marker>
    </defs>
  </svg>
);

// — Generic by category fallback —
const GenericFig = ({ method, category }) => {
  const palettes = {
    architectures: [C.blue, C.orange, C.purple],
    normalization: [C.yellow, C.green, C.yellow],
    optimization: [C.purple, C.purple, C.purple],
    generative: [C.pink, C.purple, C.green],
    rl: [C.orange, C.green, C.yellow],
    signal: [C.blue, C.blue, C.blue],
    regularization: [C.green, C.green, C.green],
  };
  const cat = category || 'architectures';
  const pal = palettes[cat] || palettes.architectures;
  const stroke = {
    architectures: [C.blueS, C.orangeS, C.purpleS],
    normalization: [C.yellowS, C.greenS, C.yellowS],
    optimization: [C.purpleS, C.purpleS, C.purpleS],
    generative: [C.pinkS, C.purpleS, C.greenS],
    rl: [C.orangeS, C.greenS, C.yellowS],
    signal: [C.blueS, C.blueS, C.blueS],
    regularization: [C.greenS, C.greenS, C.greenS],
  }[cat] || [C.blueS, C.orangeS, C.purpleS];

  if (cat === 'optimization') {
    // gradient descent landscape
    return (
      <svg viewBox="0 0 360 420" width="100%" height="100%">
        <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Loss landscape · descent path</text>
        {/* contour rings */}
        {[0,1,2,3,4,5].map(i => (
          <ellipse key={i} cx="180" cy="220" rx={150 - i * 22} ry={90 - i * 12} fill="none" stroke={C.faint} strokeWidth="0.8" opacity={0.4 + i * 0.08} />
        ))}
        {/* descent path */}
        <path d="M50 100 Q120 130 140 170 Q170 220 180 220" stroke={C.ink} fill="none" strokeWidth="1.5" />
        {[0,0.25,0.5,0.75,1].map((t, i) => {
          const x = 50 + (130) * t;
          const y = 100 + ((220 - 100)) * (t * t);
          return <circle key={i} cx={x} cy={y} r={3} fill={C.orange} stroke={C.orangeS} />;
        })}
        <circle cx="180" cy="220" r={6} fill={C.green} stroke={C.greenS} />
        <text x="180" y="240" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">θ*</text>
        <text x="180" y="320" fontSize="13" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
          θ ← θ − η ∇L(θ)
        </text>
        <text x="180" y="345" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">{(method && method.label) || 'optimizer'}</text>
      </svg>
    );
  }
  if (cat === 'normalization') {
    return (
      <svg viewBox="0 0 360 420" width="100%" height="100%">
        <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Activation normalization</text>
        {/* before */}
        <text x="80" y="60" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">before</text>
        {[0,1,2,3,4].map(i => {
          const h = [60, 30, 90, 20, 75][i];
          return <rect key={i} x={30 + i * 22} y={150 - h} width="16" height={h} fill={C.orange} stroke={C.orangeS} />;
        })}
        <line x1="20" y1="150" x2="150" y2="150" stroke={C.ink} />
        {/* arrow */}
        <text x="180" y="100" fontSize="20" fill={C.ink} textAnchor="middle">→</text>
        <text x="180" y="125" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">norm</text>
        {/* after */}
        <text x="280" y="60" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">after</text>
        {[0,1,2,3,4].map(i => {
          const h = [50, 45, 55, 42, 52][i];
          return <rect key={i} x={230 + i * 22} y={150 - h} width="16" height={h} fill={C.green} stroke={C.greenS} />;
        })}
        <line x1="220" y1="150" x2="350" y2="150" stroke={C.ink} />
        <rect x="40" y="200" width="280" height="160" rx="4" fill="#FFF9EE" stroke={C.faint} />
        <text x="180" y="225" fontSize="11" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">FORMULA</text>
        <text x="180" y="265" fontSize="14" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
          y = γ · (x − μ) / σ + β
        </text>
        <text x="180" y="305" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">{(method && method.label) || 'norm'}</text>
        <text x="180" y="325" fontSize="9" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">μ, σ computed over different axes</text>
      </svg>
    );
  }
  if (cat === 'rl') {
    return (
      <svg viewBox="0 0 360 420" width="100%" height="100%">
        <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Agent–environment interaction</text>
        <rect x="60" y="80" width="80" height="60" rx="3" fill={C.orange} stroke={C.orangeS} />
        <text x="100" y="115" fontSize="13" fontFamily="var(--mono)" fill={C.ink} textAnchor="middle">Agent</text>
        <rect x="220" y="80" width="100" height="60" rx="3" fill={C.green} stroke={C.greenS} />
        <text x="270" y="115" fontSize="13" fontFamily="var(--mono)" fill={C.ink} textAnchor="middle">Environment</text>
        <path d="M140 100 L220 100" stroke={C.ink} markerEnd="url(#arrhRL)" />
        <text x="180" y="92" fontSize="10" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">action a_t</text>
        <path d="M220 130 L140 130" stroke={C.ink} markerEnd="url(#arrhRL)" />
        <text x="180" y="148" fontSize="10" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">state s_{`t+1`}, reward r_t</text>
        <rect x="40" y="225" width="280" height="135" rx="4" fill="#FFF9EE" stroke={C.faint} />
        <text x="180" y="250" fontSize="11" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">OBJECTIVE</text>
        <text x="180" y="290" fontSize="14" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
          maximize E[Σ γ<tspan baselineShift="super" fontSize="9">t</tspan> r_t]
        </text>
        <text x="180" y="325" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">{(method && method.label) || 'policy'}</text>
        <defs>
          <marker id="arrhRL" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
            <path d="M0,0 L6,3 L0,6 z" fill={C.ink} />
          </marker>
        </defs>
      </svg>
    );
  }
  if (cat === 'signal') {
    // spectrogram tiles
    return (
      <svg viewBox="0 0 360 420" width="100%" height="100%">
        <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Time–frequency representation</text>
        {[...Array(20)].map((_, c) => (
          [...Array(12)].map((__, r) => {
            const v = (Math.sin(c * 0.6 + r * 0.4) + Math.cos(c * 0.3 - r * 0.2) + 2) / 4;
            return <rect key={`${r}-${c}`} x={30 + c * 15} y={50 + r * 22} width="14" height="20" fill={`oklch(${0.95 - v * 0.5} ${0.04 + v * 0.06} 250)`} />;
          })
        ))}
        <text x="180" y="345" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">time →</text>
        <text x="20" y="160" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle" transform="rotate(-90 20 160)">freq</text>
        <text x="180" y="380" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">{(method && method.label) || 'spectrogram'}</text>
      </svg>
    );
  }
  if (cat === 'regularization') {
    return (
      <svg viewBox="0 0 360 420" width="100%" height="100%">
        <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">Network with random units dropped</text>
        {[0,1,2,3,4,5,6,7].map(i => {
          const x = 60 + (i % 4) * 60;
          const y = 80 + Math.floor(i / 4) * 70;
          const dropped = [false, true, false, false, false, false, true, false][i];
          return (
            <g key={i}>
              <circle cx={x} cy={y} r={14} fill={dropped ? '#F2EFE8' : C.green} stroke={dropped ? C.faint : C.greenS} strokeDasharray={dropped ? '3 2' : null} opacity={dropped ? 0.5 : 1} />
              {dropped && <line x1={x-10} y1={y-10} x2={x+10} y2={y+10} stroke={C.faint} />}
            </g>
          );
        })}
        {/* connections (gray, lighter for dropped) */}
        {[[0,4],[0,5],[1,4],[1,5],[2,5],[2,6],[3,6],[3,7]].map(([a,b], i) => {
          const ax = 60 + (a % 4) * 60, ay = 80;
          const bx = 60 + (b % 4) * 60, by = 150;
          const dropped = [false, true, false, false, false, false, true, false];
          const dim = dropped[a] || dropped[b];
          return <line key={i} x1={ax} y1={ay} x2={bx} y2={by} stroke={dim ? C.faint : C.ink} strokeWidth={dim ? 0.4 : 1} opacity={dim ? 0.4 : 1} />;
        })}
        <rect x="40" y="220" width="280" height="140" rx="4" fill="#FFF9EE" stroke={C.faint} />
        <text x="180" y="245" fontSize="11" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">DROP MASK</text>
        <text x="180" y="285" fontSize="14" fontFamily="var(--serif)" fontStyle="italic" fill={C.ink} textAnchor="middle">
          y = (m ⊙ x) / (1 − p)
        </text>
        <text x="180" y="320" fontSize="10" fontFamily="var(--mono)" fill={C.faint} textAnchor="middle">{(method && method.label) || 'regularizer'}</text>
        <text x="180" y="340" fontSize="9" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">m_i ~ Bernoulli(1 − p)</text>
      </svg>
    );
  }
  // default: stack of three labeled blocks
  return (
    <svg viewBox="0 0 360 420" width="100%" height="100%">
      <text x="180" y="20" fontSize="11" fontFamily="var(--serif)" fontStyle="italic" fill={C.faint} textAnchor="middle">{(method && method.label) || 'method'}</text>
      <MFBox x={80} y={70} w={200} h={50} fill={pal[0]} stroke={stroke[0]} label="Input" fontSize={12} />
      <path d="M180 120 L180 150" stroke={C.ink} markerEnd="url(#arrhGN)" />
      <MFBox x={80} y={150} w={200} h={70} fill={pal[1]} stroke={stroke[1]} label={(method && method.label) || 'transform'} fontSize={13} />
      <path d="M180 220 L180 250" stroke={C.ink} markerEnd="url(#arrhGN)" />
      <MFBox x={80} y={250} w={200} h={50} fill={pal[2]} stroke={stroke[2]} label="Output" fontSize={12} />
      <defs>
        <marker id="arrhGN" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <path d="M0,0 L6,3 L0,6 z" fill={C.ink} />
        </marker>
      </defs>
    </svg>
  );
};

const MethodFigure = ({ method }) => {
  if (!method) return null;
  const fig = {
    transformer: <TransformerFig />,
    attention: <AttentionFig />,
    'self-attention': <AttentionFig />,
    rope: <AttentionFig />,
    flashattn: <AttentionFig />,
    cnn: <CNNFig />,
    'u-net': <UNetFig />,
    vit: <ViTFig />,
    moe: <MoEFig />,
    ddpm: <DiffusionFig />,
    'flow-matching': <DiffusionFig />,
    'score-distillation': <DiffusionFig />,
    gan: <GANFig />,
    vae: <VAEFig />,
    rlhf: <RLHFFig />,
    dpo: <RLHFFig />,
  }[method.id];
  return fig || <GenericFig method={method} category={method.category} />;
};

const MethodChip = ({ methodId, onClick }) => {
  const m = getMethod(methodId);
  if (!m) return null;
  return (
    <span
      className="method-chip"
      onClick={(e) => { e.stopPropagation(); onClick && onClick(methodId); }}
    >
      {m.label}
    </span>
  );
};

export {
  TagChip,
  MethodChip,
  Icon,
  DomainIcon,
  Header,
  Banner,
  PaperCard,
  PdfThumbnail,
  MethodFigure,
};
