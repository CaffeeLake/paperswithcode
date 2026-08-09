---
name: pwc-cli
description: "Papers With Code CLI (`pwc`) for searching and reading AI/ML papers, discovering recent and trending research, finding related work and paper lineage, browsing tasks, methods, conferences, organizations, frameworks, and benchmark leaderboards through the public Papers With Code catalog. Use whenever the user asks to find papers, survey literature, compare research, inspect an arXiv paper, explore AI/ML taxonomy or conferences, discover benchmarks or state-of-the-art models, or mentions Papers With Code, `pwc`, or `pwc-cli`."
---

Generated with `pwc v0.1.12`. Run `pwc skills add --force` to regenerate.

The `pwc` CLI is anonymous and read-only. It queries the public
[Papers With Code](https://paperswithcode.co) catalog and requires no token.
Run `pwc --help` or a nested `--help` command when the live parser and this
skill disagree; the parser is authoritative.

Use compact output for reading and discovery. Add `--json` for programmatic
filtering, joining, or schema-dependent processing.

`PAPER` accepts a modern or legacy arXiv ID, a numeric external-paper ID, or an
exact paper title. Quote titles containing spaces. Title matching is
case-insensitive but exact; ambiguous titles fail with their matching IDs.

## Commands

- `pwc search QUERY [--limit LIMIT] [--page PAGE] [--mode hybrid|keyword|semantic] [--json]` — search papers.
- `pwc paper info PAPER [--include-resources] [--include-evals] [--json]` — show paper metadata including abstract.
- `pwc paper read PAPER [--json]` — print stored paper Markdown.
- `pwc paper list [--page PAGE] [--page-size PAGE_SIZE] [--search SEARCH] [--published-after PUBLISHED_AFTER] [--published-before PUBLISHED_BEFORE] [--task TASK] [--method METHOD] [--conference CONFERENCE] [--framework FRAMEWORK] [--organization ORGANIZATION] [--all-versions] [--order-by trending|date_published|citation_count] [--order-dir asc|desc] [--time today|week|month|all_time] [--include-resources] [--json]` — list and filter papers.
- `pwc paper recent [--limit LIMIT] [--json]` — list recent papers.
- `pwc paper trending [--limit LIMIT] [--max-age-days MAX_AGE_DAYS] [--min-velocity MIN_VELOCITY] [--json]` — list trending papers.
- `pwc paper related PAPER [--limit LIMIT] [--json]` — list related papers.
- `pwc paper lineage list PAPER [--json]` — list predecessors and successors.
- `pwc task [--name NAME] [--json]` — inspect or list research tasks.
- `pwc task list [--page PAGE] [--page-size PAGE_SIZE] [--group-by-area] [--flat] [--area AREA] [--level LEVEL] [--visible-only] [--order-by name|created_at|level|paper_count] [--order-dir asc|desc] [--json]` — list and filter research tasks.
- `pwc method [--name NAME] [--json]` — inspect or list research methods.
- `pwc method list [--page PAGE] [--page-size PAGE_SIZE] [--area AREA] [--introduced-year INTRODUCED_YEAR] [--order-by name|full_name|introduced_year|created_at|paper_count] [--order-dir asc|desc] [--json]` — list and filter research methods.
- `pwc conference [--name NAME] [--json]` — inspect or list conferences.
- `pwc conference list [--year YEAR] [--json]` — list conferences with imported papers.
- `pwc organization [--name NAME] [--json]` — inspect or list research organizations.
- `pwc organization list [--featured-only] [--json]` — list research organizations.
- `pwc framework [--name NAME] [--json]` — inspect or list research frameworks.
- `pwc framework list [--domain DOMAIN] [--category CATEGORY] [--platform PLATFORM] [--json]` — list research frameworks.
- `pwc benchmark [--name NAME] [--limit LIMIT] [--is-open true|false] [--require-metrics METRIC[,METRIC]] [--min METRIC=VALUE] [--max METRIC=VALUE] [--sort METRIC[:ASC|DESC]] [--pareto METRIC:HIGHER,METRIC:LOWER] [--json]` — inspect benchmarks.
- `pwc benchmark list [--page PAGE] [--page-size PAGE_SIZE] [--search SEARCH] [--task TASK] [--group-by-area] [--flat] [--area AREA] [--benchmarks-per-task BENCHMARKS_PER_TASK] [--include-descendants] [--min-eval-count MIN_EVAL_COUNT] [--is-open true|false] [--order-by trending|name|full_name|created_at|paper_count] [--order-dir asc|desc] [--json]` — list and filter benchmarks.
- `pwc skills add [--global] [--claude] [--dest DEST] [--force]` — install the version-matched pwc CLI Skill.
- `pwc version` — show CLI and API contract versions.

## Research workflow

1. Use `pwc benchmark list --task TASK` to discover active benchmarks, then
   `pwc benchmark --name NAME` to inspect a leaderboard.
2. Use `pwc paper info` to inspect promising results. Add
   `--include-resources` when repositories, project pages, or Hugging Face
   artifacts matter.
3. Use exact `pwc paper list --task`, `--method`, `--conference`, `--framework`,
   and `--organization` filters for tagged or catalog-associated papers. Combine
   them to require every association; do not substitute a keyword search.
4. Use `pwc search` for broader discovery, then `pwc paper read` for primary
   evidence.
5. Expand the literature with `pwc paper related` and use
   `pwc paper lineage list` when model or method ancestry matters.
6. Preserve paper titles, identifiers, and URLs so claims remain traceable.

## Output and limits

- Interactive output is optimized for people; captured list output uses
  lossless TSV. Add `--json` for structured agent or script consumption.
- Stable exit codes are `0` success, `2` invalid usage, `3` network/server
  failure, and `4` invalid API response.
- `PWC_API_URL` may select another compatible v1 endpoint. The default is
  `https://paperswithcode.co/api/v1`.
- Catalog-filtered paper lists fail closed unless the server confirms every
  requested filter; never treat results from an older server as filtered.

The research commands contain no authentication, catalog mutation, ingestion,
publication, image, embedding, CRON, or infrastructure-maintenance operations.
