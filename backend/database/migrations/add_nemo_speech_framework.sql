-- Add NVIDIA NeMo Speech to the framework catalogue and recommend it for
-- the speech and audio tasks directly supported by the toolkit.

BEGIN;

INSERT INTO repositories (url, owner, name, num_stars, source)
VALUES (
    'https://github.com/nvidia-nemo/speech',
    'NVIDIA-NeMo',
    'Speech',
    0,
    'framework_catalog'
)
ON CONFLICT (url) DO UPDATE SET
    owner = EXCLUDED.owner,
    name = EXCLUDED.name;

INSERT INTO frameworks (
    category_id,
    repository_id,
    slug,
    name,
    organization_name,
    description,
    when_to_use,
    docs_url,
    display_order
)
SELECT
    category.id,
    repository.id,
    'nemo-speech',
    'NVIDIA NeMo Speech',
    'NVIDIA',
    'A PyTorch toolkit for automatic speech recognition, speech synthesis, speaker processing, speech enhancement, neural audio codecs, and audio-aware language models.',
    'Train, customize, or deploy NVIDIA-accelerated speech models across transcription, synthesis, enhancement, audio understanding, and speech generation workflows.',
    'https://docs.nvidia.com/nemo/speech/nightly/index.html',
    0
FROM framework_categories category
JOIN framework_domains domain
    ON domain.id = category.domain_id
    AND domain.slug = 'speech-audio'
JOIN repositories repository
    ON repository.url = 'https://github.com/nvidia-nemo/speech'
WHERE category.slug = 'speech-toolkits'
ON CONFLICT (slug) DO UPDATE SET
    category_id = EXCLUDED.category_id,
    repository_id = EXCLUDED.repository_id,
    name = EXCLUDED.name,
    organization_name = EXCLUDED.organization_name,
    description = EXCLUDED.description,
    when_to_use = EXCLUDED.when_to_use,
    docs_url = EXCLUDED.docs_url,
    display_order = EXCLUDED.display_order,
    updated_at = now();

WITH platform(platform) AS (
    VALUES ('gpu'), ('cpu')
)
INSERT INTO framework_platforms (framework_id, platform)
SELECT framework.id, platform.platform
FROM frameworks framework
CROSS JOIN platform
WHERE framework.slug = 'nemo-speech'
ON CONFLICT DO NOTHING;

WITH recommendation(task_slug, display_order) AS (
    VALUES
        ('audio-compression', 0),
        ('audio-generation', 3),
        ('audio-understanding', 3),
        ('automatic-speech-recognition', 3),
        ('speech-enhancement', 3),
        ('text-to-speech', 2),
        ('voice-cloning', 2)
)
INSERT INTO task_frameworks (task_id, framework_id, display_order)
SELECT task.id, framework.id, recommendation.display_order
FROM recommendation
JOIN tasks task ON task.slug = recommendation.task_slug
JOIN frameworks framework ON framework.slug = 'nemo-speech'
ON CONFLICT (task_id, framework_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

WITH recommendation(task_slug, display_order) AS (
    VALUES
        ('audio-compression', 0),
        ('audio-generation', 3),
        ('audio-understanding', 3),
        ('automatic-speech-recognition', 3),
        ('speech-enhancement', 3),
        ('text-to-speech', 2),
        ('voice-cloning', 2)
)
INSERT INTO task_recommended_frameworks (task_id, repository_id, display_order)
SELECT task.id, repository.id, recommendation.display_order
FROM recommendation
JOIN tasks task ON task.slug = recommendation.task_slug
JOIN repositories repository
    ON repository.url = 'https://github.com/nvidia-nemo/speech'
ON CONFLICT (task_id, repository_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

COMMIT;
