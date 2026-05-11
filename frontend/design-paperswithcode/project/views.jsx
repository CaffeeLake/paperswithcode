// Screen views

const FeedView = ({ onOpenPaper, onClickTag, sortBy, setSortBy, period, setPeriod, upvotes, onUpvote }) => {
  const sorted = React.useMemo(() => {
    const arr = [...window.PAPERS];
    if (sortBy === 'trending') return arr.sort((a, b) => b.upvotes - a.upvotes);
    if (sortBy === 'new') return arr.sort((a, b) => b.id.localeCompare(a.id));
    if (sortBy === 'cited') return arr.sort((a, b) => b.citations - a.citations);
    return arr;
  }, [sortBy]);

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">Trending <em>Research</em></h1>
          <div className="feed-subtitle">Curated daily from arXiv and Hugging Face</div>
        </div>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
          <div className="period-switch">
            {['Today', 'This Week', 'This Month', 'All Time'].map(p => (
              <button
                key={p}
                className={`period-btn ${period === p ? 'active' : ''}`}
                onClick={() => setPeriod(p)}
              >{p}</button>
            ))}
          </div>
          <div className="date-nav">
            <button><Icon name="arrowLeft" size={11} /></button>
            <span>Apr 27, 2026</span>
            <button><Icon name="arrowRight" size={11} /></button>
          </div>
        </div>
      </div>

      <div className="layout-with-sidebar">
        <aside className="sidebar">
          <div className="sidebar-section">
            <div className="sidebar-label">Top Domains</div>
            {window.DOMAINS.slice(0, 8).map(d => (
              <a key={d.id} className="sidebar-link" onClick={() => onClickTag(d.id)}>
                {d.label}
                <span className="count">{d.count}</span>
              </a>
            ))}
            <a className="sidebar-link" style={{ marginTop: 8, fontStyle: 'italic' }} onClick={() => onClickTag(null, 'tags')}>
              all 18 domains →
            </a>
          </div>
          <div className="sidebar-section">
            <div className="sidebar-label">Filters</div>
            <a className="sidebar-link">Has code (open source)</a>
            <a className="sidebar-link">Reproduced results</a>
            <a className="sidebar-link">From institution</a>
          </div>
        </aside>

        <div>
          <div className="sort-bar">
            <div className="sort-options">
              {[['trending','trending'], ['new','newest'], ['cited','most cited']].map(([k, l]) => (
                <button
                  key={k}
                  className={`sort-btn ${sortBy === k ? 'active' : ''}`}
                  onClick={() => setSortBy(k)}
                >{l}</button>
              ))}
            </div>
            <div className="results-count">{sorted.length} papers</div>
          </div>
          <div className="paper-list">
            {sorted.map((p, i) => (
              <PaperCard
                key={p.id}
                paper={p}
                rank={i + 1}
                onOpenPaper={onOpenPaper}
                onClickTag={onClickTag}
                upvoted={!!upvotes[p.id]}
                onUpvote={onUpvote}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const Sparkline = ({ series, arrow }) => {
  const W = 520, H = 130, pad = 24;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = max - min || 1;
  const step = (W - pad * 2) / (series.length - 1);
  const points = series.map((v, i) => {
    const x = pad + i * step;
    // If lower-is-better (↓), still draw with same orientation (high y = low value visually)
    const y = pad + (H - pad * 2) * (1 - (v - min) / range);
    return [x, y];
  });
  const path = points.map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`)).join(' ');
  // Step line for SOTA-progression feel
  const stepPath = points.reduce((acc, p, i) => {
    if (i === 0) return `M${p[0]},${p[1]}`;
    const prev = points[i - 1];
    return `${acc} L${p[0]},${prev[1]} L${p[0]},${p[1]}`;
  }, '');
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
      {/* horizontal guideline */}
      <line x1={pad} y1={pad} x2={W - pad} y2={pad} stroke="var(--hairline)" strokeDasharray="2 3" />
      <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="var(--hairline)" strokeDasharray="2 3" />
      <text x={pad - 4} y={pad + 4} fontSize="9" fontFamily="var(--mono)" fill="var(--ink-faint)" textAnchor="end">{max}</text>
      <text x={pad - 4} y={H - pad + 4} fontSize="9" fontFamily="var(--mono)" fill="var(--ink-faint)" textAnchor="end">{min}</text>
      <path d={stepPath} stroke="var(--accent)" strokeWidth="1.5" fill="none" strokeLinejoin="miter" />
      {points.map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r={i === points.length - 1 ? 4 : 2.5} fill="var(--ink)" />
      ))}
    </svg>
  );
};

const TagBrowseView = ({ tagId, onOpenPaper, onClickTag, onClickMethod, onClickBench, sortBy, setSortBy, upvotes, onUpvote, onNavigate }) => {
  const domain = window.getDomain(tagId);
  const detail = window.getDomainDetail(tagId);
  const papers = React.useMemo(() => {
    let arr = window.getPapersByTag(tagId);
    if (sortBy === 'trending') return [...arr].sort((a, b) => b.upvotes - a.upvotes);
    if (sortBy === 'new') return [...arr].sort((a, b) => b.id.localeCompare(a.id));
    if (sortBy === 'cited') return [...arr].sort((a, b) => b.citations - a.citations);
    return arr;
  }, [tagId, sortBy]);

  if (!domain) return null;

  // Common methods used in this domain's papers
  const methodCounts = {};
  papers.forEach(p => (window.PAPER_METHODS[p.id] || []).forEach(m => {
    methodCounts[m] = (methodCounts[m] || 0) + 1;
  }));
  const commonMethods = Object.entries(methodCounts)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  const sisters = (detail?.sisters || []).map(([id, count]) => ({ ...window.getDomain(id), papers: count })).filter(d => d.id);
  const benchmarks = detail?.benchmarks || [];
  const explainer = detail?.explainer || `${domain.label.charAt(0).toUpperCase() + domain.label.slice(1)} is a research domain spanning ${domain.count.toLocaleString()} papers tracked by the community.`;
  const parent = detail?.parent || 'Research';

  return (
    <div className="page">
      <div className="breadcrumb">
        <a onClick={() => onNavigate('feed')}>Papers</a>
        <span className="sep">/</span>
        <a onClick={() => onNavigate('tags')}>Tasks</a>
        <span className="sep">/</span>
        <span style={{ color: 'var(--ink-soft)' }}>{parent.toUpperCase()}</span>
        <span className="sep">/</span>
        <span style={{ color: 'var(--accent-text)' }}>{domain.label.toUpperCase()}</span>
      </div>

      <div style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--accent-text)', letterSpacing: '0.1em', marginBottom: 8 }}>
        DOMAIN · {parent.toUpperCase()}
      </div>
      <h1 className="domain-mega-title">{domain.label}</h1>
      <p className="task-explainer">{explainer}</p>
      <div className="task-quickstats">
        <span><span className="num">{domain.count.toLocaleString()}</span>PAPERS</span>
        <span><span className="num">{benchmarks.length || 1}</span>BENCHMARKS</span>
        <span><span className="num">{commonMethods.length}+</span>METHODS USED</span>
      </div>

      <div className="task-page-grid" style={{ marginTop: 28 }}>
        <div>
          {benchmarks.length > 0 && (
            <>
              <div className="task-section-head">
                <div className="task-section-eyebrow">Leaderboards · click any</div>
                <div className="task-section-title">
                  Benchmarks <span className="meta">[{benchmarks.length}]</span>
                </div>
              </div>
              {benchmarks.map((b, i) => (
                <div key={i} className="bench-row" onClick={() => onClickBench && onClickBench(tagId, b.slug)}>
                  <div className="bench-row-num">{String(i + 1).padStart(2, '0')}</div>
                  <div className="bench-row-main">
                    <div className="bench-row-name">{b.name}</div>
                    <div className="bench-row-sub">
                      <span>METRIC <strong>{b.metric}</strong></span>
                      <span className="dot-sep">·</span>
                      <span>{b.arrow === '↓' ? 'LOWER BETTER' : 'HIGHER BETTER'}</span>
                      <span className="dot-sep">·</span>
                      <span>{(b.leaderboard || []).length} ENTRIES</span>
                    </div>
                  </div>
                  <div className="bench-row-sota">
                    <div className="bench-row-sota-value">{b.sota}</div>
                    <div className="bench-row-sota-tag">SOTA · {b.sotaModel}</div>
                  </div>
                  <div className="bench-row-arrow">→</div>
                </div>
              ))}
            </>
          )}

          <div className="task-section-head" style={{ marginTop: 36 }}>
            <div className="task-section-eyebrow">Top trending · sort below</div>
            <div className="task-section-title">
              Papers <span className="meta">[{papers.length}]</span>
            </div>
          </div>

          <div className="sort-bar">
            <div className="sort-options">
              {[['trending','trending'], ['new','newest'], ['cited','most cited']].map(([k, l]) => (
                <button
                  key={k}
                  className={`sort-btn ${sortBy === k ? 'active' : ''}`}
                  onClick={() => setSortBy(k)}
                >{l}</button>
              ))}
            </div>
            <div className="results-count">{papers.length} papers in <span style={{ textTransform: 'capitalize' }}>{domain.label}</span></div>
          </div>

          {papers.length === 0 ? (
            <div className="no-results">No recent papers in this domain.</div>
          ) : (
            <div className="paper-list">
              {papers.map((p, i) => (
                <PaperCard
                  key={p.id}
                  paper={p}
                  rank={i + 1}
                  onOpenPaper={onOpenPaper}
                  onClickTag={onClickTag}
                  upvoted={!!upvotes[p.id]}
                  onUpvote={onUpvote}
                />
              ))}
            </div>
          )}
        </div>

        <aside className="task-side">
          <div className="side-block">
            <div className="side-block-num">01/</div>
            <div className="side-block-label">Domain</div>
            <div className="side-domain-pill">{parent.toUpperCase()}</div>
          </div>

          {sisters.length > 0 && (
            <div className="side-block">
              <div className="side-block-num">02/</div>
              <div className="side-block-label">Sister Tasks</div>
              {sisters.map(s => (
                <div key={s.id} className="side-link-row" onClick={() => onClickTag(s.id)}>
                  <span>{s.label.replace(/(^|[\s-])(\w)/g, (_, sep, c) => sep + c.toUpperCase()).replace(/-/g, ' ')}</span>
                  <span className="count">{s.papers.toLocaleString()}</span>
                </div>
              ))}
            </div>
          )}

          {commonMethods.length > 0 && (
            <div className="side-block">
              <div className="side-block-num">03/</div>
              <div className="side-block-label">Common Methods</div>
              {commonMethods.map(([mid, count]) => (
                <div key={mid} className="side-method-row">
                  <MethodChip methodId={mid} onClick={onClickMethod} />
                  <span className="num">·{count}</span>
                </div>
              ))}
            </div>
          )}
        </aside>
      </div>
    </div>
  );
};

const TagsIndexView = ({ onClickTag }) => {
  const MODALITY_GROUPS = [
    {
      id: 'language',
      title: 'Language',
      blurb: 'Text understanding, generation, and reasoning.',
      domainIds: ['language-modeling', 'code-generation', 'agents', 'alignment', 'interpretability', 'evaluation'],
    },
    {
      id: 'vision',
      title: 'Computer Vision',
      blurb: 'Pixels, geometry, and visual perception.',
      domainIds: ['image-classification', 'object-detection', '3d-reconstruction', 'medical-imaging'],
    },
    {
      id: 'multimodal',
      title: 'Multimodal & Generative',
      blurb: 'Cross-modal models and generative media.',
      domainIds: ['multimodal', 'diffusion-models', 'video-generation'],
    },
    {
      id: 'audio',
      title: 'Audio',
      blurb: 'Speech, music, and acoustic signals.',
      domainIds: ['speech-recognition'],
    },
    {
      id: 'embodied',
      title: 'Embodied & Decision Making',
      blurb: 'Agents acting in physical or simulated environments.',
      domainIds: ['robotics', 'reinforcement-learning'],
    },
    {
      id: 'other',
      title: 'Other',
      blurb: 'Methods that span or sit outside the modality stack.',
      domainIds: ['graph-neural-networks', 'time-series'],
    },
  ];

  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">All <em>Domains</em></h1>
          <div className="feed-subtitle">Browse research by modality. Click any domain to see trending work.</div>
        </div>
      </div>
      {MODALITY_GROUPS.map(group => {
        const domains = group.domainIds
          .map(id => window.DOMAINS.find(d => d.id === id))
          .filter(Boolean);
        if (domains.length === 0) return null;
        const totalPapers = domains.reduce((s, d) => s + d.count, 0);
        return (
          <section key={group.id} style={{ marginBottom: 48 }}>
            <div style={{
              display: 'flex',
              alignItems: 'baseline',
              justifyContent: 'space-between',
              gap: 24,
              paddingBottom: 12,
              marginBottom: 0,
              borderBottom: '1px solid var(--hairline-strong)',
            }}>
              <div>
                <h2 style={{
                  fontFamily: 'var(--serif)',
                  fontSize: 26,
                  fontWeight: 500,
                  letterSpacing: '-0.02em',
                  marginBottom: 4,
                }}>{group.title}</h2>
                <div style={{
                  fontFamily: 'var(--serif)',
                  fontStyle: 'italic',
                  fontSize: 13,
                  color: 'var(--ink-soft)',
                }}>{group.blurb}</div>
              </div>
              <div style={{
                fontFamily: 'var(--mono)',
                fontSize: 11,
                color: 'var(--ink-faint)',
                whiteSpace: 'nowrap',
              }}>
                {domains.length} {domains.length === 1 ? 'domain' : 'domains'} · {totalPapers.toLocaleString()} papers
              </div>
            </div>
            <div className="tag-grid">
              {domains.map(d => {
                const dot = `oklch(0.55 0.12 ${d.hue})`;
                return (
                  <div key={d.id} className="tag-cell" onClick={() => onClickTag(d.id)}>
                    <div className="name">
                      <span className="dot" style={{ background: dot }}></span>
                      {d.label}
                    </div>
                    <div className="meta">
                      <span>{d.count.toLocaleString()} papers</span>
                      <span>·</span>
                      <span>{Math.floor(d.count / 28)} this week</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
};

const PaperDetailView = ({ paperId, onOpenPaper, onClickTag, onClickMethod, onClickBench, onNavigate, upvotes, onUpvote }) => {
  const paper = window.getPaperOrSource ? window.getPaperOrSource(paperId) : window.PAPERS.find(p => p.id === paperId);
  if (!paper) return <div className="page">Paper not found.</div>;
  const upvoted = !!upvotes[paperId];
  const [abstractExpanded, setAbstractExpanded] = React.useState(false);

  const methodIds = window.PAPER_METHODS[paper.id] || [];
  const results = window.PAPER_RESULTS[paper.id] || [];
  const related = window.PAPERS
    .filter(p => p.id !== paperId && p.tags.some(t => paper.tags.includes(t)))
    .slice(0, 4);

  // Find any methods this paper introduced (i.e. it's the source paper)
  const introducedMethods = window.METHODS.filter(m => m.source && m.source.arxivId === paper.id);
  const isHistorical = !!window.SOURCE_PAPERS && !!window.SOURCE_PAPERS[paper.id];

  const tldr = paper.tldr || `${paper.title.split(':')[0]} — a ${(paper.tags || []).map(t => window.getDomain(t)?.label).filter(Boolean).join(' / ')} approach that improves over prior baselines while staying reproducible from the released code.`;
  const abstractShort = paper.abstract.slice(0, 240) + '…';
  const submittedDate = paper.date ? `Submitted ${paper.date}${paper.year && !/\d{4}/.test(paper.date) ? `, ${paper.year}` : ''}` : `Submitted ${paper.year}`;

  return (
    <div className="page">
      <div className="breadcrumb">
        <a onClick={() => onNavigate('feed')}>Trending</a>
        <span className="sep">/</span>
        <span>arXiv:{paper.id}</span>
      </div>

      <div className="detail-grid">
        <div>
          <h1 className="detail-title">{paper.title}</h1>
          <div className="detail-meta">
            <span>arXiv:{paper.id}</span>
            <span>·</span>
            <span>{submittedDate}</span>
            {paper.pdfPages && <><span>·</span><span>{paper.pdfPages} pages</span></>}
            {typeof paper.citations === 'number' && <><span>·</span><span>{paper.citations.toLocaleString()} citations</span></>}
            {paper.venue && <><span>·</span><span>{paper.venue}</span></>}
          </div>
          <div className="detail-authors">
            {paper.authors.map((a, i) => (
              <React.Fragment key={i}>
                <a>{a}</a>{i < paper.authors.length - 1 ? ', ' : ''}
              </React.Fragment>
            ))}
          </div>
          <div className="detail-institution">{paper.institution}</div>

          <div className="action-row">
            <button className="action-btn"><Icon name="pdf" size={12} /> View PDF</button>
            <button className="action-btn"><Icon name="external" size={12} /> arXiv page</button>
            {paper.github && <button className="action-btn"><Icon name="github" size={12} /> Code · {(paper.github / 1000).toFixed(1)}k ★</button>}
            {paper.project && <button className="action-btn"><Icon name="globe" size={12} /> Project page</button>}
            <button className="action-btn"><Icon name="bookmark" size={12} /> Save</button>
          </div>

          {introducedMethods.length > 0 && (
            <div className="introduced-banner">
              <span className="introduced-label">Introduced</span>
              <div className="introduced-methods">
                {introducedMethods.map(m => (
                  <button key={m.id} className="introduced-pill" onClick={() => onClickMethod(m.id)}>
                    {m.label}
                    <span className="introduced-arrow">→</span>
                  </button>
                ))}
              </div>
              <span className="introduced-note">This paper is the canonical source for {introducedMethods.length === 1 ? 'this method' : 'these methods'}.</span>
            </div>
          )}

          <div className="section-rule">
            <span>TL;DR · AI-generated</span>
          </div>
          <div className="tldr-box">
            {tldr}
          </div>

          <div className="section-rule">
            <span>Abstract</span>
          </div>
          <p className="abstract-text" style={{ marginBottom: 8 }}>
            {abstractExpanded ? paper.abstract : abstractShort}
          </p>
          <div className="read-full" onClick={() => setAbstractExpanded(v => !v)}>
            {abstractExpanded ? '− collapse abstract' : '+ read full abstract'}
          </div>

          <div className="section-rule">
            <span>Tasks</span>
            <span className="accent">{paper.tags.length} tagged</span>
          </div>
          <div className="paper-tags" style={{ marginBottom: 8 }}>
            {paper.tags.map(t => <TagChip key={t} tagId={t} onClick={onClickTag} />)}
          </div>

          <div className="section-rule">
            <span>Methods</span>
            <span className="accent">{methodIds.length} used</span>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
            {methodIds.map(m => <MethodChip key={m} methodId={m} onClick={onClickMethod} />)}
          </div>

          {results.length > 0 && (
            <>
              <div className="section-rule">
                <span>Results</span>
                <span className="accent">{results.length} benchmarks</span>
              </div>
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
                  {results.map((r, i) => {
                    const slug = window.benchSlug(r.benchmark);
                    const hasBench = !!window.getBenchmark(r.task, slug);
                    return (
                    <tr key={i}>
                      <td><span className="task-link" style={{ textTransform: 'capitalize' }} onClick={() => onClickTag(r.task)}>{window.getDomain(r.task)?.label || r.task}</span></td>
                      <td className="benchmark">{r.benchmark}</td>
                      <td className="metric">{r.metric}</td>
                      <td className="value">{r.value}</td>
                      <td className={`compare ${hasBench ? '' : 'disabled'}`}
                          onClick={() => hasBench && onClickBench && onClickBench(r.task, slug, paper.id)}
                          title={hasBench ? `Compare on ${r.benchmark} leaderboard` : 'No leaderboard available'}>
                        Compare →
                      </td>
                    </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </div>

        <aside className="detail-sidebar">
          <div className="sidebar-card">
            <div className="sidebar-card-title">
              GitHub
              <span className="badge">2 repos</span>
            </div>
            <div className="code-line">
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 9, fontWeight: 600, padding: '1px 4px', background: 'var(--bg-subtle)', borderRadius: 2 }}>GH</span>
                {paper.submitter}/{paper.id.split('.')[1]}-code
              </span>
              <span className="copy">copy</span>
            </div>
            <div className="code-line">
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 9, fontWeight: 600, padding: '1px 4px', background: 'var(--bg-subtle)', borderRadius: 2 }}>GH</span>
                community/repro-{paper.id.split('.')[1]}
              </span>
              <span className="copy">copy</span>
            </div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 10, color: 'var(--accent-text)', marginTop: 6 }}>✓ Official</div>
          </div>

          <div className="sidebar-card">
            <div className="sidebar-card-title">
              <span>🤗 Hugging Face</span>
            </div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-faint)', marginTop: 4, marginBottom: 6 }}>Models</div>
            <div className="code-line">
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 9, fontWeight: 600, padding: '1px 4px', background: 'var(--bg-subtle)', borderRadius: 2 }}>M</span>
                {paper.submitter}/model-7b
              </span>
              <span className="copy">copy</span>
            </div>
            <div className="code-line">
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 9, fontWeight: 600, padding: '1px 4px', background: 'var(--bg-subtle)', borderRadius: 2 }}>M</span>
                {paper.submitter}/model-14b
              </span>
              <span className="copy">copy</span>
            </div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-faint)', marginTop: 10, marginBottom: 6 }}>Datasets</div>
            <div className="code-line">
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 9, fontWeight: 600, padding: '1px 4px', background: 'var(--bg-subtle)', borderRadius: 2 }}>D</span>
                {paper.submitter}/curated
              </span>
              <span className="copy">copy</span>
            </div>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--ink-faint)', marginTop: 10, marginBottom: 6 }}>Spaces</div>
            <div className="code-line">
              <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ fontFamily: 'var(--mono)', fontSize: 9, fontWeight: 600, padding: '1px 4px', background: 'var(--bg-subtle)', borderRadius: 2 }}>S</span>
                {paper.submitter}/demo
              </span>
              <span className="copy">copy</span>
            </div>
          </div>

          <div className="sidebar-card">
            <div className="sidebar-card-title">Citation</div>
            <pre style={{ fontFamily: 'var(--mono)', fontSize: 10.5, lineHeight: 1.5, color: 'var(--ink-soft)', whiteSpace: 'pre-wrap', wordBreak: 'break-word', margin: 0 }}>
{`@article{p${paper.id.split('.')[1]},
  title={{${paper.title.slice(0, 40)}…}},
  author={{${paper.authors[0]} et al.}},
  year={{2026}}
}`}
            </pre>
          </div>

          <div className="sidebar-card">
            <div className="sidebar-card-title">Related papers</div>
            {related.map(p => (
              <div key={p.id} className="related-paper" onClick={() => onOpenPaper(p.id)}>
                <div className="related-title">{p.title}</div>
                <div className="related-meta">
                  <span>arXiv:{p.id}</span>
                  <span>↑ {p.upvotes}</span>
                </div>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </div>
  );
};

const SearchOverlay = ({ query, setQuery, onClose, onOpenPaper, onClickTag }) => {
  const inputRef = React.useRef(null);
  React.useEffect(() => {
    inputRef.current?.focus();
    const onKey = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const q = query.toLowerCase().trim();
  const matchedPapers = q ? window.PAPERS.filter(p =>
    p.title.toLowerCase().includes(q) ||
    p.abstract.toLowerCase().includes(q) ||
    p.authors.some(a => a.toLowerCase().includes(q)) ||
    p.institution.toLowerCase().includes(q)
  ).slice(0, 6) : [];
  const matchedTags = q ? window.DOMAINS.filter(d => d.label.toLowerCase().includes(q)).slice(0, 6) : [];

  return (
    <div className="search-overlay" onClick={onClose}>
      <div className="search-modal" onClick={e => e.stopPropagation()}>
        <input
          ref={inputRef}
          className="search-modal-input"
          placeholder="Search papers, authors, institutions, or domains…"
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <div className="search-results">
          {!q && (
            <div className="search-empty">
              Try “diffusion”, “Stanford”, “robotics”, or an arXiv id.
            </div>
          )}
          {q && matchedTags.length === 0 && matchedPapers.length === 0 && (
            <div className="search-empty">No matches for "{query}"</div>
          )}
          {matchedTags.length > 0 && (
            <>
              <div className="search-section-label">Domains · {matchedTags.length}</div>
              {matchedTags.map(d => (
                <div key={d.id} className="search-result-tag" onClick={() => { onClickTag(d.id); onClose(); }}>
                  <span className="dot" style={{ width: 6, height: 6, borderRadius: '50%', background: `oklch(0.55 0.12 ${d.hue})` }}></span>
                  <span className="name">{d.label}</span>
                  <span className="count">{d.count} papers</span>
                </div>
              ))}
            </>
          )}
          {matchedPapers.length > 0 && (
            <>
              <div className="search-section-label">Papers · {matchedPapers.length}</div>
              {matchedPapers.map(p => (
                <div key={p.id} className="search-result" onClick={() => { onOpenPaper(p.id); onClose(); }}>
                  <div className="search-result-title">{p.title}</div>
                  <div className="search-result-meta">
                    <span>arXiv:{p.id}</span>
                    <span>·</span>
                    <span>{p.institution}</span>
                    <span>·</span>
                    <span>↑ {p.upvotes}</span>
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const MethodsIndexView = ({ onClickMethod }) => {
  return (
    <div className="page">
      <div className="feed-header">
        <div>
          <h1 className="feed-title">Methods <em>library</em></h1>
          <div className="feed-subtitle">Common techniques used across AI research, with the papers that use them.</div>
        </div>
      </div>
      {window.METHOD_CATEGORIES.map(cat => {
        const methods = window.METHODS.filter(m => m.category === cat.id);
        if (methods.length === 0) return null;
        const totalPapers = methods.reduce((s, m) => s + m.count, 0);
        return (
          <section key={cat.id} style={{ marginBottom: 48 }}>
            <div style={{
              display: 'flex',
              alignItems: 'baseline',
              justifyContent: 'space-between',
              gap: 24,
              paddingBottom: 12,
              borderBottom: '1px solid var(--hairline-strong)',
            }}>
              <div>
                <h2 style={{
                  fontFamily: 'var(--serif)',
                  fontSize: 26,
                  fontWeight: 500,
                  letterSpacing: '-0.02em',
                  marginBottom: 4,
                }}>{cat.label}</h2>
                <div style={{
                  fontFamily: 'var(--serif)',
                  fontStyle: 'italic',
                  fontSize: 13,
                  color: 'var(--ink-soft)',
                }}>{cat.blurb}</div>
              </div>
              <div style={{
                fontFamily: 'var(--mono)',
                fontSize: 11,
                color: 'var(--ink-faint)',
                whiteSpace: 'nowrap',
              }}>
                {methods.length} methods · {totalPapers.toLocaleString()} papers
              </div>
            </div>
            <div className="tag-grid">
              {methods.map(m => (
                <div key={m.id} className="tag-cell" onClick={() => onClickMethod(m.id)}>
                  <div className="name" style={{ fontFamily: 'var(--mono)', fontSize: 15 }}>
                    {m.label}
                  </div>
                  <div className="meta">
                    <span>{m.count.toLocaleString()} papers</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
};

const MethodDetailView = ({ methodId, onOpenPaper, onClickTag, onClickMethod, onNavigate, sortBy, setSortBy, upvotes, onUpvote }) => {
  const m = window.getMethod(methodId);
  if (!m) return null;
  const cat = window.getMethodCategory(m.category);
  const papers = React.useMemo(() => {
    const arr = window.getPapersByMethod(methodId);
    if (sortBy === 'trending') return [...arr].sort((a, b) => b.upvotes - a.upvotes);
    if (sortBy === 'new') return [...arr].sort((a, b) => b.id.localeCompare(a.id));
    if (sortBy === 'cited') return [...arr].sort((a, b) => b.citations - a.citations);
    return arr;
  }, [methodId, sortBy]);

  const relatedMethods = window.METHODS.filter(x => x.category === m.category && x.id !== m.id).slice(0, 6);

  return (
    <div className="page">
      <div className="breadcrumb">
        <a onClick={() => onNavigate('methods')}>Methods</a>
        <span className="sep">/</span>
        <span style={{ color: 'var(--ink-soft)' }}>{cat?.label}</span>
        <span className="sep">/</span>
        <span style={{ color: 'var(--ink)' }}>{m.label}</span>
      </div>

      <div className="tag-hero method-hero-grid">
        <div>
          <div className="tag-hero-eyebrow">METHOD · {cat?.label.toUpperCase()}</div>
          <h1 className="tag-hero-title" style={{ fontFamily: 'var(--mono)', fontSize: 48, letterSpacing: '-0.01em' }}>{m.label}</h1>
          <p style={{ fontFamily: 'var(--serif)', fontSize: 17, color: 'var(--ink-soft)', maxWidth: 720, lineHeight: 1.55, marginTop: 16, textWrap: 'pretty' }}>
            {m.blurb}
          </p>
          {m.source && (
            <div className="method-source">
              <span className="method-source-label">Source</span>
              {m.source.arxivId ? (
                <a className="method-source-link" onClick={() => onOpenPaper(m.source.arxivId)}>
                  <span className="method-source-title">{m.source.title}</span>
                  <span className="method-source-meta">{m.source.authors} · {m.year} · arXiv:{m.source.arxivId}</span>
                </a>
              ) : (
                <span className="method-source-link is-static">
                  <span className="method-source-title">{m.source.title}</span>
                  <span className="method-source-meta">{m.source.authors} · {m.year}</span>
                </span>
              )}
            </div>
          )}
          <div className="tag-hero-meta">
            <div className="stat">
              <span className="label">Papers using</span>
              <span className="value">{m.count.toLocaleString()}</span>
            </div>
            <div className="stat">
              <span className="label">Introduced</span>
              <span className="value">{m.year}</span>
            </div>
            <div className="stat">
              <span className="label">Category</span>
              <span className="value" style={{ fontSize: 18 }}>{cat?.label}</span>
            </div>
          </div>
        </div>
        <figure className="method-figure-card">
          <div className="method-figure-svg">
            <MethodFigure method={m} />
          </div>
          <figcaption>
            Figure · schematic of {m.label}
            {m.source && <><br/><span style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--ink-faint)' }}>after {m.source.authors.split(' ')[0].replace(',','')}{m.source.authors.includes('et al') ? '' : ' et al.'}, {m.year}</span></>}
          </figcaption>
        </figure>
      </div>

      {relatedMethods.length > 0 && (
        <div className="filter-row">
          <span className="label">Related methods</span>
          {relatedMethods.map(rm => <MethodChip key={rm.id} methodId={rm.id} onClick={onClickMethod} />)}
        </div>
      )}

      <div className="sort-bar">
        <div className="sort-options">
          {[['trending','trending'], ['new','newest'], ['cited','most cited']].map(([k, l]) => (
            <button
              key={k}
              className={`sort-btn ${sortBy === k ? 'active' : ''}`}
              onClick={() => setSortBy(k)}
            >{l}</button>
          ))}
        </div>
        <div className="results-count">{papers.length} papers using {m.label}</div>
      </div>

      {papers.length === 0 ? (
        <div className="no-results">No papers tagged with this method yet.</div>
      ) : (
        <div className="paper-list">
          {papers.map((p, i) => (
            <PaperCard
              key={p.id}
              paper={p}
              rank={i + 1}
              onOpenPaper={onOpenPaper}
              onClickTag={onClickTag}
              upvoted={!!upvotes[p.id]}
              onUpvote={onUpvote}
            />
          ))}
        </div>
      )}
    </div>
  );
};

const BenchmarkChart = ({ series, dates, metric, arrow }) => {
  const W = 880, H = 320;
  const padL = 60, padR = 30, padT = 24, padB = 50;
  const min = Math.min(...series);
  const max = Math.max(...series);
  const range = max - min || 1;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;
  const step = innerW / (series.length - 1);
  const points = series.map((v, i) => {
    const x = padL + i * step;
    // for ↓ (lower-better), invert so progress goes upward visually
    const norm = arrow === '↓' ? (max - v) / range : (v - min) / range;
    const y = padT + innerH * (1 - norm);
    return [x, y, v];
  });
  // smooth curve via simple bezier approximation
  let path = `M${points[0][0]},${points[0][1]}`;
  for (let i = 1; i < points.length; i++) {
    const [x0, y0] = points[i - 1];
    const [x1, y1] = points[i];
    const cx = (x0 + x1) / 2;
    path += ` C${cx},${y0} ${cx},${y1} ${x1},${y1}`;
  }
  // y-axis ticks (5 evenly spaced including endpoints)
  const tickCount = 5;
  const ticks = Array.from({ length: tickCount }, (_, i) => {
    const v = arrow === '↓'
      ? min + (range * i) / (tickCount - 1)         // lower-better: small values at top? no — invert below
      : min + (range * i) / (tickCount - 1);
    return v;
  });
  const fmt = (v) => {
    if (Math.abs(v) >= 100) return v.toFixed(0);
    if (Math.abs(v) >= 10) return v.toFixed(1);
    if (Math.abs(v) >= 1) return v.toFixed(2);
    return v.toFixed(3);
  };
  return (
    <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block' }}>
      {/* Y-axis label */}
      <text
        x={padL - 38}
        y={padT + innerH / 2}
        fontSize="11"
        fontFamily="var(--mono)"
        fill="var(--ink-faint)"
        textAnchor="middle"
        transform={`rotate(-90 ${padL - 38} ${padT + innerH / 2})`}
      >{metric}</text>
      {/* horizontal gridlines + y ticks */}
      {ticks.map((t, i) => {
        const norm = i / (tickCount - 1); // 0 at bottom, 1 at top
        const y = padT + innerH * (1 - norm);
        // Map to actual data value at that y position
        const dataAtNorm = arrow === '↓'
          ? max - range * norm  // top shows lower (better) values
          : min + range * norm;
        return (
          <g key={i}>
            <line x1={padL} y1={y} x2={W - padR} y2={y} stroke="var(--hairline)" strokeWidth="1" />
            <text x={padL - 10} y={y + 4} fontSize="11" fontFamily="var(--mono)" fill="var(--ink-faint)" textAnchor="end">
              {fmt(dataAtNorm)}
            </text>
          </g>
        );
      })}
      {/* x-axis dates */}
      {points.map((p, i) => (
        <text key={i} x={p[0]} y={H - padB + 18} fontSize="11" fontFamily="var(--mono)" fill="var(--ink-soft)" textAnchor="middle">
          {dates && dates[i] ? dates[i] : ''}
        </text>
      ))}
      {/* line */}
      <path d={path} stroke="var(--accent)" strokeWidth="2" fill="none" strokeLinejoin="round" strokeLinecap="round" />
      {/* points */}
      {points.map((p, i) => (
        <g key={i}>
          <circle cx={p[0]} cy={p[1]} r="4.5" fill="var(--bg-elevated)" stroke="var(--accent)" strokeWidth="2" />
        </g>
      ))}
    </svg>
  );
};

const BenchmarkDetailView = ({ tagId, benchSlug, highlightPaperId, onNavigate, onClickTag, onOpenPaper }) => {
  const domain = window.getDomain(tagId);
  const detail = window.getDomainDetail(tagId);
  const bench = window.getBenchmark(tagId, benchSlug);
  const [sortKey, setSortKey] = React.useState('value');
  const [order, setOrder] = React.useState('rank');
  const [filter, setFilter] = React.useState('all');

  if (!bench) {
    return <div className="page"><div className="no-results">Benchmark not found.</div></div>;
  }

  const rows = bench.leaderboard || [];
  const sorted = React.useMemo(() => {
    const arr = [...rows];
    if (sortKey === 'value') {
      arr.sort((a, b) => {
        const av = parseFloat(a.value), bv = parseFloat(b.value);
        return bench.arrow === '↓' ? av - bv : bv - av;
      });
    } else if (sortKey === 'year') {
      arr.sort((a, b) => b.year - a.year);
    } else if (sortKey === 'model') {
      arr.sort((a, b) => a.model.localeCompare(b.model));
    }
    if (order === 'reverse') arr.reverse();
    return arr;
  }, [rows, sortKey, order, bench.arrow]);

  const bestVal = bench.sota;
  const bestModel = bench.sotaModel;

  const highlightPaper = highlightPaperId ? (window.getPaperOrSource ? window.getPaperOrSource(highlightPaperId) : window.PAPERS.find(p => p.id === highlightPaperId)) : null;
  // Determine which leaderboard values were reported by this paper for this benchmark
  const highlightValues = React.useMemo(() => {
    if (!highlightPaperId || !bench) return new Set();
    const results = (window.PAPER_RESULTS && window.PAPER_RESULTS[highlightPaperId]) || [];
    return new Set(results.filter(r => r.benchmark === bench.name).map(r => String(r.value)));
  }, [highlightPaperId, bench]);
  const isRowHighlighted = React.useCallback((row) => {
    if (!highlightPaperId) return false;
    if (row.paperId === highlightPaperId) return true;
    if (highlightValues.has(String(row.value))) return true;
    return false;
  }, [highlightPaperId, highlightValues]);
  const highlightRowsRef = React.useRef(null);
  React.useEffect(() => {
    if (highlightPaperId && highlightRowsRef.current) {
      // Soft scroll to the leaderboard card so the highlighted rows are visible
      const card = highlightRowsRef.current.closest('.bm-card');
      if (card) {
        const top = card.getBoundingClientRect().top + window.scrollY - 80;
        window.scrollTo({ top, behavior: 'smooth' });
      }
    }
  }, [highlightPaperId]);

  return (
    <div className="page">
      <div className="bm-page">
        <div className="breadcrumb">
          <a onClick={() => onNavigate('tags')}>Tasks</a>
          <span className="sep">/</span>
          <a onClick={() => onClickTag(tagId)} style={{ textTransform: 'capitalize' }}>{domain.label}</a>
          <span className="sep">/</span>
          <span style={{ color: 'var(--accent-text)' }}>{bench.name}</span>
        </div>

        <h1 className="bm-title">{bench.name}</h1>
        <div className="bm-subtitle">
          <span className="metric-tag">{bench.metric}</span>
          <span style={{ color: 'var(--hairline-strong)', margin: '0 8px' }}>·</span>
          <span>Best: <span className="best-name">{bestVal}</span> by <span className="best-name" style={{ fontStyle: 'normal' }}>{bestModel}</span></span>
        </div>

        {highlightPaper && (
          <div className="bm-highlight-banner">
            <div className="bm-highlight-dot"></div>
            <div className="bm-highlight-text">
              <span className="bm-highlight-label">Comparing</span>
              <span className="bm-highlight-paper">{highlightPaper.title}</span>
              <span className="bm-highlight-meta">
                Models from this paper are highlighted on the leaderboard below.
              </span>
            </div>
          </div>
        )}

        <div className="bm-actions">
          <button className="bm-action-btn" onClick={(e) => e.preventDefault()}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            Link to paper
          </button>
          <button className="bm-action-btn" onClick={(e) => e.preventDefault()}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
              <polyline points="15 3 21 3 21 9" />
              <line x1="10" y1="14" x2="21" y2="3" />
            </svg>
            View on Hugging Face
          </button>
        </div>

        {/* Leaderboard chart card */}
        <div className="bm-card">
          <div className="bm-card-head">
            <div className="bm-card-title">Leaderboard</div>
          </div>
          <div className="bm-controls">
            <span><span className="label">Sort by</span>
              <span className="bm-select">{bench.metric} <span className="caret">▾</span></span>
            </span>
            <span><span className="label">Order</span>
              <span className="bm-select">Rank <span className="caret">▾</span></span>
            </span>
            <span><span className="label">Filter</span>
              <span className="bm-select">All models <span className="caret">▾</span></span>
            </span>
          </div>
          <div className="bm-chart-wrap">
            <BenchmarkChart
              series={bench.series}
              dates={bench.seriesDates}
              metric={bench.metric}
              arrow={bench.arrow}
            />
          </div>
          <div className="bm-chart-foot">
            <span className="legend-dot"></span>
            Best result per paper
          </div>
        </div>

        {/* Leaderboard table */}
        <div className="bm-card">
          <div className="bm-card-head">
            <div className="bm-card-title">Leaderboard</div>
          </div>
          <table className="bm-table">
            <thead>
              <tr>
                <th className="col-rank">Rank</th>
                <th className="col-model">Model</th>
                <th className="col-value">{bench.metric} {bench.arrow}</th>
                <th className="col-paper">Paper</th>
                <th className="col-code">Code</th>
                <th className="col-year">Year</th>
              </tr>
            </thead>
            <tbody ref={highlightRowsRef}>
              {sorted.map((row, i) => {
                const isHighlighted = isRowHighlighted(row);
                return (
                <tr key={i} className={isHighlighted ? 'is-highlighted' : ''}>
                  <td className="col-rank">{i + 1}</td>
                  <td className="col-model">
                    {isHighlighted && <span className="bm-row-marker" aria-label="From this paper"></span>}
                    {row.model}
                  </td>
                  <td className={`col-value ${i === 0 ? 'is-best' : ''}`}>{row.value}</td>
                  <td className="col-paper">
                    <a onClick={() => {
                      const id = window.resolveLeaderboardPaper(row, bench, tagId);
                      if (id) onOpenPaper(id);
                    }}>{row.paper}</a>
                  </td>
                  <td className="col-code">
                    <span className={`code-link ${row.code ? '' : 'disabled'}`} title={row.code ? 'View on GitHub' : 'No code released'}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.56 0-.27-.01-1-.02-1.97-3.2.7-3.87-1.54-3.87-1.54-.52-1.32-1.27-1.67-1.27-1.67-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.02 1.75 2.69 1.25 3.34.95.1-.74.4-1.25.73-1.54-2.55-.29-5.24-1.28-5.24-5.69 0-1.26.45-2.29 1.18-3.1-.12-.29-.51-1.46.11-3.04 0 0 .96-.31 3.15 1.18.91-.25 1.89-.38 2.86-.39.97.01 1.95.13 2.86.39 2.18-1.49 3.14-1.18 3.14-1.18.62 1.58.23 2.75.11 3.04.74.81 1.18 1.84 1.18 3.1 0 4.42-2.69 5.4-5.25 5.68.41.36.78 1.06.78 2.14 0 1.55-.01 2.8-.01 3.18 0 .31.21.68.8.56C20.21 21.39 23.5 17.08 23.5 12 23.5 5.65 18.35.5 12 .5z" />
                      </svg>
                    </span>
                  </td>
                  <td className="col-year">{row.year}</td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

Object.assign(window, { FeedView, TagBrowseView, TagsIndexView, PaperDetailView, SearchOverlay, MethodsIndexView, MethodDetailView, BenchmarkDetailView });
