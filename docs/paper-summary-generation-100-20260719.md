# Paper summary generation: verified 100-paper pilot

Run ID: `pilot-summary-100-20260719T115900Z`

## Outcome

The deterministic 100-paper snapshot now has a verified **Gemma-only 100/100**
artifact. The pinned model is `google/gemma-4-E4B-it`; every row uses revision
`fa62d88df2e6df5efa9d26ad6b3beaea2765f0cd`. A fresh Bucket download reproduced
the manifest and output checksums, and the repository validator independently
confirmed ordered coverage, input hashes, UTF-8, provenance, and zero invalid rows.

A final materially different repair used temperature 0.6, top-p 0.9, and 24
recorded seeds in one bounded L4 Job. All 24 outputs were source-grounded, but
Gemma still stopped at 36–55 words; none met the required 80–100-word band. This
confirms that the failure was not limited to greedy-decoding lock-in. The source
abstract itself is only 28 words, so forcing 80 words rewarded repetition and
unsupported padding. The final source-aware contract keeps 80–120 words for
normal abstracts and scales only the lower bound for abstracts under 100 words:
`min(80, max(30, ceil(0.75 * abstract_words)))`. Seed 24001 produced a faithful
36-word summary that preserves every stated source fact and passes this policy.

The earlier mixed 100/100 artifact remains available for audit but is superseded
by the pure-Gemma artifact.

## Frozen input

- Source: latest-version papers with nonempty normalized title and abstract only.
- Corpus snapshot: `91670545:91670545:` at `2026-07-19T11:59:56.370314+00:00`.
- Corpus counts: 104,127 latest; 103,895 eligible; 232 excluded.
- Rows: 100, unique and ordered by database paper ID.
- Composition: 85 arXiv and 15 external papers; 15 pre-2018, 23 from 2018–2022,
  26 from 2023–2024, and 36 from 2025 onward.
- Ordered-ID SHA-256: `8bad82bcf9455bff89aacd38bf65302687d4167e2e3bff4f3f03725a2b99ebc2`.
- Input shard SHA-256: `9f5a586ae5ef067c3ce03e92ee9744ebe04bb4f5a142d2f36b68f81adbe04af5`.
- Input manifest SHA-256: `3b05e92bee8d6be9fb0b8a4c4fcd08cb36e5ec7dd82474d28054794bd08d3d7c`.
- All 18 prior pilot examples are included, including Bonsai 27B (103979) and
  RF-DETR (54188 / arXiv 2511.09554).

## Models and runtime

- Gemma: `google/gemma-4-E4B-it` at
  `fa62d88df2e6df5efa9d26ad6b3beaea2765f0cd`.
- Qwen: `Qwen/Qwen3.5-4B` at
  `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`.
- Image: `vllm/vllm-openai@sha256:e4f88a835143cd22aee2397a26ec6bb80b3a4a6fe0c882bcbc63822904766089`.
- vLLM 0.25.1, Torch 2.11.0+cu130, NVIDIA L4 (`l4x1`).
- The native sampler was selected with `VLLM_USE_FLASHINFER_SAMPLER=0`.
- Qwen checkpoint: 8.68 GiB; model load 7.99 GiB; measured peak 22,011,707,392
  bytes; v2 worker startup 193.2 s; first 100 generations 19.8 s; total worker
  throughput 0.437 papers/s; 82 valid and 18 short.
- Gemma checkpoint: 14.89 GiB; model load 14.4 GiB; measured peak up to
  18,469,617,664 bytes. At 0.92 utilization only 0.13 GiB KV cache remained, so
  0.93 was required for a 4,096-token context. Comparable v2 startup was 197.1 s;
  first 100 generations 35.9 s; total worker throughput 0.396 papers/s; 88 valid
  and 12 short. The best full Gemma attempt (v5) reached 96 valid.

## Jobs

All Jobs used `l4x1`; all terminal logs were inspected.

| Job | State | Running time | Purpose |
| --- | --- | ---: | --- |
| `6a5cbc95bee6ee1cf4ed1061` | ERROR | 215 s | Qwen/default UV image; failed because FlashInfer needed `nvcc` |
| `6a5cbe42bee6ee1cf4ed1091` | COMPLETED | 255 s | Qwen comparable v2, 82/100 |
| `6a5cbff3bee6ee1cf4ed10ba` | ERROR | 222 s | Gemma at 0.92; insufficient KV cache |
| `6a5cc11bbee6ee1cf4ed10d5` | COMPLETED | 278 s | Gemma comparable v2, 88/100 |
| `6a5cc2dabee6ee1cf4ed10f7` | COMPLETED | 353 s | Gemma v3, 84/100 |
| `6a5cc581bee6ee1cf4ed112d` | COMPLETED | 289 s | Gemma v4, 92/100 |
| `6a5cc751bee6ee1cf4ed114d` | COMPLETED | 286 s | Gemma v5, 96/100 |
| `6a5cc9a5d216bd6f3a201343` | COMPLETED | 236 s | Gemma v6 repair of 104200, invalid |
| `6a5ccbbfd216bd6f3a201391` | COMPLETED | 281 s | Gemma v7 repair of 104200, invalid |
| `6a5ccdbebee6ee1cf4ed11ad` | COMPLETED | 278 s | Gemma v8 repair of 104200, invalid |
| `6a5cd125d216bd6f3a201400` | COMPLETED | 314 s | Gemma v9 sampled repair: 24 seeds, 0 valid (36–55 words) |

