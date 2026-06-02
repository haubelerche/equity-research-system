---
name: data-contracts-ingestion
description: Use when working on connectors, raw payloads, source metadata, canonical fact normalization, DB migrations, data quality gates, lineage, or reconciliation. Enforces source tracing, quality gates before fact promotion, and schema migration discipline.
---

# Data Contracts and Ingestion

## When to use

- Adding or modifying a connector in `scripts/connectors/`.
- Modifying `scripts/ingest_ticker.py` or `scripts/build_facts.py`.
- Changing `backend/facts/normalizer.py` or `backend/facts/completeness.py`.
- Adding or changing a DB table in `backend/database/migrations/`.
- Debugging a quality gate failure or coverage gate failure.
- Modifying `backend/database/fact_store.py`, `backend/database/source_registry.py`, or `backend/dataops/quality_report.py`.

---

## Minimum Context to Read

```
scripts/connectors/<relevant_connector>.py
scripts/ingest_ticker.py
scripts/build_facts.py
backend/facts/normalizer.py
backend/facts/completeness.py
backend/dataops/quality_report.py
backend/database/fact_store.py
backend/database/migrate.py
backend/database/migrations/<latest>.sql
tests/unit/test_normalizer.py
tests/unit/test_data_quality.py
```

Also read `.claude/plan/DATA_INGESTION_PLAN_SUPABASE_VNSTOCK.md` for source registry decisions.

---

## Execution Procedure

### Ingestion run

```bash
python scripts/ingest_ticker.py --ticker DHG --years 5
```

Must produce:
- Source metadata record (source_type, provider, ticker, fiscal_year, ingested_at, checksum if possible).
- Raw payload saved before normalization.
- Ingestion run logged with status and errors.

### Fact build

```bash
python scripts/build_facts.py --ticker DHG
```

Must produce:
- Canonical facts with `ticker`, `fiscal_year`, `quarter`, `metric_name`, `value`, `unit`, `currency`, `source_id`, `confidence`.
- All four quality gates evaluated: `coverage_gate`, `core_keys_gate`, `source_validation_gate`, `valuation_gate`.
- Any failing gate must block fact promotion — facts do not flow to valuation with a `FAIL` gate.

---

## Hard Constraints

| Rule | Detail |
|---|---|
| Source metadata always | Every ingest run must write a source metadata record with at minimum: `source_type`, `ticker`, `ingested_at`. |
| No silent promotion | Facts must not pass to valuation if any quality gate returns `FAIL`. |
| Preserve source trace | `source_id` must be present on every canonical fact. Do not strip lineage. |
| Unit consistency | All percentage values stored as decimal (e.g. `0.15` not `15`). All monetary values in same unit as source (VND billions). |
| No mutation after ingest | Raw payloads must not be modified after initial storage. Reingestion creates a new record. |
| Schema change = migration | Any addition of a column, table, or index requires a new file in `backend/database/migrations/` numbered in sequence. |
| Migration must be backward-compatible | Do not drop columns that are referenced by application code without first removing the references. |
| Duplicate detection | Ingestion must detect and skip or version duplicate records for the same (ticker, fiscal_year, quarter, source_type). |

---

## Test Coverage Requirements

Every change to ingestion or fact normalization must maintain or add tests for:

- [ ] Normal case: valid input produces expected canonical fact.
- [ ] Missing field: connector returns `None` or empty — normalizer handles gracefully.
- [ ] Duplicate record: second ingest of same period is idempotent or versioned.
- [ ] Subtotal/total reconciliation: line item sum matches header when source provides both.
- [ ] Unit mismatch: value in wrong unit raises or is flagged.
- [ ] Period mismatch: fact for wrong quarter raises or is flagged.
- [ ] Quality gate: failing gate blocks downstream promotion.

---

## Accepted Tickers (MVP)

```python
TICKERS = ["DHG", "IMP", "DMC", "TRA", "DBD"]
```

Coverage gate passes at `≥ 3` fiscal year periods (not necessarily exactly 5). The report must state the actual `annual_reports_collected` count.

---

## Expected Output Artifacts

```
data/raw/<ticker>/<source_type>/<period>.*       # raw payload
data/processed/<ticker>/facts_<period>.json      # normalized facts
artifacts/runs/ingest_<ticker>_<timestamp>.json  # run log
```

Report gate statuses under `artifacts/runs/` or in DB `run_log` table.
