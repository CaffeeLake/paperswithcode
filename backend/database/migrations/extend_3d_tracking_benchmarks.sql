-- Separate the major 3D tracking protocols so scores with different
-- coordinate frames, temporal windows, alignments, and thresholds never rank
-- against one another. Evaluation rows remain curated through the service.

BEGIN;

UPDATE tasks
SET description = '3D tracking estimates trajectories and visibility through time in three-dimensional camera or world coordinates. It includes arbitrary sparse or dense point tracking and 3D multi-object tracking from video, depth, LiDAR, radar, or multi-sensor input. Unlike [Object Tracking](/tasks/object-tracking), which generally follows targets in the 2D image plane, 3D tracking reasons about depth, camera motion, occlusion, physical-space motion, and data association.',
    keywords = '3D tracking, 3D point tracking, dense 3D tracking, sparse 3D tracking, world-coordinate tracking, world coordinate tracking, world-frame tracking, world frame tracking, tracking any point in 3D, TAP-3D, 3D trajectories, 3D trajectory estimation, 4D tracking, 3D object tracking, 3D multi-object tracking, 3D MOT, LiDAR tracking, lidar object tracking, world-space tracking, camera-coordinate tracking',
    useful_leaderboards = 'https://tapvid3d.github.io,https://st4rtrack.github.io,https://www.nuscenes.org/tracking,https://waymo.com/open/challenges/',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = '3D-tracking';

INSERT INTO metrics (name, full_name, direction, description, scale)
VALUES
    ('EPE3D', '3D End-Point Error', 'lower_is_better',
     'Mean Euclidean end-point error between predicted and ground-truth 3D positions, reported in metres.', 'unbounded'),
    ('AMOTA', 'Average Multi-Object Tracking Accuracy', 'higher_is_better',
     'Multi-object tracking accuracy averaged across recall thresholds under the official nuScenes tracking evaluator.', '0-1'),
    ('MOTA/L2 (Vehicle)', 'Vehicle Multi-Object Tracking Accuracy at LEVEL_2', 'higher_is_better',
     'Official Waymo Open Dataset 3D tracking MOTA for the Vehicle class at LEVEL_2 difficulty.', '0-1'),
    ('MOTA/L2 (ALL_NS)', 'All-Object Multi-Object Tracking Accuracy at LEVEL_2', 'higher_is_better',
     'Official Waymo Open Dataset 3D tracking MOTA at LEVEL_2 aggregated across Vehicle, Cyclist, and Pedestrian.', '0-1')
ON CONFLICT (name) DO UPDATE SET
    full_name = EXCLUDED.full_name,
    direction = EXCLUDED.direction,
    description = EXCLUDED.description,
    scale = EXCLUDED.scale,
    updated_at = CURRENT_TIMESTAMP;

-- The first five pages use TrackCraft3R's modified protocol, not the
-- canonical source-benchmark protocols. Preserve their slugs and evaluations.
UPDATE datasets SET
    name = 'WorldTrack ADT — TrackCraft3R Protocol',
    full_name = 'WorldTrack ADT — TrackCraft3R 84-frame Sim(3) Protocol',
    description = 'TrackCraft3R evaluates the WorldTrack Aria Digital Twin subset on 50 sequences over the first 84 frames, with sparse world-coordinate trajectories, fixed 0.1/0.3/0.5/1.0 metre thresholds, and Sim(3) alignment. It reports AJ, APD3D, and occlusion accuracy on a 0–1 scale. Do not mix this page with original WorldTrack''s 64-frame global-median protocol or canonical camera-coordinate TAPVid-3D.',
    short_description = 'TrackCraft3R 84-frame Sim(3) protocol on WorldTrack ADT.',
    homepage = 'https://cvlab-kaist.github.io/TrackCraft3r/',
    introducing_paper_id = (SELECT id FROM papers WHERE arxiv_id = '2605.12587' AND is_latest_version LIMIT 1),
    introducing_paper_title = 'TrackCraft3R: Repurposing Video Diffusion Transformers for Dense 3D Tracking',
    introduced_date = DATE '2026-05-14', introduced_year = 2026,
    paper_url = 'https://paperswithcode.co/paper/2605.12587',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'worldtrack-adt';

