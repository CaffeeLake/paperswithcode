# Plan: Backfill Method Links and Make Usage Trends Comparable

## Decision

Replace the capped, method-centric historical citation pass with a resumable,
paper-centric reference backfill for methods whose citation histories cannot be
retrieved completely.

Keep `paper_methods` as the canonical public association table, but add
provenance for every association and explicit per-month backfill coverage. The
method trend API must expose coverage and must not present partially scanned
months as a complete usage history.

Run CLIP as the first production-sized backfill. Generalize the same workflow
to every method with a canonical source paper after CLIP's counts, runtime, API
usage, and storage impact have been validated. Prioritization controls order,
not final coverage.

## Resolved design decisions

### A source-paper citation counts as method relevance

A paper that cites a method's canonical source paper counts toward that
method's trend even when the method is not named in the paper's title or
abstract. Citation is sufficient evidence that the method remains relevant to
current research.

The trend is therefore a relevance/adoption proxy, not a claim that every
counted paper implemented or evaluated the method. `reference`, `keyword`,
`manual`, and `source` evidence all qualify, and a paper with several evidence
types is still counted only once.

### The user-facing label is “Mention trend”

Label the graph **Mention trend**. Its supporting copy should say that it counts
distinct papers that cite or explicitly mention the method, grouped by
publication month.

Do not call the graph “Usage trend” or “Method relevance.” “Mention trend”
communicates the chosen citation-inclusive definition without implying that
every paper implemented the method.

Rename the method-page headline statistic from **Papers using** to
**Papers mentioning** so its label matches the citation-inclusive definition.

### Show raw counts with normalized context

Use distinct monthly paper counts for bar heights. Do not normalize the primary
series.

In each tooltip, also show the percentage of all eligible latest-version papers
published in that month that mention the method. This provides context for
growth in the overall paper catalog without making the graph harder to read.

The denominator is the full Papers With Code catalog for that publication
month, not the method's area. Specifically, count distinct latest-version
papers with a non-null `date_published` in the month. Area membership must not
affect `catalog_paper_count` or `catalog_share`.

### Show the complete history since introduction

Method pages must request and display every calendar month from the method's
introduction through the current month. Remove the current 120-month product
ceiling for this route rather than truncating older methods to ten years.

The chart should reduce tick density to yearly labels for long histories while
retaining monthly bars and tooltips. A few hundred aggregate points is an
acceptable response size.

Choose the first displayed month deterministically:

1. the canonical source paper's publication month for a sourced method;
2. January of `introduced_year` for a source-less method; or
3. the earliest dated linked paper when both source date and introduced year
   are unavailable.

The backfill progress rows and trend API must use the same start-month helper so
coverage and displayed history cannot disagree.

### Backfill every sourced method

After CLIP validates the workflow, enqueue every method with a non-null
`source_paper_id` for complete historical reference coverage. Process methods
with capped or high citation counts first, then finish the remaining catalog in
bounded batches.

Methods without a canonical source paper can still receive `keyword` and
`manual` evidence. Their Mention trend remains useful and is computed from
those evidence types without requiring citation coverage.

### Use the union of all available evidence

For a method with a canonical source paper, Mention trend counts the distinct
union of:

- papers citing the canonical source paper;
- papers matched by the method's title/abstract keywords;
- manually linked papers; and
- the canonical source paper itself.

For a method without a canonical source paper, Mention trend counts the
distinct union of keyword and manual links. The graph remains available; it
does not need a warning merely because citation evidence is unavailable.

Never add the evidence counts together directly. One paper with keyword,
reference, and manual evidence contributes one mention.

### Keep one canonical source paper per method

Retain the existing single `methods.source_paper_id` model. For sourced
methods, citation matching uses that one canonical source paper together with
keyword and manual evidence.

Do not add secondary citation anchors or multiple method sources in this
iteration. If a method's source is wrong, curate the single canonical source
rather than accumulating alternatives.

### Manual removal is a durable veto

