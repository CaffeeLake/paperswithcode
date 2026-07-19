# Paper summary generation pilot: reproducible setup and launch blocker

Date: 2026-07-19 UTC

## Outcome

The repository now contains a deterministic title-plus-abstract summary export,
a restartable vLLM worker, strict artifact validation, and targeted tests. The
18-paper comparison snapshot is frozen in the existing private Bucket.

No model is selected. Both authorized comparison Jobs failed before dependency
installation or model loading because the submitted Hugging Face Jobs command
lost the `-lc` Bash option and treated the bootstrap command as a filename.
This is an orchestration failure, not evidence about either model. The two-Job
comparison cap is exhausted, so no retry or full-corpus Job was launched.

No production database row, embedding, Related Papers behavior, feature flag,
service, deployment, public artifact, scheduled Job, Dataset repository, Space,
Bucket, or Inference Endpoint was changed or created.

## Identity, models, and infrastructure

- Sanitized Hugging Face identity: `nielsr`; the existing Bucket is private.
- Bucket: `nielsr/pwc-paper-embeddings`.
- Hardware: `l4x1`, one 24 GB L4, currently `$0.0133/min` or `$0.80/hour`.
- `google/gemma-4-E4B-it` exists, is ungated, and is pinned to
  `fa62d88df2e6df5efa9d26ad6b3beaea2765f0cd`. Its BF16 weights total
  15,992,595,884 bytes. Current vLLM main registers
  `Gemma4ForConditionalGeneration` and `Gemma4ForCausalLM`.
- `Qwen/Qwen3.5-4B` exists, is ungated, and is pinned to
  `851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a`. Its BF16 weights total
  9,319,828,096 bytes. Its model card requires a current vLLM nightly/main
  build, and current vLLM main registers `Qwen3_5ForConditionalGeneration`.
- Both are configured for text-only loading, BF16, a bounded 4,096-token model
  length, and 0.92 GPU-memory utilization. Actual compatibility and VRAM remain
  unmeasured because neither worker started.

## Input and prompt contract

Eligible papers are current `is_latest_version` rows with non-empty normalized
titles and abstracts. The export runs in a read-only repeatable-read transaction
and orders rows by numeric database paper ID. It collapses whitespace while
preserving case, punctuation, LaTeX, and Unicode. No authors, citations, tasks,
methods, dates, or other metadata enter the prompt.

Snapshot facts:

- Transaction snapshot: `91663195:91663195:`
- Latest papers: 104,127
- Eligible title-plus-abstract papers: 103,895
- Excluded for missing/empty title or abstract: 232
- Pilot rows: 18
- Ordered-ID SHA-256:
  `199b1372380b1155a310846bb58edea5e4ff292fde811b099e47b25d7e607a91`

Prompt version: `retrieval-summary-v1`

Prompt SHA-256:
`d2f05a5c222fa5b4d159c320c1b2417d97243087d5bdf06ad1a6615338ffa4fd`

System prompt:

> You write factual retrieval summaries of research papers. Use only the
> supplied title and abstract. Do not add outside knowledge, citations,
> unsupported claims, or generic commentary. Return only the summary text.

User template:

```text
Write one concise 80–120 word retrieval-oriented summary.
Preserve the paper's central problem, primary method or contribution, experimental
or deployment setting, and principal result when each is stated. Do not invent a
missing result. Use concrete technical terms that would help retrieve this paper.
Do not include a heading, citation, bullet list, or boilerplate such as "this paper
presents".

Title: {title}

Abstract: {abstract}
```

Decoding is deterministic: temperature 0, top-p 1, top-k -1, seed 0, thinking
disabled, and at most 192 output tokens.

## Output schema and validation

Each JSONL row contains one semantic field, `summary`, plus provenance:

```text
paper_id, arxiv_id, paper_identifier, input_hash, summary,
model, revision, prompt_version, prompt_hash, generation_parameters,
validation_status, validation_errors, error, output_tokens
```

