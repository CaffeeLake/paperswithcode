-- Migration: Add Hugging Face artifact URL arrays to papers.
--
-- Background: For arXiv papers we can derive HF artifacts at request time
-- via Hugging Face's arxiv filter URL (e.g. huggingface.co/models?other=arxiv:<id>).
-- External papers (papers.source = 'external') have no reliable arxiv_id, so
-- HF artifacts must be persisted on the row itself.
--
-- These columns store full canonical Hugging Face URLs (e.g.
-- 'https://huggingface.co/Zyphra/ZAYA1-VL-8B') for simple frontend rendering.
-- They are intended for external rows only; arXiv rows should leave them NULL.

ALTER TABLE papers
    ADD COLUMN IF NOT EXISTS hf_models TEXT[],
    ADD COLUMN IF NOT EXISTS hf_datasets TEXT[],
    ADD COLUMN IF NOT EXISTS hf_spaces TEXT[];

COMMENT ON COLUMN papers.hf_models IS
    'Hugging Face model URLs explicitly linked to this paper. Populated for external rows only; arXiv rows derive these from arxiv_id.';
COMMENT ON COLUMN papers.hf_datasets IS
    'Hugging Face dataset URLs explicitly linked to this paper. Populated for external rows only; arXiv rows derive these from arxiv_id.';
COMMENT ON COLUMN papers.hf_spaces IS
    'Hugging Face Space URLs explicitly linked to this paper. Populated for external rows only; arXiv rows derive these from arxiv_id.';
