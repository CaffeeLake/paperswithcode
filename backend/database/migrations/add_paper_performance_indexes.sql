-- Migration: Add targeted indexes for paper API performance
-- Date: 2026-05-06
-- Description: Speeds up official-repository joins used by paper trending APIs.

-- EXPLAIN showed the hot trending join scanning paper_repositories by repository_id
-- and filtering is_official. Keep this narrow and partial so writes stay cheap.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_paper_repositories_official_repository_paper
ON paper_repositories(repository_id, paper_id)
WHERE is_official = TRUE;
