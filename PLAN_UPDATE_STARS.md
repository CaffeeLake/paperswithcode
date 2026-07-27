# Plan: Faster GitHub Star Updates for Trending Papers

## Objective

Make newly launched, fast-growing papers appear in the public trending feed
within 30 minutes of being linked to an official GitHub repository, without
starving the existing recent-paper and weekly repository refresh queues or
depending on manual score promotion.

The target applies to both ranking stages:

1. `repositories.trending_score`, derived from GitHub star velocity.
2. `papers.trending_score`, the composite score used by the production feed.

## Current State

The current pipeline has three independently scheduled stages:

1. `update_github_stars` runs hourly and stores snapshots in
   `repository_star_history`.
2. `calculate_trending_scores` runs hourly and calculates the repository EMA.
3. `calculate_paper_trending_scores` runs hourly and copies GitHub/Hugging Face
   signals into the composite paper score.

The GitHub updater runs two queues concurrently:

- A fresh queue, using `PWC_GITHUB_TOKEN`, with a maximum of 3,000 calls.
- A weekly queue, using `GITHUB_CLASSIC_TOKEN_AICONSULTANCYNIELSROGGE`, with a
  maximum of 1,000 calls.

Fresh calls are serialized with a one-second delay. Repositories linked to
papers published within six months share this queue, including the much smaller
set linked to papers published in the last 30 days. A newly linked repository
therefore waits for:

- its first GitHub snapshot;
- a second sufficiently separated snapshot;
- the repository trending calculation; and
- the paper composite calculation.

Observed on 2026-07-27:

- 3,531 repositories were in the fresh population;
- 326 were linked to papers published in the preceding 30 days;
- 1,385 were eligible for refresh at the time of inspection;
- the fresh queue budget was 3,000 calls; and
- the combined GitHub update job was still running after approximately 40
  minutes.

This indicates that latency is primarily caused by queue structure, serialized
requests, and separately scheduled scoring stages. A third token alone would
not fix those issues because the current implementation assigns only one token
to the fresh queue and one to the weekly queue.

## Proposed Design

### 1. Add a dedicated hot-repository pipeline

Create `scripts.hourly.update_hot_github_trending` as a bounded orchestration
job for official repositories linked to latest-version papers published within
the last 30 days.

Run it every 15 minutes. One invocation should:

1. Select eligible hot repositories.
2. Fetch and store GitHub star snapshots.
3. Recalculate repository trending scores for the touched repositories.
4. Recalculate composite scores for papers linked to those repositories.
5. Emit structured statistics for all four stages.

The job must be idempotent. Re-running it for the same time window may add
another timestamped snapshot, but must not duplicate repository or paper
relationships or corrupt EMA state.

### 2. Give each queue exclusive ownership

Use these non-overlapping tiers:

| Tier | Paper age | Frequency | Maximum calls | Token |
|---|---:|---:|---:|---|
| Hot | 0–30 days | Every 15 minutes | 500/run | Hot token or shared fresh token |
| Fresh | 31 days–6 months | Hourly | 2,500/run | `PWC_GITHUB_TOKEN` |
| Weekly | Older than 6 months | Every 7 days | 1,000/run | Existing weekly token |

Remove hot repositories from the existing fresh query. Exclusive ownership
avoids simultaneous writes, duplicate API calls, and ambiguous snapshot
cadence.

The 500-call hot cap covers the currently observed population of 326. It also
bounds the worst-case shared-token load at 2,000 hot calls/hour.

### 3. Support an optional third GitHub token

Add `PWC_GITHUB_TOKEN_HOT` as an optional production CRON secret.

- When set, the hot queue uses it and has an independent GitHub rate budget.
- When absent, the hot queue uses `PWC_GITHUB_TOKEN`.
- Shared-token mode must reserve at least 500 calls from the authenticated
  hourly allowance and stop before the reserve is consumed.

Do not require a third account for the initial rollout. The current queue sizes
fit within the existing authenticated budget if the fresh maximum is reduced
to 2,500 and the hot maximum remains 500 per 15-minute run. Add the third token
when monitoring shows sustained budget pressure, secondary throttling, or a hot
population approaching the configured cap.

Never log tokens or include them in command-line arguments. Configure a new
token only through `/etc/paperswithcode/production-cron.env` using the existing
host environment tooling.

### 4. Make rate limiting adaptive

Change the GitHub fetch result to retain these response headers:

- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`
- `Retry-After`, when present

Each queue should:

- stop when its remaining budget reaches the configured reserve;
- retry transient `5xx` responses with bounded exponential backoff and jitter;
- respect `Retry-After` for primary or secondary throttling;
- avoid the current unconditional 60-second sleep inside a worker;
- report rate-limit stops separately from ordinary API failures; and
- use short connection reuse through a `requests.Session`.

Start the hot queue with a 250-millisecond inter-request delay. Keep the
existing one-second delay for the larger fresh and weekly queues until metrics
show that it can safely be reduced.

### 5. Calculate an early but defensible velocity

For ordinary repositories, preserve the current EMA:

```text
new_score = 0.75 × measured_stars_per_hour + 0.25 × previous_score
```

For hot repositories:

- retain snapshots every 15 minutes;
- require at least two snapshots;
- prefer a baseline at least 30 minutes old when available;
- permit a 15-minute baseline only during the first hour after a repository is
  linked;
- clamp negative velocity to zero; and
- keep the same EMA and maximum-score safeguards as the ordinary calculation.

This gives a newly linked repository its first real signal after 15–30 minutes
without permanently changing the meaning of the trending score.

Extract the repository scoring operation so it accepts an explicit list of
repository IDs. The existing hourly full-population job should call the same
implementation.

### 6. Propagate touched scores immediately

Refactor paper composite calculation into:

1. A read phase that builds the current GitHub and Hugging Face normalization
   corpora.
2. A compute phase that can calculate all papers or an explicit set of paper
   IDs.
3. A write phase that only updates the selected papers.

The hot job should collect all latest paper IDs linked to its touched official
repositories and update only those paper rows. It must still derive
normalization from the full live corpus so a targeted score is comparable with
the rest of the feed.

This removes the extra wait for the hourly paper composite job while preserving
the existing full hourly reconciliation as a correctness backstop.

### 7. Preserve manual promotion only as an emergency control

Do not make score seeding part of normal ingestion. The hot pipeline should
remove the need for manual promotion.

If an emergency promotion mechanism is retained:

- record the reason, operator, start time, and seeded value;
- let the next real repository EMA replace or decay the seed;
- expose the active override in operational status; and
- prohibit permanent pins without an explicit expiry.

The existing paper-level decaying pin implementation is arXiv-oriented and
linear. It should not be reused as the primary solution for external papers or
for routine launch latency.

## Implementation Work

### Shared code

- Refactor GitHub request, snapshot, and queue code from
  `.github/workflows/scripts/hourly/update_github_stars.py`.
- Add targeted repository-scoring support to
  `.github/workflows/scripts/hourly/calculate_trending_scores.py`.
- Add targeted paper-scoring support to
  `.github/workflows/scripts/hourly/calculate_paper_trending_scores.py`.
- Put reusable domain logic in `backend/services/` where practical; leave CRON
  scripts as orchestration adapters.

### New hot job

- Add
  `.github/workflows/scripts/hourly/update_hot_github_trending.py`.
- Add
  `.github/workflows/scripts/run_hot_github_trending.sh`.
- Register `update_hot_github_trending` in:
  - `deploy/cron_launcher.py`;
  - `backend/services/cron_registry.py`;
  - `.github/workflows/scripts/manage_cron.py`; and
  - the CRON dashboard tests.
- Give it a separate production lock:
  `/var/lib/paperswithcode/production/cron-locks/update_hot_github_trending.lock`.

### Scheduling

- Add `.github/workflows/cron-update-hot-github-trending.yml`.
- Use the schedule `*/15 * * * *`.
- Use a distinct concurrency group with `cancel-in-progress: false`.
- Keep the hourly full GitHub updater and hourly full score reconciliation.
- Change the full updater query so the fresh queue starts at 31 days.

### Configuration

Add bounded configuration values with safe defaults:

```text
PWC_GITHUB_TOKEN_HOT=
PWC_GITHUB_HOT_WINDOW_DAYS=30
PWC_GITHUB_HOT_THRESHOLD_MINUTES=15
PWC_GITHUB_HOT_MAX_UPDATES=500
PWC_GITHUB_HOT_DELAY_SECONDS=0.25
PWC_GITHUB_RATE_LIMIT_RESERVE=500
```

The optional token belongs only in the production CRON environment overlay.
The other settings may use code defaults and environment overrides.

### Documentation

Update:

- `docs/operations.md`;
- `.github/workflows/scripts/README.md`;
- `.github/workflows/scripts/hourly/README.md`; and
- `.github/workflows/scripts/docs/TRENDING_EMA_GUIDE.md`.

Document queue ownership, schedules, rate budgets, the targeted scoring path,
and recovery commands.

## Tests

### Unit tests

Add or extend tests covering:

- hot/fresh/weekly boundary dates;
- exclusion of hot repositories from the ordinary fresh queue;
- grouping duplicate repository rows by normalized owner/name;
- 15-minute first-hour velocity calculation;
- preference for a 30-minute baseline;
- EMA decay from a temporary seed to measured velocity;
- negative-velocity clamping;
- targeted repository updates;
- targeted paper composite updates;
- rate-limit reserve handling;
- `Retry-After` and exponential retry behavior;
- missing optional hot token fallback; and
- idempotent snapshot and relationship handling.

### Integration tests

Use mocked GitHub responses and a temporary database to prove:

1. A newly linked hot repository receives a first snapshot.
2. A later run receives a second snapshot and computes velocity.
3. The linked paper receives a composite score in the same job.
4. The paper enters the trending query without waiting for hourly jobs.
5. The full hourly reconciliation produces the same score.

### Operational validation

Before production rollout:

- run the hot job in dry-run mode against the production-shaped database;
- print selected repositories without making GitHub calls or writes;
- confirm the selected population is below the cap;
- validate projected hourly calls in shared-token mode; and
- run one staging invocation with mocked or explicitly limited live calls.

## Observability

Each run should log one structured summary containing:

- eligible and selected repository groups;
- API calls, successes, failures, and retries;
- snapshots written;
- repository scores updated or skipped;
- paper scores updated or cleared;
- rate-limit limit, remaining, and reset time;
- oldest eligible hot repository age;
- time spent in fetch, repository score, and paper score stages; and
- end-to-end time from repository linkage to first non-zero paper score.

Extend CRON health with:

- last successful hot run;
- hot repositories refreshed in the last 30 minutes;
- hot repositories with only one snapshot for more than 30 minutes;
- hot repositories whose paper score is missing or stale;
- rate-limit reserve violations; and
- consecutive failed or lock-skipped runs.

Alert when the oldest eligible hot repository has waited more than 30 minutes
or when a hot paper has two valid snapshots but no fresh composite score.

## Rollout

### Phase 1: Code and dry run

- Implement queue separation and targeted calculation.
- Deploy to staging.
- Run selection-only and mocked tests.
- Confirm no overlap between queue populations.

### Phase 2: Shared-token production canary

- Enable the hot job every 15 minutes with a maximum of 100 repositories.
- Keep a 500-call reserve.
- Observe rate headers, runtime, and feed latency for 24 hours.
- Increase the cap to 500 if the canary is healthy.

### Phase 3: Optional dedicated token

- Add `PWC_GITHUB_TOKEN_HOT` only if shared-token monitoring shows pressure.
- Confirm the account and token comply with GitHub policy and operational
  ownership requirements.
- Switch the hot queue to the dedicated token without changing queue semantics.

### Phase 4: Tune and remove manual intervention

- Review the 15-minute and 30-minute velocity windows after one week.
- Remove any temporary manual trending seeds.
- Keep the hourly full reconciliation as a permanent safety net.

## Rollback

Rollback must not delete snapshots.

1. Disable the hot workflow schedule.
2. Leave the hourly fresh and weekly updater active.
3. Leave both hourly full scoring jobs active.
4. Restore the fresh queue to include 0–6-month papers if the hot job will
   remain disabled.
5. Remove `PWC_GITHUB_TOKEN_HOT` from the CRON environment only after no
   deployed release depends on it.

Existing `repository_star_history` rows remain valid input to the hourly
calculator, so rollback requires no data migration.

## Acceptance Criteria

- A newly linked official repository for a paper under 30 days old receives a
  first snapshot within 15 minutes.
- It receives a real repository velocity and paper composite score within 30
  minutes when GitHub is available.
- The public trending API reflects the new score in the same hot-job run.
- Hot, fresh, and weekly queues have no ownership overlap.
- Shared-token mode stays above the configured 500-call reserve.
- No third token is required at current load.
- Full hourly reconciliation agrees with targeted results.
- Disabling the hot workflow cleanly restores the current hourly behavior.
