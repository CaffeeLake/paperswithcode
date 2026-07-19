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
          },
        ],
      },
    ],
  },
];
