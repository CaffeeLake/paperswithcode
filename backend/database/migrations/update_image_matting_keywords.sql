-- Tighten image-matting keywords: drop overly broad terms that tagged video
-- matting papers and unrelated work citing matting as related work.

UPDATE tasks
SET keywords = 'image matting, alpha matting, natural image matting, portrait matting, trimap-free matting, trimap-free portrait matting, background matting, human matting',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'image-matting';
