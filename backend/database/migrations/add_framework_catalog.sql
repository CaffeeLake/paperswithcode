-- Promote the curated framework catalogue to normalized, database-backed entities.
-- The legacy task_recommended_frameworks table remains for rollback compatibility.

BEGIN;

CREATE TABLE IF NOT EXISTS framework_domains (
    id BIGSERIAL PRIMARY KEY,
    slug VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    description TEXT NOT NULL,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS framework_categories (
    id BIGSERIAL PRIMARY KEY,
    domain_id BIGINT NOT NULL REFERENCES framework_domains(id) ON DELETE CASCADE,
    slug VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    guide_url VARCHAR(2000),
    guide_label VARCHAR(255),
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT framework_categories_domain_slug_key UNIQUE (domain_id, slug)
);
CREATE INDEX IF NOT EXISTS idx_framework_categories_domain_id ON framework_categories(domain_id);

CREATE TABLE IF NOT EXISTS frameworks (
    id BIGSERIAL PRIMARY KEY,
    category_id BIGINT NOT NULL REFERENCES framework_categories(id) ON DELETE CASCADE,
    repository_id BIGINT REFERENCES repositories(id) ON DELETE SET NULL,
    introducing_paper_id BIGINT REFERENCES papers(id) ON DELETE SET NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    name VARCHAR(255) NOT NULL,
    organization_name VARCHAR(255),
    description TEXT NOT NULL,
    when_to_use TEXT,
    docs_url VARCHAR(2000),
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_frameworks_category_id ON frameworks(category_id);
CREATE INDEX IF NOT EXISTS idx_frameworks_repository_id ON frameworks(repository_id);
CREATE INDEX IF NOT EXISTS idx_frameworks_introducing_paper_id ON frameworks(introducing_paper_id);

CREATE TABLE IF NOT EXISTS framework_platforms (
    framework_id BIGINT NOT NULL REFERENCES frameworks(id) ON DELETE CASCADE,
    platform VARCHAR(20) NOT NULL,
    PRIMARY KEY (framework_id, platform),
    CONSTRAINT framework_platforms_platform_check CHECK (platform IN ('gpu', 'cpu', 'apple'))
);

CREATE TABLE IF NOT EXISTS task_frameworks (
    task_id BIGINT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    framework_id BIGINT NOT NULL REFERENCES frameworks(id) ON DELETE CASCADE,
    display_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (task_id, framework_id)
);
CREATE INDEX IF NOT EXISTS idx_task_frameworks_task_id ON task_frameworks(task_id);
CREATE INDEX IF NOT EXISTS idx_task_frameworks_framework_id ON task_frameworks(framework_id);

INSERT INTO framework_domains (slug, name, description, display_order)
VALUES
    ('llm', 'Large Language Models', 'Frameworks for running, serving, fine-tuning, and post-training LLMs — from local CPU inference to large-scale GPU serving and RL.', 0),
    ('computer-vision', 'Computer Vision', 'Libraries for image encoders, visual backbones, training recipes, and reusable computer-vision models.', 1),
    ('image-video-generation', 'Image and video generation', 'Frameworks for building, running, and accelerating image and video generation workflows.', 2),
    ('robotics', 'Robotics', 'Frameworks for collecting robot data, training embodied policies, evaluating behavior, and deploying models to hardware.', 3)
ON CONFLICT (slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    display_order = EXCLUDED.display_order,
    updated_at = now();

WITH category_data(domain_slug, slug, name, description, guide_url, guide_label, display_order) AS (
    VALUES
        ('llm', 'inference', 'Inference & Serving', 'Pick your inference engine based on hardware: GPU servers for throughput, CPU or Apple silicon for local/offline use.', 'https://x.com/TheAhmadOsman/status/2057183854444843202', '2026 inference engine guide', 0),
        ('llm', 'training', 'Training & Fine-tuning', 'Libraries for supervised fine-tuning (SFT), preference optimization (RLHF), and reinforcement learning from verifiable rewards (RLVR).', NULL, NULL, 1),
        ('llm', 'model-libraries', 'Model Libraries', 'General-purpose libraries for loading, training, evaluating, and sharing language and multimodal models.', NULL, NULL, 2),
        ('computer-vision', 'vision-model-libraries', 'Model Libraries', 'Reusable image architectures and pretrained backbones for training, evaluation, and transfer learning.', NULL, NULL, 0),
        ('image-video-generation', 'generation-inference', 'Generation & Inference', 'Libraries, interfaces, and inference engines for diffusion and diffusion-transformer models.', NULL, NULL, 0),
        ('robotics', 'robot-learning', 'Robot Learning', 'End-to-end libraries for datasets, imitation and reinforcement learning, vision-language-action policies, and robot control.', NULL, NULL, 0)
)
INSERT INTO framework_categories (domain_id, slug, name, description, guide_url, guide_label, display_order)
SELECT d.id, c.slug, c.name, c.description, c.guide_url, c.guide_label, c.display_order
FROM category_data c
JOIN framework_domains d ON d.slug = c.domain_slug
ON CONFLICT (domain_id, slug) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    guide_url = EXCLUDED.guide_url,
    guide_label = EXCLUDED.guide_label,
    display_order = EXCLUDED.display_order,
    updated_at = now();

WITH framework_data(
    domain_slug, category_slug, slug, name, organization_name, description,
    when_to_use, github_url, docs_url, paper_arxiv_id, platforms, display_order
) AS (
    VALUES
        ('llm','inference','vllm','vLLM','vLLM Project','High-throughput LLM serving with PagedAttention and continuous batching.','Best when you have NVIDIA GPU compute and need production-grade throughput.','https://github.com/vllm-project/vllm','https://docs.vllm.ai/','2309.06180','gpu',0),
        ('llm','inference','sglang','SGLang','SGLang Project','Fast structured generation and multi-model serving for LLMs and VLMs.','Strong choice for GPU clusters, agentic workloads, and structured outputs.','https://github.com/sgl-project/sglang','https://sgl-project.github.io/','2312.07104','gpu',1),
        ('llm','inference','llama-cpp','llama.cpp','ggml-org','Portable C/C++ inference for LLMs with broad quantization support.','Run models locally on CPU or Apple silicon without a GPU.','https://github.com/ggml-org/llama.cpp',NULL,NULL,'cpu,apple',2),
        ('llm','inference','mlx-lm','MLX-LM','Apple MLX','Run and fine-tune LLMs on Apple silicon using the MLX array framework.','Native Mac inference and lightweight fine-tuning on M-series chips.','https://github.com/ml-explore/mlx-lm','https://ml-explore.github.io/mlx/build/html/index.html',NULL,'apple',3),
        ('llm','inference','mlx-vlm','MLX-VLM','Blaizzy','Inference and fine-tuning for vision-language models on Mac via MLX.','Multimodal models (image + text) on Apple silicon.','https://github.com/Blaizzy/mlx-vlm',NULL,NULL,'apple',4),
        ('llm','inference','ollama','Ollama','Ollama','Easy local model pulling, quantization, and chat API for developers.','Quick local prototyping — abstracts away model download and runtime setup.','https://github.com/ollama/ollama','https://ollama.com/',NULL,'cpu,apple,gpu',5),
        ('llm','training','trl','TRL','Hugging Face','Transformer Reinforcement Learning — SFT, DPO, PPO, GRPO, and reward modeling.','The standard Hugging Face stack for both SFT and RL-style post-training.','https://github.com/huggingface/trl','https://huggingface.co/docs/trl/',NULL,'gpu',0),
        ('llm','training','unsloth','Unsloth','Unsloth AI','Memory-efficient, fast fine-tuning and RL for LLMs with optimized kernels.','Fast iteration on SFT and RL when VRAM or training speed is the bottleneck.','https://github.com/unslothai/unsloth','https://docs.unsloth.ai/',NULL,'gpu',1),
        ('llm','training','prime-rl','prime-rl','Prime Intellect','Agentic RL training at scale with distributed rollout and training loops.','Large-scale RL for agents and tool-use when you need custom distributed training.','https://github.com/PrimeIntellect-ai/prime-rl',NULL,NULL,'gpu',2),
        ('llm','training','verl','verl','HybridFlow','Flexible RL post-training framework (HybridFlow) for LLM alignment at scale.','Production RL post-training pipelines — PPO, GRPO, and custom reward functions.','https://github.com/verl-project/verl','https://verl.readthedocs.io/','2409.19256','gpu',3),
        ('llm','model-libraries','transformers','Transformers','Hugging Face','A broad model library for text, vision, audio, video, and multimodal architectures.','Use pretrained models or fine-tune modern architectures through a consistent PyTorch interface.','https://github.com/huggingface/transformers','https://huggingface.co/docs/transformers/','1910.03771','gpu,cpu,apple',0),
        ('computer-vision','vision-model-libraries','timm','timm','Hugging Face','A large collection of PyTorch image models, pretrained weights, layers, optimizers, and training utilities.','Start from a proven vision backbone or compare image architectures through one consistent API.','https://github.com/huggingface/pytorch-image-models','https://huggingface.co/docs/timm/',NULL,'gpu,cpu,apple',0),
        ('image-video-generation','generation-inference','diffusers','Diffusers','Hugging Face','A modular PyTorch library for pretrained diffusion models across image, video, and audio generation.','Build or train customizable generation pipelines with a broad model ecosystem.','https://github.com/huggingface/diffusers','https://huggingface.co/docs/diffusers/',NULL,'gpu',0),
        ('image-video-generation','generation-inference','comfyui','ComfyUI','Comfy Org','A node-based interface, API, and backend for composing diffusion generation workflows.','Design and share visual generation pipelines without wiring every step in code.','https://github.com/comfy-org/comfyui',NULL,NULL,'gpu',1),
        ('image-video-generation','generation-inference','sglang-diffusion','SGLang Diffusion','SGLang Project','A high-performance serving framework for image and video generation models.','Serve diffusion models with production-oriented throughput and distributed execution.','https://github.com/sgl-project/sglang','https://docs.sglang.io/docs/sglang-diffusion/index',NULL,'gpu',2),
        ('image-video-generation','generation-inference','cache-dit','Cache-DiT','Vipshop','A PyTorch-native inference engine with caching, parallelism, quantization, and CPU offload for DiTs.','Speed up diffusion-transformer inference with composable acceleration techniques.','https://github.com/vipshop/cache-dit',NULL,NULL,'gpu',3),
        ('image-video-generation','generation-inference','fastvideo','FastVideo','Hao AI Lab','A unified inference and post-training framework for accelerated video generation.','Train, fine-tune, or serve video generation models in one optimized framework.','https://github.com/hao-ai-lab/fastvideo',NULL,NULL,'gpu',4),
        ('image-video-generation','generation-inference','xdit','xDiT','xDiT Project','A scalable inference engine for diffusion transformers using multiple parallelism strategies.','Scale large image and video diffusion transformers across multiple GPUs.','https://github.com/xdit-project/xdit',NULL,'2411.01738','gpu',5),
        ('robotics','robot-learning','lerobot','LeRobot','Hugging Face','An open-source PyTorch library for real-world robotics with datasets, policies, training, evaluation, and hardware integrations.','Build an end-to-end robot-learning workflow or reproduce modern policies across supported hardware.','https://github.com/huggingface/lerobot','https://huggingface.co/docs/lerobot/','2602.22818','gpu,cpu',0)
),
repos AS (
    INSERT INTO repositories (url, owner, name, num_stars, source)
    SELECT DISTINCT github_url,
        split_part(replace(github_url, 'https://github.com/', ''), '/', 1),
        split_part(replace(github_url, 'https://github.com/', ''), '/', 2),
        0, 'framework_catalog'
    FROM framework_data
    ON CONFLICT (url) DO UPDATE SET owner = EXCLUDED.owner, name = EXCLUDED.name
    RETURNING id, url
)
INSERT INTO frameworks (
    category_id, repository_id, introducing_paper_id, slug, name,
    organization_name, description, when_to_use, docs_url, display_order
)
SELECT c.id, r.id, p.id, f.slug, f.name, f.organization_name, f.description,
       f.when_to_use, f.docs_url, f.display_order
FROM framework_data f
JOIN framework_domains d ON d.slug = f.domain_slug
JOIN framework_categories c ON c.domain_id = d.id AND c.slug = f.category_slug
JOIN repos r ON r.url = f.github_url
LEFT JOIN LATERAL (
    SELECT id FROM papers
    WHERE arxiv_id = f.paper_arxiv_id AND is_latest_version
    ORDER BY id DESC LIMIT 1
) p ON true
ON CONFLICT (slug) DO UPDATE SET
    category_id = EXCLUDED.category_id,
    repository_id = EXCLUDED.repository_id,
    introducing_paper_id = COALESCE(
        EXCLUDED.introducing_paper_id,
        frameworks.introducing_paper_id
    ),
    name = EXCLUDED.name,
    organization_name = EXCLUDED.organization_name,
    description = EXCLUDED.description,
    when_to_use = EXCLUDED.when_to_use,
    docs_url = EXCLUDED.docs_url,
    display_order = EXCLUDED.display_order,
    updated_at = now();

WITH platform_data(slug, platforms) AS (
    VALUES
        ('vllm','gpu'),('sglang','gpu'),('llama-cpp','cpu,apple'),('mlx-lm','apple'),
        ('mlx-vlm','apple'),('ollama','cpu,apple,gpu'),('trl','gpu'),('unsloth','gpu'),
        ('prime-rl','gpu'),('verl','gpu'),('transformers','gpu,cpu,apple'),
        ('timm','gpu,cpu,apple'),('diffusers','gpu'),('comfyui','gpu'),
        ('sglang-diffusion','gpu'),('cache-dit','gpu'),('fastvideo','gpu'),
        ('xdit','gpu'),('lerobot','gpu,cpu')
)
INSERT INTO framework_platforms (framework_id, platform)
SELECT f.id, unnest(string_to_array(p.platforms, ','))
FROM platform_data p
JOIN frameworks f ON f.slug = p.slug
ON CONFLICT DO NOTHING;

INSERT INTO task_frameworks (task_id, framework_id, display_order)
SELECT legacy.task_id, selected.framework_id, legacy.display_order
FROM task_recommended_frameworks legacy
JOIN LATERAL (
    SELECT f.id AS framework_id
    FROM frameworks f
    JOIN framework_categories c ON c.id = f.category_id
    JOIN framework_domains d ON d.id = c.domain_id
    WHERE f.repository_id = legacy.repository_id
    ORDER BY d.display_order, c.display_order, f.display_order
    LIMIT 1
) selected ON true
ON CONFLICT (task_id, framework_id) DO UPDATE SET
    display_order = EXCLUDED.display_order;

COMMIT;
