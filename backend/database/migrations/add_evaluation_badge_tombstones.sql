-- Preserve public leaderboard badge URLs when evaluation rows are deleted.
-- Tombstones deliberately have no foreign keys so cascading catalog cleanup
-- cannot remove the public badge contract.
\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS public.evaluation_badge_tombstones (
    evaluation_id BIGINT PRIMARY KEY,
    paper_id BIGINT NOT NULL,
    task_id BIGINT,
    dataset_id BIGINT,
    task_slug VARCHAR(255),
    dataset_slug VARCHAR(255),
    dataset_name VARCHAR(255) NOT NULL,
    deleted_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evaluation_badge_tombstones_paper_id
    ON public.evaluation_badge_tombstones (paper_id);
CREATE INDEX IF NOT EXISTS idx_evaluation_badge_tombstones_target
    ON public.evaluation_badge_tombstones (paper_id, task_id, dataset_id);

CREATE OR REPLACE FUNCTION public.capture_evaluation_badge_tombstone()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    captured_task_slug VARCHAR(255);
    captured_dataset_slug VARCHAR(255);
    captured_dataset_name VARCHAR(255);
BEGIN
    SELECT slug INTO captured_task_slug
    FROM public.tasks
    WHERE id = OLD.task_id;

    SELECT slug, name INTO captured_dataset_slug, captured_dataset_name
    FROM public.datasets
    WHERE id = OLD.dataset_id;

    INSERT INTO public.evaluation_badge_tombstones (
        evaluation_id,
        paper_id,
        task_id,
        dataset_id,
        task_slug,
        dataset_slug,
        dataset_name,
        deleted_at
    ) VALUES (
        OLD.id,
        OLD.paper_id,
        OLD.task_id,
        OLD.dataset_id,
        captured_task_slug,
        captured_dataset_slug,
        COALESCE(captured_dataset_name, 'benchmark'),
        now()
    )
    ON CONFLICT (evaluation_id) DO UPDATE SET
        paper_id = EXCLUDED.paper_id,
        task_id = EXCLUDED.task_id,
        dataset_id = EXCLUDED.dataset_id,
        task_slug = COALESCE(
            EXCLUDED.task_slug,
            public.evaluation_badge_tombstones.task_slug
        ),
        dataset_slug = COALESCE(
            EXCLUDED.dataset_slug,
            public.evaluation_badge_tombstones.dataset_slug
        ),
        dataset_name = CASE
            WHEN captured_dataset_name IS NULL
                THEN public.evaluation_badge_tombstones.dataset_name
            ELSE EXCLUDED.dataset_name
        END,
        deleted_at = EXCLUDED.deleted_at;

    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS evaluations_capture_badge_tombstone
    ON public.evaluations;
CREATE TRIGGER evaluations_capture_badge_tombstone
BEFORE DELETE ON public.evaluations
FOR EACH ROW
EXECUTE FUNCTION public.capture_evaluation_badge_tombstone();

CREATE OR REPLACE FUNCTION public.capture_dataset_evaluation_badge_tombstones()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.evaluation_badge_tombstones (
        evaluation_id,
        paper_id,
        task_id,
        dataset_id,
        task_slug,
        dataset_slug,
        dataset_name,
        deleted_at
    )
    SELECT
        evaluation.id,
        evaluation.paper_id,
        evaluation.task_id,
        evaluation.dataset_id,
        task.slug,
        OLD.slug,
        OLD.name,
        now()
    FROM public.evaluations AS evaluation
    LEFT JOIN public.tasks AS task ON task.id = evaluation.task_id
    WHERE evaluation.dataset_id = OLD.id
    ON CONFLICT (evaluation_id) DO UPDATE SET
        paper_id = EXCLUDED.paper_id,
        task_id = EXCLUDED.task_id,
        dataset_id = EXCLUDED.dataset_id,
        task_slug = COALESCE(
            EXCLUDED.task_slug,
            public.evaluation_badge_tombstones.task_slug
        ),
        dataset_slug = EXCLUDED.dataset_slug,
        dataset_name = EXCLUDED.dataset_name,
        deleted_at = EXCLUDED.deleted_at;

    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS datasets_capture_evaluation_badge_tombstones
    ON public.datasets;
CREATE TRIGGER datasets_capture_evaluation_badge_tombstones
BEFORE DELETE ON public.datasets
FOR EACH ROW
EXECUTE FUNCTION public.capture_dataset_evaluation_badge_tombstones();

CREATE OR REPLACE FUNCTION public.capture_task_evaluation_badge_tombstones()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO public.evaluation_badge_tombstones (
        evaluation_id,
        paper_id,
        task_id,
        dataset_id,
        task_slug,
        dataset_slug,
        dataset_name,
        deleted_at
    )
    SELECT
        evaluation.id,
        evaluation.paper_id,
        evaluation.task_id,
        evaluation.dataset_id,
        OLD.slug,
        dataset.slug,
        dataset.name,
        now()
    FROM public.evaluations AS evaluation
    LEFT JOIN public.datasets AS dataset ON dataset.id = evaluation.dataset_id
    WHERE evaluation.task_id = OLD.id
    ON CONFLICT (evaluation_id) DO UPDATE SET
        paper_id = EXCLUDED.paper_id,
        task_id = EXCLUDED.task_id,
        dataset_id = EXCLUDED.dataset_id,
        task_slug = EXCLUDED.task_slug,
        dataset_slug = COALESCE(
            EXCLUDED.dataset_slug,
            public.evaluation_badge_tombstones.dataset_slug
        ),
        dataset_name = COALESCE(
            EXCLUDED.dataset_name,
            public.evaluation_badge_tombstones.dataset_name
        ),
        deleted_at = EXCLUDED.deleted_at;

    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS tasks_capture_evaluation_badge_tombstones
    ON public.tasks;
CREATE TRIGGER tasks_capture_evaluation_badge_tombstones
BEFORE DELETE ON public.tasks
FOR EACH ROW
EXECUTE FUNCTION public.capture_task_evaluation_badge_tombstones();

WITH known_badges (
    evaluation_id,
    arxiv_id,
    task_slug,
    dataset_slug,
    dataset_name
) AS (
    VALUES
        (13822::BIGINT, '2606.19531', 'robotics', 'robotwin', 'RoboTwin 2.0'),
        (9521::BIGINT, '2601.10611', 'image-understanding', 'ai2d', 'AI2D'),
        (5057::BIGINT, '2603.00729', 'coding', 'evalplus', 'EvalPlus'),
        (5060::BIGINT, '2603.00729', 'coding', 'bird-sql-dev', 'Bird-SQL (dev)'),
        (17984::BIGINT, '2307.02499', 'document-understanding', 'visualmrc', 'VisualMRC'),
        (17996::BIGINT, '2602.08683', 'document-understanding', 'infovqa', 'InfoVQA'),
        (10558::BIGINT, '2606.19534', 'image-understanding', 'chartqa', 'ChartQA'),
        (17778::BIGINT, '2605.04128', 'image-editing', 'imgedit-imgedit-benchmark', 'ImgEdit (ImgEdit benchmark)'),
        (10653::BIGINT, '2605.31268', 'coding', 'evalplus', 'EvalPlus')
), resolved AS (
    SELECT
        known_badges.*,
        paper.id AS paper_id,
        task.id AS task_id,
        dataset.id AS dataset_id
    FROM known_badges
    JOIN LATERAL (
        SELECT id
        FROM public.papers
        WHERE arxiv_id = known_badges.arxiv_id
          AND is_latest_version
        ORDER BY id DESC
        LIMIT 1
    ) AS paper ON TRUE
    LEFT JOIN public.tasks AS task
        ON task.slug = known_badges.task_slug
    LEFT JOIN public.datasets AS dataset
        ON dataset.slug = known_badges.dataset_slug
)
INSERT INTO public.evaluation_badge_tombstones (
    evaluation_id,
    paper_id,
    task_id,
    dataset_id,
    task_slug,
    dataset_slug,
    dataset_name
)
SELECT
    evaluation_id,
    paper_id,
    task_id,
    dataset_id,
    task_slug,
    dataset_slug,
    dataset_name
FROM resolved
ON CONFLICT (evaluation_id) DO UPDATE SET
    paper_id = EXCLUDED.paper_id,
    task_id = EXCLUDED.task_id,
    dataset_id = EXCLUDED.dataset_id,
    task_slug = EXCLUDED.task_slug,
    dataset_slug = EXCLUDED.dataset_slug,
    dataset_name = EXCLUDED.dataset_name;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'paperswithcode_user') THEN
        GRANT SELECT, INSERT, UPDATE
            ON public.evaluation_badge_tombstones TO paperswithcode_user;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pwc_staging') THEN
        GRANT SELECT
            ON public.evaluation_badge_tombstones TO pwc_staging;
    END IF;
END $$;

COMMIT;