UPDATE datasets SET
    name = 'WorldTrack Panoptic Studio — TrackCraft3R Protocol',
    full_name = 'WorldTrack Panoptic Studio — TrackCraft3R 84-frame Sim(3) Protocol',
    description = 'TrackCraft3R evaluates the WorldTrack Panoptic Studio subset on 50 sequences over the first 84 frames, with sparse world-coordinate trajectories, fixed 0.1/0.3/0.5/1.0 metre thresholds, and Sim(3) alignment. It reports AJ, APD3D, and occlusion accuracy on a 0–1 scale. Do not mix this page with original WorldTrack''s 64-frame global-median protocol or canonical camera-coordinate TAPVid-3D.',
    short_description = 'TrackCraft3R 84-frame Sim(3) protocol on WorldTrack Panoptic Studio.',
    homepage = 'https://cvlab-kaist.github.io/TrackCraft3r/',
    introducing_paper_id = (SELECT id FROM papers WHERE arxiv_id = '2605.12587' AND is_latest_version LIMIT 1),
    introducing_paper_title = 'TrackCraft3R: Repurposing Video Diffusion Transformers for Dense 3D Tracking',
    introduced_date = DATE '2026-05-14', introduced_year = 2026,
    paper_url = 'https://paperswithcode.co/paper/2605.12587',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'worldtrack-panoptic-studio';

UPDATE datasets SET
    name = 'WorldTrack Dynamic Replica — TrackCraft3R Protocol',
    full_name = 'WorldTrack Dynamic Replica — TrackCraft3R 84-frame Sim(3) Protocol',
    description = 'TrackCraft3R evaluates the WorldTrack Dynamic Replica subset on 50 sequences over the first 84 frames, with sparse world-coordinate trajectories, fixed 0.1/0.3/0.5/1.0 metre thresholds, and Sim(3) alignment. It reports AJ, APD3D, and occlusion accuracy on a 0–1 scale. Do not mix this page with original WorldTrack''s 64-frame global-median protocol.',
    short_description = 'TrackCraft3R 84-frame Sim(3) protocol on WorldTrack Dynamic Replica.',
    homepage = 'https://cvlab-kaist.github.io/TrackCraft3r/',
    introducing_paper_id = (SELECT id FROM papers WHERE arxiv_id = '2605.12587' AND is_latest_version LIMIT 1),
    introducing_paper_title = 'TrackCraft3R: Repurposing Video Diffusion Transformers for Dense 3D Tracking',
    introduced_date = DATE '2026-05-14', introduced_year = 2026,
    paper_url = 'https://paperswithcode.co/paper/2605.12587',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'worldtrack-dynamic-replica';

UPDATE datasets SET
    name = 'WorldTrack PointOdyssey — TrackCraft3R Protocol',
    full_name = 'WorldTrack PointOdyssey — TrackCraft3R 84-frame Sim(3) Protocol',
    description = 'TrackCraft3R evaluates the WorldTrack PointOdyssey subset on 50 sequences over the first 84 frames, with sparse world-coordinate trajectories, fixed 0.1/0.3/0.5/1.0 metre thresholds, and Sim(3) alignment. It reports AJ, APD3D, and occlusion accuracy on a 0–1 scale. Do not mix this page with original WorldTrack''s 64-frame global-median protocol.',
    short_description = 'TrackCraft3R 84-frame Sim(3) protocol on WorldTrack PointOdyssey.',
    homepage = 'https://cvlab-kaist.github.io/TrackCraft3r/',
    introducing_paper_id = (SELECT id FROM papers WHERE arxiv_id = '2605.12587' AND is_latest_version LIMIT 1),
    introducing_paper_title = 'TrackCraft3R: Repurposing Video Diffusion Transformers for Dense 3D Tracking',
    introduced_date = DATE '2026-05-14', introduced_year = 2026,
    paper_url = 'https://paperswithcode.co/paper/2605.12587',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'worldtrack-pointodyssey';