The worker writes one atomic output shard and completion marker per input shard,
skips checksum-valid completed shards on resume, captures row errors, and writes
a final manifest. Validation rejects empty output, non-80–120-word output,
boilerplate, thinking markup, citation-like numeric brackets, control characters,
duplicate IDs, changed input hashes, checksum mismatches, order/coverage changes,
and source-manifest inconsistencies.

## Jobs, runtime, and cost

| Candidate | Job | Result | Scheduling | Running | Measured inference / VRAM |
| --- | --- | --- | ---: | ---: | --- |
| Gemma 4 E4B IT | `6a5cac8cd216bd6f3a200f27` | exit 127 before install | 131 s | 8 s | unavailable |
| Qwen 3.5 4B | `6a5cac97d216bd6f3a200f29` | exit 127 before install | 101 s | 8 s | unavailable |

At the published L4 rate, 16 total running seconds cost approximately `$0.0035`;
if each Job is rounded to a full minute, the upper estimate is `$0.0266`. The
Jobs API does not expose invoice line items. Throughput, startup, peak VRAM,
failure counts, factual fidelity, retrieval usefulness, and side-by-side outputs
are unavailable because inference never began.

The full 103,895-paper run was not launched. Without a successful pilot there is
no evidence-based throughput or cost projection, and launching it would violate
the requirement to select a model from measured comparison evidence.

## Immutable artifacts and checksums

Bucket prefix:

`hf://buckets/nielsr/pwc-paper-embeddings/summary-generation/runs/pilot-summary-18-20260719T120000Z`

- `input/manifest.json`: SHA-256
  `18a65c23fb13cba3916829d8299f1d8c2264e0d53843c1b1deea5d2614a0a9b1`
- `input/papers-00000.jsonl`: SHA-256
  `07b99b1a9f21c4c8ee9821ebb7eb56460374bacde6994f08ef08c1fabe0c73a7`
- `code/generate_paper_summaries_job.py`: SHA-256
  `1f922fc5b41ba0568b9eacc4f9c41ddd5fe60134ed1f6819361ded8ccb980022`
- `code/run_paper_summaries_job.sh`: SHA-256
  `1f0b94d8b88472f391852ee15292ddf00bdc052825b9833846f0501f000f18a2`

There are no output artifacts. Representative side-by-side summaries therefore
cannot be reported without fabricating results.

## Corrected reproduction/resume command

The checked-in wrapper avoids shell-option parsing by making the Bucket script
the direct Bash argument. After a fresh authorization for two comparison retries,
run one command per candidate, changing `candidate`, output path, model, and
revision:

```bash
uv run --env-file backend/keys.env hf jobs run \
  --flavor l4x1 --timeout 30m --detach --namespace nielsr \
  --label app=pwc-paper-summaries \
  --label run=pilot-summary-18-20260719T120000Z \
  --label candidate=qwen3-5-4b \
  --secrets HF_TOKEN \
  --volume hf://buckets/nielsr/pwc-paper-embeddings:/bucket \
  ghcr.io/astral-sh/uv:python3.12-bookworm \
  bash /bucket/summary-generation/runs/pilot-summary-18-20260719T120000Z/code/run_paper_summaries_job.sh \
  /bucket/summary-generation/runs/pilot-summary-18-20260719T120000Z/code/generate_paper_summaries_job.py \
  /bucket/summary-generation/runs/pilot-summary-18-20260719T120000Z/input \
  /bucket/summary-generation/runs/pilot-summary-18-20260719T120000Z/output/qwen3.5-4b \
  Qwen/Qwen3.5-4B 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
```

Validate a completed run locally with:

```bash
uv run --env-file backend/keys.env python \
  backend/scripts/prepare_paper_summary_run.py validate \
  --input /path/to/run/input --output /path/to/run/output/qwen3.5-4b
```

## Recommendation

Authorize one clean retry per candidate using the corrected wrapper, then select
only after comparing validity rate, factual fidelity, retrieval usefulness,
throughput, startup/runtime, peak VRAM, and estimated cost. Do not generate or
embed the full corpus, and do not claim summary embeddings are better, until that
pilot succeeds and a later retrieval evaluation tests the summaries.
