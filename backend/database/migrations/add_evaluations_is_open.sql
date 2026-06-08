-- Migration: Add `is_open` flag to evaluations
--
-- Marks whether the evaluated model is open-source. Defaults to TRUE because
-- the vast majority of evaluated models in the database are open. Closed-source
-- models (e.g. proprietary API models, unreleased flagship LLMs) should set this
-- to FALSE so the frontend can optionally hide them based on a user preference.
--
-- Existing rows backfill to TRUE via the DEFAULT, preserving current behavior.
--
-- Created: 2026-06-03
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_evaluations_is_open.sql

BEGIN;

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS is_open BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN evaluations.is_open IS
'Whether the evaluated model is open-source. TRUE by default; FALSE for closed-source models so the frontend can optionally hide them.';

COMMIT;