UPDATE datasets SET
    name = 'Kubric3D — TrackCraft3R Protocol',
    full_name = 'Kubric3D — TrackCraft3R 50-sequence Sim(3) Protocol',
    description = 'TrackCraft3R evaluates a held-out 50-sequence Kubric split over the first 24 frames with dense world-coordinate trajectories, fixed 0.1/0.3/0.5/1.0 metre thresholds, and Sim(3) alignment. It reports AJ, APD3D, and occlusion accuracy on a 0–1 scale. Do not mix this page with DELTA''s canonical 143-video Kubric3D test split.',
    short_description = 'TrackCraft3R 50-sequence, 24-frame Sim(3) Kubric3D protocol.',
    homepage = 'https://cvlab-kaist.github.io/TrackCraft3r/',
    introducing_paper_id = (SELECT id FROM papers WHERE arxiv_id = '2605.12587' AND is_latest_version LIMIT 1),
    introducing_paper_title = 'TrackCraft3R: Repurposing Video Diffusion Transformers for Dense 3D Tracking',
    introduced_date = DATE '2026-05-14', introduced_year = 2026,
    paper_url = 'https://paperswithcode.co/paper/2605.12587',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'kubric3d';

-- Canonical TAPVid-3D full-test constituent leaderboards.
INSERT INTO datasets (
    name, full_name, slug, description, short_description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, paper_url, split_name, variant_type
)
SELECT
    v.name, v.full_name, v.slug,
    'The canonical TAPVid-3D full_test benchmark on the ' || v.source_name || ' source evaluates long-range, camera-coordinate 3D point trajectories and visibility at 256px. Predictions are evaluated after global median depth scaling. Depth-adaptive 3D distance thresholds are derived from pixel radii {1, 2, 4, 8, 16} at 256px, and results are reported as Average Jaccard (AJ), APD3D, and Occlusion Accuracy (OA). Published percentage scores are normalized to the 0–1 metric scale. Do not mix this protocol with minival, WorldTrack, TrackCraft3R, or other scaling and threshold variants.',
    v.short_description,
    'https://tapvid3d.github.io', p.id, p.title, DATE '2024-07-08', 2024,
    'https://paperswithcode.co/paper/2407.05921', 'full_test', 'subset'
FROM (
    VALUES
      ('TAPVid-3D ADT (Full Test, 256px)', 'TAPVid-3D Aria Digital Twin (ADT) — Full Test at 256px', 'tapvid-3d-adt-full-test-256px', 'Aria Digital Twin (ADT)', 'Canonical TAPVid-3D full_test evaluation on Aria Digital Twin at 256px.'),
      ('TAPVid-3D DriveTrack (Full Test, 256px)', 'TAPVid-3D DriveTrack — Full Test at 256px', 'tapvid-3d-drivetrack-full-test-256px', 'DriveTrack', 'Canonical TAPVid-3D full_test evaluation on DriveTrack at 256px.'),
      ('TAPVid-3D Panoptic Studio (Full Test, 256px)', 'TAPVid-3D Panoptic Studio — Full Test at 256px', 'tapvid-3d-panoptic-studio-full-test-256px', 'Panoptic Studio', 'Canonical TAPVid-3D full_test evaluation on Panoptic Studio at 256px.')
) AS v(name, full_name, slug, source_name, short_description)
JOIN papers p ON p.arxiv_id = '2407.05921' AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name, full_name = EXCLUDED.full_name,
    description = EXCLUDED.description, short_description = EXCLUDED.short_description,
    homepage = EXCLUDED.homepage, introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    introduced_date = EXCLUDED.introduced_date, introduced_year = EXCLUDED.introduced_year,
    paper_url = EXCLUDED.paper_url, split_name = EXCLUDED.split_name,
    variant_type = EXCLUDED.variant_type, updated_at = CURRENT_TIMESTAMP;

