# EXECUTION STATE

> Auto-updated after each task. Source of truth for current build position.

---

## Current State

```
Current Level:       Level 9 — Pipeline Complete + Data Trust Layer DONE
Target Level:        Level 9 — Production-ready (5-ticker MVP)
Current Phase:       Phase 12 — Data Trust Layer (Phases 0-5) COMPLETE — merged to main 2026-05-31
Last Completed Task: Data Trust Layer rebuild: FactEntry provenance, CitationMap with real source titles,
                     driver_evidence catalyst rendering, 6-gate primary evaluator, LangGraph harness,
                     official document scaffold. 468 tests pass. Final export RED-by-design until
                     real DHG BCTC PDFs placed under data/official_documents/DHG/<year>/.
```

---

## Phase Completion Summary

| Phase | Script / Module | Status | Evidence |
|-------|----------------|--------|----------|
| 0 — Repo Audit | `specs/00_REPO_AUDIT.md` | DONE | Specs written |
| 1 — Data Contracts | `specs/03–07_*.md` | DONE | Specs written |
| 2 — Ingestion MVP | `scripts/ingest_ticker.py` | DONE | All 5 tickers ingested |
| 3 — Canonical Facts | `scripts/build_facts.py` | DONE | DQ gates pass for all 5 |
| 4 — Valuation | `scripts/run_valuation.py` | DONE | DCF/P-E/EV-EBITDA artifacts |
| 5 — Evidence Index | `scripts/build_index.py` | DONE | Chunks indexed in DB |
| 5b — Retrieval Test | `scripts/test_retrieval.py` | DONE | 4/4 gates pass for DHG |
| 6 — Report Generation | `scripts/generate_report.py` | DONE | Markdown + citations |
| 7 — Evaluation | `scripts/evaluate_report.py` | DONE | 5 deterministic gates |
| 8 — Stateful Workflow | `scripts/run_research.py` | DONE | Full pipeline + DB logging |
| 9 — Human Approval | `scripts/approve_report.py` | DONE | Export + approval record |
| 9b — Scheduler | `backend/jobs/scheduler.py` | DONE | 3 cron jobs registered |
| 10 — DataFoundationAgent | `backend/agents/data_foundation_agent.py` | DONE | All 5 tickers READY |
| 11 — Unit Tests | `tests/unit/` | DONE | 94 tests, 0 failures |
| 12 — Data Trust Layer | `backend/citations/`, `backend/evaluation/` | DONE | 468 tests, 0 failures; FactEntry provenance; 6-gate evaluator; catalyst rendering |

---

## Level 3 Completion Evidence (Fact-Ready)

| Ticker | FY Periods | coverage_gate | core_keys_gate | source_validation_gate | valuation_gate | valuation_ready |
|--------|-----------|--------------|----------------|----------------------|----------------|-----------------|
| DHG    | 5 (2021–2025) | pass | pass | pass | pass | True |
| IMP    | 4 (2022–2025) | pass | pass | pass | pass | True |
| DMC    | 4 (2022–2025) | pass | pass | pass | pass | True |
| TRA    | 4 (2022–2025) | pass | pass | pass | pass | True |
| DBD    | 4 (2022–2025) | pass | pass | pass | pass | True |

---

## Level 4+ Completion Evidence (Calculation + Report + Evaluation)

### DHG Full Pipeline Run (latest)
- **snapshot_id**: `snap_0c2fbaf394e8fbc5ac14`
- **DCF base**: 137,010 VND/share (intrinsic)
- **Market price**: 94,400 VND/share → upside 45.1%
- **P/E 15x implied**: 94,620 VND/share
- **EV/EBITDA 10x implied**: 109,608 VND/share
- **Evaluation**: WARN (numeric_consistency), 4x PASS → OVERALL: WARN
- **Status**: REPORT_READY → approved and exported

