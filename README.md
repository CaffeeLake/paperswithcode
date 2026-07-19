# PapersWithCode

A complete recreation of paperswithcode.com built with modern web technologies.

🌐 **Live Site**: https://paperswithcode.co (HTTPS enabled)

## Project info

This project aims to re-implement PapersWithCode and make it available for everyone.

Based on this initial Lovable design: https://lovable.dev/projects/a4609afe-13e0-46bd-8d20-9226da85ef46

## 🚀 Quick Start

### Production (HTTPS)

The site is deployed at **https://paperswithcode.co** with Nginx reverse proxy and Let's Encrypt SSL.

**Setting up HTTPS**: See [`docs/deployment.md`](docs/deployment.md)

### Development

Start both backend and frontend:

```bash
./start_services.sh
```

Stop services:

```bash
./stop_services.sh
```

## Project structure

The project consists of a `backend` folder (which implements a FastAPI app which connects to a [PostGresSQL](https://www.postgresql.org/) database) and a `frontend` folder. The backend re-implements the [PapersWithCode API](https://github.com/paperswithcode/paperswithcode-client) formerly maintained by Meta.

## Set-up

We use [uv](https://docs.astral.sh/uv/) to handle Python package management. It can be installed like so:

```bash
pip install uv
```

Next, clone the repo and install the package:

```bash
git clone https://github.com/huggingface/paperswithcode.git
cd paperswithcode
uv add paperswithcode
```

After that, you can use `uv run --env-file backend/keys.env` to run everything.

### PwC CLI

Repository maintenance workflows are exposed through the `pwc` command. For
example, generate a rule-based GitHub issue body from a paper's current
paper-native evaluations:

```bash
uv run --env-file backend/keys.env pwc github-issue body 2601.21998
```

Use `--verified` only after a human verification pass, and `--json` when the
caller also needs the issue title, official repository candidates, computed
rankings, and other structured metadata:

```bash
uv run --env-file backend/keys.env pwc github-issue body 2601.21998 --verified --json
```

Creating the issue is a separate, duplicate-safe command. It resolves only
official repositories and requires an explicit publication confirmation:

```bash
uv run --env-file backend/keys.env pwc github-issue create 2601.21998 \
  --verified --confirm PUBLISH
```

Regenerate and validate a paper thumbnail using an arXiv ID, Papers with Code
URL, or numeric external-paper ID:

```bash
uv run --env-file backend/keys.env pwc thumbnail 2512.20856
```

The command forces regeneration by default, reports old and new dimensions,
and exits non-zero when the JPEG is not a 400px-wide portrait render. PDF
thumbnails preserve the source page aspect ratio, so their height is variable
(for example, a Letter page is about 400×518). Use `--no-force` to reuse a
valid cached thumbnail or `--json` for structured output.

Download, self-host, and attribute a hero image for an existing task, method,
or conference. The command keeps a seed copy in `data/entity_image_seeds/` and
stores the image bytes and source credit on the database row:

```bash
uv run --env-file backend/keys.env pwc image add task object-detection \
  https://example.org/object-detection.png \
  --source https://example.org/object-detection
```

Manage directed paper lineage using unambiguous paper references. Supplying
more than two papers creates each adjacent predecessor-to-successor edge:

```bash
uv run --env-file backend/keys.env pwc paper lineage add \
  1810.04805 2005.14165 2303.08774
uv run --env-file backend/keys.env pwc paper lineage list 2005.14165
uv run --env-file backend/keys.env pwc paper lineage remove \
  1810.04805 2005.14165 --confirm DELETE
```

Inspect scheduled jobs by triangulating parsed logs, active processes, lock
files, database freshness, and available GitHub Actions state. The command
returns non-zero for broken or stuck jobs; add `--strict` to include degraded
and unknown jobs:

```bash
uv run --env-file backend/keys.env pwc cron health
uv run --env-file backend/keys.env pwc cron health update_github_stars --json
uv run --env-file backend/keys.env pwc cron health --strict
```

After rotating a CRON credential, probe it with the exact authentication style
used by the corresponding job without printing the secret:

```bash
uv run --env-file backend/keys.env pwc cron token-check PWC_GITHUB_TOKEN
```

Supported probes cover `PWC_GITHUB_TOKEN`, `PWC_HF_TOKEN`,
`PWC_OPENROUTER_API_KEY`, `PWC_SEMANTIC_SCHOLAR_API_KEY`, and the legacy
`PWC_GEMINI_API_KEY`.

[Pre-commit](https://pre-commit.com/) is used to automatically run Ruff on the code base each time you contribute to the repository. See the `.pre-commit-config.yaml` file. On Ubuntu, it can be installed with `apt install pre-commit`. The hooks can then be installed using `pre-commit install`.

## How to run

The backend (written in Python) can be run as follows:

```bash
uv run backend/run_server.py
```

The frontend (written in Javascript) can be run as follows:

```bash
cd frontend
npm run dev
```

The backend (written in Python) can be run as follows:

```bash
cd backend
uv run
```

## 📚 Documentation

### Documentation
- **[docs/deployment.md](docs/deployment.md)** – DNS, HTTPS, and runtime verification
- **[docs/data-workflows.md](docs/data-workflows.md)** – Dataset/evaluation ingestion
- **[docs/database.md](docs/database.md)** – PostgreSQL access and security
- **[docs/operations.md](docs/operations.md)** – Cron jobs, trending pipeline, monitoring
- **[docs/keyword-matching.md](docs/keyword-matching.md)** – Keyword tagging strategy and APIs
- **[docs/DATABASE_SCHEMA_UML.md](docs/DATABASE_SCHEMA_UML.md)** – Schema reference
- **[AGENTS.md](AGENTS.md)** – Concise agent quickstart and links to `docs/`
- **[backend/README.md](backend/README.md)** – Backend setup
- **[.github/workflows/scripts/README.md](.github/workflows/scripts/README.md)** – Cron job guide

### Key Scripts
- **[setup_ssl.sh](setup_ssl.sh)** - Automated SSL certificate setup
- **[start_services.sh](start_services.sh)** - Start backend and frontend
- **[stop_services.sh](stop_services.sh)** - Stop all services

## 🛠️ Tech Stack

- **Frontend**: React 18 + TypeScript + Vite + shadcn/ui + Tailwind CSS
- **Backend**: FastAPI + SQLAlchemy + PostgreSQL
- **Web Server**: Nginx + Let's Encrypt SSL
- **AI**: OpenRouter/Google Gemini for URL extraction
- **Package Management**: uv (Python), npm (JavaScript)

## TODOs

- all services should be checked to see if they are in line with the database schema (see also models.py)
- all cron jobs and batch_extract.py should leverage the services instead of manually writing SQL queries

## Improving extraction of evaluation results

- use pass@1 instead of accuracy on coding benchmarks
- when searching a dataset, thoroughly check which metric used to evaluate the dataset, and then use a separate agent to add the metric to the database/see if it already exists in the database.
- often adds "average", "overall" as metrics => should just be a single "Score" metric (higher is better or lower is better), or "OmniContext Score" for example with a specific scale like 0-10.
- messes up the dataset, e.g. for the Qwen2.5 paper, it links "LongBench-Chat" to the "LongBenchv2" dataset, which is a separate dataset. Step 2 requires an improvement by better matching the dataset details of the paper (e.g. description, arxiv id) to the existing dataset in the database.
