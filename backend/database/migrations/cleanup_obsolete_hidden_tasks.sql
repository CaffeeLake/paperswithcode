-- Explicitly remove the reviewed hidden-task data before task search backfill.
-- The migration is idempotent after a successful application and aborts on
-- any precondition drift instead of broadening its destructive scope.

DO $$
DECLARE
    target_task_ids bigint[] := ARRAY[281, 260, 264, 256, 265]::bigint[];
    target_dataset_ids bigint[] := ARRAY[315, 327, 370, 269, 274, 352]::bigint[];
    deleted_count integer;
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM tasks WHERE id = ANY(target_task_ids)
    ) AND NOT EXISTS (
        SELECT 1 FROM datasets WHERE id = ANY(target_dataset_ids)
    ) THEN
        IF EXISTS (
            SELECT 1
            FROM tasks
            WHERE slug = ANY(ARRAY[
                'coding',
                'other',
                'few-shot-image-classification',
                'general',
                'open-vocabulary-object-detection'
            ])
        ) THEN
            RAISE EXCEPTION 'obsolete task cleanup is partially applied';
        END IF;
        RETURN;
    END IF;

    IF (
        SELECT array_agg(id ORDER BY id)
        FROM tasks
        WHERE (id, slug) IN (
            (281, 'coding'),
            (260, 'other'),
            (264, 'few-shot-image-classification'),
            (256, 'general'),
            (265, 'open-vocabulary-object-detection')
        )
    ) IS DISTINCT FROM ARRAY[256, 260, 264, 265, 281]::bigint[] THEN
        RAISE EXCEPTION 'obsolete task identity precondition failed';
    END IF;

    IF (
        SELECT array_agg(id ORDER BY id)
        FROM datasets
        WHERE (id, slug) IN (
            (315, 'bird-sql-dev'),
            (327, 'evalplus'),
            (370, 'openrewrite-eval'),
            (269, 'navi'),
            (274, 'spair'),
            (352, 'revisited-oxford-r-ox-medium-split')
        )
    ) IS DISTINCT FROM ARRAY[269, 274, 315, 327, 352, 370]::bigint[] THEN
        RAISE EXCEPTION 'obsolete benchmark identity precondition failed';
    END IF;

    IF (SELECT count(*) FROM evaluations WHERE dataset_id = ANY(target_dataset_ids)) <> 13
       OR (
           SELECT ARRAY[
               count(*) FILTER (WHERE dataset_id = 269),
               count(*) FILTER (WHERE dataset_id = 274),
               count(*) FILTER (WHERE dataset_id = 315),
               count(*) FILTER (WHERE dataset_id = 327),
               count(*) FILTER (WHERE dataset_id = 352),
               count(*) FILTER (WHERE dataset_id = 370)
           ]
           FROM evaluations
           WHERE dataset_id = ANY(target_dataset_ids)
       ) IS DISTINCT FROM ARRAY[1, 1, 3, 5, 2, 1]::bigint[]
       OR EXISTS (
           SELECT 1 FROM evaluations
           WHERE dataset_id = ANY(target_dataset_ids)
             AND task_id NOT IN (281, 260)
       )
       OR EXISTS (
           SELECT 1 FROM evaluations
           WHERE task_id = ANY(target_task_ids)
             AND dataset_id <> ALL(target_dataset_ids)
       ) THEN
        RAISE EXCEPTION 'obsolete benchmark evaluation precondition failed';
    END IF;

    IF (SELECT count(*) FROM paper_tasks WHERE task_id = 281) <> 2
       OR (
           SELECT array_agg(paper_id ORDER BY paper_id)
           FROM paper_tasks WHERE task_id = 281
       ) IS DISTINCT FROM ARRAY[83677, 99023]::bigint[]
       OR EXISTS (
           SELECT 1 FROM paper_tasks
           WHERE task_id = ANY(ARRAY[260, 264, 256, 265]::bigint[])
       ) THEN
        RAISE EXCEPTION 'obsolete task paper-link precondition failed';
    END IF;

    IF (SELECT count(*) FROM task_datasets WHERE dataset_id = ANY(target_dataset_ids)) <> 6
       OR (
           SELECT ARRAY[
               count(*) FILTER (WHERE dataset_id = 269),
               count(*) FILTER (WHERE dataset_id = 274),
               count(*) FILTER (WHERE dataset_id = 315),
               count(*) FILTER (WHERE dataset_id = 327),
               count(*) FILTER (WHERE dataset_id = 352),
               count(*) FILTER (WHERE dataset_id = 370)
           ]
           FROM task_datasets
           WHERE dataset_id = ANY(target_dataset_ids)
       ) IS DISTINCT FROM ARRAY[1, 1, 1, 1, 1, 1]::bigint[]
       OR EXISTS (
           SELECT 1 FROM task_datasets
           WHERE dataset_id = ANY(target_dataset_ids)
             AND task_id NOT IN (281, 260)
       )
       OR EXISTS (
           SELECT 1 FROM task_datasets
           WHERE task_id = ANY(target_task_ids)
             AND dataset_id <> ALL(target_dataset_ids)
       )
       OR (SELECT count(*) FROM task_dataset_metrics WHERE dataset_id = ANY(target_dataset_ids)) <> 6
       OR (
           SELECT ARRAY[
               count(*) FILTER (WHERE dataset_id = 269),
               count(*) FILTER (WHERE dataset_id = 274),
               count(*) FILTER (WHERE dataset_id = 315),
               count(*) FILTER (WHERE dataset_id = 327),
               count(*) FILTER (WHERE dataset_id = 352),
               count(*) FILTER (WHERE dataset_id = 370)
           ]
           FROM task_dataset_metrics
           WHERE dataset_id = ANY(target_dataset_ids)
       ) IS DISTINCT FROM ARRAY[1, 1, 1, 1, 1, 1]::bigint[]
       OR EXISTS (
           SELECT 1 FROM task_dataset_metrics
           WHERE dataset_id = ANY(target_dataset_ids)
             AND task_id NOT IN (281, 260)
       )
       OR EXISTS (
           SELECT 1 FROM task_dataset_metrics
           WHERE task_id = ANY(target_task_ids)
             AND dataset_id <> ALL(target_dataset_ids)
       ) THEN
        RAISE EXCEPTION 'obsolete benchmark task/metric precondition failed';
    END IF;

    IF EXISTS (
        SELECT 1 FROM paper_datasets WHERE dataset_id = ANY(target_dataset_ids)
    ) OR EXISTS (
        SELECT 1 FROM datasets WHERE parent_dataset_id = ANY(target_dataset_ids)
    ) THEN
        RAISE EXCEPTION 'obsolete benchmark acquired material dependencies';
    END IF;

    IF EXISTS (
        SELECT 1 FROM tasks WHERE parent_id = ANY(target_task_ids)
    ) OR EXISTS (
        SELECT 1 FROM task_sister_tasks
        WHERE task_id = ANY(target_task_ids)
           OR sister_task_id = ANY(target_task_ids)
    ) OR EXISTS (
        SELECT 1 FROM task_recommended_frameworks
        WHERE task_id = ANY(target_task_ids)
    ) THEN
        RAISE EXCEPTION 'obsolete task acquired hierarchy or recommendation dependencies';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM tasks
        WHERE id = 282 AND slug = 'safety-and-grounding'
    ) THEN
        RAISE EXCEPTION 'retained safety-and-grounding task is missing';
    END IF;

    DELETE FROM evaluations WHERE dataset_id = ANY(target_dataset_ids);
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count <> 13 THEN
        RAISE EXCEPTION 'expected to delete 13 evaluations, deleted %', deleted_count;
    END IF;

    DELETE FROM task_dataset_metrics WHERE dataset_id = ANY(target_dataset_ids);
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count <> 6 THEN
        RAISE EXCEPTION 'expected to delete 6 leaderboard metrics, deleted %', deleted_count;
    END IF;

    DELETE FROM task_datasets WHERE dataset_id = ANY(target_dataset_ids);
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count <> 6 THEN
        RAISE EXCEPTION 'expected to delete 6 task-benchmark links, deleted %', deleted_count;
    END IF;

    DELETE FROM paper_tasks WHERE task_id = 281;
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count <> 2 THEN
        RAISE EXCEPTION 'expected to delete 2 coding paper links, deleted %', deleted_count;
    END IF;

    DELETE FROM datasets WHERE id = ANY(target_dataset_ids);
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count <> 6 THEN
        RAISE EXCEPTION 'expected to delete 6 benchmarks, deleted %', deleted_count;
    END IF;

    DELETE FROM tasks WHERE id = ANY(target_task_ids);
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    IF deleted_count <> 5 THEN
        RAISE EXCEPTION 'expected to delete 5 tasks, deleted %', deleted_count;
    END IF;
END
$$;
