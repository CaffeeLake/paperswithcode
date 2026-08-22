# pwc CLI

A lightweight, read-only client for the public Papers With Code catalog API.
Public reads are anonymous: no login or token is required.

```bash
uv tool install ./standalone_cli
pwc search "small vision language models" --limit 10
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
