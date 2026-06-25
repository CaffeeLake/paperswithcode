UPDATE methods
SET
    image_credit = '[Introducing Gemini 1.5, Google''s next-generation AI model](https://blog.google/innovation-and-ai/products/google-gemini-next-generation-model-february-2024/)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'gemini-1-5';