When a curator removes a method from a paper, automation must not re-add that
association from a keyword or citation match. Store a durable exclusion and
check it in the daily importer, weekly reference cron, and historical backfill.

A later explicit manual re-add removes the exclusion and creates `manual`
evidence. This makes the most recent curator decision authoritative.

### Keep new papers covered incrementally

Historical backfill complements rather than replaces the existing ingestion
path:

- the daily Hugging Face importer applies title/abstract keyword matches when a
  paper is imported; and
- the weekly `link_methods_by_references` cron scans the bibliographies of
  newly imported papers whose `methods_scanned_at` is null.

Update both writers to store provenance. Keep the weekly reference cron enabled
throughout and after the historical backfill so completed history does not
become stale.

### Isolate Semantic Scholar API keys by workload

Reserve `PWC_SEMANTIC_SCHOLAR_API_KEY` for the existing hourly citation updater
and weekly new-paper reference linker. Use
`PWC_SEMANTIC_SCHOLAR_API_KEY_2` exclusively for historical method backfills.

Do not pool or rotate the two keys within one job. If the secondary key is
missing or invalid, fail the historical backfill closed rather than falling
back to the primary key and starving incremental CRON work.

Add `PWC_SEMANTIC_SCHOLAR_API_KEY_2` to the supported credential probe without
printing its value. Document the separate workload ownership in CRON
configuration and operational logs.

## Why this is needed

The current historical linker walks citations from each method's source paper:

```text
method source paper -> Semantic Scholar citations -> local papers
```

Semantic Scholar limits offset pagination to the first 9,999 citations for one
paper. Highly cited methods therefore receive a recent-heavy partial backfill.
For CLIP:

- the source paper currently has 52,940 recorded citations;
- the historical linker can inspect at most 9,999 of them;
- October 2025 contains 309 CLIP links, but only 25 of those papers explicitly
  mention `CLIP` in their title or abstract; and
- 2,280 CLIP-linked papers currently have no publication date and are omitted
  from the monthly graph.

This creates an artificial cliff around October 2025. It does not show a real
change in CLIP usage.

The inverse scan already used for newly imported papers does not have the same
per-method ceiling:

```text
local paper -> Semantic Scholar references -> all known method source papers
```

That direction is the basis of this backfill.

## Goals

- Produce comparable monthly method-link coverage from a method's introduction
  through the present.
- Display the complete monthly history rather than only the latest 120 months.
- Complete historical reference coverage for every method with a canonical
  source paper.
- Preserve useful keyword/manual Mention trends for methods without source
  papers.
- Avoid the Semantic Scholar 9,999-citation ceiling.
- Resume safely after timeouts, rate limits, deploys, or process failures.
- Fetch a paper's references once per backfill batch and match all selected
  methods locally.
- Record whether a paper-method link came from a keyword, source-paper
  relationship, citation/reference match, manual curation, or unknown legacy
  data.
- Keep the existing `paper_methods` API and relationship contract intact.
- Make incomplete coverage visible to the API and frontend.
- Keep each run bounded for the resource-constrained production VPS.
- Support dry runs, targeted methods, targeted months, and deterministic
  verification before applying writes.

## Non-goals

- Do not claim that every citation proves the method was implemented or
  evaluated. Citation alone does qualify as research relevance and counts in
  the trend, while provenance keeps that interpretation inspectable.
- Do not scrape full paper text in this project.
- Do not replace Semantic Scholar or download its full corpus in the first
  iteration.
- Do not delete existing method links during the additive backfill.
- Do not change public method, paper, or relationship routes.
- Do not introduce multiple source papers or secondary citation anchors for one
  method.
- Do not deploy this workflow to production until CLIP has passed a staging
  dry run and the production run is explicitly approved.

## Data model

### 1. Preserve `paper_methods`

Continue using:

```text
paper_methods (paper_id, method_id)
```

as the canonical many-to-many relationship. Existing joins, API responses, and
admin operations must continue to work unchanged.

### 2. Add link provenance

Add a `paper_method_evidence` table:

```text
paper_id       BIGINT       NOT NULL
method_id      BIGINT       NOT NULL
evidence_type  VARCHAR(24)  NOT NULL
created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
last_seen_at   TIMESTAMPTZ  NOT NULL DEFAULT now()
details        JSONB        NULL

PRIMARY KEY (paper_id, method_id, evidence_type)
FOREIGN KEY (paper_id, method_id)
  REFERENCES paper_methods(paper_id, method_id)
  ON DELETE CASCADE
```

Allowed evidence types:

- `source`: the method's canonical source paper;
- `keyword`: deterministic title/abstract keyword matching;
- `reference`: the paper's bibliography contains the method source paper;
- `manual`: an explicit curator or accepted edit linked the method;
- `legacy_unknown`: an existing association whose origin cannot be recovered.

Use a database `CHECK` constraint rather than a PostgreSQL enum so adding an
evidence type does not require an enum migration.

The same link may have multiple evidence rows. For example, a paper can both
mention CLIP in its abstract and cite the CLIP source paper.

All writers must insert the parent `paper_methods` row first with
`ON CONFLICT DO NOTHING`, then upsert the corresponding evidence row. Updating
`last_seen_at` makes repeated runs idempotent and auditable.

### 3. Add durable monthly backfill state

Add a `method_reference_backfill_months` table:

```text
method_id             BIGINT       NOT NULL
month_start           DATE         NOT NULL
status                VARCHAR(16)  NOT NULL
eligible_papers       INTEGER      NOT NULL DEFAULT 0
processed_papers      INTEGER      NOT NULL DEFAULT 0
matched_papers        INTEGER      NOT NULL DEFAULT 0
unresolvable_papers   INTEGER      NOT NULL DEFAULT 0
retryable_failures    INTEGER      NOT NULL DEFAULT 0
cursor_published_at   DATE         NULL
cursor_paper_id       BIGINT       NULL
attempt_count         INTEGER      NOT NULL DEFAULT 0
started_at            TIMESTAMPTZ  NULL
completed_at          TIMESTAMPTZ  NULL
updated_at            TIMESTAMPTZ  NOT NULL DEFAULT now()
last_error            TEXT         NULL

PRIMARY KEY (method_id, month_start)
```

Allowed statuses are `pending`, `running`, `complete`, and `failed`.

This state is separate from `papers.methods_scanned_at`. The existing column was
backfilled on 2026-05-12 under the assumption that the capped bulk citation pass
was complete, so it cannot prove historical coverage.

The cursor must be the stable tuple `(date_published, paper_id)`. Never use
`OFFSET`, because new imports and version changes would make a resumed scan skip
or repeat arbitrary rows.

### 4. Add manual exclusions

Add a `paper_method_exclusions` table:

```text
paper_id       BIGINT       NOT NULL
method_id      BIGINT       NOT NULL
reason         TEXT         NULL
created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
updated_at     TIMESTAMPTZ  NOT NULL DEFAULT now()

PRIMARY KEY (paper_id, method_id)
FOREIGN KEY (paper_id) REFERENCES papers(id) ON DELETE CASCADE
FOREIGN KEY (method_id) REFERENCES methods(id) ON DELETE CASCADE
```

An exclusion deliberately does not reference `paper_methods`, because the
positive association must be absent while the exclusion exists.

Manual removal must upsert the exclusion, delete the `paper_methods` row, and
thereby cascade its positive evidence in one transaction. Manual re-add must
delete the exclusion, insert `paper_methods`, and upsert `manual` evidence in
one transaction.

Automated writers must anti-join `paper_method_exclusions` before inserting a
positive association. Historical progress still counts an excluded paper as
processed, but not matched.

### 5. Add keyword-backfill state

Add a `method_keyword_backfill_runs` table:

```text
keyword_catalog_sha256  CHAR(64)     PRIMARY KEY
status                  VARCHAR(16)  NOT NULL
eligible_papers         INTEGER      NOT NULL DEFAULT 0
processed_papers        INTEGER      NOT NULL DEFAULT 0
cursor_paper_id         BIGINT       NULL
started_at              TIMESTAMPTZ  NULL
completed_at            TIMESTAMPTZ  NULL
updated_at              TIMESTAMPTZ  NOT NULL DEFAULT now()
last_error              TEXT         NULL
```

