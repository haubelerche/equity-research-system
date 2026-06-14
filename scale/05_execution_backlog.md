# Scale Execution Backlog

## Context

Backlog nay chuyen cac ke hoach scale thanh task co thu tu. Muc tieu la mo rong 52 ticker mot cach co kiem soat, khong tao ra batch report hang loat truoc khi governance, data readiness va archetype model san sang.

## Problem Statement

Neu backlog bi sap xep sai, nhom se de dang toi uu template PDF hoac chay batch truoc khi sua data/model/gate. Thu tu dung phai di tu governance, readiness, batch control, archetype model, sau do moi den report depth va production scale.

## Technical Deep-Dive

### P0: Governance And Batch Safety

| Task | Output | Acceptance Criteria |
|---|---|---|
| Confirm fast render fail-closed | Test coverage cho `generate_fast_report` | Run chua approved khong render client-final |
| Confirm report-quality gate in export path | Gate result attached to run | `allow_export` chi khi score >= 85 va no failed gates |
| Add batch dry-run mode | `backend/batch.py --dry-run` | In selected/rejected tickers va estimated cost |
| Add ticker and segment filters | `--tickers`, `--segment`, `--exclude` | Khong can sua CSV de chay subset |
| Add readiness threshold | `--readiness-min-score` | Ticker below threshold khong submit full report |

### P1: Readiness And Pilot Expansion

| Task | Output | Acceptance Criteria |
|---|---|---|
| Build ticker readiness scanner | `ticker_readiness` artifact | Moi ticker co score va blocking reasons |
| Run MVP pilot | IMP, DMC, TRA, DBD draft runs | Co diagnostic summary cho 4 ticker |
| Classify pilot failures | Batch summary by failure taxonomy | Biet loi chinh nam o data, model, citation hay renderer |
| Improve pharma research pack | Archetype-ready pharma schema | Khong con narrative generic-only cho pharma MVP |
| Improve valuation bridge | FCFF/WACC/EV-equity bridge | Target price co the tai tinh tu artifact |

### P2: Archetype Expansion

| Task | Output | Acceptance Criteria |
|---|---|---|
| Add archetype assignment artifact | Per-ticker archetype metadata | Non-pharma khong dung pharma template |
| Add distributor model | YTC, HBH, DGW readiness | Working capital and gross spread drivers required |
| Add healthcare services model | TNH, T32, NDT readiness | Utilization, ARPU and capacity drivers required |
| Add medical equipment model | JVC, AMV, DDS readiness | FX/import/tender sensitivity required |
| Add peer selection rules | Peer engine by archetype | Peer set not only same sector label |

### P3: Production Scale

| Task | Output | Acceptance Criteria |
|---|---|---|
| Wave 2 pharma batch | 8-12 additional pharma tickers | Batch summary with cost, failures and draft outputs |
| Wave 3 long-tail pharma | Remaining pharma tickers | Each ticker has final status category |
| Wave 4 non-pharma batch | 9 non-pharma tickers | Archetype-specific draft or data-blocked result |
| Scale dashboard | Batch-level status view | Shows pass rate, failed gates, cost and latency |
| Regression suite | Tests for scale gates | New changes cannot reopen export bypass |

## Strategic Recommendations

Immediate next implementation sequence:

1. Add dry-run and filters to `backend/batch.py`.
2. Create a lightweight readiness scanner before running IMP/DMC/TRA/DBD.
3. Run the 4 ticker MVP pilot in draft-only mode.
4. Use failed gate distribution to prioritize model and evidence fixes.
5. Expand only after readiness score and report-quality diagnostics improve measurably.
