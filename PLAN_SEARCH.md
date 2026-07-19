# Plan: Hybrid Paper Search

## Decision

Build paper search in PostgreSQL, in incremental and measurable stages:

1. Replace the current `ILIKE` and citation-first implementation with weighted
   PostgreSQL full-text search (FTS).
2. Establish an offline relevance set and production search telemetry.
3. Build one versioned paper-embedding pipeline on Hugging Face Jobs and
   Buckets. Serve it from `pgvector` for both semantic related papers and dense
   search, with different ranking policies for the two products.
4. Rerank the fused candidate set with Cohere or a small local cross-encoder.
5. Evaluate true BM25 through ParadeDB `pg_search` only if native FTS is the
   measured bottleneck.

Do not add Elasticsearch at the current corpus size. It would duplicate data and
add another stateful service without a demonstrated relevance or scale need.

## Current state

As of 2026-07-17:

- PostgreSQL 16 contains approximately 104,000 latest paper rows.
- `GET /api/v1/papers/search?q=...` calls
  `PaperService.search_papers()` in `backend/services/paper_service.py`.
- Search matches title and abstract using `%ILIKE%` and ranks primarily by raw
  citation count, with small title-match boosts.
- The endpoint description says it uses full-text search, but the implementation
  does not.
- The database already has separate expression GIN indexes named
  `idx_papers_title_search` and `idx_papers_abstract_search`. The current `ILIKE`
  query cannot use them, and separate indexes do not provide a single weighted
  title-plus-abstract rank.
- Search returns only `is_latest_version` papers and must preserve that behavior.
- There is no installed or available `pgvector` extension or embedding table
  yet.
- The root filesystem has about 11 GB free and the VPS has 8 GB RAM. This is
  enough for a compact vector table and index, but not for GPU backfills, model
  caches, duplicated model processes, and unconstrained index builds.
- The current related-papers UI is not similarity based. It selects the four
  most-cited papers that share the source paper's first task.

## Goals

- Improve relevance for exact titles, technical terms, acronyms, and natural
  language descriptions.
- Keep exact identity lookups deterministic: normalized paper title and ArXiv ID
  matches should not be displaced by popularity.
- Make textual relevance the primary ranking signal. Citations and recency may
  be bounded secondary signals, not the main score.
- Keep search on the existing VPS and avoid an additional search datastore.
- Reuse one document embedding for search and related-paper retrieval.
- Use Hugging Face Jobs for accelerator-heavy batch inference, Buckets for
  durable manifests/checkpoints/artifacts, and Sentence Transformers for model
  inference.
- Preserve the existing API response model and `limit` behavior.
- Keep every search stage independently deployable, measurable, and reversible.
- Provide a graceful fallback if embedding or reranking inference is unavailable.
- Keep p95 latency suitable for the interactive search overlay.

## Non-goals

- Do not search full PDF contents in the first version.
- Do not add Elasticsearch, OpenSearch, or a hosted vector database.
- Do not make Semantic Scholar a synchronous dependency of the search endpoint.
- Do not train a custom embedding model or reranker initially.
- Do not add fuzzy spelling correction until query logs show it is needed.
- Do not change task, method, dataset, author, or evaluation search in this plan.
- Do not use a periodically downloaded FAISS index as the production source of
  truth. It complicates filtering, incremental updates, and atomic rollout while
  duplicating data already served by PostgreSQL.
- Do not restart PostgreSQL, rebuild the frontend, reload nginx, or deploy
  production as part of routine development.

## Ranking pipeline

The intended final pipeline is:

```text
query
  -> identity candidates (exact title / ArXiv ID)
  -> lexical candidates (weighted FTS, later optionally BM25)
  -> semantic candidates (pgvector HNSW)
  -> weighted RRF over candidate ranks
  -> cross-encoder rerank of the top 20-50
  -> bounded business signals and deterministic identity overrides
  -> top 10-20 results
```

RRF combines ranks rather than incompatible raw lexical and vector scores:

```text
rrf_score = lexical_weight / (rrf_k + lexical_rank)
          + semantic_weight / (rrf_k + semantic_rank)
```

Start with `rrf_k = 60` and equal weights. Tune only against the relevance set.

## Phase 0: Safety, evaluation, and baselines

### 0.1 Free disk space

Before adding embeddings or large indexes, make at least 5-10 GB available on
the root volume or expand the volume. Resolve exact cleanup targets with
read-only checks first; do not delete repository or database data broadly.

Weighted FTS development can begin before this is complete, but production index
creation must first confirm enough free space for both the new index and
temporary build data.

### 0.2 Capture the legacy baseline

Create a repeatable benchmark command that records:

