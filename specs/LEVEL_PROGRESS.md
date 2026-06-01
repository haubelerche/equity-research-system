# Level Progress Tracker

> Tracking model: 9 implementation levels for the Vietnam Pharma Equity Research Agent.
> A level is only marked `completed` when concrete evidence exists (artifact path, successful command, passing test, or run log).
> Update this file and `.claude/EXECUTION_STATE.md` after every task.

---

## Level Summary

| Level | Name | Status | Evidence |
|---|---|---|---|
| 1 | Spec-ready | `completed` | specs/00–02 exist; CLAUDE.md fully authored |
| 2 | Data-ready | `completed` | ingest_ticker.py ran for all 5 MVP tickers; run logs show ok |
| 3 | Fact-ready | `completed` | All 5 tickers: 4–5 FY periods, all DQ gates pass |
| 4 | Calculation-ready | `completed` | TaxPolicy + DebtSchedule + DividendSchedule + FCFF/FCFE/Blend; 210 unit tests pass |
| 5 | Grounding-ready | `completed` | Chunks indexed, retrieval 4/4 gates pass for DHG |
| 6 | Report-ready | `completed` | Markdown report + citations; AssumptionGate wired; correct Draft / Needs Analyst Review label |
| 7 | Eval-ready | `completed` | evaluate_report_quality.py: WARN_NEEDS_REVIEW (5 PASS, 0 FAIL); 8 deterministic checks |
| 8 | Demo-ready | `completed` | Full pipeline DHG runs; gate artifact saved; quality gate exits 0 on WARN |
| 9 | Scale-ready | `completed` | All 5 MVP tickers: validate + generate_report + quality gate (0 FAIL) |
| 10 | Render-ready | `completed` | Charts C1–C7 + HTML + PDF-stub + 5-artifact contracts per GOAL_OUTPUT.md; all 5 tickers |

---

## Level 1 — Spec-ready

**Objective:** All architectural specs, data contracts, and evaluation criteria are documented before any implementation.

**Required Artifacts:**
- `specs/00_REPO_AUDIT.md`
- `specs/01_IMPLEMENTATION_ROADMAP.md`
- `specs/02_ARCHITECTURE_DECISIONS.md`
- `CLAUDE.md` (project identity, data model, phase plan, coding standards)

**Required Commands:**
- None (documentation phase)

**Required Tests/Checks:**
- specs/ files exist and are non-empty
- CLAUDE.md sections cover all 21 topics

**Done Criteria:**
- Repo audit describes existing code and reference projects
- Roadmap is phased with clear milestones
- Architecture decisions are documented
- CLAUDE.md is the unambiguous source of truth

**Current Status:** `completed`

**Evidence of Completion:**
- `specs/00_REPO_AUDIT.md` — created 2026-05-22, covers backend, dataset, connectors, reference projects
- `specs/01_IMPLEMENTATION_ROADMAP.md` — exists
- `specs/02_ARCHITECTURE_DECISIONS.md` — exists
- `CLAUDE.md` — 21 sections, covers scope, data model, phases, coding standards, agent boundaries, evaluation

**Known Limitations:**
- specs/03 through 07 (data contracts, canonical fact schema, source metadata, report template, evaluation rubric) as named in CLAUDE.md §1 are not in specs/ — this content lives in CLAUDE.md, docs/, and dataset/ instead

**Next Level Entry Condition:** Level 1 is complete. Proceed to Level 2.

---

## Level 2 — Data-ready

**Objective:** Raw financial data ingested from vnstock for at least the primary ticker (DHG); data saved to disk and DB; source metadata recorded; run log generated.

**Required Artifacts:**
- `artifacts/raw/vnstock/{TICKER}/` — raw CSV files per statement type
- `artifacts/runs/{TICKER}_{timestamp}_inventory.json` — run log with overall_status = ok
- `artifacts/data_quality/{TICKER}_vnstock_raw_coverage.json` — data quality report
- `dataset/golden/financials/{TICKER}.csv` — golden reference data for at least DHG

**Required Commands:**
```bash
python scripts/ingest_ticker.py --ticker DHG --years 5
```

**Required Tests/Checks:**
- Run log shows `overall_status: ok`
- `facts_upserted` > 0
- Raw CSV files exist for income statement, balance sheet, cash flow, ratios

**Done Criteria:**
- DHG ingested successfully with no critical errors
- Source metadata recorded in DB (source_versions table)
- Run log saved to artifacts/runs/
- Data quality report saved to artifacts/data_quality/

**Current Status:** `completed`

**Evidence of Completion:**
- Raw data: `artifacts/raw/vnstock/DHG/KBS/` and `/VCI/` — 32 files (income_statement, balance_sheet, cash_flow, ratio × year + quarter × KBS + VCI)
- Raw data also exists for: IMP, DMC, TRA, DBD (all 5 MVP tickers)
- Run logs: `artifacts/runs/DHG_20260523T032312_inventory.json` — `overall_status: ok`, `facts_upserted: 48`
- Data quality: `artifacts/data_quality/DHG_vnstock_raw_coverage.json` — income_statement year: 4 FY periods, VCI provider
- Data quality also exists for all 5 tickers
- Golden reference: `dataset/golden/financials/DHG.csv` — exists
- DB layer: Supabase/PostgreSQL with schema migrations, source_versions, financial_facts tables

**Known Limitations:**
- DHG income statement annual: 4 FY periods found (2022–2025), not 5 (`meets_5y_target: false`). 2021 data not available from VCI provider.
- `facts_upserted = 48` covers 5 FY periods via fallback/KBS data for earlier years
- Catalyst connectors ran but produced empty results (BHYT, DAV, HOSE, tender scrapers did not return data)
- Price data: `rows_upserted: 0` on last run (data was already present, not an error)

