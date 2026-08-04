---
name: pwc-cli
description: "Papers With Code repository CLI (`pwc`) for hybrid paper search, paper metadata and Markdown, recent/trending/related papers, external-resource ingestion, paper curation and lineage, task/method/metric/benchmark administration, thumbnails and entity images, GitHub evaluation outreach, CRON diagnostics, and the versioned embedding pipeline. Use this skill whenever work in the paperswithcode repository mentions `pwc`, the PwC CLI, searching or inspecting the local paper catalog, adding or updating curated PwC data, checking CRON health or credentials, generating thumbnails, creating evaluation outreach issues, or operating paper embeddings. Prefer these rule-based commands over ad hoc SQL or one-off scripts when a command covers the task."
---

# Papers With Code CLI

Run the repository-local CLI from the repository root:

```bash
uv run --env-file backend/keys.env pwc --help
```

Use the same prefix for every command below. The environment file supplies the
database and service credentials, while `uv run` selects the project environment.
Use `<command> --help` when the live parser and this document disagree; the parser
is authoritative. Update this skill whenever `backend/cli.py` changes.

Prefer `--json` when another tool or agent will consume the result. Human-readable
output is intended for terminal inspection.

## Safety and command selection

- Read-only catalog and diagnostic commands are safe to run for inspection:
  `search`, `paper read/info/list/recent/trending/related`, `benchmark list`,
  `paper lineage list`, `github-issue body`, `cron health`, `cron token-check`,
  `embeddings status`, and dry-run embedding plans.
- Commands named `add`, `update`, `index`, `add-external`, `thumbnail`, or
  `refresh-lexeme-stats` mutate repository data, database rows, or generated
  artifacts. Run them only when the task authorizes that mutation.
- `github-issue create` publishes an externally visible GitHub issue and requires
  `--confirm PUBLISH`. Do not substitute a write-capable token into output.
- Embedding commands can launch paid infrastructure or change live retrieval.
  Keep `run` and `endpoint-plan` in their default dry-run mode until execution is
  requested. Respect every `--execute` and `--confirm` gate.
- `paper lineage remove` and `embeddings retention-apply` delete data. Review the
  exact target or generated plan before using their confirmation values.
- This checkout backs production. Never restart services, rebuild the frontend,
  reload nginx, or deploy merely because a CLI command was run.

## Paper discovery

- `pwc search QUERY` — Hybrid lexical + semantic paper search. Defaults to 10
  results and hybrid mode. `[--limit 1-100 --mode hybrid|keyword|semantic --json]`
- `pwc paper info PAPER` — Show full metadata for a PwC URL, ArXiv ID, or numeric
  external-paper ID. Human-readable output includes a Markdown paper-lineage
  section; JSON includes `predecessor_papers` and `successor_papers`.
  `[--include-resources --json]`
- `pwc paper read PAPER` — Print stored paper Markdown for a modern ArXiv ID or
  PwC paper URL.
- `pwc paper list` — Paginate and filter the paper catalog.
  `[--page N --page-size N --search TEXT --published-after YYYY-MM-DD
  --published-before YYYY-MM-DD --conference TEXT --all-versions
  --order-by trending|date_published|citation_count --order-dir asc|desc
  --time today|week|month|all_time --include-resources --json]`
- `pwc paper recent` — List latest publications. `[--limit 1-100 --json]`
- `pwc paper trending` — List repository-velocity-ranked papers.
  `[--limit 1-100 --max-age-days 1-365 --min-velocity FLOAT --json]`
- `pwc paper related ARXIV_ID` — Retrieve embedding/task-ranked related papers.
  `[--limit 1-20 --json]`

## Paper ingestion and curation

- `pwc paper index ARXIV_ID` — Idempotently index or refresh an ArXiv paper.
  `[--json]`
- `pwc paper add-external SOURCE_URL` — Fetch, extract, and ingest a non-ArXiv
  research page. `[--date-published YYYY-MM-DD --title TEXT --abstract TEXT
  --author NAME (repeatable) --thumbnail-url URL --json]`
