-- Hyper-Connections (HC) — learned multi-stream alternatives to residual connections.
-- Source: arXiv 2409.19606 (ICLR 2025).

INSERT INTO methods (
    slug,
    name,
    full_name,
    description,
    keywords,
    area_id,
    introduced_year,
    source_paper_id,
    source_url,
    source_title,
    code_snippet_url,
    image_url,
    image_credit
)
VALUES (
    'hyper-connections',
    'Hyper-Connections',
    'Hyper-Connections (HC)',
    'Hyper-Connections replace a single [residual connection](/methods/residual-block) with multiple parallel residual streams and learn both depth-wise connection strengths and width-wise mixing between streams. Static Hyper-Connections learn fixed connection weights, while Dynamic Hyper-Connections predict input-dependent weights, allowing a network to regulate information flow across depth and rearrange how layers interact while mitigating gradient vanishing and representation collapse.',
    -- Avoid the standalone HC, SHC, DHC, and mHC abbreviations: they are
    -- highly ambiguous in paper text and produce unrelated catalog matches.
    'Hyper-Connections, Hyper Connections, HyperConnections, hyper-connection, dynamic hyper-connections, static hyper-connections, manifold-constrained hyper-connections',
    (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
    2024,
    (
        SELECT id FROM papers
        WHERE arxiv_id = '2409.19606'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Hyper-Connections',
    NULL,
    NULL,
    '[Hyper-Connections](/paper/2409.19606)'
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

-- The introducing paper drives the native source link and the Introduced banner.
INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'hyper-connections' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT source_paper_id, id, 'source' FROM methods
WHERE slug = 'hyper-connections' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();

-- Curated 2026-08-17 from all 80 Semantic Scholar citations plus a catalog-wide
-- exact-phrase search. Each paper below explicitly develops, analyzes, trains,
-- or incorporates Hyper-Connections or an HC-family extension. Citation-only
-- papers and adjacent residual-routing methods are intentionally excluded.
WITH curated_papers AS (
    SELECT p.id AS paper_id, m.id AS method_id
    FROM papers p
    CROSS JOIN methods m
    WHERE m.slug = 'hyper-connections'
      AND p.is_latest_version
      AND p.arxiv_id IN (
          '2503.14125', -- Frac-Connections
          '2512.24880', -- Manifold-Constrained Hyper-Connections
          '2601.01014', -- Manifold-Geometric Transformer
          '2601.05732', -- mHC-lite
          '2601.15757', -- ES-mHC
          '2601.21579', -- KromHC
          '2601.23039', -- EPH-ASC applied to mHC training
          '2602.18308', -- JPmHC
          '2603.14833', -- causal analysis of mHC streams
          '2603.20896', -- Spectral-Sphere-Constrained Hyper-Connections
          '2604.19550', -- LoopCTR with Hyper-Connected Residuals
          '2604.21106', -- looped-LM hyperconnection experiments
          '2604.21254', -- Hyperloop Transformers
          '2605.17842', -- HC Newton for mHC-style architectures
          '2606.19348', -- DeepSeek-V4 incorporates mHC
          '2607.14530', -- Expanded Hyper-Connections
          '2608.09119'  -- Motif 3 incorporates modified mHC
      )
)
INSERT INTO paper_methods (paper_id, method_id)
SELECT paper_id, method_id FROM curated_papers
ON CONFLICT (paper_id, method_id) DO NOTHING;

WITH curated_papers AS (
    SELECT p.id AS paper_id, m.id AS method_id
    FROM papers p
    CROSS JOIN methods m
    WHERE m.slug = 'hyper-connections'
      AND p.is_latest_version
      AND p.arxiv_id IN (
          '2503.14125',
          '2512.24880',
          '2601.01014',
          '2601.05732',
          '2601.15757',
          '2601.21579',
          '2601.23039',
          '2602.18308',
          '2603.14833',
          '2603.20896',
          '2604.19550',
          '2604.21106',
          '2604.21254',
          '2605.17842',
          '2606.19348',
          '2607.14530',
          '2608.09119'
      )
)
INSERT INTO paper_method_evidence (paper_id, method_id, evidence_type)
SELECT paper_id, method_id, 'manual' FROM curated_papers
ON CONFLICT (paper_id, method_id, evidence_type) DO UPDATE SET
    last_seen_at = now();
