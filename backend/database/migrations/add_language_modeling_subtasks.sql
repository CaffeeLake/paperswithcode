-- Migration: Add Language Modeling subtasks and move benchmarks/evaluations
--
-- Creates first-class child tasks under `language-modeling` (a subtask is just
-- a child task; see `tasks.parent_id`/`level`) and moves the existing
-- `task_datasets`, `task_dataset_metrics`, and `evaluations` rows from the
-- parent Language Modeling task to the appropriate child task. Benchmarks now
-- own a single concrete leaderboard node; the parent task page renders its
-- subtasks and defers benchmarks to them.
--
-- After this migration, ranks should be recalculated per
-- `(child_task_id, dataset_id, best_metric)`. The companion script
-- `run_add_language_modeling_subtasks.py` runs this file and then invokes the
-- evaluation service's `recalculate_ranks` for every affected leaderboard.
--
-- Created: 2026-05-13
-- Usage:
--   psql -U postgres -d paperswithcode_hf \
--        -f backend/database/migrations/add_language_modeling_subtasks.sql
--   uv run --env-file backend/keys.env python \
--        backend/database/migrations/run_add_language_modeling_subtasks.py

BEGIN;

-- Capture the parent task id once for reuse.
WITH parent AS (
    SELECT id, level FROM tasks WHERE slug = 'language-modeling'
)
INSERT INTO tasks (name, description, slug, parent_id, area_id, level)
SELECT
    sub.name,
    sub.description,
    sub.slug,
    parent.id,
    NULL,
    parent.level + 1
FROM parent
CROSS JOIN (
    VALUES
        (
            'World Knowledge',
            'world-knowledge',
            'World Knowledge benchmarks evaluate how well a language model recalls and applies broad factual knowledge across academic disciplines, professional exams, and general-domain trivia. They cover MMLU-style multiple-choice exams, expert-level science (GPQA Diamond, Humanity''s Last Exam), open-ended factual QA (SimpleQA, TriviaQA), and multilingual variants such as MMMLU and Global MMLU-Lite.'
        ),
        (
            'Long Context',
            'long-context',
            'Long Context benchmarks measure a language model''s ability to retrieve, reason over, and follow instructions across very long inputs, often spanning tens to thousands of pages. They include needle-in-a-haystack style retrieval (MRCR v2, RULER), realistic long-document QA and summarization (LongBench v2, LV-Eval, ZeroSCROLLS/QuALITY), and multi-turn long-context dialogue (LongBench-Chat, MultiChallenge).'
        ),
        (
            'Instruction Following',
            'instruction-following',
            'Instruction Following benchmarks evaluate how reliably a language model adheres to detailed natural-language instructions, formatting constraints, and stylistic preferences. They include verifiable-format suites (IFEval, Multi-IF), pairwise chat preference benchmarks (Arena-Hard, MT-Bench, AlignBench), and writing-quality evaluations (WritingBench, Creative Writing Benchmark v3).'
        ),
        (
            'Math',
            'math',
            'Math benchmarks evaluate a language model''s ability to solve mathematical problems ranging from grade school word problems (GSM8k) to competition mathematics (AIME, MATH 500) and adversarial held-out problem sets (HiddenMath). They typically score final-answer correctness rather than proof style.'
        ),
        (
            'Reasoning',
            'language-reasoning',
            'Reasoning benchmarks evaluate multi-step logical, commonsense, and reading-comprehension reasoning. They include classic suites (BBH, ARC, HellaSwag, Winogrande, CommonsenseQA, OpenBookQA, DROP), structured-logic challenges (AutoLogi, ZebraLogic, MGS), and broad reasoning aggregators such as Livebench. The slug is `language-reasoning` to disambiguate from the top-level `reasoning` task that covers general reasoning models (CoT, RLVR).'
        ),
        (
            'Coding',
            'coding',
            'Coding benchmarks within Language Modeling evaluate code generation, repair, and SQL synthesis from natural-language specifications. They include functional-correctness suites (EvalPlus), text-to-SQL evaluation on real databases (Bird-SQL), and code editing benchmarks (OpenRewrite-Eval).'
        ),
        (
            'Safety and Grounding',
            'safety-and-grounding',
            'Safety and Grounding benchmarks evaluate refusal behavior, factual grounding to source material, and cross-lingual factual consistency. They include safety probe suites (SafetyBench), retrieval-grounded factuality (FACTS Grounding), and multilingual factual consistency (ECLeKTic).'
        ),
        (
            'Classic Language Modeling',
            'classic-language-modeling',
            'Classic Language Modeling benchmarks measure raw next-token modeling quality through perplexity and bits-per-character on long-standing corpora such as the Penn Treebank. These are the historical roots of the field rather than capability benchmarks for instruction-tuned models.'
        )
) AS sub(name, slug, description)
ON CONFLICT (slug) DO NOTHING;

