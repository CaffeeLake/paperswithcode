-- Add method pages identified during the May-July 2026 daily-paper audit.

BEGIN;

INSERT INTO methods (
    slug, name, full_name, description, keywords, area_id, introduced_year,
    source_paper_id, source_url, source_title, code_snippet_url,
    image_url, image_credit
)
VALUES
    (
        'bayesian-optimization',
        'Bayesian Optimization',
        'Bayesian Optimization',
        'Bayesian optimization is a sequential strategy for optimizing expensive black-box objectives. It uses a probabilistic surrogate, commonly a Gaussian process, and an acquisition function to balance exploration and exploitation when selecting the next evaluation.',
        'bayesian optimization, bayesian optimisation',
        (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
        2018,
        (SELECT id FROM papers WHERE arxiv_id = '1807.02811' AND is_latest_version ORDER BY id DESC LIMIT 1),
        NULL,
        'A Tutorial on Bayesian Optimization',
        NULL,
        NULL,
        '[A Tutorial on Bayesian Optimization](/paper/1807.02811)'
    ),
    (
        'agent-harness',
        'Agent Harness',
        'Agent Harness Engineering',
        'An agent harness is the execution layer around a model that defines its tool interface, prompts, context assembly, memory and workspace behavior, control loop, verification, recovery, and stopping policies. Harness engineering improves agent behavior without changing the underlying model weights.',
        'agent harness, agentic harness, harness engineering, model harness',
        (SELECT id FROM areas WHERE name = 'General' LIMIT 1),
        2026,
        (SELECT id FROM papers WHERE arxiv_id = '2603.25723' AND is_latest_version ORDER BY id DESC LIMIT 1),
        NULL,
        'Natural-Language Agent Harnesses',
        NULL,
        NULL,
        '[Natural-Language Agent Harnesses](/paper/2603.25723)'
    ),
    (
        'context-compression',
        'Context Compression',
        'Context and Prompt Compression',
        'Context compression reduces long prompts or retrieved context while retaining the information needed for a downstream model. Techniques include token pruning, extractive or abstractive compression, learned compressors, and query-aware filtering that reduce latency and inference cost.',
        'context compression, prompt compression, context compressor, compressed context',
        (SELECT id FROM areas WHERE name = 'Language' LIMIT 1),
        2023,
        (SELECT id FROM papers WHERE arxiv_id = '2310.05736' AND is_latest_version ORDER BY id DESC LIMIT 1),
        NULL,
        'LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models',
        NULL,
        NULL,
        '[LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models](/paper/2310.05736)'
    ),
    (
        'visual-token-pruning',
        'Visual Token Pruning',
        'Visual Token Pruning',
        'Visual token pruning removes or merges redundant image and video tokens during multimodal inference or training. By retaining tokens most relevant to the text query or model state, it reduces attention computation and memory while aiming to preserve visual reasoning quality.',
        'visual token pruning, vision token pruning, visual token reduction, visual token sparsification',
        (SELECT id FROM areas WHERE name = 'Vision' LIMIT 1),
        2024,
        (SELECT id FROM papers WHERE arxiv_id = '2403.06764' AND is_latest_version ORDER BY id DESC LIMIT 1),
        NULL,
        'An Image is Worth 1/2 Tokens After Layer 2: Plug-and-Play Inference Acceleration for Large Vision-Language Models',
        NULL,
        NULL,
        '[FastV: An Image is Worth 1/2 Tokens After Layer 2](/paper/2403.06764)'
    )
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    full_name = EXCLUDED.full_name,
    description = EXCLUDED.description,
    keywords = EXCLUDED.keywords,
    area_id = EXCLUDED.area_id,
    introduced_year = EXCLUDED.introduced_year,
    source_paper_id = EXCLUDED.source_paper_id,
    source_url = EXCLUDED.source_url,
    source_title = EXCLUDED.source_title,
    code_snippet_url = EXCLUDED.code_snippet_url,
    image_url = EXCLUDED.image_url,
    image_credit = EXCLUDED.image_credit,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO paper_methods (paper_id, method_id)
SELECT source_paper_id, id
FROM methods
WHERE slug IN (
    'bayesian-optimization', 'agent-harness',
    'context-compression', 'visual-token-pruning'
)
  AND source_paper_id IS NOT NULL
ON CONFLICT (paper_id, method_id) DO NOTHING;

COMMIT;