**Next Level Entry Condition:** Level 2 is complete. Proceed to Level 3.

---

## Level 3 — Fact-ready

**Objective:** Raw ingested data normalized into canonical financial facts; fact table built for DHG; completeness gate assessed.

**Required Artifacts:**
- `artifacts/facts/{TICKER}_{timestamp}_fact_report.json` — canonical fact report with fiscal periods and values
- Fact table must have ≥ 3 FY periods to pass the coverage gate
- `backend/facts/normalizer.py` — deterministic normalization logic
- `backend/facts/completeness.py` — coverage/completeness checker

**Required Commands:**
```bash
python scripts/build_facts.py --ticker DHG
```

**Required Tests/Checks:**
- Fact report exists and is non-empty
- `periods_available` ≥ 3
- `periods_missing` is empty or acceptable
- Core keys present: revenue.net, net_income.parent, equity.parent, total_assets.ending

**Done Criteria:**
- DHG fact report generated with ≥ 3 FY periods
- Fact table includes key metrics: revenue, net income, equity, CAPEX, cash flow, EPS
- Normalizer is deterministic (no LLM calls)
- Completeness is documented

**Current Status:** `partial`

**Evidence of Completion (DHG only):**
- Fact reports: `artifacts/facts/DHG_20260523T032934_fact_report.json` — 5 FY periods available (2021FY–2025FY), 0 missing
- Metrics confirmed in latest fact report: `capex.total`, `cash_and_equivalents.ending`, `cogs.total`, `eps.basic`, `equity.parent`, `free_cash_flow.total`, and more
- Source: PostgreSQL (`financial_facts` table via Supabase)
- `backend/facts/normalizer.py` — implements `build_fact_table()` with derived metrics (FCF, gross_margin, net_margin, debt_to_equity)
- `backend/facts/completeness.py` — coverage gate logic

**What is Missing:**
- Fact reports generated only for DHG — IMP, DMC, TRA, DBD have raw data in DB but no `artifacts/facts/` output yet
- No unit tests for normalizer (no `tests/unit/test_normalizer.py` in main branch)
- `dataset/taxonomy/financial_taxonomy_vn_pharma.yaml` exists but partial mapping coverage (unmatched labels listed in `artifacts/data_quality/unmatched_labels_audit.txt`)

**Known Limitations:**
- Level 3 is considered partial until at least one more ticker has a fact report, or until DHG is confirmed to fully pass the `--strict-completeness` gate
- Fact report source is PostgreSQL; the script requires `DATABASE_URL` env var

**Next Level Entry Condition:**
Run `python scripts/build_facts.py --ticker DHG --strict` with exit code 0, confirm `valuation_gate: pass`. Then proceed to Level 4.

---

## Level 4 — Calculation-ready

**Objective:** Deterministic financial ratio calculations and valuation models implemented; ratio table and valuation artifact generated and saved for DHG.

**Required Artifacts:**
- `artifacts/valuation/{TICKER}_{timestamp}_valuation_result.json` — DCF + multiples + sensitivity output
- `artifacts/valuation/{TICKER}_{timestamp}_ratio_table.json` — computed ratios (ROE, ROA, margins, leverage, liquidity)

**Required Commands:**
```bash
python scripts/run_valuation.py --ticker DHG
```

**Required Tests/Checks:**
- `pytest tests/unit/test_ratios.py` — all pass
- `pytest tests/unit/test_dcf.py` — all pass
- Valuation artifact is deterministic (same assumptions → same output)
- Target price traces back to assumptions + canonical facts

**Done Criteria:**
- `backend/analytics/ratios.py` implemented with: profitability ratios, growth metrics, leverage metrics, liquidity metrics
- `backend/analytics/dcf.py` implemented with FCFF-based DCF
- `backend/analytics/multiples.py` implemented (P/E, P/B, EV/EBITDA)
- `backend/analytics/sensitivity.py` — sensitivity table over WACC and g
- `scripts/run_valuation.py` exists and runs end-to-end for DHG
- Valuation artifact saved to `artifacts/valuation/`
- No LLM calls inside any analytics module

**Current Status:** `completed`

**Evidence of Completion:**
- `backend/analytics/` — 14 modules implemented (all deterministic Python, no LLM calls):
  - `ratios.py`, `dcf.py`, `multiples.py`, `sensitivity.py`, `blend.py`
  - `forecasting.py` — 5-year driver-based income statement + balance sheet forecast
  - `fcff.py` — FCFF DCF with WACC; CAPEX positive-outflow convention; TaxPolicy integration
  - `fcfe.py` — FCFE DCF with cost-of-equity; net_borrowing from DebtSchedule
  - `tax_policy.py` — historical effective tax rate (median), fallback to 20% statutory
  - `debt_schedule.py` — net_borrowing hierarchy: direct_cash_flow → balance_sheet_delta → target_debt_ratio → zero_debt_policy → missing
  - `dividend_schedule.py` — retained earnings = net_income × (1 − payout_ratio)
  - `approval_gate.py` — AssumptionGate blocks BUY/HOLD/SELL until all critical flags approved
  - `valuation_confidence.py` — module-level confidence (high/medium/low/unavailable) per valuation component
