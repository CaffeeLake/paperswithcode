-- Deprecated migration retained for history.
--
-- task_datasets is now the source of task-benchmark membership and display
-- metadata. task_dataset_metrics remains the source of allowed leaderboard
-- metrics for each task-benchmark pair.
--
-- Do not drop task_datasets.
DO $$
BEGIN
    RAISE NOTICE 'Skipping deprecated drop_task_datasets migration; task_datasets is required.';
END $$;
