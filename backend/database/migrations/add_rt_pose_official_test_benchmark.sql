-- Add the protocol-explicit RT-Pose official test benchmark for 3D Pose Estimation.
--
-- The paper reports centimetres, while the official evaluator multiplies its
-- metre-valued errors by 1000. This benchmark therefore standardizes all three
-- metrics in millimetres. It intentionally adds no evaluation rows.

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES
    (
        'MRPE (mm)',
        'Mean Root Position Error (mm)',
        'lower_is_better',
        'Mean Euclidean distance in millimetres between the predicted and ground-truth pelvis/root (joint 0) in global radar coordinates. This is the official RT-Pose localization metric (ABS_PJPE for joint 0); lower is better.',
        'unbounded'
    ),
    (
        'Root-relative MPJPE (mm)',
        'Root-relative Mean Per Joint Position Error (mm)',
        'lower_is_better',
        'Mean 15-joint Euclidean position error in millimetres after independently subtracting the predicted and ground-truth pelvis/root (joint 0). No Procrustes alignment is applied. This corresponds to PJPE in the official RT-Pose evaluator; lower is better.',
        'unbounded'
    ),
    (
        'Absolute MPJPE (mm)',
        'Absolute Mean Per Joint Position Error (mm)',
        'lower_is_better',
        'Mean 15-joint Euclidean position error in millimetres in global radar coordinates, without root or Procrustes alignment. This corresponds to ABS_PJPE in the official RT-Pose evaluator; lower is better.',
        'unbounded'
    )
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    description = EXCLUDED.description,
    scale = EXCLUDED.scale,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO datasets (
    name, full_name, slug, description, short_description, url, homepage,
    hf_url, introducing_paper_id, introducing_paper_title, paper_url,
    introduced_date, introduced_year, license_name, license_url, modalities,
    variant_type, split_name, warning
)
SELECT
    'RT-Pose Official Test (4D Radar Tensor)',
    'RT-Pose Official Test — 4D Radar Tensor Human Localization and 3D Pose Estimation',
    'rt-pose-official-test-4d-radar-tensor',
    'The official held-out RT-Pose test protocol selected by the authors'' Test.json and the repository''s tools/test.py --testset path. Systems receive processed D×Z×Y×X 4D radar tensors derived from cascade FMCW radar ADC by range, Doppler, and angle-of-arrival processing (10 fps), and must jointly infer person pelvis/center locations and 15-joint 3D poses. Ground-truth person centers, roots, crops, or proposals are not permitted. Stereo RGB and LiDAR support calibration and annotation in the released dataset but are not inference inputs for this radar-tensor leaderboard. MRPE measures global pelvis localization; root-relative MPJPE subtracts the predicted and ground-truth pelvis independently; absolute MPJPE uses global coordinates without alignment. The official evaluator reports millimetres, so centimetre values in the paper are multiplied by 10. Submissions should disclose tensor representation and preprocessing (including Doppler/phase channels, ROI, and grid), temporal context, person detection/association behavior, training data, and checkpoint.',
    'Official held-out RT-Pose test for joint person localization and 15-joint 3D pose estimation from processed 4D radar tensors.',
    'https://huggingface.co/datasets/uwipl/RT-Pose',
    'https://huggingface.co/datasets/uwipl/RT-Pose',
    'https://huggingface.co/datasets/uwipl/RT-Pose',
    p.id,
    p.title,
    'https://paperswithcode.co/paper/2407.13930',
    DATE '2024-07-18',
    2024,
    'CC BY-NC-SA 4.0',
    'https://creativecommons.org/licenses/by-nc-sa/4.0/',
    '["4D radar tensor", "Radar ADC", "Stereo RGB", "LiDAR point cloud", "3D human pose"]'::jsonb,
    'variant',
    'Official held-out test (Test.json; --testset)',
    'Use only the authors'' held-out Test.json membership through the official --testset path; do not substitute the Hub''s Train.json, a validation split, or per-action/occlusion ablations. The current Hugging Face snapshot does not expose Test.json, so test membership must come from the authors'' official release. This leaderboard excludes RGB/LiDAR fusion at inference, CFAR/radar-point-cloud-only inputs, and oracle roots/person centers/crops. Report all three errors in millimetres; convert the paper''s centimetre values by ×10 before comparison.'
FROM papers p
WHERE p.id = 34943
  AND p.arxiv_id = '2407.13930'
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    short_description = EXCLUDED.short_description,
    url = EXCLUDED.url,
    homepage = EXCLUDED.homepage,
    hf_url = EXCLUDED.hf_url,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    paper_url = EXCLUDED.paper_url,
    introduced_date = EXCLUDED.introduced_date,
    introduced_year = EXCLUDED.introduced_year,
    license_name = EXCLUDED.license_name,
    license_url = EXCLUDED.license_url,
    modalities = EXCLUDED.modalities,
    variant_type = EXCLUDED.variant_type,
    split_name = EXCLUDED.split_name,
    warning = EXCLUDED.warning,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_tasks (paper_id, task_id, source)
VALUES (34943, 424, 'manual')
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

-- Link the benchmark without enabling harness values.
INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT 424, d.id, FALSE
FROM datasets d
WHERE d.slug = 'rt-pose-official-test-4d-radar-tensor'
ON CONFLICT (task_id, dataset_id) DO UPDATE SET
    supports_harness = FALSE,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT 424, d.id, m.id
FROM datasets d
CROSS JOIN metrics m
WHERE d.slug = 'rt-pose-official-test-4d-radar-tensor'
  AND m.name IN ('MRPE (mm)', 'Root-relative MPJPE (mm)', 'Absolute MPJPE (mm)')
ON CONFLICT DO NOTHING;
