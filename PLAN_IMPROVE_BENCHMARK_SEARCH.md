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

## Resolved design decisions

### Multi-term query semantics

Use AND semantics for complete query terms, matching
`websearch_to_tsquery` behavior. A benchmark must match every complete term;
do not broaden ordinary lexical retrieval to results matching only one term.

This still supports benchmark-family discovery. For example, `SWE Bench`
matches SWE-Bench Pro, SWE-Bench Verified, SWE-Bench Multilingual, and other
variants because every result contains both terms. The more specific
`SWE Bench Multilingual` should narrow to multilingual matches rather than
injecting sibling family members that do not match the final term.

If the product later needs explicit family expansion, model and rank it as a
separate relation-aware candidate lane rather than weakening lexical matching
to OR semantics.

### Partial-token semantics

In the live-typing name/slug lane, prefix-match every query token and require
all token prefixes to match. For example, `swe ben mul` should match
`SWE-Bench Multilingual`.

Do not perform arbitrary within-token suffix or infix matching. A query such as
`imi` should not match the `Kimi` token. Exact short tokens remain valid:
`k3` matches `Kimi K3` because `K3` is a complete standalone token, not because
of substring matching.

### Searchable content boundary

Benchmark, method, and task search should match entity names, not descriptive
content. For benchmarks, ordinary lexical candidates come from the displayed
`name` only. `full_name`, `description`, and `short_description` must not
contribute ordinary matches or rank. An exact normalized `full_name` remains an
identity lookup for users who deliberately enter the complete expansion.

Apply the same boundary to follow-up method and task search:

- methods: displayed name for ordinary search and exact full name for identity,
  not description, keywords, collection description, or source text;
- tasks: name, not description, research trends, or keywords; and
- papers remain unchanged: paper keyword/hybrid search continues to use title
  and abstract.

This deliberately trades descriptive discovery for precision in navigational
entity search. It prevents results such as an EETm2 benchmark appearing for
`Transformer` solely because the description mentions transformers.

### Slug semantics

Use slugs only for exact, case-insensitive identity lookup. Do not include slug
tokens in ordinary FTS or partial-prefix matching.

This preserves navigation from pasted URLs and known stable identifiers while
ensuring every non-identity result has a visible match in its displayed name.
Legacy or internal wording present only in a slug must not produce a surprising
result.

### Sparse benchmark visibility

Global navigational search must include every configured benchmark, including
benchmarks with zero or one logical leaderboard entry. Remove the overlay's
`min_eval_count=2` argument.

Keep `min_eval_count` as a supported datasets API filter for task-page browsing
and other callers that intentionally suppress sparse leaderboards. Search must
continue to honor it when explicitly supplied, but global search should not
supply it. Leaderboard-entry count remains a secondary ranking and display
signal, not a visibility gate.

### Global trend tie-breaker

After identity and textual relevance, rank ties by benchmark reporting trend,
not raw logical leaderboard-entry count.

Global search has no task context, so compute the trend across all task
associations: count each distinct latest-version paper once per benchmark when
it reports an evaluation during the most recent 90 days, then normalize that
count to reports per 30 days, matching the existing benchmark trend concept.
For tied trend scores, prefer the most recent reporting-paper date, then
all-time distinct reporting-paper count, then alphabetical name and dataset ID.

As of 2026-07-28, only 42 of 1,484 benchmarks (2.83%) are linked to more than
one task: 39 have two tasks, two have three, and one has four. Global
aggregation is therefore equivalent to task-specific trend for nearly all
linked benchmarks while giving the global overlay one coherent signal.

Calculate trend aggregates only for the bounded textual candidate set, not the
entire benchmark catalog on every keystroke. Entry count remains response
metadata and may be a final deterministic fallback, but it is not the primary
popularity tie-breaker.

### Featured rank is outside this plan

Do not read, preserve, migrate, or rank by `task_datasets.featured_rank` in this
work. Its end-to-end removal is owned by a separate task.

Build benchmark search ranking solely from identity, name relevance, and
benchmark reporting trend. Keep this implementation compatible with the
expected absence of `featured_rank`; do not add a temporary compatibility
branch that would prolong the obsolete ranking path.

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
- incidental description text produces surprising entity matches, such as
  EETm2 appearing for `Transformer`;
- the frontend's requested `ordering=-paper_count` is not used by
  `search_datasets`, which currently forces name ordering; and
- whole-query substring matching becomes increasingly brittle as benchmark
  metadata grows.

## Goals

- Make `swe bench multilingual` find `SWE-Bench Multilingual`.
- Preserve exact lookup by numeric ID and slug.
- Rank exact name and slug matches deterministically above ordinary FTS hits.
- Search benchmark names only; exclude descriptive text from retrieval.
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

Retain a bounded token-prefix path for inputs such as `swe ben mul`. Plain
PostgreSQL FTS does not automatically match unfinished lexemes, and removing
prefix matching would regress the command-palette experience.

