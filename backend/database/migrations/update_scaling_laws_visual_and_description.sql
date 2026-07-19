-- Update Scaling Laws method hero image and add Lilian Weng explainer to description.
UPDATE methods
SET
    description = 'Scaling laws are predictable relationships that describe how the properties or performance of a system change as its scale or size is increased, often following a power-law function. In artificial intelligence, these laws explain how AI model performance improves with larger datasets, more parameters, and greater computational resources, providing insights for designing and training more effective models.

**Recommended read:** [Scaling Laws, Carefully](https://lilianweng.github.io/posts/2026-06-24-scaling-laws/).',
    source_url = NULL,
    image_url = NULL,
    image_credit = '[The Scaling Paradox](https://www.tobyord.com/writing/the-scaling-paradox)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'scaling-laws';
