-- Add the pixelSplat two-context-view RealEstate10K NVS protocol.
--
-- This is deliberately separate from `re10k-2-view`, which represents the
-- incompatible PixWorld interpolation/extrapolation generation protocol.

DO $$
DECLARE
    v_task_id BIGINT;
    v_paper_id BIGINT;
    v_paper_title TEXT;
    v_dataset_id BIGINT;
    v_metric_count INTEGER;
BEGIN
    SELECT id INTO v_task_id
    FROM tasks
    WHERE slug = 'novel-view-synthesis';

    IF v_task_id IS NULL THEN
        RAISE EXCEPTION 'novel-view-synthesis task is missing';
    END IF;

    SELECT id, title INTO v_paper_id, v_paper_title
    FROM papers
    WHERE arxiv_id = '1805.09817'
      AND is_latest_version
    ORDER BY id
    LIMIT 1;

    IF v_paper_id IS NULL THEN
        RAISE EXCEPTION 'RealEstate10K source paper 1805.09817 is missing';
    END IF;

    SELECT COUNT(*) INTO v_metric_count
    FROM metrics
    WHERE name IN ('PSNR', 'SSIM', 'LPIPS');

    IF v_metric_count <> 3 THEN
        RAISE EXCEPTION 'One or more required metrics are missing: PSNR, SSIM, LPIPS';
    END IF;

    INSERT INTO datasets (
        name,
        full_name,
        slug,
        description,
        short_description,
        homepage,
        introducing_paper_id,
        introducing_paper_title,
        introduced_year,
        introduced_date,
        paper_url
    )
    VALUES (
        'RealEstate10K (pixelSplat 2-view)',
        'RealEstate10K (pixelSplat 2-view protocol)',
        'realestate10k-pixelsplat-2-view',
        'Novel view synthesis on the standard pixelSplat RealEstate10K validation split using exactly two posed and calibrated context views and three target views per example at 256x256 resolution. Results are reported with PSNR, SSIM, and LPIPS.',
        'Standard pixelSplat validation protocol: 2 posed/calibrated context views, 3 target views, 256x256.',
        'https://google.github.io/realestate10k/',
        v_paper_id,
        v_paper_title,
        2018,
        DATE '2018-05-24',
        'https://paperswithcode.co/paper/1805.09817'
    )
    ON CONFLICT (slug) DO UPDATE SET
        name = EXCLUDED.name,
        full_name = EXCLUDED.full_name,
        description = EXCLUDED.description,
        short_description = EXCLUDED.short_description,
        homepage = EXCLUDED.homepage,
        introducing_paper_id = EXCLUDED.introducing_paper_id,
        introducing_paper_title = EXCLUDED.introducing_paper_title,
        introduced_year = EXCLUDED.introduced_year,
        introduced_date = EXCLUDED.introduced_date,
        paper_url = EXCLUDED.paper_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO v_dataset_id;

    INSERT INTO task_datasets (
        task_id,
        dataset_id,
        supports_harness
    )
    VALUES (v_task_id, v_dataset_id, FALSE)
    ON CONFLICT (task_id, dataset_id) DO UPDATE SET
        supports_harness = FALSE;

    DELETE FROM task_dataset_metrics
    WHERE task_id = v_task_id
      AND dataset_id = v_dataset_id
      AND metric_id NOT IN (
          SELECT id FROM metrics WHERE name IN ('PSNR', 'SSIM', 'LPIPS')
      );

    INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
    SELECT v_task_id, v_dataset_id, id
    FROM metrics
    WHERE name IN ('PSNR', 'SSIM', 'LPIPS')
    ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

    INSERT INTO paper_tasks (paper_id, task_id, source)
    VALUES (v_paper_id, v_task_id, 'manual')
    ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';
END $$;
