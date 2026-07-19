# Paper embedding bakeoff: 5,000-paper pilot

Date: 2026-07-18 UTC

## Outcome

The pinned document-embedding bakeoff is computationally complete on the same
ordered 5,000-paper snapshot. The original F2LLM result and two new 0.6B Jobs
completed on `l4x1`; Qwen's 256/512 variants were derived from its single
1024-dimensional pass. The pinned F2LLM-v2-80M Job exposed an incorrect
1024-dimensional repository contract. Its pinned revision natively emits 320
dimensions, so the configuration was corrected and the candidate was completed
locally at 320 dimensions after the three-Job authorization cap was exhausted.

No production winner is declared. The checked-in relevance fixture is too
sparse to discriminate candidates, while the qualitative panel and neighbor
overlaps are only proxies. A blinded human package is ready for annotation.

No application database, production migration, endpoint, Dataset repository,
feature flag, service, deployment, or full-corpus generation was touched.

## Identity, infrastructure, and artifacts

- The environment-selected Hugging Face token authenticated as `nielsr`. Its
  sanitized fine-grained metadata includes `job.write` on the user namespace;
  Jobs and private Bucket reads succeeded. No stored alternate credential was
  used.
- Private Bucket: `nielsr/pwc-paper-embeddings`, 39 files and 35,833,088 bytes
  after this phase.
- Input: the five immutable checksummed shards under
  `runs/pilot-f2llm-5000-20260718T125302Z/input`; every candidate matched the
  exact ordered 5,000 paper IDs.
- Completed new Jobs:
  - F2LLM-v2-0.6B: `6a5b7e92d216bd6f3a1fe660`
  - Qwen3-Embedding-0.6B: `6a5b7f46bee6ee1cf4ecf606`
- Failed contract-validation Job: F2LLM-v2-80M
  `6a5b7ff2d216bd6f3a1fe688`. It failed before writing a shard; its intended
  Bucket prefix is empty.
- Original completed Job reused: `6a5b7987d216bd6f3a1fe5df`.
- Local evidence root: `/tmp/pwc-embedding-pilot-20260718`.

Every completed output passed manifest and shard checksums, row count, unique
ID coverage, input order, vector dimension, finiteness, and float16 norm checks.

## Compute, artifacts, and estimated cost

Current `hf jobs hardware` pricing lists `l4x1` at $0.0133/minute or $0.80/hour.
The API does not expose the eventual invoice line item, so cost below is the
best-supported estimate from recorded running seconds. The parenthetical value
rounds each Job up to a whole billed minute.

| Configuration | Compute | Worker / Job runtime | Throughput | Startup | Peak VRAM | Parquet | Estimated Job cost |
|---|---:|---:|---:|---:|---:|---:|---:|
| F2LLM-0.6B 1024 | l4x1 | 68.50s / 103s | 72.99 papers/s | 10.20s | 1.432 GB | 7.69 MB | $0.0229 ($0.0267) |
| F2LLM-v2-0.6B 1024 | l4x1 | 66.49s / 102s | 75.20 papers/s | 7.25s | 1.432 GB | 7.68 MB | $0.0227 ($0.0267) |
| Qwen3 1024 | l4x1 | 66.66s / 102s | 75.01 papers/s | 5.95s | 2.361 GB | 7.67 MB | $0.0227 ($0.0267) |
| Qwen3 512 | same Qwen pass | no extra inference | same | same | same | 5.19 MB local derived | $0 incremental |
| Qwen3 256 | same Qwen pass | no extra inference | same | same | same | 2.77 MB local derived | $0 incremental |
| F2LLM-v2-80M 320 | local CPU | 1,336.03s | 3.74 papers/s | 15.72s | 0 GPU | 3.39 MB | $0 local compute |

The failed 80M l4 Job ran for 51 seconds, adding an estimated $0.0113
($0.0133 minute-rounded). Including the original pilot, all four l4 Jobs cost an
estimated $0.0796 by exact running seconds or at most $0.0933 with per-Job
whole-minute rounding. This continuation alone accounts for approximately
$0.0567 or $0.0667, respectively.

The 80M l4 log completed its first 1,000-paper inference in roughly 3.4 seconds
before rejecting the wrong requested dimension, which suggests high warm
throughput, but it is not a valid completed-run measurement. A future authorized
320-dimensional l4 rerun is required for comparable throughput and VRAM.

## Disposable pgvector benchmark

Environment: PostgreSQL 16.14, pgvector 0.8.1, 5,000 current papers, one
isolated generation per configuration. All imports were 5,000 rows with zero
stale rows. Results use 100 deterministic source vectors, `k=20`, exact scan
ground truth, and HNSW with `ef_search=40`. The table is the idle-host rerun;
the earlier contended reports are retained separately.

| Configuration | Recall@20 | Exact p50 / p95 | HNSW p50 / p95 | Total partition | HNSW index |
|---|---:|---:|---:|---:|---:|
| F2LLM-0.6B 1024 | 0.9945 | 15.00 / 25.83 ms | 1.70 / 2.56 ms | 28.52 MB | 13.84 MB |
| F2LLM-v2-0.6B 1024 | 0.9970 | 14.75 / 22.77 ms | 1.78 / 2.62 ms | 28.52 MB | 13.84 MB |
| Qwen3 1024 | 0.9955 | 14.44 / 16.66 ms | 1.71 / 2.27 ms | 28.52 MB | 13.84 MB |
| Qwen3 512 | 0.9945 | 10.09 / 15.14 ms | 1.40 / 2.00 ms | 12.92 MB | 7.02 MB |
| Qwen3 256 | 0.9955 | 6.93 / 13.75 ms | 1.31 / 2.21 ms | 7.82 MB | 4.36 MB |
| F2LLM-v2-80M 320 | 0.9880 | 7.51 / 11.08 ms | 1.34 / 1.76 ms | 9.45 MB | 5.31 MB |

