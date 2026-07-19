UPDATE tasks
SET
    image_url = NULL,
    image_credit = '[AI in Medical Imaging](https://pmwcintl.com/session/ai-in-medical-imaging_2022sv/)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'medical-imaging';
