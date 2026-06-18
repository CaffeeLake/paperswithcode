-- SLAM (Simultaneous Localization and Mapping) — canonical robotics/vision technique.
-- Source paper: arXiv 1606.05830 (Cadena et al., IEEE TRO 2016 survey).

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
    'slam',
    'SLAM',
    'Simultaneous Localization and Mapping (SLAM)',
    'SLAM jointly estimates a robot or camera trajectory and a map of the environment from streaming sensor observations. Classic pipelines combine front-end feature tracking or depth sensing with back-end pose-graph or bundle adjustment; modern variants include visual SLAM, RGB-D SLAM, LiDAR SLAM, and [Gaussian Splatting](/methods/gaussian-splatting) SLAM that fuse feed-forward [Transformer](/methods/transformer) priors with online mapping. SLAM underpins autonomous navigation, AR, and streaming 3D reconstruction systems such as [VGGT](/methods/vggt)-style geometry models used in online settings.',
    'SLAM, slam, simultaneous localization and mapping, visual SLAM, RGB-D SLAM, LiDAR SLAM, monocular SLAM, Gaussian Splatting SLAM',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    2016,
    (
        SELECT id FROM papers
        WHERE arxiv_id = '1606.05830'
        ORDER BY is_latest_version DESC, id DESC
        LIMIT 1
    ),
    NULL,
    'Past, Present, and Future of Simultaneous Localization And Mapping: Towards the Robust-Perception Age',
    NULL,
    NULL,
    '[Past, Present, and Future of Simultaneous Localization And Mapping](/paper/1606.05830)'
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

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id FROM methods
WHERE slug = 'slam' AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

-- Tag Geometric Context Transformer paper (2604.14141) with SLAM.
INSERT INTO paper_methods (paper_id, method_id)
SELECT p.id, m.id
FROM papers p
JOIN methods m ON m.slug = 'slam'
WHERE p.arxiv_id = '2604.14141'
ON CONFLICT (paper_id, method_id) DO NOTHING;
