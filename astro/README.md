# Astro deploy kit — news collection DAG

Runs `dags/collect_ticker_news_dag.py` (ticker-scoped CafeF/VietStock news collection for
the MVP pharma tickers, every 3h on weekdays, idempotent) on Apache Airflow via Astronomer.

> Status: **deploy kit, not runtime-validated here** — the Astro CLI is not installed in this
> workspace, so the image build / `astro dev start` has not been executed. The DAG itself is
> syntax-checked and its task logic is unit-tested (`tests/unit/test_collect_for_tickers.py`,
> `test_ticker_listing_urls.py`).

## Prerequisites
- Docker (installed) + the **Astro CLI**: https://docs.astronomer.io/astro/cli/install-cli
  - Windows: `winget install -e --id Astronomer.Astro`
- A reachable Postgres (`DATABASE_URL`) and an LLM API key (`OPENAI_API_KEY`).

## Why this is a kit (not a root Astro project)
Astro expects its files at the **repo root**, but the root already has the application's
`Dockerfile` (`python:3.11-slim`) and `requirements.txt`. To avoid clobbering the app
container, this kit keeps Astro config in `astro/` and builds an image that bundles
`backend/` + `dags/` so the DAG can import the project.

## Run locally (two options)

### A. Plain Docker (no repo restructure)
```bash
# from repo ROOT (context must include backend/ and dags/)
docker build -f astro/Dockerfile -t maer-airflow .
# then run an Airflow standalone from the image, or push to your Airflow/Astro deployment
```

### B. Full Astro project (lets you `astro dev start`)
Convert the repo root to an Astro project (changes the root container to Astro Runtime):
```bash
# copy these into the repo root, then:
#   cp astro/Dockerfile ./Dockerfile.astro   (or merge)
#   cp astro/airflow_settings.yaml ./airflow_settings.yaml
astro dev start          # builds the image, starts scheduler + webserver at :8080
```
The DAG `collect_ticker_news` appears in the UI; trigger it or let the 3h schedule run.

## Production (Astro Deployment)
- Set `DATABASE_URL` and `OPENAI_API_KEY` as Deployment environment variables (secrets),
  NOT in `airflow_settings.yaml`.
- `astro deploy` (or `astro deploy --dags` for DAG-only iterations once the image exists).

## Deploy into a STANDALONE Astro/Airflow instance (chosen approach — option A)

The backend stays a plain Python 3.11 app; Airflow is only a separate scheduler runtime.
Nothing in the app imports Airflow, and `apache-airflow` is not in the app's requirements.

1. Build the scheduler image from the **repo root** (so `backend/` + `dags/` are included):
   ```bash
   docker build -f astro/Dockerfile -t maer-airflow .
   ```
   Or, with the Astro CLI in a throwaway project dir, use `astro/Dockerfile` as the project
   Dockerfile and `astro dev start`.
2. Provide secrets to that instance (NOT in the app): `DATABASE_URL`, `OPENAI_API_KEY`
   as Deployment env vars (prod) or via `astro/airflow_settings.yaml` (local dev only).
3. The DAG `collect_ticker_news` runs `backend.news.runner.collect_for_tickers` for the MVP
   tickers every 3h on weekdays; idempotent, so re-runs are safe.
4. `astro deploy` (or `astro deploy --dags` for DAG-only iterations) to ship updates.

The app and the scheduler are decoupled: local backend development never needs Airflow.

## Validation without the Astro CLI

These run on a plain Python env (no Airflow, no Astro CLI):
```bash
# 1. Byte-compile DAG + backend (catches syntax errors; does not import Airflow)
python -m compileall dags/ backend/

# 2. Exercise the collector entrypoint the DAG calls (live; small batch)
python scripts/collect_ticker_news.py --tickers DHG TRA --limit 5
```

> **Full DAG validation** (parse/import errors, schedule, task wiring, a real run) requires an
> external Airflow/Astro runtime — e.g. `astro dev parse` / `astro dev start`, or the `af`
> CLI against a running instance. It cannot be done from the plain app environment.