Compute `keyword_catalog_sha256` from the ordered method IDs, matching keywords,
and matcher-version constant. A changed keyword or matcher creates a new
deliberate run rather than silently treating the old cursor as complete.

Only one run may be `running`. Protect it with a PostgreSQL advisory lock and
resume by stable paper ID.

## Evidence migration

Backfill provenance without changing `paper_methods`:

1. Add `source` evidence for every method's `source_paper_id`.
2. Re-run the existing deterministic longest-match keyword matcher over the
   title and abstract of already linked papers and add `keyword` evidence.
3. Add `legacy_unknown` evidence to every remaining association.
4. Do not guess whether a legacy unknown link was manual or citation-derived.
5. Update all current writers:
   - HF daily importer -> `keyword`;
   - weekly reference linker -> `reference`;
   - method source maintenance -> `source`;
   - admin and accepted pending edits -> `manual`;
   - one-off citation linker -> `reference`.
6. Update manual removal and re-add operations to maintain durable exclusions.

Add focused tests proving that repeated writers do not duplicate evidence and
that deleting a `paper_methods` association cascades its evidence. Also prove
that automated writers respect an exclusion and that a manual re-add clears it.

## Historical keyword backfill

Reference backfill alone is insufficient, especially for methods without a
canonical source paper. Run a separate deterministic keyword pass across the
entire latest-version paper catalog and every method with configured keywords.

The keyword pass must:

- reuse the exact matcher and longest-match rules used by the daily HF importer;
- stream papers in bounded ID batches rather than loading the catalog at once;
- insert `paper_methods` and `keyword` evidence idempotently;
- respect `paper_method_exclusions`;
- include dated and undated papers;
- require no Semantic Scholar API calls;
- expose `--after-paper-id`, `--limit`, `--max-runtime-seconds`, `--dry-run`,
  and `--resume`; and
- store a durable paper-ID cursor and keyword-catalog version so changes to
  method keywords can trigger a deliberate new pass.

Run this pass for all methods, including source-less methods, before declaring
their Mention trend complete.

The first implementation is additive: it does not delete legacy associations
or stale keyword evidence. After provenance is established, add a separately
reviewed reconciliation mode that can remove a stale `keyword` evidence row and
delete the parent association only when no other positive evidence remains.
Never let reconciliation override a manual link.

## Backfill workflow

### Candidate methods

Enqueue every method with a canonical source paper. Prioritize its queue
position when any of these are true:

- its source paper's citation count exceeds 9,999;
- the source-citation importer reaches its hard cap;
- an operator explicitly selects it; or
- monthly coverage is absent or known to be partial.

Start with `--method-slug clip`. Seed the rest of the method catalog only after
the CLIP run has established safe batch sizes, runtime, API usage, and storage
growth.

### Candidate papers

For each selected method and calendar month:

- consider only latest paper versions;
- start with the method source paper's publication month;
- require a non-null `date_published` for monthly trend coverage;
- order by `date_published, id`;
- prefer `semantic_scholar_id`, falling back to `arXiv:<arxiv_id>`;
- record papers with neither identifier as terminally unresolvable; and
- do not count an API error or rate limit as processed.

When several selected methods overlap the same month, fetch each paper's
reference list once and compare it with an in-memory index of all selected
method source IDs. Update the progress row for each selected method.

Process months from oldest to newest. This makes completed historical ranges
contiguous and avoids showing a misleading recent-only history while the job is
still running.

### Writes and checkpoints

- Keep the existing one-request-per-second default.
- Authenticate historical requests only with
  `PWC_SEMANTIC_SCHOLAR_API_KEY_2`; leave the primary key to existing CRON jobs.
- Bound each run by paper count and wall-clock duration.
- Commit in small batches, initially 250 papers.
- In the same transaction, insert `paper_methods`, upsert `reference` evidence,
  and advance the monthly cursor.