Artifact paths:
- `artifacts/valuation/DHG_*_valuation.json`
- `artifacts/facts/DHG_*_fact_report.json`
- `artifacts/evaluation/DHG_*_evaluation.json`
- `reports/DHG_*_full_report.md`
- `reports/approved/DHG_*_APPROVED*.md`

---

## Unit Test Suite

```
tests/unit/                        — normalizer, ratios, dcf, data_quality, gate_validation, etc.
tests/citations/                   — citation_map, event_linker, validator, driver_evidence (33 new)
tests/evaluation/                  — numeric_claim_gates, catalyst_evidence_gates, final_source_gates
tests/catalysts/                   — event_extraction
tests/reconciliation/              — financial_fact_reconciliation
tests/sources/                     — source_registry, document_fetcher
tests/official_sources/            — official_document_ingestion
tests/schema/                      — dual_source_schema
tests/documents/                   — company_ir_connector

Total: 468 passed, 22 skipped, 0 failed (as of 2026-05-31)
```

---

## Key Architecture Files

| Module | Purpose |
|--------|---------|
| `backend/facts/normalizer.py` | Build fact table, compute derived metrics (EBITDA, FCF, margins) |
| `backend/facts/completeness.py` | Three-tier DQ gate: coverage, core_keys, source_validation |
| `backend/analytics/ratios.py` | Deterministic ratio calculations |
| `backend/analytics/dcf.py` | Two-stage DCF + 3-scenario (bear/base/bull) |
| `backend/analytics/multiples.py` | P/E and EV/EBITDA valuation |
| `backend/analytics/sensitivity.py` | WACC × terminal growth sensitivity table |
| `backend/dataops/snapshot.py` | Research snapshots: frozen accepted facts for reproducible valuation |
| `backend/jobs/scheduler.py` | APScheduler: weekly_sync, daily_prices, monthly_valuation |
| `backend/agents/data_foundation_agent.py` | Orchestrates data preparation; assess/prepare/readiness report |

---

## Known Issues / Limitations

| Issue | Impact | Workaround |
|-------|--------|------------|
| Supabase pooler statement_timeout | Snapshot INSERT must use `execute_values(page_size=50)` | Fixed in snapshot.py |
| vnstock price unit (× 1000 error) | Price stored in thousands VND | Fixed: `return price * 1000` in run_valuation.py |
| EBITDA not ingested from API | EV/EBITDA unavailable without derivation | Fixed: derived from gross_profit + sga + depreciation |
| evaluation numeric_consistency WARN | Numbers in report differ slightly from source | Acceptable: formatting tolerance issue |
| APScheduler optional dependency | Scheduler silently disabled if not installed | `pip install apscheduler` |
| 2021FY data for IMP/DMC/TRA/DBD | vnstock API doesn't return 2021 data | Use golden CSV fallback when available |

---

## How to Run Full Pipeline (DHG)

```bash
# Step-by-step
python scripts/ingest_ticker.py --ticker DHG --years 5
python scripts/build_facts.py --ticker DHG
python scripts/run_valuation.py --ticker DHG
python scripts/build_index.py --ticker DHG
python scripts/test_retrieval.py --ticker DHG
python scripts/generate_report.py --ticker DHG --report-type full_report
python scripts/evaluate_report.py --ticker DHG
python scripts/approve_report.py --ticker DHG --decision approve

# Or one command:
python scripts/run_research.py --ticker DHG
python scripts/approve_report.py --ticker DHG --decision approve

# Data foundation check:
python -m backend.agents.data_foundation_agent --all
```

---

## DB State

- Schema version: `007_expand_line_items` (latest migration applied)
- All 5 tickers: 96 accepted facts each in `fact.financial_facts`
- Schemas: `ref`, `ingest`, `fact`, `research` all active
- `fact.accepted_financial_facts` view: 4–5 FY periods × 24 line items per ticker
- `research.snapshots` + `research.snapshot_items`: DHG snapshot active
- `research.runs` + `research.run_steps`: DHG pipeline run logged
- `research.run_approvals`: DHG approval record saved
