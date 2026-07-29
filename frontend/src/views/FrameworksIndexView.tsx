import React from "react";
import { Link } from "react-router-dom";

import { Icon } from "@/components";
import { chipColors, hueFromSlug } from "@/lib/colors";
import {
  FRAMEWORK_DOMAINS,
  PLATFORM_LABELS,
  type Framework,
  type FrameworkPlatform,
} from "@/lib/frameworks";

const sectionHeaderStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  gap: 24,
  paddingBottom: 12,
  borderBottom: "1px solid var(--hairline-strong)",
};

const sectionTitleStyle: React.CSSProperties = {
  fontFamily: "var(--serif)",
  fontSize: 26,
  fontWeight: 500,
  letterSpacing: "-0.02em",
  marginBottom: 4,
};

const sectionBlurbStyle: React.CSSProperties = {
  fontFamily: "var(--serif)",
  fontStyle: "italic",
  fontSize: 13,
  color: "var(--ink-soft)",
};

const categoryTitleStyle: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 13,
  fontWeight: 600,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  color: "var(--ink)",
  marginBottom: 6,
};

const PlatformChip: React.FC<{ platform: FrameworkPlatform }> = ({ platform }) => {
  const c = chipColors(hueFromSlug(platform));
  return (
    <span
      className="framework-platform-chip"
      style={{
        background: c.bg,
        color: c.text,
      }}
    >
      {PLATFORM_LABELS[platform]}
    </span>
  );
};

const FrameworkCard: React.FC<{ framework: Framework }> = ({ framework }) => {
  return (
    <article id={`framework-${framework.slug}`} className="framework-card">
      <div className="framework-card-head">
        <div>
          <h3 className="framework-card-name">{framework.name}</h3>
          {framework.org && <div className="framework-card-org">{framework.org}</div>}
        </div>
        {framework.platforms && framework.platforms.length > 0 && (
          <div className="framework-platform-row">
            {framework.platforms.map((platform) => (
              <PlatformChip key={platform} platform={platform} />
            ))}
          </div>
        )}
      </div>

      <p className="framework-card-desc">{framework.description}</p>

      {framework.whenToUse && (
        <div className="framework-card-when">
          <span className="framework-card-when-label">When to use</span>
          {framework.whenToUse}
        </div>
      )}

      {(framework.github || framework.url || framework.paperId) && (
        <div className="framework-card-links">
          {framework.paperId && (
            <Link to={`/paper/${framework.paperId}`} className="framework-link">
              Paper
            </Link>
          )}
          {framework.github && (
            <a
              href={framework.github}
              target="_blank"
              rel="noopener noreferrer"
              className="framework-link"
            >
              <Icon name="github" size={13} />
              GitHub
            </a>
          )}
          {framework.url && framework.url !== framework.github && (
            <a
              href={framework.url}
              target="_blank"
              rel="noopener noreferrer"
              className="framework-link"
            >
              Docs
            </a>
          )}
        </div>
      )}
    </article>
  );
};

const FrameworksIndexView: React.FC = () => {
  const totalFrameworks = FRAMEWORK_DOMAINS.reduce(
    (sum, domain) =>
      sum + domain.categories.reduce((catSum, category) => catSum + category.frameworks.length, 0),
    0,
  );

  React.useEffect(() => {
    const frameworkId = window.location.hash.slice(1);
    if (frameworkId) {
      document.getElementById(frameworkId)?.scrollIntoView();
    }
  }, []);

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">
            AI <em>Frameworks</em>
          </h1>
          <div className="feed-subtitle">
            Curated libraries and tools to run, serve, and train models — pick the right stack for
            your hardware and workload.
          </div>
        </div>
      </div>

      {FRAMEWORK_DOMAINS.map((domain) => (
        <section key={domain.id} style={{ marginBottom: 56 }}>
          <div style={sectionHeaderStyle}>
            <div>
              <h2 style={sectionTitleStyle}>{domain.name}</h2>
              <div style={sectionBlurbStyle}>{domain.blurb}</div>
            </div>
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 11,
                color: "var(--ink-faint)",
                whiteSpace: "nowrap",
              }}
            >
              {domain.categories.length}{" "}
              {domain.categories.length === 1 ? "category" : "categories"} ·{" "}
              {domain.categories.reduce((s, c) => s + c.frameworks.length, 0)} frameworks
            </div>
          </div>

          {domain.categories.map((category) => (
            <div key={category.id} className="framework-category">
              <div className="framework-category-head">
                <div>
                  <h3 style={categoryTitleStyle}>{category.name}</h3>
                  {category.blurb && <p className="framework-category-blurb">{category.blurb}</p>}
                  {category.guideUrl && (
                    <a
                      href={category.guideUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="framework-guide-link"
                    >
                      {category.guideLabel ?? "Read guide"} →
                    </a>
                  )}
                </div>
                <div className="framework-category-meta">
                  {category.frameworks.length}{" "}
                  {category.frameworks.length === 1 ? "framework" : "frameworks"}
                </div>
              </div>

              <div className="framework-grid">
                {category.frameworks.map((framework) => (
                  <FrameworkCard key={framework.slug} framework={framework} />
                ))}
              </div>
            </div>
          ))}
        </section>
      ))}

      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11,
          color: "var(--ink-faint)",
          marginTop: 8,
        }}
      >
        {totalFrameworks} frameworks across {FRAMEWORK_DOMAINS.length}{" "}
        {FRAMEWORK_DOMAINS.length === 1 ? "domain" : "domains"}. More areas coming soon.
      </div>
    </div>
  );
};

export default FrameworksIndexView;