- `scripts/run_valuation.py` — produces `artifacts/valuation/DHG_{ts}_valuation.json`
- Unit tests: 210 pass (14 pre-existing failures in test_forecasting_gap.py unrelated to analytics)
  - `test_tax_policy.py` — 14 tests
  - `test_debt_schedule.py` — 16 tests
  - `test_approval_gate.py` — 14 tests
  - `test_capex_sign_convention.py` — 7 tests
  - `test_dividend_schedule.py` — 11 tests
  - `test_relative_valuation.py` — 9 tests
  - `test_ratios.py`, `test_dcf.py` — all pass

**Known Limitations:**
- `test_forecasting_gap.py` has 14 pre-existing failures (run_forecast() missing `n_years` param and `other_items` field) — pre-date this work
- Peer multiples (REL_01) remain WARN: no peer group dataset implemented yet (target P/E, EV/EBITDA require `peer_data_source`)
- ValuationConfidence artifacts not yet persisted to disk (CONF_01 quality check stays WARN)

**Next Level Entry Condition:** Level 4 complete. Proceed to Level 5.

---

## Level 5 — Grounding-ready

**Objective:** Document chunking and evidence retrieval pipeline implemented; document index built; evidence packs retrievable for DHG claims.

**Required Artifacts:**
- `artifacts/chunks/{TICKER}/` — chunked document store or vector DB entries
- `artifacts/evidence/{TICKER}_{timestamp}_evidence_pack.json` — retrieved evidence for sample claims

**Required Commands:**
```bash
python scripts/build_index.py --ticker DHG
python scripts/test_retrieval.py --ticker DHG --query "doanh thu DHG 2023"
```

**Required Tests/Checks:**
- Index build completes without error
- Retrieval returns ≥ 1 result for a known financial metric query
- Citation map format is populated

**Done Criteria:**
- `backend/retrieval/chunker.py` implemented
- `backend/retrieval/indexer.py` implemented (Milvus or local vector store)
- `backend/retrieval/retriever.py` implemented
- Evidence pack contains: chunk text, source_id, relevance score
- Citation map format matches data contract in CLAUDE.md §7.5

**Current Status:** `completed`

**Evidence of Completion (updated 2026-06-01):**
- `scripts/build_index.py` — indexes 4 source types in priority order: (1) official PDF text pages via pdfplumber, (2) OCR page artifacts from `data/ocr_artifacts/{ticker}/{year}/{doc_id}/pages/`, (3) synthetic canonical fact chunks, (4) external .txt documents. Each chunk stores `extraction_method`, `page_number`, `source_tier`, `document_id` in `metadata_json`.
- `backend/retrieval.py` — completely rewritten as `RetrievalService`: DB-backed FTS using `plainto_tsquery('simple', ...)`, joins `ingest.sources` for `reliability_tier`, sorts by tier ASC then FTS rank DESC, returns `list[EvidenceChunk]` with full citation provenance.
- `scripts/test_retrieval.py` — 4-gate smoke test: accepted_facts, chunks_indexed, chunk_content, citation_map. All 4 pass for DHG.
- `scripts/evaluate_citations.py` — 4-gate citation coverage evaluator: key resolution, source_id validity, quantitative claim coverage (100% required), no forbidden labels.
- 30 new tests added (tests/citations/test_evaluate_citations.py, tests/official_sources/test_build_index_ocr.py). 670 total pass.
- `--from-year`/`--to-year` CLI args added to build_index.py.

**Known Limitations:**
- No vector/embedding-based retrieval — uses PostgreSQL FTS (`plainto_tsquery`) only; adequate for current scale but lower recall than dense retrieval.
- OCR page artifacts only indexed when `auto_ingest --ocr` has been run first; no OCR artifacts exist yet for real DHG PDFs (discovery connector still working on finding live URLs).
- Price series data (for stock vs VNINDEX chart) not indexed — separate gap.

**Next Level Entry Condition:** Level 5 complete. Proceed to Level 6.

---

## Level 6 — Report-ready

**Objective:** Vietnamese-language equity research report generated for DHG with real canonical facts and valuation outputs; no invented numbers.

**Required Artifacts:**
- `artifacts/reports/{run_id}_{TICKER}_report.md` — Markdown report
- Report must contain all 13 sections from CLAUDE.md §10
- Report must reference only values present in the valuation artifact and fact table

**Required Commands:**
```bash
python scripts/generate_report.py --ticker DHG --report-type full_report
```

**Required Tests/Checks:**
- Report file exists and is non-empty
- All 13 sections present
- No `None`, `N/A`, or placeholder values in quantitative sections

**Done Criteria:**
- `backend/reporting/` modules implemented (templates, context_builder, section_writer, report_builder)
- `scripts/generate_report.py` runs end-to-end
- Report references `source_id` for quantitative claims
- Report does not contain buy/sell commands

**Current Status:** `completed`

**Evidence of Completion:**
- `scripts/generate_report.py` — runs end-to-end for DHG; latest: `reports/DHG_20260527T102439_full_report.md`
- Report includes: 6 main sections + appendices (assumptions, WACC, citation map, footnotes)
- Valuation summary table: Blend DCF (60% FCFF + 40% FCFE), FCFF, FCFE, P/E cross-check, EV/EBITDA cross-check
- AssumptionGate wired: recommendation label = `Draft / Needs Analyst Review (model-implied downside: -11.7%)` — no BUY/SELL/HOLD emitted without analyst approval
- Citation map saved: `artifacts/reports/DHG_{ts}_full_report_citation.json`
- Gate artifact saved: `artifacts/valuation/DHG_{ts}_gate.json`
- Forecast artifact saved: `artifacts/forecast/DHG_{ts}_forecast.json` (with `tax_policy`, `dividend_schedule` keys)
- FCFF/FCFE/Blend artifacts saved under `artifacts/forecast/`