-- Canonical original WorldTrack protocol, kept separate from TrackCraft3R.
INSERT INTO datasets (
    name, full_name, slug, description, short_description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, modalities, paper_url
)
SELECT
    v.name, v.full_name, v.slug,
    'The canonical St4RTrack WorldTrack protocol for ' || v.source_name || ' evaluates 50 sequences over the first 64 frames with approximately 1,000 all-points queries per sequence in world coordinates. Predictions are aligned using a single global median scale, APD3D uses fixed distance thresholds of 0.1, 0.3, 0.5, and 1.0 metres, and EPE3D is reported in metres.',
    v.short_description, 'https://st4rtrack.github.io/', p.id, p.title,
    DATE '2025-04-17', 2025, '["3D", "video"]'::jsonb,
    'https://paperswithcode.co/paper/2504.13152'
FROM (
    VALUES
      ('WorldTrack ADT — Original Protocol', 'WorldTrack - Aria Digital Twin — Original 64-frame Global-Median Protocol', 'worldtrack-adt-original-protocol', 'Aria Digital Twin', 'Original 64-frame global-median WorldTrack protocol on Aria Digital Twin.'),
      ('WorldTrack Panoptic Studio — Original Protocol', 'WorldTrack - Panoptic Studio — Original 64-frame Global-Median Protocol', 'worldtrack-panoptic-studio-original-protocol', 'Panoptic Studio', 'Original 64-frame global-median WorldTrack protocol on Panoptic Studio.'),
      ('WorldTrack Dynamic Replica — Original Protocol', 'WorldTrack - Dynamic Replica — Original 64-frame Global-Median Protocol', 'worldtrack-dynamic-replica-original-protocol', 'Dynamic Replica', 'Original 64-frame global-median WorldTrack protocol on Dynamic Replica.'),
      ('WorldTrack PointOdyssey — Original Protocol', 'WorldTrack - PointOdyssey — Original 64-frame Global-Median Protocol', 'worldtrack-pointodyssey-original-protocol', 'PointOdyssey', 'Original 64-frame global-median WorldTrack protocol on PointOdyssey.')
) AS v(name, full_name, slug, source_name, short_description)
JOIN papers p ON p.arxiv_id = '2504.13152' AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name, full_name = EXCLUDED.full_name,
    description = EXCLUDED.description, short_description = EXCLUDED.short_description,
    homepage = EXCLUDED.homepage, introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    introduced_date = EXCLUDED.introduced_date, introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities, paper_url = EXCLUDED.paper_url,
    updated_at = CURRENT_TIMESTAMP;

-- DELTA's canonical dense test split is not TrackCraft3R's held-out subset.
INSERT INTO datasets (
    name, full_name, slug, description, short_description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, modalities, paper_url
)
SELECT
    'Kubric3D — DELTA 143-video Test',
    'Kubric3D — DELTA Canonical 143-video Test Protocol',
    'kubric3d-delta-143-video-test',
    'The canonical DELTA Kubric3D test protocol evaluates 143 generated videos over 24 frames with dense first-frame pixel queries and ground-truth 3D trajectories and visibility. It reports AJ, APD3D, and occlusion accuracy and is distinct from the TrackCraft3R held-out 50-sequence Sim(3) protocol.',
    'DELTA canonical 143-video, 24-frame dense Kubric3D test protocol.',
    'https://snap-research.github.io/DELTA/', p.id, p.title,
    DATE '2024-10-31', 2024, '["3D", "video"]'::jsonb,
    'https://paperswithcode.co/paper/2410.24211'