- Acquire a PostgreSQL advisory lock so two backfills cannot process the same
  method/month concurrently.
- Retry 429 and transient 5xx responses with bounded exponential backoff.
- Leave retryable failures behind the cursor in a bounded retry queue or process
  them before marking the month complete.
- Mark a month complete only when:
  `processed + unresolvable == eligible` and retryable failures are zero.
- Recount eligibility before completion to include papers imported while the
  month was being scanned.

The command should support:

```text
--method-id / --method-slug
--month-from / --month-to
--limit
--max-runtime-seconds
--request-delay
--dry-run
--resume
--retry-failures
```

Implement the domain logic in `backend/services/` and keep the scheduled-job
adapter under `.github/workflows/scripts/`.

## Publication dates

Null publication dates are a separate source-quality problem and must not be
silently assigned to a month.

Add an audit output containing:

- total method links excluded because `date_published` is null;
- counts grouped by `source` and presence of `arxiv_id`; and
- a sample of affected papers.

Where authoritative Hugging Face or arXiv metadata provides an exact date,
repair the paper row through the existing paper metadata refresh path. Do not
invent a day from the arXiv identifier merely to make the chart look complete.

The trend API must report `undated_paper_count`.

Keep the method page's headline paper total inclusive of dated and undated
associations. Near the graph, show concise copy such as
`2,280 papers without publication dates are not plotted` when the excluded
count is non-zero. The total and chart are intentionally different scopes and
must not appear to disagree silently.

## Trend API and frontend behavior

Extend each monthly trend point with:

```text
eligible_paper_count
processed_paper_count
coverage_ratio
coverage_status
catalog_paper_count
catalog_share
```

Also return:

```text
undated_paper_count
history_complete
current_month_is_partial
```

Coverage describes reference-backfill completeness, not confidence that every
link represents an implementation or evaluation.

For methods without a canonical source paper, reference coverage fields are
not applicable rather than incomplete. Their `history_complete` value depends
on keyword/manual ingestion coverage and must not remain permanently false only
because citation evidence is unavailable.

Frontend rules:

- label the graph `Mention trend`;
- rename the headline statistic to `Papers mentioning`;
- describe it as distinct papers citing or explicitly mentioning the method by
  publication month;
- use the distinct paper count for bar height and expose `catalog_share` only in
  the tooltip;
- include the current calendar month, render its bar with a lighter treatment,
  and label its tooltip `month to date`;
- request the complete history since introduction and use yearly axis labels
  when monthly or quarterly labels would overlap;
- render ordinary bars only for complete months;
- visually mark or suppress partial months;
- show a concise “historical tagging in progress” note while any displayed
  month is incomplete;
- expose excluded undated papers in accessible explanatory text;
- do not calculate a period-over-period comparison across incomplete months;
- exclude the current partial calendar month from month-over-month comparisons,
  even when its reference coverage is otherwise complete;
  and
- keep the current recent trend score only when its entire recent and baseline
  windows have complete incremental scan coverage.

The API additions must be optional/defaulted so old clients continue to parse
the response.

## Validation

### Unit and integration tests

- Evidence upserts are idempotent.
- One paper with multiple evidence types still contributes one monthly count.
- A manual exclusion prevents keyword and reference relinking.
- A subsequent manual re-add clears the exclusion and restores the link.
- The historical keyword pass covers sourced and source-less methods,
  respects exclusions, resumes from its cursor, and is idempotent.
- Only latest paper versions are counted.
- A failed request does not advance coverage.
- A resumed run starts strictly after the stored tuple cursor.
- A newly imported paper prevents premature month completion.
- Multiple selected methods share one fetched reference list.
- Null publication dates are excluded and reported.
- Trend history marks partial months and suppresses invalid comparisons.
- Methods older than ten years return and render their complete history.
- Existing method and paper APIs remain unchanged.
- Historical backfill refuses to start without a valid secondary Semantic
  Scholar key and never consumes the primary key.