- query
- ordered paper IDs
- title
- citation count
- request latency
- query plan for representative query shapes

Include at least these query classes:

- exact titles: `Attention Is All You Need`
- ArXiv IDs: `1706.03762`, with and without a version suffix
- acronyms and identifiers: `BERT`, `DETR`, `LoRA`, `SAM 2`
- task phrases: `monocular depth estimation`, `3d object detection`
- natural language: `generate video from a text description`
- rare technical terms: `rotary position embedding`, `gaussian splatting`
- broad terms: `transformer`, `image generation`
- punctuation and web syntax: quoted phrases, hyphens, parentheses
- stop-word-heavy and blank/whitespace queries

Store a small hand-judged fixture under
`backend/tests/fixtures/paper_search_relevance.json`. Each entry should contain
the query and relevant paper IDs with optional graded relevance (`0`, `1`, `2`).
Do not make the first release wait for a perfect dataset; 50-100 useful queries
are enough to prevent obvious regressions.

### 0.3 Metrics and release gates

Measure:

- MRR@10
- nDCG@10 when graded judgments exist
- Recall@20
- zero-result rate
- p50 and p95 endpoint latency
- percentage of queries using the intended index

Initial gates for Phase 1:

- Exact normalized title and ArXiv ID cases return the intended paper first.
- No judged query class regresses materially from the legacy baseline.
- Aggregate MRR@10 improves over legacy search.
- Warm-cache p95 database time is below 150 ms for the fixture queries on the
  VPS; revisit the target after measuring real traffic.
- `EXPLAIN (ANALYZE, BUFFERS)` shows the new GIN index is used for representative
  selective queries.

## Phase 1: Weighted PostgreSQL full-text search

This is the first implementation milestone.

### 1.1 Add one maintained weighted search vector

Use one `tsvector` containing weighted fields:

```sql
setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
setweight(to_tsvector('english', coalesce(abstract, '')), 'B')
```

Do not include citation count, date, tasks, or methods in the vector. Those are separate signals with different update behavior.

Recommended low-lock migration:

1. Add nullable `papers.search_vector tsvector` without a table default.
2. Add a small trigger function and `BEFORE INSERT OR UPDATE OF title, abstract`
   trigger to populate it for new and changed rows.
3. Backfill existing rows in bounded batches, committing between batches.
4. Validate that all latest rows have a non-null vector.
5. Create a partial GIN index concurrently:

   ```sql
   CREATE INDEX CONCURRENTLY idx_papers_latest_search_vector
   ON papers USING gin (search_vector)
   WHERE is_latest_version;
   ```

6. After the new path is proven, remove the redundant title and abstract GIN
   expression indexes in a later migration, not in the initial rollout.

Put the schema migration in
`backend/database/migrations/add_paper_search_vector.sql`. Put the resumable
backfill in a dedicated Python script if batching cannot be expressed safely in
the migration. Database commands must use:

```bash
uv run --env-file backend/keys.env ...
```

Do not apply this migration to production until deployment is explicitly
requested. Test it against an isolated database first.

### 1.2 Add the model field

Add the PostgreSQL `TSVECTOR` column to `Paper` in
`backend/models/database.py`. The application should treat it as database-
maintained and must not try to construct vectors in Python.

### 1.3 Replace the search query

Update `PaperService.search_papers()` to:

1. Trim and validate the query. Return an empty list for blank input.
2. Normalize an ArXiv URL or ID for an exact identity lookup.
3. Build the lexical query with
   `websearch_to_tsquery('english', :query)` so normal user punctuation does not produce `tsquery` syntax errors.
4. Match `search_vector @@ query` and only latest paper versions.
5. Rank with `ts_rank_cd(search_vector, query, 32)`.
6. Apply deterministic tiers in this order:
   - exact ArXiv ID
   - exact normalized title
   - lexical rank
   - bounded popularity tie-breaker
   - publication date and ID as stable final tie-breakers
7. Limit in SQL, not in Python.

Do not directly add raw `citation_count` to the FTS score. Initially use citation
count only after textual relevance, or use a very small `ln(1 + citation_count)`
term whose maximum effect is explicitly capped and covered by tests.

Keep an identity lane separate from FTS when necessary. ArXiv identifiers and
some punctuation-heavy model names are not natural-language search terms and
should not depend on the English dictionary.

### 1.4 Keep the API contract accurate

Update the `/papers/search` summary and docstring in
`backend/routers/papers.py` so they describe the implementation that actually
runs. Preserve:

- endpoint path
- `q` parameter
- `limit` range
- `List[PaperSummary]` response

Add a temporary setting such as:

