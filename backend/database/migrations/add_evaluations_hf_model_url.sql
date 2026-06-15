-- Migration: Add optional `hf_model_url` column to evaluations
--
-- Stores a link to the Hugging Face model page for a given evaluation row
-- (e.g. https://huggingface.co/MiniMaxAI/MiniMax-M3). Kept on the evaluation
-- rather than only on the paper (`papers.hf_models`) so each leaderboard row
-- can link directly to the exact evaluated model and the frontend can turn the
-- model name into an outbound link.
--
-- The column is nullable (existing rows have no known model URL) and uses a
-- CHECK constraint so non-null values must point at huggingface.co.
--
-- Created: 2026-06-14
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_evaluations_hf_model_url.sql

BEGIN;

ALTER TABLE evaluations
    ADD COLUMN IF NOT EXISTS hf_model_url TEXT;

ALTER TABLE evaluations
    DROP CONSTRAINT IF EXISTS evaluations_hf_model_url_huggingface;

ALTER TABLE evaluations
    ADD CONSTRAINT evaluations_hf_model_url_huggingface
    CHECK (hf_model_url IS NULL OR hf_model_url LIKE 'https://huggingface.co/%');

-- Backfill MiniMax M3 evaluation rows. The MiniMax M3 release is an external
-- paper (no arXiv id) keyed by its canonical blog source_url, so scope the
-- backfill on that URL. Only touches rows that have no URL yet, so the
-- migration is safe to re-run.
UPDATE evaluations e
SET hf_model_url = 'https://huggingface.co/MiniMaxAI/MiniMax-M3'
FROM papers p
WHERE e.paper_id = p.id
  AND p.source_url = 'https://www.minimax.io/blog/minimax-m3'
  AND e.hf_model_url IS NULL;

COMMIT;
