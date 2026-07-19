-- Drop bare "tar" and "far" from face-verification keywords: they false-positive
-- on common English ("far from", "tar file") and unrelated metric mentions.

UPDATE tasks
SET keywords = 'face verification,face recognition,lfw,ijb',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'face-verification';
