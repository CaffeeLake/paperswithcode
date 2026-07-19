-- Tighten Motion Generation task keywords: focus on skeletal / text-to-motion synthesis,
-- not avatar rendering, video generation, rigging, or motion prediction.

UPDATE tasks
SET keywords = 'text-to-motion, text-driven human motion, text-driven motion generation, human motion generation, human motion synthesis, generating human motion, 3d human motion generation, whole-body motion generation, human interaction generation, motion synthesis, motion diffusion, skeletal motion generation, video-to-motion, dance generation, music-conditioned dance, text-guided motion generation, motion inpainting, physics-based character control, open-vocabulary motion generation, motion-language',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'motion-generation';