FROM papers p
WHERE p.arxiv_id = '2410.24211' AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name, full_name = EXCLUDED.full_name,
    description = EXCLUDED.description, short_description = EXCLUDED.short_description,
    homepage = EXCLUDED.homepage, introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    introduced_date = EXCLUDED.introduced_date, introduced_year = EXCLUDED.introduced_year,
    modalities = EXCLUDED.modalities, paper_url = EXCLUDED.paper_url,
    updated_at = CURRENT_TIMESTAMP;

-- Tracking-specific 3D MOT pages avoid contaminating generic detection rows.
INSERT INTO datasets (
    name, full_name, slug, description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, paper_url, split_name, variant_type
)
SELECT
    'nuScenes 3D Tracking (Official Test)',
    'nuScenes 3D Multi-Object Tracking — Official Test',
    'nuscenes-3d-tracking-official-test',
    'Official hidden-test protocol for online 3D multi-object tracking on nuScenes. Systems predict class-labelled 3D bounding-box trajectories from past and current sensor frames. Evaluation matches predictions to ground truth using a 2 m center-distance threshold in the ground plane rather than 3D IoU. The primary metric is AMOTA, averaged across classes and recall thresholds on a 0–1 scale.',
    'https://www.nuscenes.org/tracking', p.id, p.title, DATE '2019-03-26',
    2019, 'https://paperswithcode.co/paper/1903.11027',
    'Official hidden test — online 3D MOT; 2 m ground-plane center matching', 'split'
FROM papers p WHERE p.arxiv_id = '1903.11027' AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name, full_name = EXCLUDED.full_name,
    description = EXCLUDED.description, homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    introduced_date = EXCLUDED.introduced_date, introduced_year = EXCLUDED.introduced_year,
    paper_url = EXCLUDED.paper_url, split_name = EXCLUDED.split_name,
    variant_type = EXCLUDED.variant_type, updated_at = CURRENT_TIMESTAMP;

-- Offboard/full-sequence results use future context and are not comparable to
-- the online challenge rows above.
INSERT INTO datasets (
    name, full_name, slug, description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, paper_url, split_name, variant_type
)
SELECT
    v.name, v.full_name, v.slug, v.description,
    'https://waymo.com/open/challenges/2020/3d-tracking/', p.id, p.title,
    DATE '2019-12-10', 2019, 'https://paperswithcode.co/paper/1912.04838',
    v.split_name, 'split'
FROM (
    VALUES
      ('Waymo Open Dataset 3D Tracking (Official Test, Offboard Vehicle L2)',
       'Waymo Open Dataset 3D Tracking — Official Test, Offboard Vehicle LEVEL_2',
       'waymo-open-dataset-3d-tracking-official-test-offboard-vehicle-l2',
       'Official hidden-test offboard 3D tracking protocol on the Waymo Open Dataset, restricted to Vehicle at LEVEL_2. Full-sequence methods may use future temporal context. This page uses Vehicle MOTA/L2 on a 0–1 scale and is separate from the online/no-future challenge protocol.',
       'Official hidden test — OFFBOARD/full sequence; Vehicle LEVEL_2'),
      ('Waymo Open Dataset 3D Tracking (Official Test, Offboard ALL_NS L2)',
       'Waymo Open Dataset 3D Tracking — Official Test, Offboard ALL_NS LEVEL_2',
       'waymo-open-dataset-3d-tracking-official-test-offboard-all-ns-l2',
       'Official hidden-test offboard 3D tracking protocol on the Waymo Open Dataset, aggregated across Vehicle, Cyclist, and Pedestrian at LEVEL_2. Full-sequence methods may use future temporal context. This page uses ALL_NS MOTA/L2 on a 0–1 scale and is separate from the online/no-future challenge protocol.',
       'Official hidden test — OFFBOARD/full sequence; ALL_NS LEVEL_2')
) AS v(name, full_name, slug, description, split_name)
JOIN papers p ON p.arxiv_id = '1912.04838' AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name, full_name = EXCLUDED.full_name,
    description = EXCLUDED.description, homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    introduced_date = EXCLUDED.introduced_date, introduced_year = EXCLUDED.introduced_year,
    paper_url = EXCLUDED.paper_url, split_name = EXCLUDED.split_name,
    variant_type = EXCLUDED.variant_type, updated_at = CURRENT_TIMESTAMP;