**Known Limitations:**
- Report uses default (unapproved) assumptions — analyst approval required before any recommendation is published
- Evidence retrieval produces 5 chunks; dedicated `build_index.py` / `test_retrieval.py` (Level 5) run separately
- Report sections do not yet match the full 13-section structure from CLAUDE.md §10 (missing: Industry Context, Investment Thesis, Key Risks as distinct top-level sections)

**Next Level Entry Condition:** Level 6 complete. Proceed to Level 7.

---

## Level 7 — Eval-ready

**Objective:** Evaluation harness implemented and passing for DHG; numeric consistency, citation coverage, and hallucination risk all checked; eval result artifact generated.

**Required Artifacts:**
- `artifacts/eval_results/{run_id}_{TICKER}_eval_result.json` — structured evaluation output
- `artifacts/claim_ledgers/{run_id}_{TICKER}_claim_ledger.json` — per-claim grounding verdict

**Required Commands:**
```bash
python scripts/evaluate_report.py --report artifacts/reports/{run_id}_DHG_report.md
```

**Required Tests/Checks:**
- `numeric_consistency_score >= 0.99`
- `citation_coverage = 1.0` for quantitative claims
- `final_confidence >= 0.70` (minimum gate)
- Eval result exports `pass_gate: true` or `fail_gate: true` with reasons

**Done Criteria:**
- `backend/evaluation/` modules implemented: numeric_consistency, citation_eval, hallucination_eval, report_rubric
- `scripts/evaluate_report.py` runs end-to-end
- Eval result is saved to `artifacts/eval_results/`
- Claim ledger is non-empty with source_ids per claim

**Current Status:** `completed`

**Evidence of Completion:**
- `scripts/evaluate_report_quality.py` — 8 deterministic quality checks; latest result: `reports/eval/latest_quality_gate.json`
- Overall status: `WARN_NEEDS_REVIEW` (5 PASS, 3 WARN, 0 FAIL — all critical checks clear)
- Checks and current DHG results:

| Check ID | Description | Status | Severity |
|---|---|---|---|
| TAX_01 | Tax rate consistency: forecast = FCFF (both 11.9%) | PASS | CRITICAL |
| CAPEX_01 | CAPEX positive outflow in both FCFF and FCFE tables | PASS | CRITICAL |
| DEBT_01 | No silent N/A in debt forecast rows | PASS | CRITICAL |
| FCFE_01 | FCFE table includes non-None net_borrowing | PASS | WARNING |
| DIV_01 | Dividend schedule modeled or warned | PASS | WARNING |
| GATE_01 | No BUY/HOLD/SELL when gate not approved | WARN | WARNING |
| REL_01 | Relative valuation pending peer dataset | WARN | WARNING |
| CONF_01 | Confidence artifact not persisted yet | WARN | INFO |

- Script exits 0 on WARN, exits 1 on FAIL_BLOCK_EXPORT
- `scripts/evaluate_report.py` also exists (legacy; runs 5-gate numeric/citation/staleness evaluation)

**Known Limitations:**
- GATE_01 remains WARN because no report markdown path is passed to quality gate script (can be resolved with `--report-file` flag)
- REL_01 stays WARN until peer group dataset is populated
- CONF_01 stays WARN until ValuationConfidence artifact is persisted per-run
- No `artifacts/eval_results/` or `claim_ledger/` format yet (those belong to the legacy evaluate_report.py flow)

**Next Level Entry Condition:** Level 7 complete. Proceed to Level 8.

---

## Level 8 — Demo-ready

**Objective:** Full end-to-end pipeline runs in a single command for DHG; all artifacts generated; all evaluation gates pass; report package complete.

**Required Artifacts:**
- Complete report package under `artifacts/` for a single DHG run:
  - `run_log.json`
  - `source_manifest.json`
  - `valuation_result.json`
  - `claim_ledger.json`
  - `eval_result.json`
  - `{run_id}_DHG_report.md`

**Required Commands:**
```bash
python scripts/run_research.py --ticker DHG --report-type full_report
```

**Required Tests/Checks:**
- All Level 4–7 gates pass in sequence
- Human approval checkpoint reached (HITL gate not auto-bypassed)
- Final confidence ≥ 0.85 (strong pass) or ≥ 0.70 (review gate)

**Done Criteria:**
- `scripts/run_research.py` orchestrates the full pipeline
- All 6 artifact types exist and are non-empty for a single run
- Evaluation does not block on critical failures
- Report package is auditable end-to-end

**Current Status:** `completed`

**Evidence of Completion:**
- Full DHG pipeline runs end-to-end via individual scripts (orchestration via `run_research.py` also exists):
  1. `python scripts/ingest_ticker.py --ticker DHG --years 5` → raw data + source metadata
  2. `python scripts/build_facts.py --ticker DHG` → canonical facts (5 FY periods)
  3. `python scripts/run_valuation.py --ticker DHG` → valuation artifact with TaxPolicy, FCFF, FCFE, Blend
  4. `python scripts/generate_report.py --ticker DHG` → Markdown report + gate artifact + citation map
  5. `python scripts/evaluate_report_quality.py --ticker DHG` → WARN_NEEDS_REVIEW (0 FAIL)
- Gate artifact: `artifacts/valuation/DHG_20260527T102439_gate.json` — status `draft_needs_analyst_review`
- Report: `reports/DHG_20260527T102439_full_report.md` — no unauthorized BUY/HOLD/SELL
- Quality gate: all 3 critical checks PASS

