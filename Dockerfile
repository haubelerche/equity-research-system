FROM python:3.11-slim

# ── System dependencies ────────────────────────────────────────────────────────
# tesseract + Vietnamese language data for OCR on scanned PDFs
# poppler-utils for pdf2image (PDF→image conversion before OCR)
# libpq-dev for psycopg2 native compilation (psycopg2-binary covers this but kept for safety)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    pkg-config \
    python3-dev \
    tesseract-ocr \
    tesseract-ocr-vie \
    poppler-utils \
    libpq-dev \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpango1.0-dev \
    libgdk-pixbuf-2.0-0 \
    libgdk-pixbuf-2.0-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python dependencies (cached layer) ────────────────────────────────────────
COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel && \
    ok=0 && \
    for i in 1 2 3 4 5; do \
      pip install \
        --no-cache-dir \
        --retries 20 \
        --timeout 120 \
        --prefer-binary \
        -r requirements.txt && ok=1 && break; \
      echo "pip install failed (attempt $i/5), retrying in 10s..."; \
      sleep 10; \
    done && \
    test "$ok" -eq 1

# ── Application code ───────────────────────────────────────────────────────────
COPY . .

# ── Data directories (created at build time so they exist in container) ────────
RUN mkdir -p \
    data/raw \
    data/processed \
    data/facts \
    data/official_documents \
    data/ocr_artifacts \
    data/candidate_facts \
    data/reconciliation \
    reports \
    reports/approved \
    artifacts/valuation \
    artifacts/evaluation \
    artifacts/runs \
    artifacts/facts \
    artifacts/index \
    artifacts/reports \
    artifacts/official_sources

# ── Runtime configuration via environment variables ───────────────────────────
# Override these at runtime: docker run -e TICKER=IMP -e ENABLE_OCR=true ...
ENV TICKER=DHG
ENV FROM_YEAR=2021
ENV TO_YEAR=2025
# Set to "true" to enable OCR pipeline for scanned official PDFs
ENV ENABLE_OCR=false
# Passed through to psycopg2; override with docker-compose or -e flag
ENV DATABASE_URL=""
ENV APP_MODE=api
ENV PORT=8010
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# ── OCR runtime smoke test at build time (verifies tesseract install) ──────────
RUN python scripts/check_ocr_runtime.py || true

# ── Healthcheck: verify the DB migrations table is reachable ──────────────────
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
  CMD test "${APP_MODE}" != "api" || curl -fsS "http://127.0.0.1:${PORT:-8010}/health" || exit 1

# ── Entrypoint: run DB migrations then the research pipeline ──────────────────
# ENABLE_OCR=true adds --ocr flag automatically
CMD ["sh", "-c", \
  "python -m backend.database.migrate && \
   if [ \"${APP_MODE}\" = \"worker\" ]; then \
     python scripts/run_research.py \
       --ticker ${TICKER} \
       --from-year ${FROM_YEAR} \
       --to-year ${TO_YEAR} \
       $([ \"${ENABLE_OCR}\" = \"true\" ] && echo --ocr || echo ''); \
   else \
     python -m uvicorn backend.api:app --host 0.0.0.0 --port ${PORT:-8010}; \
   fi"]
