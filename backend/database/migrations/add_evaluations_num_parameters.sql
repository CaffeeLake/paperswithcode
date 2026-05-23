-- Migration: Add optional `num_parameters` column to evaluations
--
-- Stores the raw number of model parameters for a given evaluation row
-- (e.g. 7000000000 for a 7B model). Kept on the evaluation rather than
-- the model_name string so that future visualizations and filters can
-- query/sort by parameter count directly.
--
-- The column is nullable (existing rows have no known count) and uses a
-- CHECK constraint to keep values non-negative. BIGINT is wide enough to
-- represent foreseeable parameter counts (trillions of params).
--
-- Created: 2026-05-21
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_evaluations_num_parameters.sql

BEGIN;

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS num_parameters BIGINT;

ALTER TABLE evaluations
    DROP CONSTRAINT IF EXISTS evaluations_num_parameters_non_negative;

ALTER TABLE evaluations
    ADD CONSTRAINT evaluations_num_parameters_non_negative
    CHECK (num_parameters IS NULL OR num_parameters >= 0);

COMMIT;