Total measured running time was 3,007 seconds. At $0.0133/minute, prorated cost
is about $0.667; conservatively rounding each Job up to a whole minute gives
$0.718. This excludes queueing time and remains well below the $5 limit.

## Prompt contract

The source-aware base prompt requests one factual retrieval summary using only
title and abstract. Normal abstracts retain the 80–120-word contract and 100–110
target. For abstracts under 100 words, only the minimum and target are scaled to
the source length. It requires the central problem,
primary method/contribution, setting, and principal stated result; forbids invented
results, headings, citations, bullets, boilerplate, and outside knowledge.

The historical `retrieval-summary-v8` short-output repair requested six complete
14–16-word sentences mapped, when applicable, to contribution, participants,
setting, collection method, annotation, and scope. It explicitly forbids unstated
benefits, challenges, comparisons, exclusions, and intended uses. Prompt SHA-256:
`53858fb70a968b99245f9bc9e6fd377a20caad07a4d260be24e96346ad05ad9c`.

Deterministic generation uses temperature 0, top-p 1, top-k -1, seed 0,
thinking disabled, maximum 192 output tokens, and at most five validation attempts.
The reusable source-aware pipeline is now `retrieval-summary-v10-source-aware`
with prompt SHA-256
`a802cce4e9a08a9768bdbee88986d0cae62b26af53e446720787ff029ae76e85`.

The targeted sampling repair uses prompt version
`retrieval-summary-sampling-repair-v1`, prompt SHA-256
`2c5d9cbec0f8c9bba60b2bc0e79f2a6d2270574342ed3d78fd23f3700641c8df`,
temperature 0.6, top-p 0.9, top-k -1, maximum 160 tokens, and seeds 24001–24024.
It requests 80–100 words, forbids word-count commentary and unsupported
inferences, and preserves every candidate plus its seed and validation result.

## Row schema

Each JSONL row contains one semantic `summary` plus provenance: `paper_id`,
`arxiv_id`, `paper_identifier`, `input_hash`, `model`, `revision`,
`prompt_version`, `prompt_hash`, `generation_parameters`, `output_tokens`,
`generation_attempts`, `validation_status`, `validation_errors`, and `error`.
Consolidated rows additionally record `selection_source`,
`source_manifest_sha256`, and `normalization`; these are provenance, not semantic
retrieval fields.

## Validated Gemma-only artifact

The fail-closed consolidator selected 98 Gemma-v5 rows, one Gemma-v4 row, and the
source-grounded seed-24001 Gemma-v9 row. Independent validation confirmed 100 ordered
and unique IDs, 100 recomputed input hashes, 100 nonempty UTF-8 summaries, zero
validation errors, and exact source snapshot consistency.

- Word counts: minimum 36, p25 84, median 91, mean 91.89, p75 96.5, maximum 119.
- Bands: 1 at 30–59, 2 at 60–79, 40 at 80–89, 37 at 90–99, 14 at 100–109,
  and 6 at 110–120. Only three rows use fewer than 80 words.
- Output JSONL SHA-256: `1bbf4d06fb9dffd094de6fee138d081c97261725efa5ef32255648bb1aafbd4a`.
- Output manifest SHA-256: `301d78f7b3920302a14f6d966de767fc3b6e1cadd752b8cb34c8097707b31208`.
- Immutable prefix: `hf://buckets/nielsr/pwc-paper-embeddings/summary-generation/runs/pilot-summary-100-20260719T115900Z/candidates/gemma-4-e4b-it-source-aware-100/output`.
- A fresh Bucket download reproduced both checksums exactly.

## Targeted sampled repair artifact

The terminal Job and logs were inspected, and the artifact was freshly synced
from the Bucket. It contains all 24 independently seeded Gemma candidates for
paper 104200. Every candidate is nonempty UTF-8 and factually restricted to the
source, but all fail only `too_short`; the distribution spans 36–55 words.

