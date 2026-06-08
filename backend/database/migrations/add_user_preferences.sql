-- Migration: Add user_preferences table
--
-- Per-HF-user account preferences keyed on the lowercased HF username carried
-- in the session JWT (see backend/routers/auth.py). The first preference is
-- `hide_closed_source_evals`, which lets a signed-in user hide closed-source
-- model rows on benchmark and paper evaluation pages.
--
-- Created: 2026-06-03
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_user_preferences.sql

BEGIN;

CREATE TABLE IF NOT EXISTS user_preferences (
    hf_username              VARCHAR(255) NOT NULL,
    hide_closed_source_evals BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at               TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (hf_username)
);

COMMENT ON TABLE user_preferences IS
'Per-HF-user account preferences. Written exclusively through /api/v1/me/preferences which requires the pwc_session cookie.';

COMMIT;