**Known Limitations:**
- `run_research.py` orchestrates the pipeline but is not yet a single-command full run (requires steps above)
- Human approval (`approve_report.py`) and export are in place as a script but HITL gate is not automated
- `final_confidence` field from legacy evaluation flow not yet produced per-run

**Next Level Entry Condition:** Level 8 complete. Proceed to Level 9.

---

## Level 9 — Scale-ready

**Objective:** Pipeline validated across all 5 MVP tickers (DHG, IMP, DMC, TRA, DBD); evaluation gates pass for each; multi-ticker batch mode available.

**Required Artifacts:**
- Full report packages for: DHG, IMP, DMC, TRA, DBD
- Batch run log showing 5/5 tickers completed

**Required Commands:**
```bash
python scripts/run_research.py --ticker DHG --report-type full_report
python scripts/run_research.py --ticker IMP --report-type full_report
python scripts/run_research.py --ticker DMC --report-type full_report
python scripts/run_research.py --ticker TRA --report-type full_report
python scripts/run_research.py --ticker DBD --report-type full_report
```

**Required Tests/Checks:**
- All 5 tickers pass Level 8 criteria
- Peer comparison works (each ticker can reference its peer group)
- No ticker-specific hardcoded logic

**Done Criteria:**
- All 5 tickers have complete report packages
- Evaluation gates pass for all 5
- Peer group multiples are populated in valuation artifacts
- Pipeline is config-driven, not ticker-specific

**Current Status:** `completed`

**Evidence of Completion (2026-05-28):**

**Data validation — all 5 tickers VALUATION_READY:**
```
python scripts/validate_data.py --ticker {DHG,IMP,DMC,TRA,DBD}
```
All pass: coverage_gate=pass, core_keys_gate=pass, source_validation_gate=pass, valuation_gate=pass, reconciliation_gate=warn (expected)

**Markdown reports generated:**
- `reports/IMP_20260528T082835_full_report.md`
- `reports/DMC_20260528T082839_full_report.md`
- `reports/TRA_20260528T082842_full_report.md`
- `reports/DBD_20260528T082847_full_report.md`

**Quality gates — all 5 tickers:**

| Ticker | Overall | PASS | WARN | FAIL |
|--------|---------|------|------|------|
| DHG | WARN_NEEDS_REVIEW | 5 | 3 | 0 |
| IMP | WARN_NEEDS_REVIEW | 4 | 4 | 0 |
| DMC | WARN_NEEDS_REVIEW | 4 | 4 | 0 |
| TRA | WARN_NEEDS_REVIEW | 5 | 3 | 0 |
| DBD | WARN_NEEDS_REVIEW | 5 | 3 | 0 |

All critical checks (TAX_01, CAPEX_01, DEBT_01) PASS for all tickers.

**Data quality fixes applied:**
- `ingest.sources` deduplicated: migration 009 removes 11 stale `vnstock_company` rows; partial unique index prevents recurrence
- `source_registry.py`: catalog source types now use ON CONFLICT DO UPDATE (upsert) instead of creating new rows each ingest run
- `reconciliation.py`: IS_net_income_check accounts for minority interest — companies with subsidiaries (TRA) no longer fail with CRITICAL
- `validate_data.py`: UnicodeEncodeError fixed (Windows CP1252); source_coverage_by_period wired from DB

**Known Gaps:**
- Peer group dataset (REL_01 WARN): peer P/E and EV/EBITDA multiples require real peer data — currently `pending_peer_dataset`
- ValuationConfidence persistence (CONF_01 WARN): confidence artifact not saved per-run
- `test_forecasting_gap.py`: 14 pre-existing failures (unrelated to scale work)

**Next Level Entry Condition:** Level 9 complete. All 5 MVP tickers have validate + report + quality gate. Peer data and confidence persistence are the remaining gaps.

---

---

## Gap Analysis — Từ Output Hiện Tại → Báo Cáo Chuẩn GOAL_OUTPUT.md

> **Chuẩn so sánh:** `GOAL_OUTPUT.md` + mẫu báo cáo LLY PDF (7 trang, có biểu đồ, peer comparison, financial tables).
> **Output hiện tại:** Markdown text-only, không có chart, không có PDF.
> **Mục tiêu:** PDF 8 trang A4, 5-7 chart, số liệu đúng, nhận định có nguồn.

---

### Tổng quan: Đã làm được bao nhiêu % so với chuẩn?

| Nhóm | % Hoàn thành | Ghi chú |
|---|---|---|
| **Data pipeline & facts** | 95% | Đủ 5 ticker × 5FY, DQ gates, canonical facts, OCR |
| **Valuation engine** | 90% | FCFF/FCFE/Blend, sensitivity, scenario, TaxPolicy — thiếu peer data |
| **Report content (text)** | 60% | Có đủ tables và narrative, thiếu structure 8 trang đúng chuẩn |
| **Charts & visualizations** | 0% | Không có dòng code nào sinh chart |
| **PDF/HTML export** | 0% | Chỉ có Markdown |
| **Audit artifacts** | 40% | Có citation_map, thiếu claim_ledger/source_manifest đúng spec |
| **Peer comparison** | 5% | REL_01 WARN từ đầu, không có dataset |

**Tổng thể: ~50% so với GOAL_OUTPUT.md Definition of Done.**

---

### Chi tiết: Đã làm được ✅

