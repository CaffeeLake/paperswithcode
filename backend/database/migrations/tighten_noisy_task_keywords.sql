-- Tighten task keywords that repeatedly produced false-positive tags in the
-- 2026-06-29 through 2026-07-19 Hugging Face daily-paper cohorts.
--
-- Generic model-family names (LLM, VLM, MLLM) describe the system being used,
-- not necessarily the task being studied. Likewise, NeRF/Gaussian Splatting
-- are methods used across several 3D tasks, bare "QA" is ambiguous, and
-- "video understanding" does not imply video classification.

UPDATE tasks
SET keywords = 'language modeling, language modelling, language generation, text generation, next-token prediction, next token prediction, autoregressive language model, masked language model, causal language model, language model pretraining, language model training, diffusion language model, speech language model',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'language-modeling';

UPDATE tasks
SET keywords = 'image understanding, visual understanding, visual reasoning, fine-grained visual reasoning, image reasoning, image perception, visual perception, visual question answering, VQA',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'image-understanding';

UPDATE tasks
SET keywords = 'question answering, reading comprehension, machine comprehension',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'question-answering';

UPDATE tasks
SET keywords = 'video classification, action recognition, temporal classification',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'video-classification';

UPDATE tasks
SET keywords = '3d generation, 3d generative model, 3d asset generation, 3d scene generation, image-to-3d, image to 3d, text-to-3d, text to 3d, multi-view generation',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = '3d-generation';

UPDATE tasks
SET keywords = 'novel view synthesis, NVS, view synthesis, novel-view synthesis, neural rendering, radiance field, radiance fields, sparse-view reconstruction, sparse view synthesis, generalizable novel view synthesis',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'novel-view-synthesis';
