# Papers With Code Posterly publication contract

Prepare exactly one paper first with `pwc-artifact prepare PAPER_ROUTE_ID`. Its
JSON output names a read-only input directory containing `metadata.json` and
`paper.md`. Create one artifact below `/workspace/artifacts/IDENTIFIER/`, where
`IDENTIFIER` is a lowercase hyphenated slug.

Follow `/opt/posterly/SKILL.md` and its pinned tools. The canonical output is a
static PNG. The HTML must contain an explicit `@page { size: WIDTHin HEIGHTin; }`
rule and may use only bundled relative assets—no remote `src` or CSS `url()`.
The PNG must match the canvas aspect ratio. A final PDF must be exactly one page
at the declared canvas dimensions.

The artifact directory must contain `manifest.json` plus only the files it
declares. `manifest.json` has this strict shape (replace example values):

```json
{
  "schema_version": 1,
  "identifier": "paper-title-poster",
  "kind": "posterly",
  "title": "Paper Title — Research Poster",
  "canvas": {"width": 60.0, "height": 36.0, "unit": "in", "orientation": "landscape"},
  "qr_destination": null,
  "entrypoint": "poster.html",
  "preview": "poster.png",
  "downloads": [{"path": "poster.pdf", "label": "Print PDF"}],
  "source_files": ["poster.html", "gate-report.json"],
  "gate_report": "gate-report.json",
  "gate_status": "passed",
  "gate_summary": [],
  "paper": {
    "route_id": "2601.00001",
    "paper_id": "123",
    "arxiv_id": "2601.00001v1",
    "paper_version": "v1",
    "content_sha256": "64 lowercase hex characters copied from metadata.json",
    "source_available": false
  },
  "direction": "clean technical grid",
  "canvas_defaulted": true,
  "omitted_branding": ["logo", "qr"]
}
```

List every local CSS, JSON, Markdown, text, and image asset used by the poster
in `source_files`; include the HTML entrypoint and gate report. Do not list the
preview PNG or PDF there. Set `qr_destination` only to the normalized public
HTTPS URL explicitly supplied by the user; otherwise use null and include
`"qr"` in `omitted_branding`.

Write `gate-report.json` as JSON containing at least
`{"gate_status":"passed"}`. Allowed statuses are `passed`, `warnings`, and
`failed`. If a Posterly hard gate still fails after the bounded repair loop,
publish a visible non-final draft: set both reports to `failed` and set
`downloads` to `[]`; do not include a PDF file. Soft warnings use `warnings`
and concise `gate_summary` items. Passed/warning versions require exactly one
PDF.

Publish only after all files are complete:

```bash
pwc-artifact publish /workspace/artifacts/IDENTIFIER
```

The command uploads a bounded ZIP to the trusted backend. A success receipt is
the only way to create a poster card in chat.