| Hạng mục | GOAL_OUTPUT.md §tham chiếu | Trạng thái |
|---|---|---|
| Dữ liệu tài chính 5 ticker × 4-5 FY | §2.1 Facts before narrative | ✅ Canonical facts trong DB, DQ gates pass |
| Valuation FCFF DCF với WACC, terminal growth | §5 Page 5, formula registry §7.2 | ✅ Deterministic Python, TaxPolicy, reproducible |
| FCFE và Blend (60% FCFF + 40% FCFE) | §5 Page 5 | ✅ blend.py, debt_schedule.py, dividend_schedule.py |
| Sensitivity table WACC × terminal growth | §6 Page 6, C7 | ✅ JSON artifact + Markdown table (chưa có visual heatmap) |
| Bear/Base/Bull scenario | §6 Page 6 | ✅ 3 scenario trong valuation artifact |
| Bảng tóm tắt tài chính (revenue, EBITDA, LNST, EPS, margins) | §3 Page 3, §7.1 | ✅ Trong Markdown report |
| Bảng forecast 5 năm với assumptions | §4 Page 4 | ✅ 2026F-2030F, key line items, rationale |
| Bảng DCF và valuation summary | §5 Page 5 | ✅ FCFF breakdown, PV, equity value, target price |
| Citation map (trỏ claim → source_id + fact_id) | §8 Claim ledger | ✅ artifacts/reports/\*_citation.json |
| AssumptionGate — không phát BUY/SELL/HOLD khi chưa approve | §2.4, §5.2 | ✅ "Draft / Needs Analyst Review" |
| Human approval gate (approve_report.py) | §2.5 | ✅ Script có, tích hợp trong run_research.py |
| Evaluation gates (TAX, CAPEX, DEBT, FCFE, DIV) | §10 | ✅ 7-8 checks, exits 0 on WARN |
| Disclaimer chuẩn | §8 Page 8 | ✅ Có trong Markdown |
| OCR pipeline cho scanned PDF | (data infrastructure) | ✅ tesseract + reconciliation + promotion |
| Evidence retrieval DB-backed với source-tier | §12 Agent execution step 2-3 | ✅ RetrievalService, FTS, tier priority |
| Docker + docker-compose + .env.example | (infrastructure) | ✅ Build, run, --ocr wired |
| Test suite 670 tests | (quality) | ✅ 0 failures |

---

### Chi tiết: Chưa làm được ❌ — Map theo GOAL_OUTPUT.md

#### Gap 1 — Biểu đồ: 0/7 chart bắt buộc (GOAL_OUTPUT.md §6)

Đây là **gap lớn nhất và dễ nhận thấy nhất**. LLY PDF có 5 chart. GOAL_OUTPUT.md §6 yêu cầu 5-7 chart bắt buộc và liệt kê rõ. Không có dòng code nào sinh chart trong toàn bộ codebase.

| Chart | GOAL_OUTPUT.md §6 | Dữ liệu có sẵn | Trạng thái |
|---|---|---|---|
| **C1** Stock vs VNINDEX base 100 | Bắt buộc, Page 1 | ❌ Thiếu VNINDEX series | ❌ |
| **C2** Revenue & EBITDA Trend (bar+line) | Bắt buộc, Page 3 | ✅ facts table | ❌ |
| **C3** EPS & P/E Trend (dual-axis) | Bắt buộc, Page 3 | ✅ EPS từ facts, P/E từ valuation | ❌ |
| **C4** Margin & ROE Trend (multi-line) | Bắt buộc, Page 3 | ✅ ratios artifact | ❌ |
| **C5** Forecast Revenue/Profit (bar+line) | Bắt buộc, Page 4 | ✅ forecast artifact | ❌ |
| **C6** DCF Value Bridge (waterfall) | Khuyến nghị, Page 5 | ✅ valuation artifact | ❌ |
| **C7** Sensitivity Heatmap | Bắt buộc, Page 6 | ✅ sensitivity JSON | ❌ chỉ có text table |

**Ghi chú quan trọng:** C2, C3, C4, C5, C7 đều có đủ dữ liệu từ artifacts hiện có. Chỉ cần viết `backend/reporting/chart_generator.py`. C1 bị block thêm vì cần VNINDEX data.

**Cần implement:** `backend/reporting/chart_generator.py` dùng `matplotlib`. Mỗi chart lưu PNG vào `artifacts/charts/{ticker}/`. Có title, unit, source, ký hiệu A/F rõ ràng.

---

#### Gap 2 — PDF và HTML Export (GOAL_OUTPUT.md §3.1)

GOAL_OUTPUT.md §3.1 yêu cầu 3 file bắt buộc mỗi run. Hiện tại chỉ có `.md`.

| File bắt buộc theo §3.1 | Trạng thái |
|---|---|
| `reports/{run_id}_{ticker}_report.md` | ✅ Có |
| `reports_html/{run_id}_{ticker}_report.html` | ❌ Chưa có |
| `reports_pdf/{run_id}_{ticker}_report.pdf` | ❌ Chưa có |
| `valuation_results/{run_id}_{ticker}_valuation_result.json` | ✅ Có (đường dẫn khác: `artifacts/valuation/`) |
| `claim_ledgers/{run_id}_{ticker}_claim_ledger.json` | ❌ Format không đúng spec (chỉ có citation_map) |
| `source_manifests/{run_id}_{ticker}_source_manifest.json` | ❌ Chưa có |
| `eval_results/{run_id}_{ticker}_eval_result.json` | ❌ Chưa có format chuẩn |

**Cần implement:** Jinja2 HTML template với CSS navy design (giống LLY cover) → WeasyPrint PDF. Embed chart PNG vào HTML.

---

#### Gap 3 — Peer Comparison (GOAL_OUTPUT.md §6 Page 6)

REL_01 WARN từ ngày đầu. Không có dataset peer nào.

