# Plan: Improve Benchmark Search

## Decision

Replace benchmark search's whole-query `%ILIKE%` behavior with weighted
PostgreSQL full-text search (FTS), while retaining deterministic identity
matches and a normalized partial-match lane for live typing.

Use the same lexical principles as paper keyword search:

- `websearch_to_tsquery` for tokenization and punctuation-insensitive matching;
- a maintained, weighted `tsvector`;
- exact identity matches pinned above relevance-ranked results; and
- stable secondary ordering.

Do not call the paper retrieval implementation directly. Paper and benchmark
search have different models, filters, popularity signals, and response types.
Extract small shared query-normalization helpers only where doing so removes
real duplication.

Implement benchmark search first. Apply the same pattern to method search in a
separate follow-up after benchmark relevance and latency are validated.

## Problem

The global search overlay advertises benchmark search, but benchmark queries
currently pass the entire input to substring predicates over the dataset ID,
slug, name, full name, and description.

For example:

```text
stored name: SWE-Bench Multilingual
user query:  swe bench multilingual
```

The user query does not match because the space between `swe` and `bench` is
not the literal hyphen stored in the benchmark name. The same overlay returns
papers because paper search uses tokenized lexical/hybrid retrieval.

The current behavior also has these limitations:

- word order and punctuation variations frequently produce zero results;
- a relevant name match and an incidental description match are not ranked by
  a common lexical relevance score;
- the frontend's requested `ordering=-paper_count` is not used by
  `search_datasets`, which currently forces name ordering; and
- whole-query substring matching becomes increasingly brittle as benchmark
  metadata grows.

## Goals

- Make `swe bench multilingual` find `SWE-Bench Multilingual`.
- Preserve exact lookup by numeric ID and slug.
- Rank exact name and slug matches deterministically above ordinary FTS hits.
- Weight benchmark names more strongly than descriptive text.
- Preserve useful results while the user is still typing a final partial word.
- Preserve all existing dataset filters, especially task scoping,
  descendant-task expansion, `min_eval_count`, and `is_open`.
- Keep the existing datasets API and frontend response contracts.
- Keep warm search latency suitable for the debounced global overlay.
- Make rollout measurable, reversible, and safe on the resource-constrained
  production VPS.

## Non-goals

- Do not add semantic embeddings or hybrid vector search for benchmarks.
- Do not add Elasticsearch, OpenSearch, or another search service.
- Do not change paper hybrid search.
- Do not remove the overlay's `min_eval_count=2` visibility rule.
- Do not redesign the global search overlay.
- Do not combine papers, tasks, methods, and benchmarks into one API endpoint.
- Do not deploy to production without explicit production-release approval.

## Intended query behavior

Benchmark retrieval should use three candidate lanes.

### 1. Identity lane

Pin matches in this order:

1. exact numeric ID;
2. exact slug, case-insensitive;
3. exact normalized name;
4. exact normalized full name.

Normalization for identity comparison should:

- trim leading and trailing whitespace;
- case-fold;
- replace punctuation and separator runs with one space; and
- collapse repeated whitespace.

This makes `SWE-Bench Multilingual`, `swe bench multilingual`, and
`swe-bench multilingual` equivalent for exact normalized-name matching without
changing the stored display value.

### 2. Partial live-typing lane

Retain a bounded normalized partial-name path for inputs such as `swe mult`.
Plain PostgreSQL FTS does not automatically match an unfinished lexeme such as
`mult` to `multilingual`, and removing partial matching would regress the
command-palette experience.

Apply partial matching only to normalized slug, name, and full name, not the
full description. Prefer:

1. normalized name prefix;
2. normalized name substring;
3. normalized full-name prefix;
4. normalized full-name substring;
5. normalized slug prefix or substring.

Keep this lane index-friendly where practical. Measure an expression index or
`pg_trgm` only if query plans show it is needed; do not add an extension by
default.

### 3. Weighted FTS lane

Add a maintained `datasets.search_vector` with these initial weights:

