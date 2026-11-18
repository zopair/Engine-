# Autonomous AI Engine

## Architecture

A five-layer, CPU-only FastAPI system with SQLite/Huey persistence, LiteLLM fallback routing, semantic caching, and optional Cloudflare R2 replication.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn api.main:app --host 0.0.0.0 --port 7860
```

## Endpoints

- `GET /health`
- `GET /docs`

## Deployment

Configure environment variables and run through the included Docker image. Cloudflare R2 requires Litestream endpoint and credential variables.
