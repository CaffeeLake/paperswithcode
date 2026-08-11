-- Add research task pages identified during the May-July 2026 daily-paper audit.

BEGIN;

INSERT INTO tasks (
    name, slug, description, keywords, area_id, level, parent_id,
    is_visible, image_url, image_credit, useful_leaderboards
)
VALUES
    (
        'Video Editing',
        'video-editing',
        'Video editing transforms an existing video according to a user instruction while preserving content that should remain unchanged. It includes local and global edits, object and attribute changes, motion edits, style transfer, and temporally coherent video-to-video transformation, complementing [Video generation](/tasks/video-generation) and [Image Editing](/tasks/image-editing).',
        'video editing, video edit, text-guided video editing, instruction-based video editing, instruction-guided video editing, video-to-video editing, audio-video editing',
        (SELECT id FROM areas WHERE name = 'Video' LIMIT 1),
        0,
        NULL,
        TRUE,
        NULL,
        '[CoVEBench: Benchmarking Compositional Video Editing](/paper/2606.08415)',
        NULL
    ),
    (
        'Visual Grounding',
        'visual-grounding',
        'Visual grounding connects natural-language expressions to the corresponding objects, regions, or pixels in an image or video. Systems may localize referred entities with boxes, masks, points, or grounded multimodal responses, bridging [Image Understanding](/tasks/image-understanding) and detection or segmentation tasks.',
        'visual grounding, phrase grounding, referring expression comprehension, pixel grounding, grounded visual reasoning',
        (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
        0,
        NULL,
        TRUE,
        NULL,
        '[Grounding DINO: Marrying DINO with Grounded Pre-Training for Open-Set Object Detection](/paper/2303.05499)',
        NULL
    ),
    (
        'Deep Research Agents',
        'deep-research-agents',
        'Deep research agents plan and execute multi-step investigations over web, document, and tool-based sources, then synthesize evidence into a cited answer or report. Evaluation emphasizes retrieval breadth, source quality, factual synthesis, citation support, and robustness on long-horizon research questions.',
        'deep research agent, deep-research agent, deep research system, deep research benchmark, deepresearch agent',
        (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
        1,
        (SELECT id FROM tasks WHERE slug = 'agents' LIMIT 1),
        TRUE,
        NULL,
        '[MiroEval: A Benchmark for Multimodal Deep Research Agents](/paper/2603.28407)',
        NULL
    ),
    (
        'Membership Inference',
        'membership-inference',
        'Membership inference determines whether a particular example was included in a model''s training data. The task is used to measure memorization and privacy leakage, audit machine-learning systems, and compare attacks under controlled member and non-member data distributions.',
        'membership inference attack, membership inference attacks, membership inference auditing, training data membership inference',
        (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
        0,
        NULL,
        TRUE,
        NULL,
        '[CheckMIABench: Firm Foundations For Membership Inference Attacks on Language Models](/paper/2606.17464)',
        NULL
    ),
    (
        'Full-Duplex Spoken Dialogue',
        'full-duplex-spoken-dialogue',
        'Full-duplex spoken dialogue models listen and speak concurrently, enabling natural turn-taking, interruptions, backchannels, and low-latency conversational overlap. Unlike cascaded turn-based voice systems, they model bidirectional audio streams continuously during interaction.',
        'full-duplex speech, full duplex speech, full-duplex spoken dialogue, full duplex spoken dialogue, full-duplex dialogue, full duplex dialogue',
        (SELECT id FROM areas WHERE name = 'Audio' LIMIT 1),
        0,
        NULL,
        TRUE,
        NULL,
        '[Moshi: a speech-text foundation model for real-time dialogue](/paper/2410.00037)',
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

-- Ensure each task's representative paper is present even when its title or
-- abstract does not contain every keyword used by the automated backfill.
INSERT INTO paper_tasks (paper_id, task_id, source)
SELECT p.id, t.id, 'manual'
FROM (VALUES
    ('2606.08415', 'video-editing'),
    ('2303.05499', 'visual-grounding'),
    ('2603.28407', 'deep-research-agents'),
    ('2606.17464', 'membership-inference'),
    ('2410.00037', 'full-duplex-spoken-dialogue')
) AS v(arxiv_id, task_slug)
JOIN papers p ON p.arxiv_id = v.arxiv_id AND p.is_latest_version
JOIN tasks t ON t.slug = v.task_slug
ON CONFLICT (paper_id, task_id) DO UPDATE SET source = 'manual';

COMMIT;