INSERT INTO datasets (
    name, full_name, slug, description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, paper_url, split_name, variant_type
)
SELECT
    'Waymo Open Dataset 3D Tracking (Official Test, Vehicle L2)',
    'Waymo Open Dataset 3D Tracking — Official Test, Vehicle LEVEL_2',
    'waymo-open-dataset-3d-tracking-official-test-vehicle-l2',
    'Official hidden-test 3D tracking protocol on the Waymo Open Dataset Perception Dataset, restricted to Vehicle at LEVEL_2 difficulty. Systems predict upright 3D bounding boxes and consistent identities over a temporal sequence using current and prior lidar and/or camera frames, with no future frames. LEVEL_2 includes LEVEL_1 and LEVEL_2 ground truth. This contract uses Vehicle MOTA/L2 on a 0–1 scale.',
    'https://waymo.com/open/challenges/2020/3d-tracking/', p.id, p.title,
    DATE '2019-12-10', 2019, 'https://paperswithcode.co/paper/1912.04838',
    'Official hidden test — Vehicle LEVEL_2; any sensors; prior frames only', 'split'
FROM papers p WHERE p.arxiv_id = '1912.04838' AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name, full_name = EXCLUDED.full_name,
    description = EXCLUDED.description, homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    introduced_date = EXCLUDED.introduced_date, introduced_year = EXCLUDED.introduced_year,
    paper_url = EXCLUDED.paper_url, split_name = EXCLUDED.split_name,
    variant_type = EXCLUDED.variant_type, updated_at = CURRENT_TIMESTAMP;

INSERT INTO datasets (
    name, full_name, slug, description, homepage,
    introducing_paper_id, introducing_paper_title, introduced_date,
    introduced_year, paper_url, split_name, variant_type
)
SELECT
    'Waymo Open Dataset 3D Tracking (Official Test, ALL_NS L2)',
    'Waymo Open Dataset 3D Tracking — Official Test, ALL_NS LEVEL_2',
    'waymo-open-dataset-3d-tracking-official-test-all-ns-l2',
    'Official hidden-test 3D tracking protocol on the Waymo Open Dataset Perception Dataset, aggregated across Vehicle, Cyclist, and Pedestrian (ALL_NS) at LEVEL_2 difficulty. Systems predict upright 3D bounding boxes and consistent identities using current and prior lidar and/or camera frames, with no future frames. This contract uses aggregate MOTA/L2 on a 0–1 scale and remains separate from the Vehicle-only slice.',
    'https://waymo.com/open/challenges/2020/3d-tracking/', p.id, p.title,
    DATE '2019-12-10', 2019, 'https://paperswithcode.co/paper/1912.04838',
    'Official hidden test — ALL_NS LEVEL_2; Vehicle + Cyclist + Pedestrian', 'split'
FROM papers p WHERE p.arxiv_id = '1912.04838' AND p.is_latest_version
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name, full_name = EXCLUDED.full_name,
    description = EXCLUDED.description, homepage = EXCLUDED.homepage,
    introducing_paper_id = EXCLUDED.introducing_paper_id,
    introducing_paper_title = EXCLUDED.introducing_paper_title,
    introduced_date = EXCLUDED.introduced_date, introduced_year = EXCLUDED.introduced_year,
    paper_url = EXCLUDED.paper_url, split_name = EXCLUDED.split_name,
    variant_type = EXCLUDED.variant_type, updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
