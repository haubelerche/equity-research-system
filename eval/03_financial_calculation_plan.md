# Financial Calculation Evaluation Plan

## Context

Mo hinh tai chinh la lop co rui ro cao nhat ve product liability. Repo da co nhieu module deterministic trong `backend/analytics/`, shared governance trong `backend/evaluation/governance.py`, gates trong `backend/evaluation/numeric_consistency.py`, `backend/evaluation/report_quality.py`, `backend/harness/gates.py`, valuation method policy trong `backend/valuation_method_policy.py`, va test trong `tests/unit/test_dcf.py`, `test_ratios.py`, `test_debt_schedule.py`, `test_sensitivity.py`, `test_export_gate.py`, `test_valuation_workings.py`, `tests/evaluation/test_client_final_governance.py`.

## Problem Statement

LLM-as-judge khong duoc phep xac nhan cong thuc tai chinh. Moi phep tinh phai duoc kiem bang invariant deterministic, golden fixture, formula trace va reconciliation bridge. Neu finance evaluation fail, report phai bi block truoc khi den lop narrative.

## Technical Deep-Dive

### 0. Current implementation alignment

| Logic hien tai | Dieu chinh trong ke hoach |
|---|---|
| `governance.py` quy dinh real decomposition line, bridge validity, forecast sanity va valuation reproduction | Finance eval phai reuse issue codes nhu `profit_growth_requires_bridge`, `sga_decline_requires_bridge`, `weighted_target_price_not_reproducible` |
| `forecast_reasonableness_gate` yeu cau pharma revenue decomposition co it nhat 2 channel va 1 product group that, khong tinh aggregate-only line | Forecast tests phai seed aggregate-only negative case |
| `financial_model_integrity_gate` check BS, net debt, EPS, dividend yield va FCFF bridge | `financial_eval.json` phai expose forecast rows va valuation fields dung shape hien tai |
| `valuation_completeness_gate` yeu cau valuation bridge, WACC decomposition, EV-to-equity bridge va target price reproduction | Report/valuation plan khong duoc coi target price la publishable neu chi co summary |
| `evaluate_export_gate` sensitivity gate v2 yeu cau FCFF, FCFE va blend sensitivity matrix; old shape `sensitivity.fcff_wacc_g`, `fcfe_re_g`, `blend_grid` van duoc chap nhan | Acceptance phai block missing FCFE/blend sensitivity trong final, khong chi check FCFF matrix varies |
| `select_valuation_methods` hien mac dinh FCFF/FCFE 60/40 khi ca hai publishable va ghi excluded methods nhu DDM | Finance eval phai test selected/excluded methods va khong cho method bi excluded xuat hien nhu khuyen nghi chinh |

### 1. Doi tuong can eval

| Module | Can kiem dinh | Critical failure |
|---|---|---|
| Ratios | Formula, unit, denominator, period scope | ROE/ROA/margin sai do unit VND bn vs VND mn |
| Forecast | Driver support, margin sanity, BS balance, cash-flow consistency | Loi nhuan tang bat thuong khong co bridge |
| Working capital | AR, inventory, AP days, delta NWC | Delta NWC bi dat 0 hoac sai dau |
| Debt schedule | Short-term debt, long-term debt, net borrowing | FCFE tinh khi khong co debt schedule |
| Dividend schedule | DPS, payout, dividend yield, total return | Dividend yield bang 0 trong khi DPS duong |
| FCFF | EBIT tax, D&A, CAPEX, NWC, TV, WACC, EV-to-equity | Target price thieu bridge |
| FCFE | NI, D&A, CAPEX, NWC, net borrowing, Re | FCFE nhan la hop le khi net borrowing missing |
| Blend valuation | Method weights, FCFF/FCFE availability | Goi blended target khi FCFE blocked |
| Multiples | Peer selection, forward EPS, P/E/EV-EBITDA | Default peer multiple khong co dataset |
| Sensitivity | FCFF WACC/g, FCFE Re/g, blend grid, base-cell reconciliation, matrix variation | Missing FCFE/blend grid hoac base cell khong khop target |

