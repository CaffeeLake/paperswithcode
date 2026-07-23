---
name: remote-paper-curation
description: Safely curate one Papers With Code paper from a remote Hugging Face Job without direct database access.
---

# Remote Paper Curation

This Job has no PostgreSQL credentials. Never read `backend/keys.env`, run SQL,
or edit repository files. Fetch the job-scoped paper context with:

```bash
python jobs/curation_api.py context
```

Search existing task/method taxonomy with:

```bash
python jobs/curation_api.py taxonomy "image generation"
```

For `add-evals`, follow the conservative rules in `add-evals/SKILL.md`, but
write a JSON payload containing only `evaluations` (each has this job's
`paper_id`) and submit it with `python jobs/curation_api.py apply payload.json`.
Use only configured leaderboard IDs returned by context/taxonomy or trusted
source data; never invent benchmark IDs or import comparator rows.

For `enrich-paper`, preserve the existing task/method/link lists from context,
append only high-confidence additions, and submit an `enrich` payload with the
complete replacement list for each changed relation. Set `urls_extracted` only
when official artifacts were actually validated.

The remote container must not generate or upload thumbnails itself. Ask the VPS
to run its existing validated thumbnail pipeline by including
`"regenerate_thumbnail": true` inside `enrich` whenever the context has no
`thumbnail_url`, or when the existing thumbnail is stale, broken, squat, or
letterboxed. The apply response reports the old and generated dimensions,
public URL, validation result, and warnings. Include that outcome in the audit
report. Do not claim the thumbnail was fixed unless the response says
`"status": "regenerated"` and `"success": true`.

Example:

```json
{
  "enrich": {
    "task_ids": [19, 429],
    "method_ids": [59, 67, 86],
    "repositories": [
      {"url": "https://github.com/example/project", "is_official": true}
    ],
    "project_pages": [],
    "regenerate_thumbnail": true,
    "urls_extracted": true
  }
}
```

Finish with a concise audit report. The runner reports it to the VPS.