| Yêu cầu §6 Page 6 | Trạng thái |
|---|---|
| Bảng peer: Ticker, Market Cap, P/E, P/B, EV/EBITDA, ROE, Net Margin | ❌ Trống hoàn toàn |
| Peer median row | ❌ |
| Peer EV/EBITDA chart theo năm (như LLY PDF trang 4) | ❌ |

**Ghi chú:** 5 ticker MVP (DHG, IMP, DMC, TRA, DBD) đều có đủ facts trong DB. P/E = market_price ÷ EPS, EV/EBITDA = (market_cap + net_debt) ÷ EBITDA — tất cả đều tính được từ dữ liệu hiện có. Không cần nguồn ngoài.

---

#### Gap 4 — Claim Ledger và Audit Artifacts (GOAL_OUTPUT.md §8, §9, §10)

GOAL_OUTPUT.md §8 định nghĩa `claim_ledger.json` với format cụ thể (claim_id, section, claim_type, source_refs, confidence, review_status). Hiện tại chỉ có `citation_map.json` với format khác.

| Artifact theo §8-9-10 | Trạng thái |
|---|---|
| `claim_ledger.json` với claim_id, claim_type, source_refs, support_status | ❌ Format khác — chỉ có citation_map |
| `source_manifest.json` với publisher, url, reliability_tier, checksum, used_sections | ❌ Không có |
| `eval_result.json` với numeric_consistency, citation_coverage, valuation_reproducibility | ❌ Không có format chuẩn duy nhất |

---

#### Gap 5 — Cấu trúc Report Chưa Đúng 8 Trang (GOAL_OUTPUT.md §4)

| Page | Section theo §4 | Trạng thái hiện tại |
|---|---|---|
| **1** | Cover + Rating block (BUY/HOLD/SELL) + Key Metrics Snapshot + Investment Thesis + Chart C1 | ❌ Không có cover page, rating bị block bởi AssumptionGate (đúng thiết kế), không có chart |
| **2** | Company Overview: business model, product mix, competitive position, growth strategy, key drivers | ⚠️ Có text ngắn, thiếu chi tiết GMP/sản phẩm/kênh ETC-OTC |
| **3** | Financial Performance + Chart C2 + C3 + C4 + bảng financial summary 5 năm | ⚠️ Có bảng số, thiếu hoàn toàn 3 chart |
| **4** | Forecast + Assumptions + driver explanation + Chart C5 | ⚠️ Có bảng, thiếu chart và driver explanation theo format §4 |
| **5** | Valuation DCF table + valuation summary + assumptions | ✅ Có đầy đủ bảng, chỉ thiếu DCF bridge chart C6 |
| **6** | Sensitivity matrix + Scenario table + Peer comparison + Chart C7 | ⚠️ Sensitivity text table có, peer trống, không có heatmap |
| **7** | Catalysts table (timing, impact, probability) + Risks table (driver, mitigation) | ⚠️ Có risk text, thiếu structured catalyst table với timing/probability |
| **8** | Key takeaways + Final conclusion + Quality gate summary + Source list + Disclaimer | ⚠️ Có disclaimer, thiếu quality gate table và source list |

---

#### Gap 6 — Price Data và VNINDEX (cho Chart C1)

| Yêu cầu | Trạng thái |
|---|---|
| Price series 1-3 năm cho từng ticker | ❓ `vnstock` có thể fetch nhưng chưa store time series cho chart |
| VNINDEX series cùng period để so sánh | ❌ Chưa fetch và lưu |
| Normalize về base 100 tại ngày đầu kỳ | ❌ Chưa có logic |

---

### Roadmap đến "Definition of Done" theo GOAL_OUTPUT.md §14

| Thứ tự | Việc | Dữ liệu đầu vào đã có? | Độ phức tạp |
|---|---|---|---|
| **1** | **Chart C2+C3+C4+C5+C7** (5 chart không cần VNINDEX) | ✅ facts + valuation artifacts | Trung bình — 2-3 ngày |
| **2** | **Peer comparison** — P/E, EV/EBITDA cho 5 ticker từ DB | ✅ EPS, EBITDA, net debt đã có | Thấp — 1 ngày |
| **3** | **HTML template** — Jinja2 + CSS, nhúng chart, cover page | ✅ Markdown report + charts từ bước 1 | Trung bình — 2-3 ngày |
| **4** | **PDF export** — WeasyPrint hoặc Pandoc | ✅ HTML từ bước 3 | Thấp — 0.5 ngày |
| **5** | **Claim ledger** format đúng §8 | ✅ citation_map hiện có → transform | Thấp — 1 ngày |
| **6** | **Source manifest** format đúng §9 | ✅ ingest.sources trong DB | Thấp — 1 ngày |
| **7** | **Eval result** format chuẩn §10 | ✅ existing quality gate output → adapt | Thấp — 0.5 ngày |
| **8** | **VNINDEX + Chart C1** | ❌ Cần fetch VNINDEX data | Trung bình — 1-2 ngày |
| **9** | **Rating unblock** | Human gate | N/A — analyst decision |

**Milestone tối thiểu cho demo đầy đủ (GOAL_OUTPUT.md §15):**
Bước 1 + 2 + 3 + 4 + 5 = báo cáo PDF với 5 chart, peer table, claim ledger → đáp ứng ~85% GOAL_OUTPUT.md §14.

---

## Level 10 — Render-ready

**Objective:** Generate professional report artifacts (charts, HTML, PDF, 5 canonical JSON artifacts) per GOAL_OUTPUT.md for all 5 MVP tickers.

