# Private paper authoring guide

Use this guide only when trusted metadata enables paper artifacts for an
ordinary research chat. The selected model decides whether the user's request
is an explicit manuscript request.

Run `pwc-paper create --title "..."` only to create the one private project for
the current chat. It compiles a neutral standard-article draft and prints a
bounded receipt. If metadata already contains a project, use `pwc-paper
begin-edit` to inspect its current head before proposing a narrow change. This
release does not expose arbitrary file writes: never claim a source edit unless
`pwc-paper` reports a published version.

For an explicit repair request, run `pwc-paper repair-context --directory
/workspace/paper`, inspect the checked-out source and diagnostics, then make a
narrow source change. Submit it with `pwc-paper repair --directory
/workspace/paper --artifact-id <artifact-id> --expected-parent-version-id
<failed-id>`. The service permits at most three failed repair attempts;
intermediate failures are not paper versions.

Use `pwc` first for catalog evidence, `s2` for citation identities beyond the
catalog, and restricted `hf` only for relevant public Hub evidence. Preserve
unknown facts as TODOs. Never fabricate bibliography entries, results, or
claim-level support. The project uses pdfLaTeX, BibTeX, and natbib; do not add
packages, shell escape, remote files, or unsupported assets.