```sql
setweight(to_tsvector('simple',  coalesce(name, '')),              'A') ||
setweight(to_tsvector('simple',  coalesce(full_name, '')),         'A') ||
setweight(to_tsvector('simple',  coalesce(slug, '')),              'A') ||
setweight(to_tsvector('english', coalesce(short_description, '')), 'B') ||
setweight(to_tsvector('english', coalesce(description, '')),       'C')
```

Use `websearch_to_tsquery` and `ts_rank_cd`, following the paper keyword-search
implementation. If combining `simple` name lexemes with an `english` query
causes measured acronym or stemming regressions, use separate name and
description vectors/queries and combine their ranks rather than guessing.

The relevance fixture described below decides the final configuration.

## Ranking

Rank candidate benchmarks by:

1. identity tier;
2. partial-name tier;
3. descending weighted FTS rank;
4. descending logical leaderboard-entry count (`paper_count`);
5. ascending benchmark name;
6. ascending benchmark ID.

A benchmark may appear in more than one candidate lane. Deduplicate by dataset
ID and retain its best identity/partial tier and best lexical rank.

When task scoping is active, preserve the existing featured-rank rule before
ordinary relevance only if product behavior requires curated pins to override
an explicit search query. Add a test documenting the chosen behavior. The
recommended default is that exact identity matches come first, then featured
rank, then lexical relevance.

Do not use raw evaluation-record count as popularity. Continue using the
service's distinct logical leaderboard-row count so ranking and displayed
entry counts agree.

## Implementation phases

### Phase 0: Baseline and relevance fixture

Create `backend/tests/fixtures/benchmark_search_relevance.json` with queries
covering:

- punctuation variants: `swe bench multilingual`, `swe-bench multilingual`;
- acronyms: `gpqa`, `mmlu pro`, `humaneval`;
- exact slug and numeric ID;
- reordered or descriptive queries;
- partial live input: `swe mult`, `multi swe`;
- broad terms with multiple legitimate results;
- quoted phrases and punctuation;
- stop-word-heavy input;
- blank or whitespace-only input; and
- task-scoped queries with `min_eval_count`.

Record the current ordered IDs and zero-result cases before changing search.
Hand-label the expected first result and any acceptable top results.

Initial release gates:

- all exact ID and slug cases return the intended benchmark first;
- `swe bench multilingual` returns benchmark `427` /
  `swe-bench-multilingual`;
- no fixture query loses a previously useful partial-name match;
- zero-result rate improves on the fixture;
- warm database p95 remains appropriate for the overlay, initially below
  100 ms for the fixture on the staging database; and
- representative `EXPLAIN (ANALYZE, BUFFERS)` output uses the GIN index for
  selective FTS queries.

### Phase 1: Schema and maintained search vector

Add a migration that:

1. adds nullable `datasets.search_vector tsvector`;
2. adds a trigger function that rebuilds it on inserts and changes to the
   indexed metadata fields; and
3. installs the trigger without performing an unbounded backfill in the same
   transaction.

Add the column to `backend/models/database.py` using the same PostgreSQL
`TSVECTOR` / SQLite `Text` variant as `Paper.search_vector`.

Backfill existing datasets in bounded, committed batches. The benchmark table
is expected to be small, but inspect its row count, disk headroom, and lock
impact rather than relying on that assumption.