### CLIP acceptance checks

Before writes, capture a snapshot of:

- distinct latest-version CLIP papers by publication month;
- explicit title/abstract mentions by month;
- total, dated, and undated CLIP links;
- evidence-type counts; and
- current 90-day and baseline-window counts.

After the backfill:

- every month from March 2021 through the last fully elapsed month is complete
  or has an explicitly reported unresolvable count;
- no artificial boundary remains at October 2025;
- rerunning the completed range inserts zero new associations;
- every new association has `reference` evidence;
- the source paper and explicit keyword matches retain their evidence;
- the total method count equals the distinct union of all evidence-backed
  associations; and
- sampled reference-derived links actually contain the CLIP source paper in
  their Semantic Scholar bibliography.

Review random samples from early, middle, and recent years. Include both matches
and non-matches.

### Operational checks

- Log papers processed, API calls, retries, matches, new links, cursor, and
  estimated remaining work per month.
- Add cron-registry health based on progress-table `updated_at`, not only
  `papers.methods_scanned_at`.
- Add a non-secret token check for `PWC_SEMANTIC_SCHOLAR_API_KEY_2` and verify
  workload logs identify `secondary` key routing without logging credentials.
- Measure database growth and free disk before and after the CLIP run.
- Run `ANALYZE` on new tables after the initial bulk load; do not run a broad
  `VACUUM FULL`.

## Rollout

### Phase 1: schema and provenance

1. Add the evidence, reference-progress, exclusion, and keyword-run tables with
   their indexes.
2. Add evidence-writing helpers.
3. Update all association writers.
4. Backfill recoverable evidence and label the remainder `legacy_unknown`.
5. Deploy to staging and confirm existing APIs are unchanged.

### Phase 2: catalog-wide keyword backfill

1. Run the deterministic keyword pass in staging.
2. Verify sourced and source-less method samples.
3. Confirm exclusions, cursor resume, and idempotency.
4. Apply the bounded keyword pass before citation-based completeness is
   evaluated.

### Phase 3: CLIP reference dry run

1. Seed monthly progress rows for CLIP.
2. Run one old month and one recent month in dry-run mode.
3. Estimate total API time, retries, link growth, and disk impact.
4. Compare sampled matches with Semantic Scholar.

### Phase 4: CLIP staged reference write

1. Process a small completed historical range.
2. verify idempotency and monthly coverage;
3. expose coverage through the staging API and chart; and
4. stop if match quality or API failure rates are unacceptable.

### Phase 5: production backfill

After explicit production approval, run bounded off-peak batches through the
installed `pwc-cron` allowlist. Do not run repository scripts directly against
the production database.

Pause safely if disk headroom, API error rate, or normal cron latency crosses
the agreed threshold. Resume from the stored month cursor.

### Phase 6: complete the sourced method catalog

Enqueue every remaining method with a canonical source paper. Prioritize
methods whose source citation counts exceed the API cap or whose histories show
a coverage discontinuity, then continue until all sourced methods have complete
monthly coverage.

## Rollback

- Stop scheduling new backfill batches.
- The workflow is additive, so existing `paper_methods` remain usable.
- Hide coverage metadata and revert the trend response/UI independently if
  necessary.
- Keep evidence and progress rows for diagnosis; they do not affect legacy
  joins.
- If a backfill is proven invalid, delete only associations whose sole evidence
  is the affected backfill's `reference` evidence. Never delete links that also
  have `manual`, `keyword`, or `source` evidence.
- Never remove manual exclusions as part of a backfill rollback.

## Completion criteria

This work is complete when:

- CLIP has continuous, explicitly measured historical coverage;
- the October 2025 discontinuity is gone or transparently marked incomplete;
- every new method link has provenance;
- every configured method has complete historical keyword coverage;
- all historical jobs are resumable and idempotent;
- undated links are disclosed rather than silently omitted;
- trend comparisons are gated on coverage; and
- every method with a canonical source paper has complete historical reference
  coverage and ongoing incremental coverage from the weekly cron.