```text
PWC_PAPER_SEARCH_MODE=legacy|fts
```

Default to `legacy` until the isolated migration and relevance checks pass.
Production rollout can switch to `fts` without deleting the old implementation.
Remove the legacy path after the FTS rollout has been stable and evaluated; do
not retain a permanent compatibility abstraction.

### 1.5 Tests

Add real pytest coverage rather than relying on the current manual
`backend/tests/test_citation_search.py` script.

Required cases:

- exact title ranks first despite a less relevant paper having more citations
- title matches outrank abstract-only matches because of A/B weights
- stemming works for an English query
- multi-term and quoted queries are accepted
- punctuation cannot cause a `tsquery` syntax error
- ArXiv IDs resolve deterministically
- only latest versions are returned
- blank input is handled without querying all papers
- result count respects `limit`
- stable ordering when rank and citation counts tie
- the API response schema is unchanged
- legacy mode still works during the rollout window

Use a PostgreSQL integration test for ranking semantics. SQLite or mocked ORM
tests cannot verify `tsvector`, GIN, `websearch_to_tsquery`, or `ts_rank_cd`.

### 1.6 Phase 1 verification

Before enabling FTS:

```bash
uv run --env-file backend/keys.env pytest <targeted search tests>
uv run --env-file backend/keys.env python <search benchmark command>
```

Also verify:

- latest-row vector coverage is 100%
- the trigger populates inserts and title/abstract updates
- the partial GIN index is valid
- representative plans use the partial GIN index
- the old and new endpoint responses serialize identically
- the feature flag can return immediately to legacy search

## Phase 2: Search telemetry and relevance iteration

Add privacy-conscious application metrics before semantic retrieval:

- search mode
- normalized query fingerprint, not raw query text by default
- result count
- database duration
- total duration
- timeout/error/fallback count
- clicked result position if frontend analytics policy permits it

If raw queries are retained for relevance work, define a retention window and
exclude obvious secrets or personal data. Search must continue working when
telemetry fails.

Use observed queries to expand the relevance fixture. Tune field weights and
identity rules before adding a more complex retrieval system.

## Phase 3: shared embedding corpus and pgvector semantic retrieval

Proceed only after Phase 1 is stable. Follow the model, Jobs/Buckets pipeline,
schema-generation, sizing, incremental-refresh, and operational design in
`PLAN_RELATED_PAPERS.md`. Roll out embedding-based related papers first: they
exercise the document corpus and ANN index without adding synchronous model
inference to search requests.

### 3.1 Extension and schema

Install a PostgreSQL-16-compatible `pgvector` package in an isolated environment
and validate the extension before any production change.

Use versioned generation and embedding tables rather than a permanent embedding
column on `papers`. The abbreviated search-facing shape is:

```text
paper_embeddings
  generation_id     bigint
  paper_id          bigint
  content_hash      text
  embedding         halfvec(1024)
  created_at        timestamptz
```

Start by evaluating pinned `codefuse-ai/F2LLM-0.6B`: use
`encode_document` for stored title-plus-abstract papers and `encode_query` for
search text. It produces 1024-dimensional vectors and is also the primary model
candidate for related-paper similarity. Do not combine query and document
vectors produced by different models.

F2LLM replaces the earlier `BAAI/bge-small-en-v1.5` default because the supplied
MTEB analysis targets title-plus-abstract scientific clustering directly and
because a shared high-quality corpus avoids immediately maintaining two vector
generations. This is still an evaluation hypothesis: hybrid-search judgments
must test query retrieval independently of clustering performance.

### 3.2 Backfill and incremental maintenance

- Compute `content_hash` from the exact normalized embedding input and version
  that formatting contract.
- Make exports, GPU encoding, artifact shards, and imports resumable and
  idempotent.
- Export from the VPS to a private Hugging Face Bucket, encode with Sentence
  Transformers on a Hugging Face Job GPU, then import verified shards into a
  non-active PostgreSQL generation.
- Keep database credentials off Jobs; Buckets are the handoff boundary.
- Embed new or changed latest papers incrementally from the ingestion workflow.
- Do not load the embedding model separately in every Uvicorn worker. Benchmark
  one bounded local query-encoder sidecar; use a protected Hugging Face
  Inference Endpoint with Text Embeddings Inference if local memory/latency does
  not meet the gate.
- Never use a transient HF Job to serve synchronous search requests.

### 3.3 Hybrid candidate retrieval

Retrieve an initial 50 lexical and 50 semantic candidates in parallel where
practical. Union by paper ID and calculate RRF, retaining the component ranks and
scores for debugging.

Rules:

