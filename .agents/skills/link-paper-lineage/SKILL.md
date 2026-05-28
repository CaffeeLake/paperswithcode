---
name: link-paper-lineage
description: Link PapersWithCode paper pages as predecessor/successor follow-ups in the paperswithcode database. Use this whenever the user says one paper is a follow-up, successor, sequel, continuation, predecessor, earlier version, next version, canonical source for a later paper, or asks to connect model-family papers such as GPT-2 -> GPT-3 -> GPT-4, GLM releases, DeepSeek releases, DINO versions, or similar paper lineage chains.
---

# Link Paper Lineage

This skill adds directed edges to `paper_relations`. The direction is:

```text
source_paper_id = predecessor / earlier paper
target_paper_id = successor / follow-up paper
```

For "paper B is a follow-up of paper A", insert `A -> B`. For "paper A has successor paper B", insert the same `A -> B`. Do not add the reverse edge unless the user explicitly asks for a bidirectional relationship.

## Workflow

1. Resolve every paper mentioned by the user:
   - PapersWithCode routes: `/paper/<arxiv_id>` or `/paper/<paper_id>`.
   - arXiv IDs: query `papers.arxiv_id`, preferring `is_latest_version`.
   - Titles or model names: fuzzy search `papers.title`, then confirm from source/date/context before writing.
   - External rows: query by numeric paper id, `source_url`, or title.

2. For chains, expand the directed edges:
   - "GPT-4 follows GPT-3 follows GPT-2" means `GPT-2 -> GPT-3` and `GPT-3 -> GPT-4`.
   - "X is a follow-up of Y and Z" means `Y -> X` and `Z -> X`.
   - If the wording is ambiguous, ask once before writing.

3. Insert idempotently:

```bash
uv run --env-file backend/keys.env python - <<'PY'
from sqlalchemy import text
from backend.database.connection import get_engine

edges = [
    # (predecessor_paper_id, successor_paper_id)
    (<source_id>, <target_id>),
]

with get_engine().begin() as conn:
    for source_id, target_id in edges:
        if source_id == target_id:
            raise ValueError(f"Refusing self-link for paper {source_id}")
        conn.execute(text("""
            INSERT INTO paper_relations (source_paper_id, target_paper_id)
            VALUES (:source_id, :target_id)
            ON CONFLICT DO NOTHING
        """), {"source_id": source_id, "target_id": target_id})
PY
```

4. Verify both SQL and API shape:

```bash
uv run --env-file backend/keys.env python - <<'PY'
import json
from urllib.request import urlopen
from sqlalchemy import text
from backend.database.connection import get_engine

paper_ids = [<source_id>, <target_id>]
with get_engine().connect() as conn:
    rows = conn.execute(text("""
        SELECT pr.source_paper_id, s.title AS source_title,
               pr.target_paper_id, t.title AS target_title
        FROM paper_relations pr
        JOIN papers s ON s.id = pr.source_paper_id
        JOIN papers t ON t.id = pr.target_paper_id
        WHERE pr.source_paper_id = ANY(:paper_ids)
           OR pr.target_paper_id = ANY(:paper_ids)
        ORDER BY pr.source_paper_id, pr.target_paper_id
    """), {"paper_ids": paper_ids}).mappings().all()
    for row in rows:
        print(dict(row))

for paper_id in paper_ids:
    with urlopen(f"http://localhost:8000/api/v1/papers/{paper_id}?include_resources=true") as resp:
        paper = json.load(resp)
    print(paper_id, {
        "predecessors": [p["id"] for p in paper.get("predecessor_papers") or []],
        "successors": [p["id"] for p in paper.get("successor_papers") or []],
    })
PY
```

If the API is stale because the backend needs a restart, run `./start_services.sh` without asking.

## Reporting Back

Report the inserted directed edges using paper titles or ids, for example:

```text
Linked `Language Models are Unsupervised Multitask Learners` -> `Language Models are Few-Shot Learners`.
```

Mention if an edge already existed, and give the local paper URL for the successor paper the user most likely wants to inspect.

## When Not To Use This Skill

- The user wants to add evaluation rows. Use `add-evals`.
- The user wants to add or fix a benchmark source. Use `add-benchmark`.
- The user wants to create a method page. Use `add-method`.
- The user wants to create a new external paper row. Use `add-external-paper`.
