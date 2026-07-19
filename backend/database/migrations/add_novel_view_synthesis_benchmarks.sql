DO $$
DECLARE
    v_task_id BIGINT := (SELECT id FROM tasks WHERE slug = 'novel-view-synthesis');
    psnr_id BIGINT := (SELECT id FROM metrics WHERE name = 'PSNR');
    ssim_id BIGINT := (SELECT id FROM metrics WHERE name = 'SSIM');
    lpips_id BIGINT := (SELECT id FROM metrics WHERE name = 'LPIPS');
    benchmark RECORD;
    v_dataset_id BIGINT;
BEGIN
    IF v_task_id IS NULL THEN
        RAISE EXCEPTION 'novel-view-synthesis task is missing';
    END IF;

    FOR benchmark IN
        SELECT * FROM (VALUES
            ('NeRF Synthetic (full-view)', 'nerf-synthetic-full-view',
             'Full-view novel view synthesis on the canonical eight Blender synthetic scenes using the full NeRF training-view protocol.',
             '2003.08934', 2020),
            ('Mip-NeRF 360', 'mip-nerf-360',
             'Full-view novel view synthesis on the nine indoor and outdoor Mip-NeRF 360 scenes using the official every-eighth-image test split.',
             '2111.12077', 2021),
            ('Mip-NeRF 360 (30-view sparse)', 'mip-nerf-360-30-view',
             'Sparse-view novel view synthesis on the nine Mip-NeRF 360 scenes using 30 calibrated input views.',
             '2111.12077', 2021),
            ('ACID (2-view)', 'acid-2-view',
             'Two-view novel view synthesis on the Aerial Coastline Imagery Dataset.',
             '2012.09855', 2020),
            ('OmniScene (sparse panorama)', 'omniscene-sparse-panorama',
             'Sparse panoramic novel view synthesis on the Omni-Scene benchmark scenes.',
             '2412.06273', 2024),
            ('360Roam (sparse panorama)', '360roam-sparse-panorama',
             'Sparse panoramic novel view synthesis on the real-world 360Roam indoor scenes.',
             '2208.02705', 2022),
            ('Replica (4-view low-overlap)', 'replica-4-view-low-overlap',
             'Novel view synthesis on Replica using four sparse panoramas and target views with less than 35 percent input-view coverage.',
             '1906.05797', 2019)
        ) AS v(name, slug, description, arxiv_id, introduced_year)
    LOOP
        INSERT INTO datasets (
            name, slug, description, short_description,
            introducing_paper_id, introducing_paper_title,
            introduced_year, paper_url
        )
        SELECT
            benchmark.name,
            benchmark.slug,
            benchmark.description,
            benchmark.description,
            p.id,
            p.title,
            benchmark.introduced_year,
            'https://paperswithcode.co/paper/' || p.arxiv_id
        FROM papers p
        WHERE p.arxiv_id = benchmark.arxiv_id AND p.is_latest_version
        ON CONFLICT (slug) DO UPDATE SET
            name = EXCLUDED.name,
            description = EXCLUDED.description,
            short_description = EXCLUDED.short_description,
            introducing_paper_id = EXCLUDED.introducing_paper_id,
            introducing_paper_title = EXCLUDED.introducing_paper_title,
            introduced_year = EXCLUDED.introduced_year,
            paper_url = EXCLUDED.paper_url,
            updated_at = CURRENT_TIMESTAMP
        RETURNING id INTO v_dataset_id;

        INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
        VALUES (v_task_id, v_dataset_id, FALSE)
        ON CONFLICT (task_id, dataset_id) DO NOTHING;

        INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
        VALUES
            (v_task_id, v_dataset_id, psnr_id),
            (v_task_id, v_dataset_id, ssim_id),
            (v_task_id, v_dataset_id, lpips_id)
        ON CONFLICT DO NOTHING;

        INSERT INTO paper_tasks (paper_id, task_id, source)
        SELECT p.id, v_task_id, 'manual'
        FROM papers p
        WHERE p.arxiv_id = benchmark.arxiv_id AND p.is_latest_version
        ON CONFLICT (paper_id, task_id) DO NOTHING;
    END LOOP;

    -- Existing view-count-specific datasets use the same source protocols as StructSplat.
    FOR v_dataset_id IN
        SELECT id FROM datasets WHERE slug IN ('re10k-2-view', 'dl3dv-10k-2-view')
    LOOP
        INSERT INTO task_datasets (task_id, dataset_id, supports_harness)
        VALUES (v_task_id, v_dataset_id, FALSE)
        ON CONFLICT (task_id, dataset_id) DO NOTHING;

        INSERT INTO task_dataset_metrics (task_id, dataset_id, metric_id)
        VALUES
            (v_task_id, v_dataset_id, psnr_id),
            (v_task_id, v_dataset_id, ssim_id),
            (v_task_id, v_dataset_id, lpips_id)
        ON CONFLICT DO NOTHING;
    END LOOP;

    -- Tag the evaluated papers and the method family without disturbing other tags.
    INSERT INTO paper_tasks (paper_id, task_id, source)
    SELECT p.id, v_task_id, 'manual'
    FROM papers p
    WHERE p.arxiv_id IN (
        '2111.12077', '2308.04079', '2412.16604', '2505.23716',
        '2511.10647', '2606.31556', '2606.28321', '2606.27071'
    )
      AND p.is_latest_version
    ON CONFLICT (paper_id, task_id) DO NOTHING;

    INSERT INTO paper_methods (paper_id, method_id)
    SELECT p.id, m.id
    FROM papers p
    JOIN methods m ON m.slug = 'gaussian-splatting'
    WHERE p.arxiv_id IN (
        '2308.04079', '2412.16604', '2505.23716',
        '2606.31556', '2606.28321', '2606.27071'
    )
      AND p.is_latest_version
    ON CONFLICT (paper_id, method_id) DO NOTHING;
END $$;