### 2. Framework va cong nghe

| Cong nghe | Vai tro |
|---|---|
| `pytest` | Unit tests, regression tests, invariant tests |
| Golden artifacts | Expected valuation outputs cho DHG/DBD |
| Property-based testing, optional `hypothesis` | Sinh input bien de bat loi cong thuc o edge cases |
| Formula trace JSON | Audit tung buoc tinh va version cong thuc |
| Custom deterministic gates | Block export khi cong thuc, bridge hoac assumption fail |

### 3. Invariants bat buoc

| Invariant | Cong thuc | Severity |
|---|---|---|
| Net debt | `interest_bearing_debt - cash - short_term_investments` | Critical |
| EPS | `net_income * 1000 / diluted_shares_mn` neu NI la VND bn | Critical |
| BS balance | `assets = equity + debt + other_liabilities` trong tolerance | Critical |
| FCFF | `EBIT * (1 - tax) + D&A - CAPEX - delta_NWC` | Critical |
| FCFE | `NI + D&A - CAPEX - delta_NWC + net_borrowing` | Critical |
| EV-to-equity | `EV + cash + ST investments - debt - minority_interest` | Critical |
| Target price | `equity_value / diluted_shares` voi unit policy ro rang | Critical |
| Gordon Growth | `discount_rate > terminal_growth` | Critical |
| Sensitivity | Matrix co it nhat 2 gia tri khac nhau | Critical |
| Sensitivity base cell | Base cell cua FCFF/FCFE/blend khop target price tuong ung trong tolerance | Critical |
| Recommendation | BUY/HOLD/SELL khop upside policy | Critical neu final |

### 4. Acceptance thresholds

| Nhom | Threshold |
|---|---|
| Formula unit tests | 100% pass |
| Golden valuation drift | 0% ngoai tolerance da khai bao |
| Critical invariant failures | 0 |
| Missing formula trace for final valuation | 0 |
| Missing WACC decomposition | 0 trong final |
| Missing EV-to-equity bridge | 0 trong final |
| FCFE blocked but report mentions FCFE target | 0 |
| Missing FCFE or blend sensitivity in final export path | 0 |

### 5. Execution plan

| Tan suat | Scope | Lenh de xuat |
|---|---|---|
| Moi PR | Finance unit tests | `python -m pytest tests/unit/test_dcf.py tests/unit/test_ratios.py tests/unit/test_debt_schedule.py tests/unit/test_dividend_schedule.py tests/unit/test_sensitivity.py tests/unit/test_export_gate.py tests/unit/test_valuation_workings.py tests/evaluation/test_client_final_governance.py` |
| Moi valuation run | Numeric and report-quality finance gates | Chay `backend.evaluation.numeric_consistency` va `backend.evaluation.report_quality` tren artifacts |
| Truoc export | Package validation gate | `PACKAGE_VALIDATION_GATE` phai pass |
| Hang thang | Golden fixture refresh review | Cap nhat fixture chi khi co source chinh thuc moi |

## Strategic Recommendations

### 1. P0 actions

| Hanh dong | Ly do |
|---|---|
| Dinh nghia `financial_eval.json` | Tach ro finance failures khoi narrative failures |
| Block final khi FCFF bridge hoac WACC decomposition missing | Day la dieu kien toi thieu cua report valuation |
| Block final khi profit/EPS jump khong co bridge | Giam rui ro target price ao |
| Block final neu relative valuation khong co peer dataset | Khong cho default multiple tao cam giac chinh xac |

### 2. P1 actions

| Hanh dong | Ly do |
|---|---|
| Them property-based tests cho formula edge cases | Bat loi denominator zero, negative debt, negative cash, high growth |
| Tao valuation golden artifact versioned | So sanh sau moi refactor |
| Them model card cho tung valuation method | Ghi ro assumption, limitation, status va blocking reason |
