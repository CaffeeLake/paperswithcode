-- Image inpainting task (Vision): fill missing regions with coherent content.

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Image Inpainting',
    'image-inpainting',
    'Image inpainting reconstructs missing or masked regions in an image with semantically and visually coherent content. Methods range from patch-based and GAN-based fill to diffusion and latent diffusion models evaluated on scene benchmarks such as Places2 and portrait sets such as CelebA-HQ and FFHQ, complementing [Image Restoration](/tasks/image-restoration) and [Image generation](/tasks/image-generation).',
    'image inpainting, inpainting, image completion, hole filling, mask filling, free-form inpainting, semantic inpainting, portrait inpainting, object removal, image fill',
    (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[Moebius: 0.2B Lightweight Image Inpainting Framework with 10B-Level Performance](/paper/2606.19195)',
    NULL
)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    level = EXCLUDED.level,
    parent_id = EXCLUDED.parent_id,
    is_visible = EXCLUDED.is_visible,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    useful_leaderboards = EXCLUDED.useful_leaderboards,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO task_sister_tasks (task_id, sister_task_id, display_order)
SELECT t.id, s.id, v.ord
FROM tasks t
CROSS JOIN (VALUES ('image-restoration', 0), ('image-generation', 1)) AS v(slug, ord)
JOIN tasks s ON s.slug = v.slug
WHERE t.slug = 'image-inpainting'
ON CONFLICT DO NOTHING;
