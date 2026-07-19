-- Motion Generation task (Vision): synthesize motion for rigged characters, humans, and agents.
-- Sister of 3D generation (static/dynamic 3D content vs temporal skeletal motion).

BEGIN;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Motion Generation',
    'motion-generation',
    'Motion generation synthesizes temporally coherent movement — skeletal animation for rigged 3D characters, human body motion from text or video, and related articulated dynamics. Methods span diffusion models, GANs, and physics-aware controllers for applications in animation, robotics, and 4D content creation. Closely related to [3D generation](/tasks/3d-generation) for static or spatiotemporal 3D assets, and [Video generation](/tasks/video-generation) when the output is pixel video rather than structured motion.',
    'text-to-motion, text-driven human motion, text-driven motion generation, human motion generation, human motion synthesis, generating human motion, 3d human motion generation, whole-body motion generation, human interaction generation, motion synthesis, motion diffusion, skeletal motion generation, video-to-motion, dance generation, music-conditioned dance, text-guided motion generation, motion inpainting, physics-based character control, open-vocabulary motion generation, motion-language',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[MotionDreamer: Universal Skeletal Motion Generation for 3D Rigged Shapes](/paper/2606.01518)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;

-- Sister tasks: Motion Generation <-> 3D generation (bidirectional).
INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = '3d-generation'
WHERE t.slug = 'motion-generation'
ON CONFLICT DO NOTHING;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, 0
FROM tasks t
JOIN tasks s ON s.slug = 'motion-generation'
WHERE t.slug = '3d-generation'
ON CONFLICT DO NOTHING;

-- MotionDreamer introducing paper on the new task.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = 'motion-generation'
WHERE p.arxiv_id = '2606.01518'
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET
    source = 'manual';

-- Move MotionDreamer Test benchmark from 3D generation to Motion Generation.
INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
JOIN datasets d ON d.slug = 'motiondreamer-test'
WHERE t.slug = 'motion-generation'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN datasets d ON d.slug = 'motiondreamer-test'
JOIN metrics m ON m.name IN ('MPJPE', 'CD')
WHERE t.slug = 'motion-generation'
ON CONFLICT DO NOTHING;

-- Drop the old 3D-generation links for this benchmark only.
DELETE FROM task_dataset_metrics tdm
USING tasks t, datasets d
WHERE tdm.task_id = t.id
  AND tdm.dataset_id = d.id
  AND t.slug = '3d-generation'
  AND d.slug = 'motiondreamer-test';

DELETE FROM task_datasets td
USING tasks t, datasets d
WHERE td.task_id = t.id
  AND td.dataset_id = d.id
  AND t.slug = '3d-generation'
  AND d.slug = 'motiondreamer-test';

-- Relink MotionDreamer eval rows to Motion Generation.
UPDATE evaluations e
SET task_id = mg.id,
    updated_at = CURRENT_TIMESTAMP
FROM tasks mg, tasks old, datasets d, papers p
WHERE e.task_id = old.id
  AND e.dataset_id = d.id
  AND e.paper_id = p.id
  AND old.slug = '3d-generation'
  AND mg.slug = 'motion-generation'
  AND d.slug = 'motiondreamer-test'
  AND p.arxiv_id = '2606.01518';

-- MotionDreamer no longer needs the 3D-generation tag (Motion Generation is the primary home).
DELETE FROM paper_tasks pt
USING papers p, tasks t
WHERE pt.paper_id = p.id
  AND pt.task_id = t.id
  AND p.arxiv_id = '2606.01518'
  AND t.slug = '3d-generation';

COMMIT;
