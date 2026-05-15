-- Migration: Add user_bookmarks table
-- Description: Per-user paper bookmarks keyed on the HF username carried in
-- the session JWT. Rows are removed automatically when the underlying paper
-- is deleted.
-- Date: 2026-05-15

CREATE TABLE IF NOT EXISTS user_bookmarks (
    hf_username VARCHAR(255) NOT NULL,
    paper_id    BIGINT       NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    created_at  TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (hf_username, paper_id)
);

CREATE INDEX IF NOT EXISTS idx_user_bookmarks_user
    ON user_bookmarks(hf_username);

CREATE INDEX IF NOT EXISTS idx_user_bookmarks_paper
    ON user_bookmarks(paper_id);

COMMENT ON TABLE user_bookmarks IS
'Per-HF-user paper bookmarks. Written exclusively through /api/v1/me/bookmarks endpoints which require the pwc_session cookie.';
