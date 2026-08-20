---
name: s2-cli
description: "Semantic Scholar CLI (`s2`) for on-demand citation graph lookup: papers a work cites, papers that cite a work, and graph search across 200M+ papers. Use whenever the user asks for Semantic Scholar, S2, cited papers, references, bibliography, citing papers, citation count from Semantic Scholar, or papers that may not be in the local Papers With Code catalog. Prefer `s2` over curl or ad-hoc Graph API requests. `pwc search` is the local catalog only; `s2 search` is the broader Semantic Scholar graph."
---

The `s2` CLI is read-only. It queries the Semantic Scholar Graph API and
requires `PWC_SEMANTIC_SCHOLAR_API_KEY` or `S2_API_KEY`. Run `s2 --help` or a
nested `--help` command when the live parser and this skill disagree; the
parser is authoritative.

Use compact TSV for reading. Add `--json` for programmatic filtering, joining,
or schema-dependent processing.

`PAPER` accepts a modern or legacy arXiv ID, a DOI, a 40-character Semantic
Scholar paper ID, a prefixed ID (`ARXIV:`, `DOI:`, `CorpusId:`, `PMID:`,
`URL:`), an arXiv or Semantic Scholar URL, or a quoted title. Title matching
uses Semantic Scholar's closest-title endpoint and prints a header with the
matched title, ID, arXiv ID, and match score. If the header is wrong, rerun
with an ID. Do not fall back to `s2 search` to resolve a specific paper.

In this Papers With Code checkout, prefix every command with:

```bash
uv run --env-file backend/keys.env --directory s2_cli
```

Elsewhere, install with `uv tool install git+https://github.com/huggingface/s2-cli.git`
and export `S2_API_KEY` or `PWC_SEMANTIC_SCHOLAR_API_KEY`.

## Commands

- `s2 refs PAPER [--limit LIMIT] [--offset OFFSET] [--fields FIELDS] [--json]` — papers this paper cites.
- `s2 citations PAPER [--limit LIMIT] [--offset OFFSET] [--fields FIELDS] [--json]` — papers that cite this paper.
- `s2 search QUERY [--limit LIMIT] [--offset OFFSET] [--year YEAR] [--fields FIELDS] [--json]` — search the Semantic Scholar graph.
- `s2 version` — show CLI and API contract versions.

Default `--limit` is 20. Search max `--limit` is 100; refs/citations max is
1000. There is no `--all`. When stderr prints `# more: rerun with --offset N`,
pass that offset. Citations must keep `offset + limit <= 9999`.

## Research workflow

1. Prefer `pwc search` / `pwc paper info` for papers already in Papers With Code.
2. Use `s2 search QUERY --limit 100 --json` when you need the broader graph,
   high-citation classics, or papers missing from the local catalog.
3. Run a second `s2 search QUERY --year 2025-2026 --limit 100 --json` for a
   recent slice. Do not treat one search as both the classic and recent lists.
4. Use `s2 refs PAPER` for a bibliography and `s2 citations PAPER` for citing
   work. Quote titles. Prefer `ARXIV:` IDs after the first resolution.
5. Extract arXiv IDs from the `arxiv` TSV column or `externalIds.ArXiv` in JSON.
6. Do not curl `api.semanticscholar.org` while this CLI is available.

## Output and limits

- Stable exit codes are `0` success, `2` invalid usage or missing key, `3`
  network/rate-limit failure, and `4` not found or invalid API response.
- Never read `PWC_SEMANTIC_SCHOLAR_API_KEY_2`. That key is reserved for
  historical backfill jobs.
- Default request pacing is 1.5s. Do not page citations of famous papers up to
  the 10k cap unless the user explicitly asks.