- `pwc paper update PAPER tasks [TASK_ID ...]` — Replace all task links. `[--json]`
- `pwc paper update PAPER methods [METHOD_ID ...]` — Replace all method links.
  `[--json]`
- `pwc paper update PAPER organizations [ORGANIZATION_ID ...]` — Replace all
  organization links. `[--json]`
- `pwc paper update PAPER repositories [URL ...]` — Replace repository links;
  positional URLs are official. `[--unofficial URL (repeatable) --json]`
- `pwc paper update PAPER project-pages [URL ...]` — Replace project-page links;
  positional URLs are official. `[--unofficial URL (repeatable) --json]`
- `pwc paper update PAPER hf-artifacts` — Replace explicit Hugging Face artifact
  links and immediately synchronize their normalized `hf_artifacts` and
  `paper_hf_artifacts` rows. The write also invalidates the discovery checkpoint
  so the hourly job can reconcile removals and arXiv-discovered extras.
  `[--model URL --dataset URL --space URL (each repeatable) --json]`
- `pwc paper update PAPER source-url URL` — Replace an external paper's canonical
  source URL. `[--json]`

`PAPER` accepts a PwC paper URL, ArXiv ID, or numeric external-paper ID unless the
individual command above states otherwise. Replace-style commands accept an empty
list to clear that relation category, so do not omit values accidentally.
After an HF-artifact write, verify both the paper arrays and normalized links;
an artifact URL displayed on a paper is not sufficient evidence that its Hub
trending metrics are participating in the composite paper score.

## Paper lineage

- `pwc paper lineage add PAPER PAPER [PAPER ...]` — Add each adjacent
  predecessor-to-successor edge idempotently. `[--json]`
- `pwc paper lineage list PAPER` — List predecessors and successors. `[--json]`
- `pwc paper lineage remove PREDECESSOR SUCCESSOR --confirm DELETE` — Remove one
  directed edge. `[--json]`

## Taxonomy, metrics, and benchmarks

- `pwc task add SLUG` — Idempotently create/update a task. Requires `--name`, one
  of `--description` or `--description-file`, `--keywords`, and `--area`.
  `[--parent SLUG_OR_ID --json]`
- `pwc method add SLUG` — Idempotently create/update a method. Requires `--name`,
  `--full-name`, one description input, `--keywords`, `--area`,
  `--introduced-year`, one of `--source-paper` or `--source-url`, and
  `--source-title`. `[--code-snippet-url URL --image-credit TEXT --json]`
- `pwc metric add NAME --direction higher_is_better|lower_is_better` —
  Idempotently create/update a metric. `[--full-name TEXT --scale TEXT
  --description TEXT --json]`
- `pwc benchmark add NAME` — Idempotently create/configure a benchmark. Requires
  one of `--description` or `--description-file`, repeatable `--task`, repeatable
  `--metric`, and `--source-paper`. `[--full-name TEXT --url URL --hf-url URL
  --homepage URL --supports-harness --json]`
- `pwc benchmark list` — List/filter benchmarks. `[--page N --page-size N
  --search TEXT --task SLUG_OR_ID
  --include-descendants --min-eval-count N --is-open true|false
  --order-by name|full_name|created_at|paper_count --order-dir asc|desc
  --group-by-area --flat --area NAME_OR_ID --benchmarks-per-task N --json]`
- `pwc benchmark --name NAME` — Show one benchmark and its leaderboard.
  `NAME` accepts the exact benchmark name, full name, slug, or ID.

## Images and thumbnails

- `pwc thumbnail PAPER` — Regenerate and validate a paper thumbnail. Regeneration
  is forced by default. `[--no-force --json]`
- `pwc image add task|method|conference SLUG IMAGE_URL --source SOURCE` — Download,
  self-host, attribute, and attach an entity hero image. `[--json]`

## GitHub evaluation outreach

- `pwc github-issue body PAPER` — Generate a rule-based evaluation outreach issue
  draft. `[--task TASK_SLUG --verified --json]`