Apply token-prefix matching only to normalized `name`. Require every query
token to prefix-match a token in that displayed name.

Do not add arbitrary within-token suffix or infix matching. Keep this lane
index-friendly where practical. Prefer PostgreSQL prefix `tsquery` terms if
they produce the required behavior and acceptable plans. Measure an expression
index or `pg_trgm` only if query plans show it is needed; do not add an
extension by default.

### 3. Name FTS lane

Add a maintained `datasets.search_vector` with these initial weights:

```sql
setweight(to_tsvector('simple', coalesce(name, '')), 'A')
```

Use `websearch_to_tsquery` and `ts_rank_cd`, following the paper keyword-search
implementation. Unquoted multi-term queries use AND semantics: all complete
terms must match. Use the `simple` configuration so entity names, acronyms, and
identifiers are not English-stemmed. Do not include description or
short-description fields in the vector. Do not include `full_name`; it is
identity-only.

The relevance fixture described below decides the final configuration.

## Ranking

Rank candidate benchmarks by:

1. identity tier;
2. partial-name tier;
3. descending weighted FTS rank;
4. descending global 90-day reporting trend;
5. descending latest reporting-paper date;
6. descending all-time distinct reporting-paper count;
7. ascending benchmark name;
8. ascending benchmark ID.

A benchmark may appear in more than one candidate lane. Deduplicate by dataset
ID and retain its best identity/partial tier and best lexical rank.

Do not use raw evaluation-record count or logical leaderboard-row count as the
primary popularity signal. Continue using the distinct logical leaderboard-row
count for the displayed `paper_count` value so the API and benchmark page agree.

## Implementation phases

### Phase 0: Baseline and relevance fixture

Create `backend/tests/fixtures/benchmark_search_relevance.json` with queries
covering:

- punctuation variants: `swe bench multilingual`, `swe-bench multilingual`;
- acronyms: `gpqa`, `mmlu pro`, `humaneval`;
- exact slug and numeric ID;
- reordered or descriptive queries;
- partial live input: `swe ben mul`, `k3`;
- negative infix input: `imi` must not match a standalone `Kimi` token;
- broad terms with multiple legitimate results;
- quoted phrases and punctuation;
- stop-word-heavy input;
- blank or whitespace-only input; and
- task-scoped queries with `min_eval_count`.
- exact global-search matches with zero and one leaderboard entry.

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
- descriptions not creating matches;
- global trend, latest report date, and all-time reporting-paper tie-breaks;
- deterministic ordering for ties;
- deduplication across candidate lanes;
- pagination and total counts;
- `min_eval_count`;
- global overlay visibility for zero- and one-entry benchmarks;
- task scoping and descendant inclusion;
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

Do not run a routine frontend production build. The expected frontend change
is limited to removing `min_eval_count: 2` from the global overlay's benchmark
request.

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

The API retains `min_eval_count`; the global overlay no longer supplies it.

The frontend currently supplies `ordering=-paper_count`. Decide explicitly
whether search should honor that parameter. The recommended behavior is:

- relevance is always primary when `q` is present;
- the global overlay stops requesting `ordering=-paper_count`; and
- global benchmark reporting trend is the default popularity tie-breaker.

Update the endpoint documentation so “search” describes tokenized,
relevance-ranked matching rather than generic substring matching.

## Methods follow-up

Yes, methods should use the same search pattern after benchmarks.

Method search currently performs the same whole-query `%ILIKE%` matching over
name, full name, and description. It is therefore vulnerable to punctuation,
word-order, and ranking problems.

For methods, use:

- weight A: displayed name only;
- exact ID/slug/normalized-name identity lanes;
- normalized partial-name matching for live typing; and
- a separately defined method popularity tie-breaker; benchmark reporting trend
  must not be copied to methods because their evidence model differs.

Do not search method descriptions, keywords, collection descriptions, or
source text. The global entity search is navigational and name-only.

Do not implement methods in the benchmark migration. First extract and validate
the reusable pieces:

- query normalization;
- identity-tier construction;
- partial-name-tier construction; and
- result-ordering conventions.

Then create a separate method search vector, migration, relevance fixture, and
targeted rollout. This limits blast radius and prevents a benchmark-specific
ranking choice from becoming an accidental generic abstraction.

Tasks should eventually adopt the same name-only matching boundary, but they
should be evaluated separately because hierarchy and curated navigation make
their ranking policy materially different. Task descriptions, research trends,
and keywords should not create search matches.

## Completion criteria

The benchmark-search work is complete when:

- punctuation and whitespace variants find the intended benchmark;
- exact identifiers remain deterministic;
- partial live typing has not regressed;
- relevance is text-first with global reporting trend only as a tie-breaker;
- all existing filters and API contracts are preserved;
- the maintained vector and GIN index are verified;
- focused tests and lint pass;
- the exact pushed commit is healthy on staging; and
- production has not been changed without explicit approval.
