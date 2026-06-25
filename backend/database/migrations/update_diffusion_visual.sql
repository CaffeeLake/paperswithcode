UPDATE methods
SET
    image_url = NULL,
    image_credit = '[Diffusion Models in Machine Learning](https://www.geeksforgeeks.org/artificial-intelligence/diffusion-models-in-machine-learning/)',
    updated_at = CURRENT_TIMESTAMP
WHERE slug = 'diffusion';
