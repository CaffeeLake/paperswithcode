-- Structured editorial summaries shown below task descriptions.

BEGIN;

ALTER TABLE tasks
ADD COLUMN IF NOT EXISTS research_trends JSONB;

COMMENT ON COLUMN tasks.research_trends IS
'Exactly three editorial bullets summarizing the task field direction; Markdown is supported.';

UPDATE tasks
SET research_trends = jsonb_build_array(
    'The transition from classic detector-recognizer pipelines toward end-to-end pretrained models began with work such as [TrOCR](/paper/2109.10282) and [Donut](/paper/2111.15664). Recent document VLMs extend this idea from text transcription to unified parsing that preserves reading order, layout, tables, formulas, and visual regions in structured outputs.',
    'High-resolution accuracy and inference efficiency are now a central frontier: [MinerU2.5](/paper/2509.22186) combines low-resolution layout analysis with native-resolution crops, [Unlimited OCR](/paper/2606.23050) keeps the KV cache constant during long multi-page generation, and [HunyuanOCR-1.5](/paper/2607.04884) accelerates dense structured decoding while retaining a lightweight model.',
    'Recent performance gains increasingly come from data curation and post-training rather than indiscriminate scaling: [PaddleOCR-VL-1.6](/paper/2606.03264) targets underperforming document regions with curated data and progressive reinforcement learning, while [OvisOCR2](/paper/2607.13639) combines synthetic and real supervision, RL, on-policy distillation, and model fusion.'
),
updated_at = NOW()
WHERE slug = 'ocr';

ALTER TABLE tasks
DROP CONSTRAINT IF EXISTS tasks_research_trends_three_items;

ALTER TABLE tasks
ADD CONSTRAINT tasks_research_trends_three_items
CHECK (
    research_trends IS NULL
    OR (
        jsonb_typeof(research_trends) = 'array'
        AND jsonb_array_length(research_trends) = 3
    )
);

COMMIT;