Create the GIN index separately and concurrently after the backfill:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_datasets_search_vector
ON datasets USING gin (search_vector);
```

Provide verification queries for null-vector count, trigger behavior, index
validity, and representative query plans.

### Phase 2: Service retrieval and ranking

Refactor `DatasetService.search_datasets` so it no longer delegates unchanged
to the generic whole-query `get_datasets(search=...)` branch.

Build a dedicated search query that:

- computes identity and normalized partial tiers;
- uses the maintained FTS vector;
- preserves task and descendant scoping;
- preserves `min_eval_count` as a `HAVING` condition over logical leaderboard
  rows;
- preserves `is_open` behavior for best-model summaries;
- preserves pagination and total count;
- returns the existing `Datasets` API model; and
- uses deterministic ordering.

Avoid duplicating the complex dataset-to-API conversion and batched
best-result/harness lookups. Extract internal helpers from `get_datasets`
before implementing search if that keeps the query and projection readable.

Keep ID/slug lookup independent from the GIN-dependent lexical lane so exact
navigation still works if a row has not yet been backfilled.

### Phase 3: Tests

Add targeted tests for:

- punctuation-insensitive matching;
- exact ID, slug, name, and full-name priority;
- partial final-token matching;
- name matches outranking description-only matches;
- entry count as a secondary, not primary, relevance signal;
- deterministic ordering for ties;
- deduplication across candidate lanes;
- pagination and total counts;
- `min_eval_count`;
- task scoping and descendant inclusion;
- featured benchmark ordering under search;
- `is_open` summary selection;
- empty, whitespace, punctuation-only, and quoted queries;
- newly inserted and updated rows receiving a search vector; and
- the GIN index being valid after migration.

Use PostgreSQL-backed tests for FTS semantics. Keep normalization and ranking
policy helpers pure where possible so their edge cases can also be tested
cheaply without a database.

Run focused checks rather than the full suite:

```bash
uv run --env-file backend/keys.env pytest <targeted dataset/search tests>
uv run --env-file backend/keys.env ruff check <changed Python files>
git diff --check
```

Do not run a routine frontend production build. No frontend change should be
required unless the existing API wiring exposes a defect during validation.

### Phase 4: Staging rollout and validation

Follow the repository publishing contract:

1. validate the source changes locally;
2. fetch `origin main` and confirm local/remote `main` have not diverged;
3. commit the intended changes directly to `main`;
4. push `origin main`;
5. deploy that exact commit to staging with `pwc-deploy`;
6. run the standard staging smoke tests; and
7. exercise the global overlay with the relevance fixture.

Also compare:

- ordered results before and after;
- zero-result rate;
- p50 and p95 endpoint latency;
- query plans and index usage; and
- behavior while progressively typing representative queries.

Production deployment remains a separate, explicit user decision.

## API and frontend compatibility

Keep:

- `GET /api/v1/datasets/?q=...`;
- the `Datasets` response model;
- pagination fields;
- task, descendant, `min_eval_count`, and `is_open` parameters; and
- the overlay's existing benchmark rendering and navigation.

The frontend currently supplies `ordering=-paper_count`. Decide explicitly
whether search should honor that parameter. The recommended behavior is:

- relevance is always primary when `q` is present;
- requested ordering is a documented secondary tie-breaker; and
- `paper_count` remains the default secondary tie-breaker for the overlay.

Update the endpoint documentation so “search” describes tokenized,
relevance-ranked matching rather than generic substring matching.

## Methods follow-up

Yes, methods should use the same search pattern after benchmarks.

Method search currently performs the same whole-query `%ILIKE%` matching over
name, full name, and description. It is therefore vulnerable to punctuation,
word-order, and ranking problems, and method metadata already has useful
keyword and descriptive fields.

For methods, use:

- weight A: name, full name, slug;
- weight B: explicit `keywords`;
- weight C: description and collection description;
- exact ID/slug/normalized-name identity lanes;
- normalized partial-name matching for live typing; and
- paper count as a stable secondary popularity signal.

Do not implement methods in the benchmark migration. First extract and validate
the reusable pieces:

- query normalization;
- identity-tier construction;
- partial-name-tier construction; and
- result-ordering conventions.

Then create a separate method search vector, migration, relevance fixture, and
targeted rollout. This limits blast radius and prevents a benchmark-specific
ranking choice from becoming an accidental generic abstraction.

Tasks likely have the same eventual need, but they should be evaluated
separately because hierarchy, aliases/keywords, and curated navigation make
their ranking policy materially different.

## Completion criteria

The benchmark-search work is complete when:

- punctuation and whitespace variants find the intended benchmark;
- exact identifiers remain deterministic;
- partial live typing has not regressed;
- relevance is text-first with entry count only as a secondary signal;
- all existing filters and API contracts are preserved;
- the maintained vector and GIN index are verified;
- focused tests and lint pass;
- the exact pushed commit is healthy on staging; and
- production has not been changed without explicit approval.
