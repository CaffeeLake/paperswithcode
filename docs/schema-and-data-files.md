# Schema overview and data files

High-level picture of PostgreSQL contents and on-disk legacy dumps. For connection and security, see `docs/database.md`. For ER diagrams, see `docs/DATABASE_SCHEMA_UML.md`.

## Main tables (`paperswithcode_hf`)

**Core**:
- **`papers`**: metadata, abstracts, ArXiv IDs, versions, citation counts
- **`authors`**: authors with Hugging Face profile integration
- **`repositories`**: GitHub repositories, stars, update timestamps
- **`project_pages`**: project page URLs for papers
- **`tasks`**: task hierarchy via `parent_id` self-FK and `level`. Subtasks are first-class child rows (e.g. `language-modeling` → `world-knowledge`, `math`, …) with their own description, page, benchmarks, and evaluations
- **`methods`**: techniques (ResNet, Transformer, Adam, …)
- **`datasets`**: benchmark datasets (COCO, ImageNet, …)
- **`evaluations`**: benchmark results with metrics and ranks. `task_id` may reference any task in the hierarchy (top-level OR subtask) but each row belongs to exactly one `(task_id, dataset_id, best_metric)` leaderboard; pick the most-specific child task. Optional `harness` column for model+harness benchmarks (e.g. Terminal-Bench scores a model running inside an agentic harness like `Claude Code` or `Terminus`); leave NULL for plain model-only benchmarks. Optional `hf_model_url` column links the evaluated model to its Hugging Face model page (e.g. `https://huggingface.co/MiniMaxAI/MiniMax-M3`) so the leaderboard model name can become an outbound link
- **`metrics`**: evaluation metrics (AP, WER, BLEU, …)
- **`areas`**: research areas (Computer Vision, NLP, …)

**Junction (many-to-many)**:
- **`paper_authors`**, **`paper_tasks`**, **`paper_methods`**, **`paper_repositories`**, **`paper_project_pages`**
- **`task_datasets`** (task ↔ dataset display metadata: `featured_rank`, `supports_harness`)
- **`task_dataset_metrics`** (task ↔ dataset ↔ metric leaderboard definition)

**Tracking**:
- **`repository_star_history`**: star snapshots for trending

**Indexes**:
- Full-text search (GIN) on paper titles and abstracts
- B-tree indexes on common filters (ArXiv IDs, dates, …)

## Legacy data (`data/legacy_pwc_data/`)

1. **`papers-with-abstracts.json`** (~2.2GB): paper metadata, abstracts, authors, proceedings, ArXiv URLs, tasks/methods/datasets, GitHub links
2. **`evaluation-tables.json`** (~236MB): task/dataset hierarchies, leaderboards, metrics
3. **`jul-28-datasets.json`**, **`jul-28-methods.json`**: dataset/method definitions
4. **`links-between-papers-and-code.json`**: paper–repository associations

## Initial database setup

```bash
# Create database
psql -U postgres -c "CREATE DATABASE paperswithcode_hf;"

# Schema
psql -U postgres -d paperswithcode_hf -f backend/database/papers_setup/setup_database.sql

# Import HF papers
uv run --env-file backend/keys.env python backend/database/papers_setup/add_hf_papers.py

# Optional: legacy PWC JSON
uv run --env-file backend/keys.env python backend/database/papers_setup/add_pwc_papers_streaming.py
```

More detail: `backend/database/README.md`.