The first immediate 80M query plan did not use HNSW because the new partition
had not been analyzed. The reusable index builder now runs `ANALYZE` after
creating the index. The pre-analyze full-sort report is preserved as failure
evidence; the table above confirms the corrected HNSW plan.

## Quality proxies and limitations

The sanitized related-paper fixture reports nDCG@4, graded Precision@4, and
Recall@20 of zero for every configuration. This is not useful model evidence:
only three fixture source IDs occur in the 5,000-paper snapshot, one judged
target lies outside it, and none of the remaining sparse targets occurs in the
top 20. The fixture is a contract/loader smoke test, not a release set.

The 59-query search fixture cannot be scored fairly from these artifacts. The
Jobs generated document vectors only; candidate-specific instructed query
vectors were not exported, and deploying an online query endpoint was out of
scope.

Across the 100 annotation sources, mean top-20 set overlap was:

- Qwen 1024 vs 512: 0.8155
- Qwen 1024 vs 256: 0.6910
- Qwen 512 vs 256: 0.7485
- original F2LLM vs F2LLM-v2 0.6B: 0.5430
- F2LLM-v2 0.6B vs Qwen 1024: 0.5040
- F2LLM-v2 80M vs F2LLM-v2 0.6B: 0.3565

These overlaps show that truncation and model choice materially change the
candidate pool; they do not say which differences are better.

The fixed six-paper qualitative panel produced plausible neighbors across all
systems. Qwen's three dimensions consistently retrieved YOLO-family papers for
YOLO, and the v2/Qwen systems kept diffusion-specific work above unrelated
generative models for DDPM. All systems returned direct NeRF follow-ups for
NeRF and BERT variants for BERT. The 80M result was somewhat more diffuse on
BERT and had the lowest overlap with its 0.6B sibling. These observations are
promising but too few and too visible to support selection.

## Human evaluation package

Local package: `/tmp/pwc-embedding-pilot-20260718/human-evaluation-package`

Archive: `/tmp/pwc-embedding-pilot-20260718/human-evaluation-package.tar.gz`

Archive SHA-256:
`e2da3e4aa79bc1a02b5f58387aa2da811bd9d688ee29de5c0a17941f531fa928`

The package contains exactly 100 source papers, balanced 20/20/20/20/20 across
document-length quintiles, and 1,400 unique source-candidate pairs. It pools
depth four from one lexical TF-IDF run, six exact dense configurations, and six
lexical+dense RRF hybrids. Candidates are de-duplicated and shuffled within
source. Annotator rows contain no system identity; `provenance.jsonl` must stay
hidden until judgments are frozen. The package includes 13 run files,
instructions, a declared schema, source strata, and a manifest.

The JSONL was loaded successfully with Hugging Face `datasets` using explicit
features: string IDs/text/notes, int64 paper IDs, int32 display order, and int8
grade. All 1,400 blind IDs and pairs are unique, all 100 sources are represented,
no source is its own candidate, and provenance coverage is exact. No Dataset
repository was created.

## Failures and reusable fixes

1. The 80M pinned config requested 1024 dimensions even though the pinned model
   README and transformer config specify 320. The worker correctly failed
   closed. The bakeoff config now uses 320.
2. Bakeoff Jobs can explicitly reuse a checksummed immutable snapshot exported
   for another model without weakening shard verification; outputs record the
   candidate model and source snapshot run.
3. Qwen truncations are now materialized deterministically by prefix truncation
   followed by L2 normalization, with fresh manifests and checksums.
4. New pgvector partitions are analyzed immediately after HNSW creation so the
   first queries do not fall back to a full sort.
5. The annotation builder emits blinded, stratified, de-duplicated local
   packages with lexical, dense, and RRF provenance.

Targeted Ruff checks passed. Embedding unit tests passed (10), and the migration
integration test passed against the explicit disposable PostgreSQL
16/pgvector 0.8.1 URL after applying the migration idempotently.

## Exact next recommendations

1. Have at least two annotators independently grade a randomized overlap of at
   least 20% of the 1,400 pairs; adjudicate disagreements and report weighted
   agreement before opening provenance.
2. Score each dense and hybrid run with per-source bootstrap confidence
   intervals for nDCG@4, graded Precision@4, Recall@20, win rate, and stratum
   slices. Treat Qwen dimensions as tied unless human confidence intervals
   separate them.
3. Add an offline, pinned query-embedding export for the 59-query search fixture
   and compare keyword, dense, and RRF MRR/nDCG/Recall. This does not require an
   endpoint, but it does require a separately planned query-vector run.
4. If Qwen 256 is non-inferior in human judgments, it is the current systems
   efficiency candidate: it preserves 0.9955 HNSW recall while using 27% of the
   1024-dimensional partition storage and materially reducing exact latency.
   If it loses quality, evaluate 512 as the middle point. This is a conditional
   recommendation, not a winner declaration.
5. Before considering 80M, authorize one corrected 320-dimensional l4 pilot to
   measure comparable throughput, VRAM, and billed runtime. Its lower HNSW
   recall at `ef_search=40` should also be swept at higher `ef_search` values.
6. Do not authorize the 104k run or production activation until human related
   judgments and offline search judgments both pass explicit release gates.