- Exact identity candidates are always included.
- Filters must be applied consistently to both retrieval branches.
- A semantic inference timeout, endpoint cold start, or missing document
  embedding falls back to lexical results.
- Candidate counts and weights are configuration, but are changed only through
  measured experiments.

Phase 3 must improve Recall@20 and nDCG@10 on natural-language queries without
regressing exact-title, acronym, or identifier queries.

## Phase 4: Cross-encoder reranking

Rerank only the fused top 20-50 candidates. Pass title plus a truncated abstract,
not full PDFs.

Evaluate two implementations behind the same narrow interface:

1. Cohere Rerank for the quickest high-quality production experiment.
2. `cross-encoder/ms-marco-MiniLM-L6-v2` through quantized ONNX/OpenVINO for a
   fully local, CPU-friendly path.

Do not begin with `bge-reranker-base` on this VPS: its roughly 300M parameters
make CPU latency and resident memory substantially less attractive than the
22.7M-parameter MiniLM model.

Requirements:

- strict inference timeout
- lexical/hybrid fallback on failure
- concurrency bound so reranking cannot starve API workers
- query-result cache with a short, versioned key if traffic justifies it
- component latency and fallback metrics
- no network call when local/Cohere reranking is disabled

Choose Cohere versus local inference using measured relevance, p95 latency,
traffic-based monthly cost, and operational reliability. Do not assume the local
model is cheaper if it requires a larger VPS.

## Phase 5: Optional true BM25

Native PostgreSQL FTS is not BM25: `ts_rank` and `ts_rank_cd` do not use global
corpus inverse-document-frequency statistics.

Evaluate ParadeDB `pg_search` only if query judgments show lexical ranking is a
remaining limitation. Test it on an isolated copy of the database and compare:

- native FTS alone
- `pg_search` BM25 alone
- native FTS plus vectors plus reranking
- BM25 plus vectors plus reranking

Evaluate relevance, index size, build time, query latency, PostgreSQL version
compatibility, backup/restore behavior, extension upgrade procedures, and
licensing. Adopt it only if it gives a material end-to-end improvement after the
reranker; a better first-stage score may not change final top results.

## Operations and rollback

- All schema and index changes must first run against an isolated PostgreSQL
  instance or database copy.
- Use `CREATE INDEX CONCURRENTLY` for the production GIN and HNSW indexes.
- Check `pg_stat_progress_create_index`, disk space, and database load during
  production index creation.
- Do not run production migrations, restart PostgreSQL, restart FastAPI, rebuild
  the frontend, or reload nginx without an explicit deployment request.
- Keep each stage controlled independently:
  - lexical mode: `legacy|fts|bm25`
  - semantic retrieval: enabled/disabled
  - reranker: `disabled|cohere|local`
- The fallback chain is reranked hybrid -> RRF hybrid -> weighted FTS -> legacy
  only during the initial rollout window.
- Rollback should normally change configuration first. Do not drop a valid index
  or embedding table during an incident.

## Suggested implementation order

1. Add the relevance fixture and benchmark command.
2. Add the search-vector migration and isolated migration test.
3. Add the SQLAlchemy field and weighted FTS query behind `fts` mode.
4. Add PostgreSQL integration tests and query-plan checks.
5. Benchmark legacy versus FTS and adjust only evidence-backed ranking rules.
6. Explicitly deploy the Phase 1 migration and enable FTS gradually.
7. Add telemetry and expand judgments from observed query shapes.
8. Resolve disk headroom, then add pgvector and the embedding backfill.
9. Add RRF and validate hybrid retrieval.
10. Compare Cohere with a local MiniLM reranker.
11. Evaluate `pg_search` BM25 only if the measurements justify it.

## Definition of done

### Weighted FTS milestone

- A maintained, weighted title/abstract `tsvector` exists for every latest paper.
- A valid partial GIN index supports current-version search.
- `/papers/search` uses safe query parsing and relevance-first ranking in FTS
  mode.
- Exact title and ArXiv ID behavior is deterministic.
- Targeted PostgreSQL tests and the relevance benchmark pass.
- Query plans and p95 latency meet the Phase 1 gates.
- The endpoint documentation matches the implementation.
- Production can switch between legacy and FTS modes during rollout.

### Hybrid-search project

- Lexical and vector candidate retrieval are independently measurable.
- RRF improves the judged retrieval set without regressing identity queries.
- Reranking improves nDCG/MRR at acceptable p95 latency and cost.
- Every inference stage has timeouts, concurrency limits, metrics, and fallback.
- Incremental ingestion keeps search vectors and embeddings current.
- Operational documentation covers model upgrades, re-embedding, index rebuilds,
  rollback, and disk-capacity checks.
