-- Credit the curated Healthcare & Medical AI task thumbnail.

BEGIN;

UPDATE tasks
SET image_credit = '[Medical AI photo by Vecteezy](https://www.vecteezy.com/free-photos/medical-ai)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'healthcare';

COMMIT;
