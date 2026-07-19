-- Add "diffusion model" keyword for case-insensitive word-boundary matching on
-- title/abstract (also matches plural "diffusion models" via the matcher).

UPDATE methods
SET keywords = 'diffusion, DDPM, diffusion model',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'diffusion';
