INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES (
    'Healthcare',
    'healthcare',
    'Healthcare evaluates AI systems on clinical reasoning, medical knowledge, biomedical question answering, clinical dialogue, electronic health record workflows, and multimodal medical interpretation. It includes text-only and image-grounded medical tasks, complementing narrower areas such as [Medical Imaging](/tasks/medical-imaging).',
    'healthcare, health care, medical ai, medicine, clinical reasoning, medical reasoning, medical knowledge, medical question answering, clinical question answering, medical QA, clinical QA, biomedical question answering, healthcare AI, clinical AI, medical LLM, medical language model, medical multimodal model, clinical decision support, EHR, electronic health record, FHIR, medical calculator, medical calculation, diagnosis, differential diagnosis, physician, clinician',
    (SELECT id FROM areas WHERE name = 'Other' LIMIT 1),
    0,
    NULL,
    true,
    NULL,
    '[Medical Sphere](https://medicalsphere.ai/benchmarks)',
    'https://medicalsphere.ai/benchmarks'
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