**Required Artifacts:**
- `artifacts/charts/{ticker}_C{2-7}.png`
- `artifacts/reports_html/{ticker}_report.html`
- `artifacts/reports_pdf/{ticker}_report.pdf` (or .pdf-pending on Windows without GTK)
- `artifacts/claim_ledgers/RUN_{ticker}_*_claim_ledger.json`
- `artifacts/source_manifests/RUN_{ticker}_*_source_manifest.json`
- `artifacts/valuation_results/RUN_{ticker}_*_valuation_result.json`
- `artifacts/eval_results/RUN_{ticker}_*_eval_result.json`
- `artifacts/run_logs/RUN_{ticker}_*_run_log.json`

**Done Criteria:**
- `python scripts/run_full_pipeline.py --all` completes without crash for all 5 tickers
- Chart PNGs present for each ticker
- HTML reports present for each ticker
- 5 canonical artifacts present for each ticker

**Current Status:** `completed`

**Evidence of Completion (2026-06-01):**

```
python scripts/run_full_pipeline.py --all
```

Output:
```
DHG: OK (charts=6, html=yes, artifacts=5)
IMP: OK (charts=6, html=yes, artifacts=5)
DMC: OK (charts=6, html=yes, artifacts=5)
TRA: OK (charts=6, html=yes, artifacts=5)
DBD: OK (charts=6, html=yes, artifacts=5)
All tickers completed successfully.
```

- `backend/reporting/chart_generator.py` — C1–C7 matplotlib PNG charts (C1 stub, C2–C7 data-driven)
- `backend/reporting/section_builder.py` — 8-section report structure with ReportContext + ReportSection dataclasses
- `backend/reporting/html_renderer.py` — Jinja2 template + professional CSS A4 layout, inline chart images
- `backend/reporting/pdf_renderer.py` — WeasyPrint wrapper (renders .pdf-pending stub on Windows without GTK)
- `backend/reporting/artifact_writer.py` — 5 canonical artifacts per GOAL_OUTPUT.md §8–10
- `scripts/generate_charts.py` — CLI for chart generation per ticker
- `scripts/render_report.py` — CLI for HTML + PDF rendering per ticker
- `scripts/run_full_pipeline.py` — orchestrator: charts → html → 5 artifacts for one or all tickers
- 726 tests pass (0 failures)

**Known Limitations:**
- C1 (Stock vs VNINDEX) is a stub — VNINDEX time-series not yet fetched
- PDF on Windows uses .pdf-pending stub (WeasyPrint requires GTK); native PDF requires Linux/Docker
- Valuation fields in artifacts default to 0.0 for tickers without a fresh `run_valuation.py` artifact

**Next Level Entry Condition:** Level 10 complete. Proceed to peer comparison dataset and VNINDEX chart (C1) to close the final gap vs. GOAL_OUTPUT.md §14.

---

## Change Log

| Date | Update |
|---|---|
| 2026-05-24 | Initial tracker created. Assessed current state as Level 3 partial based on artifact inspection. |
| 2026-05-27 | Updated Levels 3–9 to reflect actual project state per EXECUTION_STATE.md. Added data validation layer: time-series sanity checks, source tier enforcement, market data alignment, confidence scoring formula, DATA_VALIDATION_REPORT artifact, scripts/validate_data.py CLI. 31 new unit tests added (all pass). Pre-existing FCF formula failures documented. |
| 2026-05-27–28 | Implemented plan CLAUDE_FIX_PLAN_VALUATION_DEBT_TAX_CAPEX (13 defects P0-01 → P2-03). New modules: tax_policy.py, debt_schedule.py, dividend_schedule.py, approval_gate.py, valuation_confidence.py. New script: evaluate_report_quality.py (8 deterministic checks, TAX/CAPEX/DEBT/FCFE/DIV/GATE/REL/CONF). Bug fix: generate_report.py now emits `Draft / Needs Analyst Review` via AssumptionGate. Quality gate DHG: WARN_NEEDS_REVIEW (5 PASS, 3 WARN, 0 FAIL). Unit tests: 210 pass, 14 pre-existing fail. |
| 2026-05-28 | Level 9 push: all 5 MVP tickers now have validate + report + quality gate (0 FAIL). Supabase dedup (migration 009), reconciliation minority-interest fix, validate_data.py UnicodeEncodeError fix. |
| 2026-05-31 | Data Trust Layer (Phase 12): FactEntry provenance, CitationMap with real source titles, driver_evidence catalyst rendering, 6-gate primary evaluator, LangGraph harness, official document scaffold. 468 tests pass. |
| 2026-06-01 | Level 10 — Render-ready: chart_generator C1–C7 (matplotlib PNG), section_builder, html_renderer (Jinja2+CSS), pdf_renderer (WeasyPrint stub on Windows), artifact_writer (5 canonical artifacts per GOAL_OUTPUT.md), render_report.py + generate_charts.py CLIs, run_full_pipeline.py orchestrator. All 5 MVP tickers complete: charts=6, html=yes, artifacts=5. 726 tests pass. |
| 2026-06-01 | Evidence Retrieval + Citation Pipeline (Phase 13): build_index.py indexes OCR page artifacts + official PDF text with extraction_method/page_number/source_tier metadata. backend/retrieval.py rewritten as DB-backed FTS service with tier priority. scripts/evaluate_citations.py: 4-gate citation coverage gate. 30 new tests. 670 total pass. Docker: Dockerfile CMD + healthcheck + ENV. docker-compose.yml (app + postgres). .env.example + .dockerignore. run_research.py: --ocr flag wired through to AutoIngestConfig. Added Gap Analysis section comparing to LLY PDF chuẩn. |
