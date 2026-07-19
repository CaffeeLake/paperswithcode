# Plan: Shared Embeddings for Related Papers and Hybrid Search

## Decision

Build one versioned title-plus-abstract embedding corpus and use it for two
features:

1. paper-to-paper nearest-neighbor retrieval for the Related papers card;
2. query-to-paper dense retrieval as the semantic branch of hybrid search in
   `PLAN_SEARCH.md`.

One shared corpus is the preferred default, not a hard product requirement.
Judge paper-to-paper similarity and query-to-paper retrieval independently. A
second specialized embedding generation is permitted only when the shared model
materially fails one feature and the measured relevance gain justifies the
additional storage, backfill, query inference, and operational burden.

Do not choose a production model from a family-level MTEB average. Run the same
Papers With Code evaluation and serving benchmark over this compact V1
shortlist, pinning the tested Hub revision:

| Candidate | Why it is in the bakeoff | Inspected revision |
| --- | --- | --- |
| [`codefuse-ai/F2LLM-0.6B`](https://huggingface.co/codefuse-ai/F2LLM-0.6B) | Strong known scientific P2P clustering baseline; Apache-2.0; 1024 dimensions | `eb2778d335980b42b986c75d7fe3a78be19ef3a6` |
| [`codefuse-ai/F2LLM-v2-0.6B`](https://huggingface.co/codefuse-ai/F2LLM-v2-0.6B) | Current 0.6B successor trained on a larger multilingual corpus; Apache-2.0; query/document APIs | `2b4159091278275a3b00d2c39095754d59d7d7de` |
| [`Qwen/Qwen3-Embedding-0.6B`](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | Apache-2.0; instruction-aware retrieval; TEI support; native Matryoshka output from 32–1024 dimensions | `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3` |
| [`codefuse-ai/F2LLM-v2-80M`](https://huggingface.co/codefuse-ai/F2LLM-v2-80M) | Efficiency challenger for online CPU query encoding; Apache-2.0; much smaller model | `f4a16a11c9f5c8c7e22694653de6ce75430f4538` |

This four-way bakeoff is a required V1 model-selection gate. Do not designate a
default winner or run the full-corpus production backfill until every candidate
has been evaluated on the same corpus snapshot, input contract, judgments, and
serving measurements. Qwen3 dimension variants count as configurations of one
candidate, not independently curated test sets.

Do not include 1.7B–14B candidates in the initial bakeoff. GPU document
backfilling makes them possible offline, but their online query encoder would
push V1 toward a permanently warm accelerator endpoint before a compact model
has been shown inadequate.

The supplied MTEB English v2 snapshot places the original F2LLM sixth on
ArXivHierarchicalClusteringP2P and third when averaging that task with
BiorxivClusteringP2P.v2 and MedrxivClusteringP2P.v2. Its warning for training on
those benchmark splits is acceptable for product shortlisting because the
target behavior is intentionally similar, but it makes the Papers With Code
judgment set below essential rather than optional.

Evaluate
[`jinaai/jina-embeddings-v5-text-small-clustering`](https://huggingface.co/jinaai/jina-embeddings-v5-text-small-clustering)
as an offline challenger, not the default. It has a useful clustering objective,
1024-dimensional Matryoshka embeddings, and did not train on the target MTEB
tasks according to the supplied model-selection advice. Its CC-BY-NC-4.0
license requires an explicit legal/product decision before production use on a
public service. Do not silently treat it as interchangeable with Apache-2.0.

Keep the serving index in PostgreSQL with pgvector on the VPS. Run bulk and
scheduled document encoding on Hugging Face Jobs GPUs. Keep immutable input
manifests, output shards, checkpoints, and run metadata in a private Hugging Face
Bucket. Do not put the model in each FastAPI worker and do not make a Hugging
Face Job part of a synchronous web request.

PostgreSQL + pgvector is the committed V1 serving architecture. Do not delay V1
for a Qdrant or other vector-database bakeoff. Keep the artifact format,
embedding-generation model, and retrieval service boundary portable enough to
permit a later migration, but do not build a generic multi-backend abstraction
before it is needed. Reconsider a dedicated vector database only if production
measurements show that pgvector cannot meet an agreed latency or ANN-recall
target, filtered retrieval is unreliable, vector workloads materially harm the
transactional database, or the corpus/traffic outgrows a single PostgreSQL
node.

## Why one platform but two ranking policies

The expensive operation is document encoding. F2LLM's `encode_document` output
can be computed once and reused:

```text
paper title + abstract
        |
        v
F2LLM encode_document on HF Job
        |
        +--> pgvector paper-to-paper KNN --> related papers
        |
        +--> pgvector query-to-paper KNN --+
                                             +--> RRF with PostgreSQL FTS --> search
query --> F2LLM encode_query ----------------+
```

Related papers should establish direct document cosine similarity as the dense
baseline, then test a related-specific hybrid variant that fuses dense neighbors
with lexical neighbors derived from the source paper's title and salient
abstract terms. Search independently fuses query semantic and lexical candidate
ranks and keeps exact-title/ArXiv identity overrides. Sharing vectors and
retrieval primitives does not mean sharing candidate construction or a final
score.

## Current state and sizing

As measured on 2026-07-18:

- 104,101 latest paper rows exist; 103,870 have a non-empty abstract.
- The average normalized title-plus-abstract input is 1,366 characters and the
  maximum is 3,672 characters.
- The `papers` relation including indexes is about 719 MB.
- The VPS has about 11 GB disk free and 8 GB RAM.
- PostgreSQL does not currently expose the `vector` extension in
  `pg_available_extensions`; installing the PostgreSQL-16 pgvector package and
  running `CREATE EXTENSION vector` are explicit deployment steps.
- Raw `halfvec(1024)` payload for 104,101 rows is about 203 MiB. Budget roughly
  1-2 GB for the versioned table, row/index overhead, HNSW construction, and one
  old model generation during an atomic rollout. Measure the real index before
  fixing a capacity number.
- Vector dimensionality is a first-class model-selection and serving metric.
  Higher dimensions increase raw storage, HNSW index memory, cache pressure,
  distance-computation work, Bucket artifacts, and transfer/import time. At the
  current corpus size 1024 dimensions are feasible, but feasibility alone is
  not a reason to retain dimensions that do not produce measurable quality.

The current frontend implementation in `PaperDetailView.tsx` fetches five
papers for the source paper's first task, orders them by citations, excludes the
source, and displays four. This favors famous papers and fails when task tags
are broad, incomplete, or ordered differently.

## Ownership: Hugging Face versus VPS

| Component | Location | Reason |
| --- | --- | --- |
| Model weights | Hub model repo / HF Job cache | Pin revisions; avoid consuming VPS disk for batch GPU inference |
| Graded search and related-paper judgments | Private-then-sanitized HF Dataset repo | Canonical schema, reviewable revisions, dataset card, Parquet, and reproducible evaluation |
| Corpus export manifests | Private HF Bucket | Durable, inspectable, restartable input contract |
| Embedding shards and checkpoints | Private HF Bucket | Resume after crashes and preserve provenance for validation/reimport |
| Bulk and scheduled document encoding | HF Jobs GPU | Accelerator-friendly and isolated from the live 8 GB VPS |
| Canonical embedding rows and ANN index | VPS PostgreSQL + pgvector | Low-latency joins, latest-version filters, transactions, and simple rollback |
| Search query encoder | Protected HF Inference Endpoint | Keep model inference off the resource-constrained VPS; lexical search remains the timeout fallback |
| Related-paper request | VPS API and PostgreSQL | No runtime model call: use the already stored source-paper vector |
| Model/run configuration and metrics | Repository + PostgreSQL | Reviewable deployment state and production observability |

Dataset repositories and Buckets have deliberately different roles. The HF
Dataset repo is the version-controlled source of truth for curated judgments.
Buckets are mutable S3-like object storage for corpus exports, pooled candidate
files awaiting annotation, embedding shards, checkpoints, logs, and other
large/intermediate run artifacts that do not need Git history. Because Buckets
are not version-controlled, every run writes to a new content-addressed/run-ID
prefix and finalized manifests are never overwritten in place.

Buckets are the artifact and recovery layer, not the live serving database or
the canonical evaluation dataset.
A bucket-hosted FAISS index is reasonable for offline evaluation, but promoting
it to production would require atomic downloads, memory mapping, metadata/filter
coordination, incremental rebuilds, and synchronization across API processes.
At this corpus size pgvector is the simpler authoritative serving path.
Qdrant is an explicit post-V1 escape hatch rather than a V1 evaluation
dependency.

Apply this Bucket retention policy by run prefix:

- retain complete artifacts for the active and immediately previous embedding
  generations;
- retain successful experimental/bakeoff runs for 90 days;
- retain failed or incomplete runs for 14 days unless explicitly pinned for an
  investigation;
- retain compact final manifests, checksums, benchmark metrics, and provenance
  records indefinitely;
- exempt any run referenced by an active generation or pinned Dataset revision
  from age-based cleanup.

Implement retention as a rule-based maintenance command with separate dry-run
plan and apply steps. Never delete Bucket artifacts opportunistically from an
embedding Job, importer, or API process.

## Data contract

### Canonical embedding input

Construct one deterministic UTF-8 string:

```text
<normalized title>\n\n<normalized abstract>
```

Normalization should trim outer whitespace, collapse repeated whitespace, and
preserve case, punctuation, LaTeX, and Unicode. Do not initially add authors,
citations, tasks, methods, or publication dates: those are mutable metadata and
ranking signals, not paper content. Papers without abstracts use the title only.
Record the formatting contract as `input_format_version`, because even a
whitespace or prefix change invalidates old vectors.

Title + abstract is the committed V1 embedding contract, not merely the first
untested format. Authors, tasks, methods, venue, year, citations, and other
metadata stay outside the vector. Test any future content-format change as an
ablation against the versioned relevance datasets before creating a new
embedding generation. Track title-only papers as a separate evaluation slice
and telemetry dimension rather than silently mixing them into aggregate scores.

Use `SentenceTransformer.encode_document(..., normalize_embeddings=True)` for
every stored paper. For search use `encode_query`, which applies F2LLM's query
prompt. Never use `encode_query` for the source paper in paper-to-paper
similarity.

### PostgreSQL schema

Use a generation-oriented schema so a new model can be loaded and validated
without overwriting the active one:

```sql
paper_embedding_generations
  id                    bigint primary key
  model_name            text not null
  model_revision        text not null
  dimensions            integer not null
  input_format_version  text not null
  bucket_run_uri        text not null
  status                text not null  -- loading, ready, active, retired, failed
  created_at             timestamptz not null
  activated_at           timestamptz

paper_embeddings partitioned by list (generation_id)
  generation_id         bigint not null references paper_embedding_generations
  paper_id               bigint not null references papers
  content_hash           text not null
  embedding              halfvec not null
  created_at             timestamptz not null
  primary key (generation_id, paper_id)
```

Create one list partition per generation, enforce its declared dimension, and
create a dimension-specific HNSW cosine expression index such as
`((embedding::halfvec(512)) halfvec_cosine_ops)`. Query the explicitly
configured active generation with the matching cast so approximate search never
mixes model spaces and then post-filters most neighbors. A constant-predicate
partial index per generation is an acceptable alternative if it produces
reliable plans in isolated tests. Exact schema/index choices must be tested
against the installed pgvector version. Store normalized vectors and still use
cosine distance explicitly for readable semantics.

Do not key only by `model_name`. A Hub revision, input format, dimension, or
normalization change defines a new incompatible generation.

## Hugging Face batch pipeline

### 1. Export on the VPS

Add a small repository CLI/script that exports latest papers needing a vector to
Parquet or JSONL shards. Each row contains only:

```text
paper_id, title, abstract, content_hash, updated_at
```

Write a manifest containing row count, shard hashes, schema version, model ID,
model revision, input format version, requested output dimension, and creation
time. The export must be a consistent snapshot and must not expose database
credentials to Jobs.

Upload the run directory to a private bucket, for example:

```bash
uv run --env-file backend/keys.env hf buckets create pwc-paper-embeddings \
  --private --region eu --exist-ok
uv run --env-file backend/keys.env hf buckets sync ./embedding-run \
  hf://buckets/nielsr/pwc-paper-embeddings/runs/<run-id>
```

The exact namespace and bucket are deployment configuration, not hard-coded.
Creating a bucket is an external mutation and is not part of routine development.

### 2. Encode on an HF Job

Keep the worker as a checked-in, PEP 723-compatible script so the same revision
is runnable locally and through `hf jobs uv run`. Start with one `l4x1`: 24 GB
VRAM is ample for a 0.6B BF16 encoder, and L4 is a cost-efficient inference GPU.
Benchmark `t4-small` as the cheaper alternative before standardizing hardware.

Use `l4x1` as the default V1 Jobs flavor. As of 2026-07-18 it provides one
24 GB L4, 8 vCPU, 30 GB RAM, and 400 GB ephemeral storage for $0.80/hour. It has
ample memory for the compact shortlist, native modern inference dtypes, and more
CPU/storage headroom for tokenization and Parquet than `t4-small`. Treat
`t4-small` ($0.40/hour, 16 GB) as a cost challenger using FP16 rather than BF16;
use `a10g-small` ($1.00/hour, 24 GB) only if the pilot shows a better total
cost-to-completion. Hardware prices are inputs captured in each run manifest,
not permanent constants.

The current corpus contains roughly 36 million input tokens when estimating
four characters per token from the measured 1,366-character average. A
45-minute L4 run would cost $0.60, but it would require about 13,300 non-padding
tokens/second across the whole run and almost no startup, tokenization, I/O, or
validation overhead. Treat that as an optimistic lower bound, not a budget.

Until the pilot measures the actual Sentence Transformers workload, assume
roughly 2,000-10,000 non-padding tokens/second. That implies about 1-5 hours of
model compute for 36 million tokens; budget 1.5-6 billed L4 hours, or $1.20-$4.80
at the current rate, and round the operational allowance to $2-$6 for one full
0.6B corpus pass including model download, tokenization, Parquet I/O,
validation, and a retry margin. Budget roughly $1-$3 for the 5k-10k
four-candidate bakeoff and $6-$18 only if every candidate is unnecessarily run
over the complete corpus. These are planning ranges, not release gates. The
pilot must report papers/second, non-padding tokens/second, padded tokens/second,
GPU utilization, peak VRAM, startup time, and actual billed runtime before
approving the full run. Qwen3 dimension variants come from one full-dimensional
encoding pass and should not be billed as separate inference runs.

Illustrative invocation:

```bash
uv run --env-file backend/keys.env hf jobs uv run \
  --flavor l4x1 \
  --timeout 4h \
  --detach \
  --label app=pwc-paper-embeddings \
  --label model=f2llm-0.6b \
  --secrets HF_TOKEN \
  --volume hf://buckets/nielsr/pwc-paper-embeddings:/bucket \
  backend/scripts/embed_papers_job.py \
  --input /bucket/runs/<run-id>/input \
  --output /bucket/runs/<run-id>/output \
  --model codefuse-ai/F2LLM-0.6B \
  --revision eb2778d335980b42b986c75d7fe3a78be19ef3a6
```

The worker must:

- verify the input manifest and refuse a model/config mismatch;
- download the pinned model revision;
- use Sentence Transformers `encode_document` with BF16, dynamic batches,
  length-sorted inputs, normalized output, and inference mode;
- write small atomic Parquet shards containing `paper_id`, `content_hash`, and
  float16 embeddings;
- write a completed-shard marker only after checksum validation;
- skip valid completed shards on retry;
- emit a final manifest with dimensions, dtype, counts, package versions,
  hardware, duration, and checksums;
- fail if vectors contain NaN/Inf, are the wrong dimension, have abnormal norms,
  or paper IDs are duplicated/missing.

Bucket writes make the job restartable without opening PostgreSQL to ephemeral
Job IPs. Use `hf jobs inspect`, `hf jobs logs`, and `hf jobs wait` for operation;
never pass `backend/keys.env` wholesale because it includes unrelated secrets.

### 3. Validate and import on the VPS

Download or mount the completed artifacts, verify the final manifest, then bulk
load into a new generation with `COPY`/staging tables in bounded transactions.
Reject any row whose `content_hash` no longer matches the current paper. Validate:

- expected row coverage and uniqueness;
- dimension, finite values, and near-unit norms;
- sampled nearest neighbors by exact cosine search;
- HNSW recall against exact search on a sampled query set;
- table/index size and index build memory/duration.

Build the index without blocking production writes (`CREATE INDEX CONCURRENTLY`)
and activate the generation only after quality gates pass. Activation is one
small transactional configuration change. Keep the prior generation until the
new one is stable, then retire/delete it in a separate capacity-managed action.

### 4. Incremental refresh

Initial rollout can run a daily scheduled Job over a compact delta manifest.
The importer selects papers with missing embeddings or a changed content hash;
idempotent upserts make retries safe. A paper is eligible only when it is the
latest version. When a newer version arrives, encode the new row and let serving
filters exclude the old one; delete stale vectors later in a maintenance pass.

Embed only `is_latest_version` papers, including external resources. Do not
backfill historical ArXiv versions. Title-only papers remain eligible but are a
separate coverage and quality slice. During the bounded interval between a new
version becoming latest and receiving its own vector, Related papers may use the
most recent prior-version vector for the same canonical ArXiv ID as a stale
source query vector; it must return current paper metadata and expose this state
in telemetry. Prior versions must never appear as recommendation or search
candidates. Dense search may omit the new version until its current vector is
ready, while FTS continues to retrieve it.

Expose the pipeline as rule-based commands such as `pwc embeddings export`,
`run`, `import`, and `status`, then orchestrate them after paper ingestion. The
VPS/exporting workflow must create the delta artifact before an HF Job runs, and
the importer must wait for a valid completion manifest; an HF scheduled Job by
itself cannot discover new PostgreSQL rows. Use a scheduled HF Job only after
this handoff is reliable, and prevent overlap with scheduled-job concurrency
controls. Target freshness under 24 hours initially. Search falls back to FTS
and Related papers falls back to the current task-based list when a source
embedding is absent, so ingestion is not coupled to Job availability.

The committed V1 freshness SLO is 24 hours, implemented as a daily delta after
paper ingestion. Track age of the oldest eligible unembedded paper, eligible
missing count, and last successful export/Job/import timestamps. A later phase
may enqueue embedding directly after import or run more frequent micro-batches,
but only after the daily path is reliable and telemetry shows user value in a
shorter window. Event-driven embedding must remain asynchronous: paper import
success never waits for an HF Job or embedding import.

## Related-papers serving and ranking

Add a dedicated endpoint rather than overloading `/tasks/{id}/papers`:

```text
GET /api/v1/papers/{paper_id}/related?limit=4
```

Resolve ArXiv/external routes consistently with paper detail, require the active
generation, exclude the source paper and all non-latest versions, and retrieve
more candidates than displayed (start with K=50). The endpoint must be a single
indexed query plus bounded metadata hydration; it performs no model inference.

Benchmark two V1 retrieval configurations against the same judgments:

```text
dense:   document embedding KNN
hybrid:  document embedding KNN + lexical paper-neighbor retrieval -> RRF
```

This dense-versus-hybrid comparison is a required V1 ranking gate. Do not ship
hybrid merely because both retrieval branches exist. Dense-only wins by default
when the judged difference is inconclusive because it has fewer moving parts.
Promote hybrid only when it improves graded relevance without a material loss
of result diversity or an increase in superficial acronym/terminology matches.

The lexical related-paper branch should use the existing weighted title/abstract
`tsvector`, but it must not turn the entire abstract into an enormous user-style
`tsquery`. Start with the normalized title plus a bounded set of rare,
distinctive abstract lexemes/acronyms selected using corpus document frequency.
Retrieve a bounded top K independently and use RRF so incomparable FTS and
cosine scores are never added directly. Version lexical-term selection and
fusion configuration as part of `ranking_version`.

After retrieval, apply only explicit quality rules:

1. collapse duplicate/version-equivalent papers;
2. exclude rows without enough display metadata;
3. optionally require one shared task/category only as a weak reranking feature,
   never as a hard filter;
4. use global `citation_count` and recency only as capped tie-breakers;
5. add a modest diversity pass such as maximal marginal relevance only if the
   top four are near-duplicates.

Do not guarantee curated lineage edges in the candidate set: coverage is too
sparse for them to define product behavior. Use known lineage pairs as positive
evaluation examples and diagnostics. Embedding similarity remains the broad
candidate generator. The current database stores global citation counts and can
fetch bibliographies from Semantic Scholar for a separate method-tagging job,
but it does not store a general citation graph, citation contexts, or per-pair
in-paper mention counts. Defer directed mention-frequency extraction until
after V1, and revisit it only if the dense-versus-hybrid evaluation reveals a
relationship class that lexical and dense retrieval consistently miss.

Do not set an arbitrary global cosine threshold before inspecting the score
distribution. A threshold can hide the card for niche papers even when their
relative neighbors are useful. Calibrate a minimum score and ambiguity margin
from judgments, and fall back to the task-based implementation when confidence
is low.

Return up to four items. Put qualified dense/hybrid recommendations first. If
fewer than four pass the calibrated confidence rule, fill the remaining slots
with deduplicated results from the current first-task/citation fallback, ordered
after all qualified semantic items. Store per-item retrieval provenance
(`dense`, `lexical`, `hybrid`, or `task_fallback`) in internal response/debug
metadata and telemetry, without requiring the current UI to label it. Hide the
card only when neither semantic/hybrid retrieval nor the task fallback yields a
useful item. Never lower the semantic confidence rule solely to fill four slots.

Related-paper discovery is bidirectional in publication time. Include both
earlier foundations and later follow-ups relative to the source paper. Do not
apply a `candidate.date_published <= source.date_published` filter. Publication
date may be displayed and used only as an independently evaluated, capped
tie-breaker; Related papers represents what is useful to read now, not only what
the authors could have known at publication time.

Frontend changes should switch the query key to the paper ID/generation-aware
endpoint, retain the present four-card layout, and handle loading/empty/fallback
states. Consider a small “semantic similarity” explanation only if it improves
user trust; do not claim two papers share a task unless the API provides that
evidence.

## Hybrid-search query inference

Related-paper retrieval needs no online encoder, but dense text search does.
Use a protected Hugging Face Inference Endpoint as the committed V1 query
encoder so the 8 GB VPS does not carry model weights or inference runtimes.
Deploy the exact model revision and output dimension used for the active
document generation, preferably with Text Embeddings Inference when the winner
is supported. Treat endpoint configuration, query instruction, normalization,
and output dimension as part of the embedding generation contract.

Production may scale the endpoint to zero. This explicitly accepts that the
first searches after an idle period can fall back to keyword-only retrieval
while the endpoint becomes ready. Do not promise identical hybrid results or
latency during a cold start. Record endpoint state/cold-start fallback in search
telemetry so relevance and latency analyses can separate lexical fallbacks from
true hybrid requests. Staging and bakeoff endpoints should also scale to zero
when idle.

Measure warm and cold p50/p95 latency, concurrency behavior, availability,
autoscaling, and cost. Enforce a short application timeout, a concurrency bound,
and a circuit breaker; FTS is always the immediate fallback. Cache query vectors
only with a short-lived key containing the full generation and instruction
version, and never log raw query text by default.

Set the initial semantic-inference request budget to 500 ms, measured from the
VPS through response validation. On endpoint unavailability, initialization,
timeout, malformed output, or circuit-breaker open, return the completed FTS
ranking immediately. The failed/slow request may wake a scaled-to-zero endpoint
for later searches, but the frontend must not replace or reorder results already
shown for the current request. Cover warm success, cold fallback, timeout, and
recovery-after-open-circuit behavior with integration tests.

Do not use ephemeral HF Jobs as a request-serving endpoint, and do not choose a
different query model against the stored document vectors: embeddings from
different models are not in a shared vector space. A single bounded local
sidecar may be evaluated later only as a disaster-recovery or cost optimization;
it is not a V1 requirement.

The search service requests `encode_query`, retrieves semantic KNN candidates,
and combines those ranks with FTS using RRF as specified in `PLAN_SEARCH.md`.
Exact ArXiv IDs and normalized titles stay deterministic overrides.

## Model evaluation and release gates

MTEB guides model shortlisting but is not a production acceptance test. Build a
Papers With Code judgment set before activation.

Maintain two versioned, graded relevance datasets with stable paper IDs and a
recorded corpus snapshot/generation:

```text
search_relevance:
  query, relevant_paper_id, relevance_grade

related_papers_relevance:
  source_paper_id, related_paper_id, relevance_grade
```

The search dataset represents user questions, natural-language descriptions,
exact titles, identifiers, acronyms, and technical keyword queries. The related
dataset represents paper-to-paper usefulness under the labeling rubric below.
Both datasets must support multiple relevant papers and graded judgments; a
single expected result is insufficient for retrieval evaluation.

Store the complete canonical datasets in a Hugging Face Dataset repository,
initially private during collection and review. Include a dataset card covering
the rubric, sampling, assessors, splits, corpus snapshot, known biases, and
privacy policy. Pin the exact Dataset revision in benchmark manifests. Keep the
schema/loader and a small frozen non-sensitive CI fixture in this repository;
do not duplicate the full mutable judgment set in Git. Publish a sanitized
Dataset revision later if useful, but never publish raw production queries
without a separate privacy review.

For every material retrieval or representation change, compare at least these
three modes with equal filters and comparable candidate budgets:

1. keyword-only retrieval;
2. vector-only retrieval;
3. hybrid keyword + vector retrieval with RRF.

Use these datasets for model, dimension, query-instruction, lexical-term
selection, fusion, ranking-feature, and embedding-input ablations. Separate
configuration tuning from the held-out release comparison so repeated
experiments do not optimize directly on the reported test examples.

### Related-paper offline set

Human relevance judgments are a mandatory model-selection and production-release
gate. Task/category agreement, lexical overlap, citation relationships, and
click telemetry are diagnostics and cannot select the winner by themselves.

Use this product definition in the labeling instructions: a strongly related
paper is a useful next paper for someone researching the source paper's central
technical contribution. This can include shared problems/methods as well as
work that substantially builds on, adopts, extends, or evaluates the source,
even when the relationship is asymmetric or the high-level task labels differ.
No single relationship type is privileged: the LatentMoE/Nemotron pair
(arXiv:2601.18089 and arXiv:2512.20856) is one positive example, not a template
that the ranking should overfit. A shared citation, author, venue, broad field,
or generic baseline comparison alone is insufficient. Grade 1 means a shared
central problem or important technique with a materially different main
question. Same broad category alone is grade 0.

Use a two-stage blinded evaluation. For the initial bakeoff, sample 100 source
papers across research areas, years, citation bands, abstract lengths, external
resources, and sparse/missing task metadata. Pool and deduplicate the top
candidates from every model/configuration, hide model identity and similarity
scores, randomize candidate order, and grade every source-candidate pair as
`0 = unrelated`, `1 = somewhat related`, or `2 = strongly related`. This shared
pool ensures every candidate is judged against the same labels and avoids
grading duplicate neighbors repeatedly. Expand the stratified set to at least
200 source papers before production activation. Include hard cases:

- same task but different problem/setting;
- same method across different tasks;
- asymmetric technical dependencies where one paper builds on or deploys the
  other's central contribution;
- survey versus primary paper;
- later follow-up versus duplicated version;
- generic abstracts and acronym collisions;
- biomedical papers to test whether the three-task MTEB average matters.

Measure nDCG@4, graded Precision@4, intra-list diversity, duplicate rate,
coverage, task/category agreement as diagnostics, and latency. Compare against
the current first-task-plus-citations baseline and a simple TF-IDF/FTS baseline.
Also compare dense-only related retrieval with the dense-plus-lexical RRF
variant; ship hybrid only if it improves the blinded set without creating an
acronym or superficial lexical-overlap bias.
Preserve the anonymized judgments as a versioned fixture so future model and
ranking changes are evaluated against the same gate, while periodically adding
fresh examples to limit overfitting to the fixture.

### Search set

Use the existing search fixture and metrics in `PLAN_SEARCH.md`. Evaluate the
same document vectors with F2LLM `encode_query`; clustering strength alone does
not establish retrieval quality. Hybrid search must improve natural-language
Recall@20/nDCG@10 without regressing title, acronym, or identifier queries.

### Model decision

There is no hard V1 dimension ceiling. Promote a model/dimension pair only if it
beats the current related baseline materially and meets hybrid-search gates.
Use each model's full native output as its quality reference, then choose the
smallest model-supported dimension that stays within the agreed relevance
tolerance. Test Qwen3's native Matryoshka outputs at minimum at 256, 512, and
1024 dimensions. The F2LLM cards do not advertise Matryoshka dimensions, so do
not truncate them by assumption. Consider PCA only after V1 because it adds a
fitted, versioned transformation that must also run on every online query.

Run Jina as a challenger only after resolving its non-commercial license. If a
single model cannot satisfy both recommendation and search, retain the shared
pipeline/schema but permit separate versioned generations; accept the doubled
storage and backfill cost only for a measured relevance gain. Include raw vector
size, total HNSW index size, warm/cold KNN latency, exact-versus-HNSW recall,
query-encoding latency, and end-to-end relevance in every model/dimension
comparison; do not select on MTEB score alone.

## Observability, rollout, and rollback

Feature flags:

```text
PWC_RELATED_PAPERS_MODE=task|embedding
PWC_PAPER_SEARCH_SEMANTIC_ENABLED=false|true
PWC_EMBEDDING_GENERATION_ID=<id>
PWC_QUERY_EMBEDDER=disabled|hf_endpoint
```

Record generation ID, source-vector availability, KNN latency, returned count,
similarity distribution, fallback reason, query-encoding latency, and hybrid
component ranks. Do not log raw search queries by default. Cache related results
by `(paper_id, generation_id, ranking_version)`; invalidate naturally on a
generation/ranking-version change.

Roll out Related papers first because it requires no synchronous inference:

1. shadow-query embeddings and compare results/latency without changing UI;
2. enable for admins or a small traffic percentage;
3. compare clicks on related cards, downstream dwell/return signals if policy
   permits, coverage, fallback rate, and latency;
4. expand gradually, with the task mode as instant rollback;
5. only then enable hybrid-search semantic retrieval behind its independent
   flag.

Never drop the old generation during rollout. A rollback changes configuration,
not data or indexes.

## Implementation order

1. Create the related-paper judgment fixture and evaluation script.
2. Prototype the four compact candidates in the V1 shortlist on a
   representative 5k-10k corpus with an HF Job; save artifacts to a temporary
   private Bucket and compare exact neighbors. For Qwen3, evaluate 256, 512, and
   1024 native dimensions from the same full embeddings.
3. Install and test the committed pgvector V1 backend in an isolated PostgreSQL
   16 environment; record latency, exact-versus-HNSW recall, filtered retrieval,
   index size, and database resource impact as the migration baseline.
4. Add generation tables, importer, exact/HNSW recall tests, and migrations.
5. Run the full F2LLM backfill through Jobs/Buckets and import a non-active
   generation.
6. Add the indexed related endpoint, backend tests, and frontend integration
   behind `PWC_RELATED_PAPERS_MODE`.
7. Shadow, evaluate, and gradually enable embedding-related papers.
8. Add the incremental export/Job/import workflow and freshness monitoring.
9. Deploy and benchmark a protected HF Inference Endpoint for the selected
   model revision, dimension, instruction, and normalization contract.
10. Add semantic candidates and RRF to search, then roll out independently.

## Definition of done

- Every latest paper has either an active-generation embedding or an explicit,
  observable reason it does not.
- The model revision, input format, dimensions, normalization, artifacts, and
  package versions are reproducible from a run manifest.
- Failed Jobs and imports resume without recomputing valid shards or corrupting
  the active generation.
- Related papers improve nDCG@4/Precision@4 over the task-plus-citations
  baseline and meet latency/coverage gates.
- Related requests require no online model inference and fall back safely.
- Hybrid search reuses the corpus vectors, uses the matching query encoder, and
  improves the search relevance set without identity-query regressions.
- PostgreSQL, VPS memory/disk, Job, Bucket, endpoint, latency, and fallback
  metrics have documented alerts and runbooks.
- Model generation activation and every product flag can be rolled back without
  deleting data or interrupting production.
