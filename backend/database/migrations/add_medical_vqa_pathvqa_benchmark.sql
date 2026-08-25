-- Restore the legacy Medical Visual Question Answering task and PathVQA benchmark.
--
-- PathVQA has two established evaluation protocols: classification-style
-- accuracy split into open/closed question types, and generation-style text
-- metrics on open-ended answers. Keep the metric labels explicit so unlike
-- quantities are not collapsed into a generic Accuracy leaderboard.

BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM papers
        WHERE arxiv_id = '2003.10286'
          AND is_latest_version
          AND title = 'PathVQA: 30000+ Questions for Medical Visual Question Answering'
    ) THEN
        RAISE EXCEPTION 'PathVQA source paper identity precondition failed';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM areas WHERE name = 'Vision') THEN
        RAISE EXCEPTION 'Vision area precondition failed';
    END IF;
END
$$;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    image_url, image_credit, useful_leaderboards
)
VALUES (
    'Medical Visual Question Answering',
    'medical-visual-question-answering',
    'Medical visual question answering (Med-VQA) requires a system to answer natural-language questions about clinical or biomedical images. It combines [Medical Imaging](/tasks/medical-imaging) with [Question Answering](/tasks/question-answering) and is evaluated on both closed-ended diagnostic questions and open-ended answer generation.',
    'medical visual question answering, medical VQA, Med-VQA, MedVQA, biomedical visual question answering, pathology visual question answering, PathVQA, radiology visual question answering',
    (SELECT area_id FROM tasks WHERE slug = 'medical-imaging' LIMIT 1),
    (SELECT level + 1 FROM tasks WHERE slug = 'medical-imaging' LIMIT 1),
    (SELECT id FROM tasks WHERE slug = 'medical-imaging' LIMIT 1),
    NULL,
    '[PathVQA: 30000+ Questions for Medical Visual Question Answering](/paper/2003.10286)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO metrics (name, full_name, direction, scale, description)
VALUES
    (
        'Overall Accuracy',
        'Overall Accuracy',
        'higher_is_better',
        '0-100',
        'Accuracy over the complete benchmark test set.'
    ),
    (
        'Open-Ended Accuracy',
        'Open-Ended Question Accuracy',
        'higher_is_better',
        '0-100',
        'Accuracy restricted to open-ended or free-form questions.'
    ),
    (
        'Closed-Ended Accuracy',
        'Closed-Ended Question Accuracy',
        'higher_is_better',
        '0-100',
        'Accuracy restricted to closed-ended yes/no questions.'
    ),
    (
        'Exact Match (%)',
        'Exact Match Percentage',
        'higher_is_better',
        '0-100',
        'Percentage of generated answers that exactly match the reference answer.'
    ),
    (
        'Open-Ended Recall',
        'Open-Ended Token Recall',
        'higher_is_better',
        '0-100',
        'Token-level recall on the open-ended subset.'
    )
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    scale = EXCLUDED.scale,
    description = EXCLUDED.description,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO datasets (
    name,
    full_name,
    slug,
    description,
    short_description,
    url,
    hf_url,
    homepage,
    image_url,
    thumbnail_url,
    verified_image_url,
    introducing_paper_id,
    introducing_paper_title,
    paper_url,
    introduced_date,
    introduced_year,
    modalities,
    languages,
    variants,
    pwc_url
)
SELECT
    'PathVQA',
    'PathVQA: Pathology Visual Question Answering',
    'pathvqa',
    'PathVQA is a pathology visual question answering benchmark containing 32,799 manually checked questions over 4,998 pathology images. Its official split contains closed-ended yes/no questions and open-ended questions evaluated with answer-generation or classification-style metrics.',
    'A pathology VQA benchmark with 32,799 questions over 4,998 pathology images.',
    'https://github.com/UCSD-AI4H/PathVQA',
    'https://huggingface.co/datasets/flaviagiammarino/path-vqa',
    'https://github.com/UCSD-AI4H/PathVQA',
    'https://production-media.paperswithcode.com/datasets/876e85ce-8c44-40cc-8f41-1385ae65a75c.png',
    'https://production-media.paperswithcode.com/thumbnails/dataset/90597463-9b1a-427e-a138-13fc96b3ecba.jpg',
    'https://production-media.paperswithcode.com/thumbnails/dataset-small/0aaff5de-723a-47f8-8552-620f6193a507.jpg',
    p.id,
    p.title,
    'https://paperswithcode.co/paper/2003.10286',
    DATE '2020-03-07',
    2020,
    '["images", "text", "medical", "pathology"]'::jsonb,
    '["English"]'::jsonb,
    '["official train/validation/test split"]'::jsonb,
    'https://paperswithcode.com/dataset/pathvqa'
FROM papers p
WHERE p.arxiv_id = '2003.10286'
  AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    url = EXCLUDED.url,
    hf_url = EXCLUDED.hf_url,
    homepage = EXCLUDED.homepage,
    image_url = EXCLUDED.image_url,
    thumbnail_url = EXCLUDED.thumbnail_url,
    verified_image_url = EXCLUDED.verified_image_url,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities,
    languages = EXCLUDED.languages,
    variants = EXCLUDED.variants,
    pwc_url = EXCLUDED.pwc_url,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
CROSS JOIN tasks t
WHERE p.arxiv_id = '2003.10286'
  AND p.is_latest_version
  AND t.slug = 'medical-visual-question-answering'
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
CROSS JOIN datasets d
WHERE t.slug = 'medical-visual-question-answering'
  AND d.slug = 'pathvqa'
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = EXCLUDED.supports_harness,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
CROSS JOIN datasets d
CROSS JOIN metrics m
WHERE t.slug = 'medical-visual-question-answering'
  AND d.slug = 'pathvqa'
  AND m.name IN (
      'Overall Accuracy',
      'Open-Ended Accuracy',
      'Closed-Ended Accuracy',
      'BLEU-1 (%)',
      'BLEU-2 (%)',
      'BLEU-3 (%)',
      'Exact Match (%)',
      'F1',
      'Open-Ended Recall'
  )
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

COMMIT;
