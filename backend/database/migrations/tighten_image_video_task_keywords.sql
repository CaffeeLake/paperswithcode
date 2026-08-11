-- Keep task keywords about tasks rather than particular model families.
-- Image/video conflicts are resolved by title-aware rules in keyword_matching.py.

UPDATE tasks
SET keywords = 'image editing, image edit, text-guided image editing, instruction-based image editing, instruction-guided image editing, image-to-image editing',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'image-editing';

UPDATE tasks
SET keywords = 'image generation, text-to-image, image synthesis',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'image-generation';

UPDATE tasks
SET keywords = 'video generation, text-to-video, image-to-video',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'video-generation';

UPDATE tasks
SET keywords = 'video language model, video-language model, video-language-model, video LLM, video-LLM, video large multimodal model, video understanding, video reasoning, video perception, video question answering, video QA, VideoQA, video analysis',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'video-understanding';