- `pwc github-issue create PAPER --confirm PUBLISH` — Duplicate-safely publish the
  issue to an official repository. `[--task TASK_SLUG --verified
  --repository OWNER/REPO --token-env ENV_NAME --json]`

Use `--verified` only after a human verification pass. `body` is the preview path;
inspect it before `create` when publication scope or repository selection is unclear.

## CRON diagnostics

- `pwc cron health [JOB]` — Triangulate schedules, logs, processes, locks,
  database writes, and available Actions state. `[--json --strict]`
- `pwc cron token-check ENVIRONMENT_VARIABLE` — Probe a configured credential
  without displaying its value. `[--json]`

Registered health jobs currently include `update_github_stars`,
`update_hot_github_trending`,
`update_citations`, `extract_urls`, `calculate_trending_scores`,
`calculate_paper_trending_scores`, `update_hf_artifacts`,
`import_hf_daily_papers`, `sync_3d_arena`, `sync_open_asr`, `sync_hf_organizations`,
`calculate_organization_trending_scores`, `preload_thumbnails`,
`mirror_thumbnails_to_disk`,
`link_methods_by_references`, `backfill_method_keywords`,
`backfill_method_references`, and `link_papers_by_task_keywords`.
The active-generation maintenance job `refresh_paper_embeddings` is also
registered and runs hourly after paper ingestion.
The local `process_curation_thumbnails` worker runs every minute through its
systemd timer; pass `--retry-failed` only for an explicit operator retry.

Supported token probes are `PWC_GEMINI_API_KEY`, `PWC_GITHUB_TOKEN`,
`PWC_GITHUB_TOKEN_HOT`,
`PWC_HF_TOKEN`, `PWC_OPENROUTER_API_KEY`, and
`PWC_SEMANTIC_SCHOLAR_API_KEY`. Historical method-reference backfills use the
separately owned `PWC_SEMANTIC_SCHOLAR_API_KEY_2` probe.

## Versioned paper embeddings

- `pwc embeddings export --output-root PATH --run-id ID --model MODEL
  --revision REV --dimensions N` — Export a checksummed snapshot.
  `[--generation-id N --shard-rows N --max-rows N]`
- `pwc embeddings run --input BUCKET_PATH --output BUCKET_PATH --volume MOUNT
  --model MODEL --revision REV --dimensions N` — Print an HF Job plan by default.
  `[--flavor FLAVOR --timeout DURATION --allow-matryoshka --reuse-snapshot
  --execute --confirm RUN_HF_JOB]`
- `pwc embeddings endpoint-plan --name NAME --namespace NS --model MODEL
  --revision REV` — Print a scale-to-zero TEI deployment plan by default.
  `[--accelerator TYPE --scale-to-zero-timeout N --execute
  --confirm DEPLOY_HF_ENDPOINT]`
- `pwc embeddings import --output PATH --input-manifest PATH
  --bucket-run-uri URI` — Validate and import output shards.
  `[--generation-id N]`
- `pwc embeddings status` — Show generation freshness and coverage. `[--json]`
- `pwc embeddings activate GENERATION_ID --confirm ACTIVATE` — Atomically activate
  a ready, fully covered generation.
- `pwc embeddings refresh-lexeme-stats --confirm REFRESH` — Refresh bounded
  related-paper lexical statistics.
- `pwc embeddings retention-plan --runs PATH` — Create a non-destructive Bucket
  retention plan. `[--output PATH]`
- `pwc embeddings retention-apply --plan PATH --confirm DELETE_BUCKET_ARTIFACTS`
  — Apply a reviewed retention plan through `hf buckets`.

## Maintenance checklist

When changing `backend/cli.py`:

1. Run `uv run --env-file backend/keys.env pwc --help` and the affected nested
   `--help` command.
2. Update this command inventory and README examples when behavior changes.
3. Add or update parser/handler tests in `backend/tests/test_maintenance_cli.py`.
4. Run targeted tests and `git diff --check`; do not rebuild or restart production.
