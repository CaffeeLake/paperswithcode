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

Finish with a concise audit report. The runner reports it to the VPS.
