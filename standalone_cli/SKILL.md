---
name: pwc-cli
description: Use the standalone read-only Papers With Code CLI for bounded public paper and benchmark research.
---

# Standalone Papers With Code CLI

This public client is anonymous and read-only. Run `pwc --help` or nested help
for the current bounded flags. Use compact output by default; add `--json` only
for programmatic filtering, joining, or transformation.

```bash
pwc search "small vision language models" --limit 10
pwc search "small vision language models" --has-official-implementation
pwc paper info 2501.01234 --include-resources
pwc paper read 2501.01234
pwc paper list --conference CVPR --page-size 20
pwc paper recent --limit 10 --implementation-coverage
pwc paper trending --limit 20
pwc paper related 2501.01234 --limit 4
pwc paper lineage list 2501.01234
pwc benchmark list
pwc benchmark list --task OCR
pwc benchmark --name "SWE-Bench Pro"
pwc version
```

Paper discovery commands accept `--implementation-coverage` to add
`official_implementation` and `code_repositories` columns. JSON and paper info
always include both fields. They describe repository links in the catalog
across all versions of a paper; `false` is not evidence that code does not
exist elsewhere.
Use `--has-official-implementation` with `pwc search` or `pwc paper list` to
require a catalog-linked official repository. The CLI rejects results unless
the server confirms that it applied this filter.

Benchmark lists group the top benchmarks under each visible task by research
area in an interactive terminal. Use `--flat` for the paginated dataset table
or `--group-by-area` to force Markdown when piping. Every row places the
benchmark description and optional Hugging Face dataset URL immediately after
its name. Grouped rows also include the full name when distinct, slug, and ID.
Task-scoped lists include the slug and ID alongside the best model, paper title,
and preferred code repository. Use either identifier with
`pwc benchmark --name IDENTIFIER` for leaderboard details.

The standalone parser contains no authentication, mutation, ingestion,
publication, image, CRON, embedding, or infrastructure commands. Do not
substitute repository-maintenance commands into a public or sandbox workflow.
