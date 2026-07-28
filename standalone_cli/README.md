# pwc CLI

A lightweight, read-only client for the public Papers With Code catalog API.
Public reads are anonymous: no login or token is required.

```bash
uv tool install ./standalone_cli
pwc search "small vision language models" --limit 10
pwc paper info 2501.01234
pwc paper read 2501.01234
pwc benchmark list --task OCR
```

`pipx install ./standalone_cli` is also supported. `PWC_API_URL` selects a
compatible versioned API origin; it defaults to
`https://paperswithcode.co/api/v1`. Run `pwc --help` for the complete read-only
command tree. Task-scoped benchmark lists include the best model, its paper
title, and the preferred code repository. The stable exit codes are 0
(success), 2 (usage), 3 (network or server failure), and 4 (invalid response).
