# pwc CLI

A lightweight, read-only client for the public Papers With Code catalog API.
Public reads are anonymous: no login or token is required.

```bash
uv tool install ./standalone_cli
pwc search "small vision language models" --limit 10
pwc search "small vision language models" --has-official-implementation
pwc paper recent --implementation-coverage
pwc paper info 2501.01234
pwc paper read 2501.01234
pwc benchmark list
```

`pipx install ./standalone_cli` is also supported. `PWC_API_URL` selects a
compatible versioned API origin; it defaults to
`https://paperswithcode.co/api/v1`. Run `pwc --help` for the complete read-only
command tree. In an interactive terminal, benchmark lists render the top
benchmarks under each visible task, grouped by research area. Use `--flat` for
the paginated dataset table or `--group-by-area` to force Markdown when piping.
Each benchmark list row places its description and optional Hugging Face dataset
URL immediately after its name. Grouped rows also include the full name when
distinct, slug, and ID;
inspect it with `pwc benchmark --name IDENTIFIER`. Task-scoped benchmark lists
also include the benchmark ID and slug alongside the best model, its paper
title, and the preferred code repository. Either identifier can be passed to
`pwc benchmark --name`. The stable exit codes are 0 (success), 2 (usage), 3
(network or server failure), and 4 (invalid response).

Paper discovery commands accept `--implementation-coverage` to add
`official_implementation` and `code_repositories` to their compact TSV rows;
JSON and `pwc paper info` always include both fields. The boolean reports whether
the catalog links an official repository to any version of the paper; `false`
does not prove that no official code exists elsewhere. `pwc search` and
`pwc paper list` accept
`--has-official-implementation` and fail closed unless the API confirms that it
applied the filter.
