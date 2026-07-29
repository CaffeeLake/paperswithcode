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
to other methods only after CLIP's counts, runtime, API usage, and storage impact
have been validated.

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

- Do not infer that every citation means a paper used a method. Citation-based
  links remain a discovery proxy, and provenance must make that distinction
  inspectable.
- Do not scrape full paper text in this project.
- Do not replace Semantic Scholar or download its full corpus in the first
  iteration.
- Do not delete existing method links during the additive backfill.
- Do not change public method, paper, or relationship routes.
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

Add focused tests proving that repeated writers do not duplicate evidence and
that deleting a `paper_methods` association cascades its evidence.

## Backfill workflow

### Candidate methods

Automatically flag a method for paper-centric backfill when any of these are
true:

- its source paper's citation count exceeds 9,999;
- the source-citation importer reaches its hard cap;
- an operator explicitly selects it; or
- monthly coverage is absent or known to be partial.

Start with `--method-slug clip`. Do not enqueue the entire method catalog before
measuring CLIP.

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

## Trend API and frontend behavior

Extend each monthly trend point with:

```text
eligible_paper_count
processed_paper_count
coverage_ratio
coverage_status
```

Also return:

```text
undated_paper_count
history_complete
```

Coverage describes reference-backfill completeness, not confidence that every
link represents actual usage.

Frontend rules:

- render ordinary bars only for complete months;
- visually mark or suppress partial months;
- show a concise “historical tagging in progress” note while any displayed
  month is incomplete;
- expose excluded undated papers in accessible explanatory text;
- do not calculate a period-over-period comparison across incomplete months;
  and
- keep the current recent trend score only when its entire recent and baseline
  windows have complete incremental scan coverage.

The API additions must be optional/defaulted so old clients continue to parse
the response.

## Validation

### Unit and integration tests

- Evidence upserts are idempotent.
- One paper with multiple evidence types still contributes one monthly count.
- Only latest paper versions are counted.
- A failed request does not advance coverage.
- A resumed run starts strictly after the stored tuple cursor.
- A newly imported paper prevents premature month completion.
- Multiple selected methods share one fetched reference list.
- Null publication dates are excluded and reported.
- Trend history marks partial months and suppresses invalid comparisons.
- Existing method and paper APIs remain unchanged.

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
- Measure database growth and free disk before and after the CLIP run.
- Run `ANALYZE` on new tables after the initial bulk load; do not run a broad
  `VACUUM FULL`.

## Rollout

### Phase 1: schema and provenance

1. Add both tables and indexes.
2. Add evidence-writing helpers.
3. Update all association writers.
4. Backfill recoverable evidence and label the remainder `legacy_unknown`.
5. Deploy to staging and confirm existing APIs are unchanged.

### Phase 2: CLIP dry run

1. Seed monthly progress rows for CLIP.
2. Run one old month and one recent month in dry-run mode.
3. Estimate total API time, retries, link growth, and disk impact.
4. Compare sampled matches with Semantic Scholar.

### Phase 3: CLIP staged write

1. Process a small completed historical range.
2. verify idempotency and monthly coverage;
3. expose coverage through the staging API and chart; and
4. stop if match quality or API failure rates are unacceptable.

### Phase 4: production backfill

After explicit production approval, run bounded off-peak batches through the
installed `pwc-cron` allowlist. Do not run repository scripts directly against
the production database.

Pause safely if disk headroom, API error rate, or normal cron latency crosses
the agreed threshold. Resume from the stored month cursor.

### Phase 5: expand selectively

Prioritize other methods whose source citation counts exceed the API cap or
whose histories show a coverage discontinuity. Do not automatically rescan
every method until the CLIP results establish a sustainable operating cost.

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

## Completion criteria

This work is complete when:

- CLIP has continuous, explicitly measured historical coverage;
- the October 2025 discontinuity is gone or transparently marked incomplete;
- every new method link has provenance;
- all historical jobs are resumable and idempotent;
- undated links are disclosed rather than silently omitted;
- trend comparisons are gated on coverage; and
- the same workflow can be safely queued for another high-citation method
  without code changes.
