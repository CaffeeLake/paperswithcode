# PapersWithCode

A complete recreation of paperswithcode.com built with modern web technologies.

🌐 **Live Site**: https://paperswithcode.co (HTTPS enabled)

## Project info

This project aims to re-implement PapersWithCode and make it available for everyone.

Based on this initial Lovable design: https://lovable.dev/projects/a4609afe-13e0-46bd-8d20-9226da85ef46

## 🚀 Quick Start

### Production (HTTPS)

The site is deployed at **https://paperswithcode.co** with Nginx reverse proxy and Let's Encrypt SSL.

**Setting up HTTPS**: See [SSL_CHECKLIST.md](SSL_CHECKLIST.md) or [DNS_SETUP_INSTRUCTIONS.md](DNS_SETUP_INSTRUCTIONS.md)

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
git clone https://github.com/NielsRogge/paperswithcode.git
cd paperswithcode
uv add paperswithcode
```

After that, you can use `uv run --env-file backend/keys.env` to run everything.

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

### HTTPS/SSL Setup
- **[SSL_CHECKLIST.md](SSL_CHECKLIST.md)** - Step-by-step checklist for SSL setup
- **[DNS_SETUP_INSTRUCTIONS.md](DNS_SETUP_INSTRUCTIONS.md)** - Quick DNS configuration guide
- **[HTTPS_SETUP_SUMMARY.md](HTTPS_SETUP_SUMMARY.md)** - Current setup status
- **[docs/HTTPS_SETUP.md](docs/HTTPS_SETUP.md)** - Complete HTTPS setup guide

### Development
- **[AGENTS.md](AGENTS.md)** - Complete development guide for AI agents and developers
- **[backend/README.md](backend/README.md)** - Backend API documentation
- **[cron/README.md](cron/README.md)** - CRON jobs documentation
- **[docs/](docs/)** - Additional documentation (API guides, database schema, etc.)

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