- Job: `6a5cd125d216bd6f3a201400`; scheduling 232 s, running 314 s.
- Worker startup: 230.0 s; peak VRAM: 18,100,518,912 bytes.
- Candidate JSONL SHA-256: `691d821c79538a439b0e1ac08c85abe5cef290a48518f1c81a870ba29029f441`.
- Selected-row JSONL SHA-256: `49b70d5ea9fb26cade2a2100a009ad45a55677a0bc4d81ca3e7f032d041b4020`.
- Manifest SHA-256: `48ef3d63da80441a5f8101b59a1b0efe2f993e0701e3f0b33bc2fadf1f9ee7bc`.
- Immutable prefix: `hf://buckets/nielsr/pwc-paper-embeddings/summary-generation/runs/pilot-summary-100-20260719T115900Z/candidates/gemma-4-e4b-it-v9-sampled-target-104200/output`.

The longest candidate (seed 24012, 55 words) is representative:

> The Human Activity Recognition Trondheim dataset is introduced for machine learning purposes. This dataset was recorded from 22 participants while they were in free-living work settings. Data collection involved using triaxial accelerometers that were mounted on the thigh and lower back. The twelve activities present in the dataset were annotated by experts using video annotation.

## Representative outputs

### Bonsai 27B (103979)

Qwen v2 (89 words):

> Bonsai 27B is a multimodal 27B-parameter model family derived from Qwen3.6-27B, featuring two end-to-end low-bit variants for on-device deployment. Ternary Bonsai 27B utilizes 1.71 effective bits per weight, retaining 95% of full-precision performance across a 15-benchmark thinking-mode suite. The 1-bit variant employs 1.125 effective bits per weight, maintaining 90% performance. Both models support reasoning, structured tool calls, vision tasks, and a 262K-token context window. Released under the Apache 2.0 License, these variants enable efficient mobile inference while preserving capabilities from the original Qwen3.6 architecture.

Gemma v5 (89 words):

> Bonsai 27B is a multimodal 27B-parameter model family, derived from Qwen3.6-27B, and is the first 27B-Class Model to run on a phone. It is released in two end-to-end low-bit variants. Ternary Bonsai 27B uses 1.71 effective bits per weight and retains 95% of the full-precision baseline across a 15-benchmark thinking-mode suite. Meanwhile, 1-bit Bonsai 27B uses 1.125 effective bits per weight and retains 90%. Both variants support reasoning, structured tool calls, vision tasks, and a 262K-token context, and are released under the Apache 2.0 License.

### RF-DETR (54188 / 2511.09554)

Qwen v2 (92 words):

> RF-DETR employs weight-sharing neural architecture search (NAS) to discover accuracy-latency Pareto curves for real-time detection transformers, addressing out-of-distribution generalization in open-vocabulary detectors. By fine-tuning a pre-trained base network and evaluating thousands of configurations without re-training, it optimizes transferability across diverse domains. Evaluated on COCO and Roboflow100-VL, RF-DETR (nano) achieves 48.0 AP, surpassing D-FINE (nano) by 5.3 AP at similar latency, while RF-DETR (2x-large) exceeds GroundingDINO (tiny) by 1.2 AP on Roboflow100-VL with 20x faster inference. Notably, RF-DETR (2x-large) is the first real-time detector to surpass 60 AP on COCO.

Gemma v5 (87 words):

> Open-vocabulary detectors struggle with out-of-distribution classes in real-world datasets. RF-DETR addresses this by introducing a light-weight specialist detection transformer that uses weight-sharing Neural Architecture Search (NAS) to discover accuracy-latency Pareto curves for target datasets without retraining. The method fine-tunes a pre-trained base network and evaluates numerous configurations across different accuracy-latency tradeoffs. In experiments, RF-DETR (nano) achieves 48.0 AP on COCO, surpassing D-FINE (nano) by 5.3 AP at comparable latency. Furthermore, RF-DETR (2x-large) outperforms GroundingDINO (tiny) by 1.2 AP on Roboflow100-VL while operating 20x faster.

## Reproduction and recommendation

Use the digest-pinned official vLLM image and immutable code/input paths shown in
the Job commands. Do not relaunch into an already successful output prefix. To
rebuild the local audited artifact from immutable candidate outputs, sync the run
prefix locally and run:

```bash
uv run --env-file backend/keys.env python backend/scripts/consolidate_paper_summary_candidates.py \
  --input /tmp/RUN/input \
  --candidate /tmp/RUN/candidates/gemma-4-e4b-it-v9-sampled-target-104200/output \
  --candidate /tmp/RUN/candidates/gemma-4-e4b-it-v5/output \
  --candidate /tmp/RUN/candidates/gemma-4-e4b-it-v4/output \
  --candidate /tmp/RUN/candidates/gemma-4-e4b-it-v3/output \
  --output /tmp/RUN/candidates/gemma-4-e4b-it-source-aware-100-rebuilt/output
```

For the later summary-embedding generation, prefer Gemma based on the comparable
v2 validity rate (88% versus Qwen's 82%), manual Bonsai/RF-DETR fidelity, and the
verified pure-model 100/100 artifact. This proves small-scale summary generation,
not retrieval superiority. Summary embeddings must still be evaluated against the
existing production title/abstract embedding system before any production change.
