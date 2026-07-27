# Image editing research-trends evidence map

Snapshot: 2026-07-22. This is the internal evidence matrix used to author the task page's three `research_trends` bullets.

| Paper | Unified multimodal editor | Deliberation / post-training | Efficiency / preservation |
|---|---|---|---|
| Prompt-to-Prompt (2208.01626) | Classic attention-map control over a pretrained diffusion model; represents the earlier task-specific, training-free paradigm. | — | Cross-attention injection preserves the original composition but still uses iterative diffusion. |
| InstructPix2Pix (2211.09800) | Pivotal shift to a single instruction-conditioned diffusion editor trained from synthetic edit pairs. | Its conclusion identifies spatial reasoning, human feedback, and evaluation as open problems. | Direct forward editing avoids per-example fine-tuning. |
| Qwen-Image (2508.02324) | Shared latent-space training across T2I, I2I, and text-guided editing; Qwen2.5-VL semantic features plus VAE reconstruction features condition an MMDiT. | Progressive training and data engineering improve prompt and edit alignment. | — |
| Emu3.5 (2510.26583) | Unified next-token prediction over more than 10T interleaved vision-language tokens; native any-to-image editing and interleaved generation. | Long-horizon native multimodal reasoning supplies world knowledge for open-world edits. | Supports multi-image input and outputs up to 2K. |
| NextFlow (2601.02204) | Decoder-only autoregressive transformer over unified text-image tokens with next-scale visual prediction. | RL-tuned variant leads or nearly leads the two most-reported editing boards. | Next-scale generation produces 1024×1024 outputs in under five seconds in the paper's setup. |
| ReasonEdit (2511.22625) | MLLM reasoner plus DiT generator. | Trains thinking and reflection so abstract requests become actionable edits and intermediate failures can be corrected. | Iterative stopping avoids unnecessary further refinement once the edit is satisfactory. |
| EditThinker (2512.05965) | Model-agnostic MLLM thinker wraps Qwen, FLUX, and OmniGen2 editors. | SFT and RL train a Critique–Refine–Repeat loop from ThinkEdit-140K trajectories. | Reuses existing editors rather than retraining each editing backbone. |
| Uni-Edit (2605.21487) | Treats intelligent editing as a general tuning task for unified multimodal models. | Uni-Edit-148K converts VQA into reasoning-intensive edits; tuning improves editing, understanding, and generation together. | Task-focused tuning avoids full unified-model retraining from scratch. |
| Mage-Flow (2607.19064) | Native-resolution MMDiT and lightweight Mage-VAE form one generation-and-editing stack. | Diffusion-NFT supplies post-training alignment. | About 2.5× training throughput plus four-step Turbo variants; the paper reports interactive 1024² latency. |
| VIBE (2601.02242) | Compact VLM, connector, and diffusion backbone jointly ground instructions in the source image. | Four-stage alignment, image-to-image pretraining, SFT, and DPO; teacher distillation and aggressive data filtering. | A compact 2B-class VLM plus 1.6B diffusion backbone targets low-cost inference and source consistency. |
| RegionE (2510.25590) | Applies to several existing foundation editors. | — | Training-free region-aware early prediction and velocity-decay caching remove spatial/temporal redundancy; reported 2.06–2.57× speedups. |

## Benchmark evidence

- GEdit-Bench (18 comparable papers) and ImgEdit-Bench (12) are the dominant shared reporting surfaces. Their leaders span unified editors, RL/post-trained variants, iterative reasoning wrappers, and compact models rather than one architecture family.
- PIE-Bench (4 papers) remains the strongest historical preservation-oriented board because it separates background PSNR/LPIPS, structure distance, and edit-region/whole-image CLIP.
- RISEBench and KRIS-Bench are sparse but coherent emerging reasoning boards. Their leading rows use explicit thinking, reflection, or reasoning-focused tuning.

## Selected directions

1. Unified multimodal editors replacing task-specific control pipelines.
2. Deliberation and post-training for reasoning-heavy editing.
3. Interactive efficiency co-designed with source preservation.