-- Mapping table: dataset slug -> child task slug for the LM benchmarks.
CREATE TEMPORARY TABLE _lm_subtask_map (
    dataset_slug TEXT PRIMARY KEY,
    child_task_slug TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO _lm_subtask_map (dataset_slug, child_task_slug) VALUES
    ('mmlu', 'world-knowledge'),
    ('mmlu-pro', 'world-knowledge'),
    ('mmlu-redux', 'world-knowledge'),
    ('mmmlu', 'world-knowledge'),
    ('gpqa', 'world-knowledge'),
    ('gpqa-diamond', 'world-knowledge'),
    ('humanitys-last-exam-hle', 'world-knowledge'),
    ('global-mmlu-lite', 'world-knowledge'),
    ('okapi-mmlu-translated', 'world-knowledge'),
    ('supergpqa', 'world-knowledge'),
    ('c-eval', 'world-knowledge'),
    ('include', 'world-knowledge'),
    ('simpleqa', 'world-knowledge'),
    ('c-simpleqa', 'world-knowledge'),
    ('triviaqa', 'world-knowledge'),
    ('openbookqa', 'world-knowledge'),
    ('mrcr-v2-1m', 'long-context'),
    ('mrcr-v2-128k', 'long-context'),
    ('longbench-v2', 'long-context'),
    ('longbench-chat', 'long-context'),
    ('lv-eval', 'long-context'),
    ('ruler', 'long-context'),
    ('zeroscrolls-quality', 'long-context'),
    ('multichallenge', 'long-context'),
    ('ifeval', 'instruction-following'),
    ('multi-if', 'instruction-following'),
    ('arena-hard', 'instruction-following'),
    ('mtbench', 'instruction-following'),
    ('alignbench', 'instruction-following'),
    ('writingbench', 'instruction-following'),
    ('creative-writing-benchmark-v3', 'instruction-following'),
    ('sysbench-isr', 'instruction-following'),
    ('aime-2024', 'math'),
    ('aime-2025', 'math'),
    ('math-500', 'math'),
    ('gsm8k', 'math'),
    ('hiddenmath', 'math'),
    ('math', 'math'),
    ('drop', 'language-reasoning'),
    ('hellaswag', 'language-reasoning'),
    ('winogrande', 'language-reasoning'),
    ('bbh', 'language-reasoning'),
    ('arc', 'language-reasoning'),
    ('commonsenseqa', 'language-reasoning'),
    ('autologi', 'language-reasoning'),
    ('zebralogic', 'language-reasoning'),
    ('mgs', 'language-reasoning'),
    ('livebench', 'language-reasoning'),
    ('evalplus', 'coding'),
    ('bird-sql-dev', 'coding'),
    ('openrewrite-eval', 'coding'),
    ('safetybench', 'safety-and-grounding'),
    ('facts-grounding', 'safety-and-grounding'),
    ('eclektic', 'safety-and-grounding'),
    ('penn-treebank-wsj-section-23', 'classic-language-modeling');

-- Resolve mapping to numeric (lm_task_id, child_task_id, dataset_id) triples.
CREATE TEMPORARY TABLE _lm_subtask_moves AS
SELECT
    lm.id        AS lm_task_id,
    child.id     AS child_task_id,
    d.id         AS dataset_id,
    d.slug       AS dataset_slug,
    child.slug   AS child_task_slug
FROM _lm_subtask_map m
JOIN tasks lm    ON lm.slug = 'language-modeling'
JOIN tasks child ON child.slug = m.child_task_slug
JOIN datasets d  ON d.slug = m.dataset_slug;

-- Sanity logging (visible via NOTICE when running with psql -e or via Python).
DO $$
DECLARE
    expected INTEGER;
    resolved INTEGER;
BEGIN
    SELECT COUNT(*) INTO expected FROM _lm_subtask_map;
    SELECT COUNT(*) INTO resolved FROM _lm_subtask_moves;
    RAISE NOTICE 'LM subtask map entries: %, resolved (existing dataset+child task): %',
                 expected, resolved;
END $$;

-- Move task_datasets rows from LM parent to the chosen child task.
INSERT INTO task_datasets
    (task_id, dataset_id, featured_rank, supports_harness, created_at, updated_at)
SELECT
    mv.child_task_id,
    td.dataset_id,
    td.featured_rank,
    td.supports_harness,
    td.created_at,
    NOW()
FROM task_datasets td
JOIN _lm_subtask_moves mv
  ON mv.lm_task_id = td.task_id
 AND mv.dataset_id = td.dataset_id
ON CONFLICT (task_id, dataset_id) DO UPDATE
SET supports_harness = EXCLUDED.supports_harness OR task_datasets.supports_harness,
    featured_rank   = COALESCE(task_datasets.featured_rank, EXCLUDED.featured_rank),
    updated_at      = NOW();

DELETE FROM task_datasets td
USING _lm_subtask_moves mv
WHERE td.task_id    = mv.lm_task_id
  AND td.dataset_id = mv.dataset_id;

-- Move task_dataset_metrics rows similarly.
INSERT INTO task_dataset_metrics
    (task_id, dataset_id, metric_id, created_at)
SELECT
    mv.child_task_id,
    tdm.dataset_id,
    tdm.metric_id,
    tdm.created_at
FROM task_dataset_metrics tdm
JOIN _lm_subtask_moves mv
  ON mv.lm_task_id = tdm.task_id
 AND mv.dataset_id = tdm.dataset_id
ON CONFLICT (task_id, dataset_id, metric_id) DO NOTHING;

DELETE FROM task_dataset_metrics tdm
USING _lm_subtask_moves mv
WHERE tdm.task_id    = mv.lm_task_id
  AND tdm.dataset_id = mv.dataset_id;

-- Move evaluations to the child task. The PK is the synthetic `evaluations.id`
-- so a simple UPDATE is safe; ranks within each leaderboard are recalculated
-- by the Python wrapper after this SQL completes.
UPDATE evaluations e
SET task_id = mv.child_task_id,
    updated_at = NOW()
FROM _lm_subtask_moves mv
WHERE e.task_id = mv.lm_task_id
  AND e.dataset_id = mv.dataset_id;

-- Quick verification: nothing should remain on the parent for these datasets.
DO $$
DECLARE
    lm_id     INTEGER;
    leftover  INTEGER;
    eval_left INTEGER;
BEGIN
    SELECT id INTO lm_id FROM tasks WHERE slug = 'language-modeling';

    SELECT COUNT(*) INTO leftover
    FROM task_datasets td
    JOIN _lm_subtask_moves mv
      ON mv.lm_task_id = td.task_id
     AND mv.dataset_id = td.dataset_id;
    IF leftover > 0 THEN
        RAISE EXCEPTION 'task_datasets still references LM parent for % mapped datasets', leftover;
    END IF;

    SELECT COUNT(*) INTO eval_left
    FROM evaluations e
    JOIN _lm_subtask_moves mv
      ON mv.lm_task_id = e.task_id
     AND mv.dataset_id = e.dataset_id;
    IF eval_left > 0 THEN
        RAISE EXCEPTION 'evaluations still on LM parent for % mapped datasets', eval_left;
    END IF;

    RAISE NOTICE 'LM subtask migration: parent (id=%) cleared of mapped benchmarks', lm_id;
END $$;

-- Note: We intentionally skip COMMENT ON COLUMN here because the migration
-- user does not own the `tasks` table. The schema documentation in
-- `docs/DATABASE_SCHEMA_UML.md` covers the same intent: subtasks are child
-- tasks (`tasks.parent_id`), and benchmarks/evaluations should target the most
-- specific node in the hierarchy.

COMMIT;