SELECT t.id, d.id, FALSE
FROM tasks t
JOIN datasets d ON d.slug IN (
    'tapvid-3d-adt-full-test-256px',
    'tapvid-3d-drivetrack-full-test-256px',
    'tapvid-3d-panoptic-studio-full-test-256px',
    'worldtrack-adt-original-protocol',
    'worldtrack-panoptic-studio-original-protocol',
    'worldtrack-dynamic-replica-original-protocol',
    'worldtrack-pointodyssey-original-protocol',
    'kubric3d-delta-143-video-test',
    'nuscenes-3d-tracking-official-test',
    'waymo-open-dataset-3d-tracking-official-test-vehicle-l2',
    'waymo-open-dataset-3d-tracking-official-test-all-ns-l2',
    'waymo-open-dataset-3d-tracking-official-test-offboard-vehicle-l2',
    'waymo-open-dataset-3d-tracking-official-test-offboard-all-ns-l2'
)
WHERE t.slug = '3D-tracking'
ON CONFLICT (task_id, dataset_id) DO NOTHING;

INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
SELECT t.id, d.id, m.id
FROM tasks t
JOIN (
    VALUES
      ('tapvid-3d-adt-full-test-256px', 'AJ'),
      ('tapvid-3d-adt-full-test-256px', 'APD3D'),
      ('tapvid-3d-adt-full-test-256px', 'OA'),
      ('tapvid-3d-drivetrack-full-test-256px', 'AJ'),
      ('tapvid-3d-drivetrack-full-test-256px', 'APD3D'),
      ('tapvid-3d-drivetrack-full-test-256px', 'OA'),
      ('tapvid-3d-panoptic-studio-full-test-256px', 'AJ'),
      ('tapvid-3d-panoptic-studio-full-test-256px', 'APD3D'),
      ('tapvid-3d-panoptic-studio-full-test-256px', 'OA'),
      ('worldtrack-adt-original-protocol', 'APD3D'),
      ('worldtrack-adt-original-protocol', 'EPE3D'),
      ('worldtrack-panoptic-studio-original-protocol', 'APD3D'),
      ('worldtrack-panoptic-studio-original-protocol', 'EPE3D'),
      ('worldtrack-dynamic-replica-original-protocol', 'APD3D'),
      ('worldtrack-dynamic-replica-original-protocol', 'EPE3D'),
      ('worldtrack-pointodyssey-original-protocol', 'APD3D'),
      ('worldtrack-pointodyssey-original-protocol', 'EPE3D'),
      ('kubric3d-delta-143-video-test', 'AJ'),
      ('kubric3d-delta-143-video-test', 'APD3D'),
      ('kubric3d-delta-143-video-test', 'OA'),
      ('nuscenes-3d-tracking-official-test', 'AMOTA'),
      ('waymo-open-dataset-3d-tracking-official-test-vehicle-l2', 'MOTA/L2 (Vehicle)'),
      ('waymo-open-dataset-3d-tracking-official-test-all-ns-l2', 'MOTA/L2 (ALL_NS)'),
      ('waymo-open-dataset-3d-tracking-official-test-offboard-vehicle-l2', 'MOTA/L2 (Vehicle)'),
      ('waymo-open-dataset-3d-tracking-official-test-offboard-all-ns-l2', 'MOTA/L2 (ALL_NS)')
) AS v(dataset_slug, metric_name) ON TRUE
JOIN datasets d ON d.slug = v.dataset_slug
JOIN metrics m ON m.name = v.metric_name
WHERE t.slug = '3D-tracking'
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM papers p
JOIN tasks t ON t.slug = '3D-tracking'
WHERE p.arxiv_id IN ('1903.11027', '1912.04838', '2407.05921', '2410.24211', '2504.13152')
  AND p.is_latest_version
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

-- Remove two keyword false positives without touching manual curation.
DELETE FROM paper_tasks pt
USING papers p, tasks t
WHERE pt.paper_id = p.id
  AND pt.task_id = t.id
  AND pt.source = 'auto'
  AND t.slug = '3D-tracking'
  AND p.arxiv_id IN ('2101.10775', '2103.13282');

COMMIT;
