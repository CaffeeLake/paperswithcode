# Completion audit: related papers and shared search embeddings

Audit date: 2026-07-18. Scope is all of `PLAN_RELATED_PAPERS.md` plus the
shared-embedding and hybrid-RRF portions of `PLAN_SEARCH.md`. Search reranking
and optional ParadeDB BM25 remain outside this shared-embedding scope.

| Requirement | Implementation | Verification |
| --- | --- | --- |
| Versioned judgment fixtures and four-way model bakeoff | Sanitized graded fixtures, pinned candidate configuration, exact-neighbor run builder, blinded pool/evaluator, pinned HF Dataset loader | Unit metric/ranking tests; full human labels and model runs require authorized external resources |
| Deterministic shared input contract | `embedding_contracts.py` normalizes title/abstract and hashes the format version plus exact text | Unit normalization/hash/manifest tests |
| Consistent export and immutable artifacts | Repeatable-read JSONL shards, checksums, corpus snapshot, model/revision/dimension contract, full/delta export | Manifest checksum tests and CLI parser tests |
| HF Jobs GPU worker | PEP 723 worker; pinned revision; `encode_document`; length sorting; adaptive OOM batches; normalized float16 Parquet; atomic markers/resume; full provenance and throughput | Compilation/lint plus contract tests; dry-run command only, as required |
| Bucket retention | Rule-based protected active/previous/pinned policy; separate plan/apply commands and destructive confirmation | Unit retention-policy test |
| pgvector generations and atomic activation | Extension migration; list partitions; dimension trigger; per-generation HNSW; concurrently built indexes; zero-missing/stale activation gate; prior-generation retention | Disposable integration test is implemented and safely skips because host pgvector is unavailable |
| Verified import | Output checksum/schema/dtype/dimension/norm/uniqueness/coverage checks; current content-hash rejection; bounded idempotent upserts | Unit contract coverage; live pgvector import awaits isolated extension authority |
| ANN serving benchmark | Exact-vs-HNSW Recall@K, filtered KNN latency, plans, and relation/index bytes | Script compiles; execution awaits isolated pgvector database |
| Related ranking and fallback | Dense K=50; optional rare-lexeme+RRF ranking version; latest-only candidates; stale source-vector support; confidence floor; semantic-first task fill; provenance; generation-aware cache | Task fallback API integration test; dense SQL covered by isolated migration/benchmark path |
| Related frontend | Paper-ID endpoint/query key, existing four-card layout, loading/empty behavior, ArXiv/external routes | ESLint and TypeScript checks |
| Incremental refresh and observability | Active-generation hash delta export, idempotent import, 24-hour freshness state, missing/title-only counts, oldest missing, recent runs, structured privacy-safe serving logs | Unit pipeline policy tests and documented alert/runbook paths |
| Protected scale-to-zero query inference | Dry-run protected TEI endpoint plan pinned to revision; prompt-name query encoding; 500 ms default; shared concurrency/cache/circuit state; strict response validation; immediate FTS fallback | Warm/cache, malformed, circuit-open, timeout, and recovery tests |
| Hybrid search | 50 lexical + 50 semantic candidates, weighted RRF, component ranks, latest-only filters, exact-title/ArXiv overrides, independent flag and lexical fallback | RRF tests, existing PostgreSQL FTS suite, hybrid-capable benchmark command |
| Rollback | Independent related/search/query-encoder/generation flags; activation is transactional; no deletion required | Configuration and runbook review |

No Bucket, Dataset repository, Job, scheduled Job, or Inference Endpoint was
created. No production migration, build, restart, reload, or deployment was
performed. The empirical release gates (human relevance gain, real GPU serving
measurements, real ANN recall/latency, full corpus coverage) intentionally remain
unclaimed until an operator authorizes the isolated/external pilot and supplies
the expanded blinded judgments.
