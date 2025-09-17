# PapersWithCode

## Project info

This project aims to re-implement PapersWithCode and make it available for everyone.

Based on this initial Lovable design: https://lovable.dev/projects/a4609afe-13e0-46bd-8d20-9226da85ef46

## Project structure

The project consists of a `backend` folder (which implements a FastAPI app which connects to a PostGresSQL database) and a `frontend` folder.

## Set-up

```bash
git clone <...>
cd paperswithcode
```

[Pre-commit](https://pre-commit.com/) is used to automatically run Ruff on the code base each time you contribute to the repository. See the `.pre-commit-config.yaml` file. On Ubuntu, it can be installed with `apt install pre-commit`.

## How to run

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