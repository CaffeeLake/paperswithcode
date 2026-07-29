export type FrameworkPlatform = "gpu" | "cpu" | "apple";

export interface Framework {
  slug: string;
  name: string;
  org?: string;
  description: string;
  whenToUse?: string;
  platforms?: FrameworkPlatform[];
  github?: string;
  url?: string;
  paperId?: string;
}

export interface FrameworkCategory {
  id: string;
  name: string;
  blurb?: string;
  guideUrl?: string;
  guideLabel?: string;
  frameworks: Framework[];
}

export interface FrameworkDomain {
  id: string;
  name: string;
  blurb: string;
  categories: FrameworkCategory[];
}

export const PLATFORM_LABELS: Record<FrameworkPlatform, string> = {
  gpu: "GPU",
  cpu: "CPU",
  apple: "Apple silicon",
};

export const FRAMEWORK_DOMAINS: FrameworkDomain[] = [
  {
    id: "llm",
    name: "Large Language Models",
    blurb:
      "Frameworks for running, serving, fine-tuning, and post-training LLMs — from local CPU inference to large-scale GPU serving and RL.",
    categories: [
      {
        id: "inference",
        name: "Inference & Serving",
        blurb:
          "Pick your inference engine based on hardware: GPU servers for throughput, CPU or Apple silicon for local/offline use.",
        guideUrl: "https://x.com/TheAhmadOsman/status/2057183854444843202",
        guideLabel: "2026 inference engine guide",
        frameworks: [
          {
            slug: "vllm",
            name: "vLLM",
            org: "vLLM Project",
            description: "High-throughput LLM serving with PagedAttention and continuous batching.",
            whenToUse: "Best when you have NVIDIA GPU compute and need production-grade throughput.",
            platforms: ["gpu"],
            github: "https://github.com/vllm-project/vllm",
            url: "https://docs.vllm.ai/",
            paperId: "2309.06180",
          },
          {
            slug: "sglang",
            name: "SGLang",
            org: "SGLang Project",
            description: "Fast structured generation and multi-model serving for LLMs and VLMs.",
            whenToUse: "Strong choice for GPU clusters, agentic workloads, and structured outputs.",
            platforms: ["gpu"],
            github: "https://github.com/sgl-project/sglang",
            url: "https://sgl-project.github.io/",
            paperId: "2312.07104",
          },
          {
            slug: "llama-cpp",
            name: "llama.cpp",
            org: "ggml-org",
            description: "Portable C/C++ inference for LLMs with broad quantization support.",
            whenToUse: "Run models locally on CPU or Apple silicon without a GPU.",
            platforms: ["cpu", "apple"],
            github: "https://github.com/ggml-org/llama.cpp",
          },
          {
            slug: "mlx-lm",
            name: "MLX-LM",
            org: "Apple MLX",
            description: "Run and fine-tune LLMs on Apple silicon using the MLX array framework.",
            whenToUse: "Native Mac inference and lightweight fine-tuning on M-series chips.",
            platforms: ["apple"],
            github: "https://github.com/ml-explore/mlx-lm",
            url: "https://ml-explore.github.io/mlx/build/html/index.html",
          },
          {
            slug: "mlx-vlm",
            name: "MLX-VLM",
            org: "Blaizzy",
            description: "Inference and fine-tuning for vision-language models on Mac via MLX.",
            whenToUse: "Multimodal models (image + text) on Apple silicon.",
            platforms: ["apple"],
            github: "https://github.com/Blaizzy/mlx-vlm",
          },
          {
            slug: "ollama",
            name: "Ollama",
            org: "Ollama",
            description: "Easy local model pulling, quantization, and chat API for developers.",
            whenToUse: "Quick local prototyping — abstracts away model download and runtime setup.",
            platforms: ["cpu", "apple", "gpu"],
            github: "https://github.com/ollama/ollama",
            url: "https://ollama.com/",
          },
        ],
      },
      {
        id: "training",
        name: "Training & Fine-tuning",
        blurb:
          "Libraries for supervised fine-tuning (SFT), preference optimization (RLHF), and reinforcement learning from verifiable rewards (RLVR).",
        frameworks: [
          {
            slug: "trl",
            name: "TRL",
            org: "Hugging Face",
            description: "Transformer Reinforcement Learning — SFT, DPO, PPO, GRPO, and reward modeling.",
            whenToUse: "The standard Hugging Face stack for both SFT and RL-style post-training.",
            platforms: ["gpu"],
            github: "https://github.com/huggingface/trl",
            url: "https://huggingface.co/docs/trl/",
          },
          {
            slug: "unsloth",
            name: "Unsloth",
            org: "Unsloth AI",
            description: "Memory-efficient, fast fine-tuning and RL for LLMs with optimized kernels.",
            whenToUse: "Fast iteration on SFT and RL when VRAM or training speed is the bottleneck.",
            platforms: ["gpu"],
            github: "https://github.com/unslothai/unsloth",
            url: "https://docs.unsloth.ai/",
          },
          {
            slug: "prime-rl",
            name: "prime-rl",
            org: "Prime Intellect",
            description: "Agentic RL training at scale with distributed rollout and training loops.",
            whenToUse: "Large-scale RL for agents and tool-use when you need custom distributed training.",
            platforms: ["gpu"],
            github: "https://github.com/PrimeIntellect-ai/prime-rl",
          },
          {
            slug: "verl",
            name: "verl",
            org: "HybridFlow",
            description: "Flexible RL post-training framework (HybridFlow) for LLM alignment at scale.",
            whenToUse: "Production RL post-training pipelines — PPO, GRPO, and custom reward functions.",
            platforms: ["gpu"],
            github: "https://github.com/verl-project/verl",
            url: "https://verl.readthedocs.io/",
            paperId: "2409.19256",
          },
        ],
      },
      {
        id: "model-libraries",
        name: "Model Libraries",
        blurb:
          "General-purpose libraries for loading, training, evaluating, and sharing language and multimodal models.",
        frameworks: [
          {
            slug: "transformers",
            name: "Transformers",
            org: "Hugging Face",
            description:
              "A broad model library for text, vision, audio, video, and multimodal architectures.",
            whenToUse:
              "Use pretrained models or fine-tune modern architectures through a consistent PyTorch interface.",
            platforms: ["gpu", "cpu", "apple"],
            github: "https://github.com/huggingface/transformers",
            url: "https://huggingface.co/docs/transformers/",
            paperId: "1910.03771",
          },
        ],
      },
    ],
  },
  {
    id: "computer-vision",
    name: "Computer Vision",
    blurb:
      "Libraries for image encoders, visual backbones, training recipes, and reusable computer-vision models.",
    categories: [
      {
        id: "vision-model-libraries",
        name: "Model Libraries",
        blurb:
          "Reusable image architectures and pretrained backbones for training, evaluation, and transfer learning.",
        frameworks: [
          {
            slug: "timm",
            name: "timm",
            org: "Hugging Face",
            description:
              "A large collection of PyTorch image models, pretrained weights, layers, optimizers, and training utilities.",
            whenToUse:
              "Start from a proven vision backbone or compare image architectures through one consistent API.",
            platforms: ["gpu", "cpu", "apple"],
            github: "https://github.com/huggingface/pytorch-image-models",
            url: "https://huggingface.co/docs/timm/",
          },
        ],
      },
    ],
  },
  {
    id: "image-video-generation",
    name: "Image and video generation",
    blurb:
      "Frameworks for building, running, and accelerating image and video generation workflows.",
    categories: [
      {
        id: "generation-inference",
        name: "Generation & Inference",
        blurb:
          "Libraries, interfaces, and inference engines for diffusion and diffusion-transformer models.",
        frameworks: [
          {
            slug: "diffusers",
            name: "Diffusers",
            org: "Hugging Face",
            description:
              "A modular PyTorch library for pretrained diffusion models across image, video, and audio generation.",
            whenToUse:
              "Build or train customizable generation pipelines with a broad model ecosystem.",
            platforms: ["gpu"],
            github: "https://github.com/huggingface/diffusers",
            url: "https://huggingface.co/docs/diffusers/",
          },
          {
            slug: "comfyui",
            name: "ComfyUI",
            org: "Comfy Org",
            description:
              "A node-based interface, API, and backend for composing diffusion generation workflows.",
            whenToUse:
              "Design and share visual generation pipelines without wiring every step in code.",
            platforms: ["gpu"],
            github: "https://github.com/comfy-org/comfyui",
          },
          {
            slug: "sglang-diffusion",
            name: "SGLang Diffusion",
            org: "SGLang Project",
            description:
              "A high-performance serving framework for image and video generation models.",
            whenToUse:
              "Serve diffusion models with production-oriented throughput and distributed execution.",
            platforms: ["gpu"],
            github: "https://github.com/sgl-project/sglang",
            url: "https://docs.sglang.io/docs/sglang-diffusion/index",
          },
          {
            slug: "cache-dit",
            name: "Cache-DiT",
            org: "Vipshop",
            description:
              "A PyTorch-native inference engine with caching, parallelism, quantization, and CPU offload for DiTs.",
            whenToUse:
              "Speed up diffusion-transformer inference with composable acceleration techniques.",
            platforms: ["gpu"],
            github: "https://github.com/vipshop/cache-dit",
          },
          {
            slug: "fastvideo",
            name: "FastVideo",
            org: "Hao AI Lab",
            description:
              "A unified inference and post-training framework for accelerated video generation.",
            whenToUse:
              "Train, fine-tune, or serve video generation models in one optimized framework.",
            platforms: ["gpu"],
            github: "https://github.com/hao-ai-lab/FastVideo",
          },
          {
            slug: "xdit",
            name: "xDiT",
            org: "xDiT Project",
            description:
              "A scalable inference engine for diffusion transformers using multiple parallelism strategies.",
            whenToUse:
              "Scale large image and video diffusion transformers across multiple GPUs.",
            platforms: ["gpu"],
            github: "https://github.com/xdit-project/xDiT",
          },
        ],
      },
    ],
  },
  {
    id: "robotics",
    name: "Robotics",
    blurb:
      "Frameworks for collecting robot data, training embodied policies, evaluating behavior, and deploying models to hardware.",
    categories: [
      {
        id: "robot-learning",
        name: "Robot Learning",
        blurb:
          "End-to-end libraries for datasets, imitation and reinforcement learning, vision-language-action policies, and robot control.",
        frameworks: [
          {
            slug: "lerobot",
            name: "LeRobot",
            org: "Hugging Face",
            description:
              "An open-source PyTorch library for real-world robotics with datasets, policies, training, evaluation, and hardware integrations.",
            whenToUse:
              "Build an end-to-end robot-learning workflow or reproduce modern policies across supported hardware.",
            platforms: ["gpu", "cpu"],
            github: "https://github.com/huggingface/lerobot",
            url: "https://huggingface.co/docs/lerobot/",
            paperId: "2602.22818",
          },
        ],
      },
    ],
  },
];
