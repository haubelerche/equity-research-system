---
name: financial-evaluation
description: Use this skill when implementing, auditing, debugging, or reviewing financial calculations, valuation logic, equity research assumptions, forecast models, sensitivity analysis, and numeric consistency for the Vietnam Pharma Equity Research project.
---

# Financial Evaluation Skill

## 1. Purpose

This skill governs all work related to financial validation, valuation logic, forecasting, equity research quality control, deterministic financial computation, and numeric consistency in the Vietnam Pharma Multi-Agent Equity Research project.

The core responsibility is to ensure that the system produces **auditable, reproducible, financially coherent valuation artifacts** before any narrative report is generated.

This project must not behave like a generic LLM report writer. It must behave like a controlled equity research workflow:

```text
raw data -> normalized data -> canonical facts -> ratios -> forecast -> valuation artifacts -> sensitivity -> evaluation gates -> grounded report -> human approval
```

## 2. When to Use This Skill

Use this skill for any task involving:

- financial ratio calculation
- DCF valuation
- FCFF / FCFE computation
- WACC, Re, terminal growth, terminal value
- P/E, EV/EBITDA, P/B, P/S valuation
- forecast assumptions
- revenue, margin, CAPEX, working capital, debt, EPS forecast
- sensitivity analysis
- valuation warning rules
- financial model QA
- numeric consistency checks in reports
- code changes under valuation, analytics, ratios, forecast, report tables, or evaluation modules
- bug fixes where incorrect numbers, signs, periods, units, or formulas are suspected

Do not use this skill for generic copywriting, UI styling, non-financial backend plumbing, or unrelated infrastructure tasks.

## 3. Minimum Context to Read

Read only the minimum necessary context. Do not load the entire repository.

### Required project truth

Read these first if present:

1. `PRD.md`
2. `PROBLEM-BRIEF.md`
3. `AI Product Spec Dự Án.txt`

### Required financial formula truth

Read these when available:

1. `Cam_nang_dinh_gia_60_FCFF_40_FCFE_ban_sach.md`
2. `Huong_dan_danh_gia_sensitivity_analysis.md`
3. `FORMULA_FINANCE.md`
4. Any formula dictionary, valuation contract, or financial schema file in the repository

### Relevant implementation files

Use targeted search for:

```text
valuation
dcf
fcff
fcfe
wacc
cost_of_equity
terminal
sensitivity
ratio
eps
ebitda
market_cap
enterprise_value
peer
forecast
report
```

Likely files or directories:

```text
backend/analytics/
backend/valuation/
backend/forecast/
backend/reporting/
backend/evaluation/
backend/models/
backend/schemas/
scripts/generate_report.py
tests/
```

If a file does not exist, do not invent it. Report the absence and work with the actual repository structure.

## 4. Source of Truth Priority

Use this order when resolving conflicts:

1. Project PRD and problem brief
2. Approved formula documents
3. Existing financial schema and tests
4. Existing implementation behavior
5. User task instruction
6. General finance knowledge

If formula documents conflict with code, treat the code as suspect until verified by tests or explicit project decision.

## 5. Non-Negotiable Rules

### 5.1 Deterministic calculation

LLM must not invent, directly calculate, or silently modify final financial facts.

All final values must come from code, structured facts, or explicit user-approved assumptions.

### 5.2 Artifact-first valuation

Valuation must produce structured artifacts before report writing.

Required artifact classes:

```text
normalized_financials
ratio_table
forecast_table
fcff_dcf_artifact
fcfe_dcf_artifact
dcf_blend_artifact
relative_valuation_artifact
sensitivity_artifact
financial_evaluation_report
warnings
```

The report writer may read these artifacts but must not mutate them.

### 5.3 No mixed cash flow and discount rate

Mandatory rule:

```text
FCFF must be discounted by WACC.
FCFE must be discounted by Re / Cost of Equity.
```

Never discount FCFF using Re.
Never discount FCFE using WACC.

### 5.4 No fake precision

If input data is missing, stale, approximated, or inconsistent, the system must emit a warning or `Needs Analyst Review`.

Do not hide weak data behind polished prose.

### 5.5 Human approval for risky outputs

Any final recommendation, target price, upside/downside conclusion, or investment stance must remain draft-level until human approval.

## 6. Canonical Formula Contract

Use these formulas as the canonical baseline unless the project has a more recent approved formula file.

### 6.1 Sign conventions

```text
CAPEX_positive = ABS(CAPEX_CFS) if CAPEX_CFS < 0 else CAPEX_CFS

Interest Expense = positive value
Net Borrowing = Debt Issuance - Principal Debt Repayment
Net Debt = Interest-bearing Debt - Cash - Short-term Investments
Delta NWC = Operating NWC_t - Operating NWC_t-1
```

Critical CAPEX rule:

```text
If CAPEX_CFS is already negative:
  FCFF from CFO = CFO + Interest Expense * (1 - Tax Rate) + CAPEX_CFS
  FCFE from CFO = CFO + CAPEX_CFS + Net Borrowing

If CAPEX is normalized positive:
  FCFF from CFO = CFO + Interest Expense * (1 - Tax Rate) - CAPEX_positive
  FCFE from CFO = CFO - CAPEX_positive + Net Borrowing
```

Never do:

```text
CFO - CAPEX_CFS
```

when `CAPEX_CFS` is already negative.

### 6.2 Core income and return formulas

```text
YoY Revenue Growth = (Revenue_t - Revenue_t-1) / Revenue_t-1
YoY Net Income Growth = (NI_t - NI_t-1) / NI_t-1
CAGR = (Ending Value / Beginning Value)^(1/n) - 1

Gross Margin = Gross Profit / Revenue
EBIT Margin = EBIT / Revenue
Net Margin = Net Income / Revenue

ROA = Net Income / Average Total Assets
ROE = Net Income Attributable to Parent / Average Equity Attributable to Parent
ROIC = NOPAT / Average Invested Capital

EBIT = Profit Before Tax + Interest Expense
EBITDA = EBIT + Depreciation & Amortization
NOPAT = EBIT * (1 - Tax Rate)
```

### 6.3 Working capital and operating efficiency

```text
Operating NWC = AR + Inventory + Other Operating Current Assets
              - AP - Other Operating Current Liabilities

Delta NWC = Operating NWC_t - Operating NWC_t-1

DSO = Average Accounts Receivable / Revenue * 365
DIO = Average Inventory / COGS * 365
DPO = Average Accounts Payable / COGS * 365
Cash Conversion Cycle = DSO + DIO - DPO
```

### 6.4 FCFF DCF

```text
FCFF = EBIT * (1 - Tax Rate) + D&A - CAPEX_positive - Delta NWC
FCFF_from_CFO = CFO + Interest Expense * (1 - Tax Rate) - CAPEX_positive
WACC = E/(D+E) * Re + D/(D+E) * Rd * (1 - Tax Rate)
Terminal Value FCFF = FCFF_N * (1 + g) / (WACC - g)
EV_FCFF = SUM(FCFF_t / (1 + WACC)^t) + TV_FCFF / (1 + WACC)^N
Equity Value_FCFF = EV_FCFF - Net Debt - Minority Interest + Non-operating Assets
Price_FCFF = Equity Value_FCFF / Diluted Shares Outstanding
```

Validation:

```text
WACC > g
Discount rate must be WACC
FCFF terminal year must be normalized
EV must be bridged to Equity Value before Price_FCFF
```

### 6.5 FCFE DCF

```text
FCFE = Net Income + D&A - CAPEX_positive - Delta NWC + Net Borrowing
FCFE_from_CFO = CFO - CAPEX_positive + Net Borrowing
Re = Rf + Beta * Equity Risk Premium + Size Premium + Liquidity Premium + Country Risk Premium
Terminal Value FCFE = FCFE_N * (1 + g) / (Re - g)
Equity Value_FCFE = SUM(FCFE_t / (1 + Re)^t) + TV_FCFE / (1 + Re)^N
Price_FCFE = Equity Value_FCFE / Diluted Shares Outstanding
```

Validation:

```text
Re > g
Discount rate must be Re
Do not subtract Net Debt again from FCFE equity value
FCFE terminal year must not be distorted by abnormal borrowing/repayment
```

### 6.6 Blended DCF

```text
Target Price_DCF = 0.60 * Price_FCFF + 0.40 * Price_FCFE
Equity Value_DCF = 0.60 * Equity Value_FCFF + 0.40 * Equity Value_FCFE
Upside = Target Price_DCF / Current Market Price - 1
Margin of Safety = Intrinsic Value / Market Price - 1
```

Important:

```text
Price_FCFF must already be equity-per-share.
Price_FCFE must already be equity-per-share.
Do not blend EV_FCFF with Equity Value_FCFE.
Do not subtract net debt after blending per-share prices.
```

### 6.7 Relative valuation

```text
Market Cap = Current Share Price * Shares Outstanding
EV = Market Cap + Interest-bearing Debt + Preferred Equity + Minority Interest
   - Cash & Cash Equivalents - Short-term Investments

Trailing P/E = Current Price / EPS_TTM
Forward P/E = Current Price / EPS_FY1
Target Price_PE = Target Forward P/E * EPS_FY1

EV/EBITDA = EV / EBITDA
Target EV = EBITDA_FY1 * Target EV/EBITDA
Target Price_EVEBITDA = (Target EV - Net Debt + Non-operating Assets - Minority Interest) / Diluted Shares

BVPS = Equity Attributable to Common Shareholders / Shares Outstanding
P/B = Current Price / BVPS
Target Price_PB = BVPS_FY1 * Target P/B

Sales per Share = Revenue_FY1 / Shares Outstanding
P/S = Market Cap / Revenue
Target Price_PS = SPS_FY1 * Target P/S
```

Validation:

```text
Do not compute P/E when EPS <= 0 unless clearly marked as not meaningful.
Do not compute EV/EBITDA when EBITDA <= 0 unless clearly marked as not meaningful.
Use peer median rather than average when sample is small or outlier-prone.
Peer group must match business model, sector, size, margin, growth, and liquidity as much as possible.
```

## 7. Forecast Evaluation Rules

### 7.1 Forecast must be driver-based

Forecast must not be a naked number.

Each forecast line should tie to a driver:

```text
Revenue_t = Revenue_t-1 * (1 + Revenue Growth_t)
Gross Profit_t = Revenue_t * Gross Margin_t
EBIT_t = Revenue_t * EBIT Margin_t
Tax_t = PBT_t * Tax Rate_t
D&A_t = Revenue_t * D&A/Sales or linked to fixed asset schedule
CAPEX_t = Revenue_t * CAPEX/Sales or linked to expansion plan
NWC_t = Revenue_t * NWC/Sales or line-item turnover
EPS_FY1 = Forecast Net Income_FY1 / Forecast Diluted Shares_FY1
```

### 7.2 Forecast assumptions require provenance

Each material assumption should include:

```yaml
assumption_name:
value:
unit:
period:
source_type: historical_average | management_guidance | analyst_input | peer_benchmark | macro_input | manual_override
evidence_or_reason:
confidence:
warning:
```

### 7.3 Forecast consistency checks

Check:

- revenue growth vs historical trend
- gross margin vs historical margin and peer margin
- EBIT margin vs cost structure
- tax rate vs historical effective tax and statutory tax
- CAPEX vs depreciation and expansion thesis
- NWC vs revenue growth and CCC
- debt forecast vs interest expense and net borrowing
- EPS forecast vs share count
- dividend forecast vs FCFE and payout ratio
- terminal-year FCFF/FCFE normalization

## 8. Sensitivity Analysis Contract

Sensitivity is mandatory before outputting target price.

### 8.1 Required sensitivity tables

At minimum:

```text
FCFF: WACC x terminal growth
FCFE: Re x terminal growth
Blended DCF: Price_FCFF x Price_FCFE
Relative valuation: EPS_FY1 x Target P/E
EV/EBITDA: EBITDA_FY1 x Target EV/EBITDA
```

When applicable:

```text
One-way sensitivity: revenue growth, EBIT margin, CAPEX/Sales, NWC/Sales
Scenario analysis: Bear / Base / Bull
Break-even analysis: WACC or P/E needed for market price
Tornado chart data: rank driver impact
```

### 8.2 Sensitivity warnings

```text
TV Weight = PV(Terminal Value) / Enterprise Value
Valuation Gap = Price_FCFF / Price_FCFE - 1
Elasticity = (% Change in Output) / (% Change in Input)
```

Warning thresholds:

| Condition | Severity | Required behavior |
|---|---:|---|
| WACC <= g | Critical | Return INVALID; block target price |
| Re <= g | Critical | Return INVALID; block target price |
| CAPEX_CFS < 0 and formula uses CFO - CAPEX_CFS | Critical | Block valuation; fix sign convention |
| Terminal value weight > 85% | Critical | Mark valuation unreliable without stronger evidence |
| Terminal value weight > 70% | High | Add warning and require sensitivity discussion |
| abs(Price_FCFF / Price_FCFE - 1) > 25% | High | Require audit of net borrowing, net debt, CAPEX, NWC |
| FCFE negative for extended forecast horizon | High | Prefer FCFF and label FCFE as cautionary |
| Target P/E has no valid peer group | High | Do not use P/E target as valuation anchor |
| EPS <= 0 with P/E valuation | High | Mark P/E as not meaningful |
| EBITDA <= 0 with EV/EBITDA valuation | High | Mark EV/EBITDA as not meaningful |
| Base case outside peer range | Medium | Require explicit premium/discount rationale |
| Missing market price date or shares date | Medium | Mark output as stale or incomplete |
| Default assumptions with empty warnings | Medium | Force warning generation |

## 9. Financial Evaluation Procedure

Follow this sequence when auditing or implementing any valuation logic.

### Step 1. Identify task type

Classify as one or more:

```text
ratio_calculation
forecast_model
fcff_dcf
fcfe_dcf
dcf_blend
relative_valuation
sensitivity_analysis
report_numeric_consistency
bug_fix
test_creation
```

### Step 2. Inspect current contracts

Find schemas, dataclasses, pydantic models, SQL tables, fixtures, and tests related to the task.

Do not change formulas before understanding:

```text
input fields
units
period conventions
source lineage
output schema
existing tests
downstream consumers
```

### Step 3. Validate data prerequisites

Before calculation, check:

```text
ticker
fiscal_year / quarter
currency
unit scale
period type: annual / quarterly / TTM / forecast
source_uri / fact_id
ingested_at / effective_date
confidence
parser_version
```

### Step 4. Normalize signs and units

Normalize:

```text
CAPEX
interest expense
COGS
SG&A
tax expense
debt
cash
working capital
shares outstanding
currency unit
```

Never mix:

```text
VND and thousand VND
annual and quarterly figures
basic and diluted shares
reported EPS and normalized EPS
market price date and stale share count
```

### Step 5. Compute with deterministic code

Use pure functions where possible.

Preferred function properties:

```text
explicit input schema
explicit output schema
no hidden global state
no LLM dependency
stable rounding policy
warning list
error list
traceable formula id
```

### Step 6. Reconcile outputs

Check:

```text
subtotal vs total
FCFF from EBIT vs FCFF from CFO where both available
market cap vs price * shares
EV bridge
equity value bridge
FCFF vs FCFE spread
DCF vs relative valuation spread
forecast vs historical trend
```

### Step 7. Run sensitivity and warnings

No target price should be considered complete without sensitivity and warning generation.

### Step 8. Emit evaluation report

Output a structured evaluation report.

Required fields:

```yaml
status: pass | warn | fail | invalid
ticker:
valuation_date:
methods_checked:
critical_errors:
warnings:
assumptions_review:
formula_checks:
numeric_reconciliation:
sensitivity_summary:
peer_group_quality:
report_claim_checks:
recommended_next_action:
```

## 10. Testing Requirements

Every financial calculation change must include or update tests.

### 10.1 Unit tests

Cover normal cases and edge cases:

```text
positive CAPEX input
negative CAPEX_CFS input
zero revenue
zero or negative EPS
zero or negative EBITDA
zero denominator
negative net debt
negative net borrowing
missing debt data
missing share count
quarterly vs annual period mismatch
unit mismatch
WACC <= g
Re <= g
terminal value weight > 70%
FCFF/FCFE gap > 25%
```

### 10.2 Regression tests

Add tests for previously fixed bugs.

The test name should encode the failure:

```text
test_fcfe_does_not_subtract_negative_capex_cfs_twice
test_fcff_uses_wacc_not_re
test_fcfe_uses_re_not_wacc
test_ev_to_equity_bridge_subtracts_net_debt_once
test_pe_is_invalid_when_eps_negative
test_terminal_value_invalid_when_growth_exceeds_discount_rate
```

### 10.3 Golden tests

For key tickers or sample fixtures, maintain golden expected outputs:

```text
ratio_table
forecast_table
fcff_dcf_artifact
fcfe_dcf_artifact
dcf_blend_artifact
sensitivity_artifact
financial_evaluation_report
```

Use tolerance-based comparisons for floating-point values.

Suggested tolerances:

```text
ratios: 1e-4 absolute or 0.01 percentage point when displayed
currency: <= 1 VND for raw deterministic values, or defined rounding tolerance
percentages: <= 0.01 percentage point after formatting
valuation per share: project-defined tolerance based on unit scale
```

### 10.4 Property-style checks

Where practical, assert financial invariants:

```text
higher WACC lowers FCFF valuation if all else equal
higher Re lowers FCFE valuation if all else equal
higher terminal growth increases valuation when g < discount rate
higher CAPEX lowers FCFF and FCFE if all else equal
higher net borrowing increases FCFE but should raise warning if unsustainable
higher net debt lowers FCFF-derived equity value
```

## 11. Report Numeric Consistency Checks

When reviewing generated report content, verify:

- every quantitative claim maps to a structured fact or valuation artifact
- numbers in text equal numbers in tables after rounding
- units are consistent
- periods are explicit
- forecast vs actual are clearly labeled
- trailing P/E and forward P/E are not confused
- target price, upside, and recommendation use the same market price snapshot
- sensitivity warnings appear in the valuation section
- assumptions are visible before recommendation
- unresolved critical warnings block final publish

The report must not state a confident conclusion when the underlying evaluation status is `invalid`, `fail`, or unresolved `high`.

## 12. Common Failure Modes

Actively look for these:

1. CAPEX sign inversion.
2. FCFE discounted by WACC.
3. FCFF discounted by Re.
4. FCFE equity value incorrectly subtracts net debt again.
5. EV/EBITDA target price computed by dividing EV directly by shares without net debt bridge.
6. P/E used with negative EPS.
7. Peer average used despite outliers.
8. Terminal growth greater than discount rate.
9. Terminal value dominates valuation without warning.
10. Forecast margin improves without thesis or evidence.
11. Revenue growth assumption inconsistent with historical trend and sector context.
12. Working capital grows in the wrong direction relative to revenue.
13. Net borrowing treated as recurring when it is one-off.
14. Quarterly figures mixed with annual figures.
15. VND, thousand VND, million VND, and billion VND mixed silently.
16. Basic shares mixed with diluted shares.
17. Market price date not aligned with share count and market cap.
18. Report text uses stale or unapproved valuation artifact.
19. LLM-generated numbers enter the valuation artifact.
20. Warning list is empty despite default assumptions.

## 13. Implementation Style

Prefer small, deterministic, testable functions.

Recommended design:

```python
def compute_fcff(inputs: FCFFInputs) -> FCFFResult:
    ...

def compute_fcfe(inputs: FCFEInputs) -> FCFEResult:
    ...

def compute_wacc(inputs: WACCInputs) -> WACCResult:
    ...

def compute_dcf_blend(inputs: DCFBlendInputs) -> DCFBlendResult:
    ...

def evaluate_valuation_artifact(artifact: ValuationArtifact) -> FinancialEvaluationReport:
    ...
```

Each result should include:

```yaml
value:
unit:
formula_id:
inputs_used:
warnings:
errors:
source_fact_ids:
assumptions_used:
```

## 14. Output Format When Using This Skill

When completing a task using this skill, respond with:

```markdown
## Financial Evaluation Summary

### Task
<what was evaluated or changed>

### Files Inspected
<short list>

### Files Changed
<short list, if any>

### Formula/Logic Decisions
<which formulas were applied and why>

### Validation Result
- Status: PASS | WARN | FAIL | INVALID
- Critical errors:
- Warnings:
- Tests run:

### Financial Risks Remaining
<what still needs analyst review>

### Next Action
<minimal next step>
```

For bug fixes, include:

```markdown
### Root Cause
<exact bug>

### Fix
<minimal patch>

### Regression Test
<test added/updated>
```

For implementation tasks, include:

```markdown
### Acceptance Criteria Checked
- [ ] deterministic calculation
- [ ] source/fact lineage preserved
- [ ] unit and period handling checked
- [ ] sign convention checked
- [ ] edge cases tested
- [ ] sensitivity/warnings generated
- [ ] report downstream compatibility checked
```

## 15. Hard Stop Conditions

Stop and ask for clarification or mark `Needs Analyst Review` if:

- formula source conflicts and no project decision exists
- required financial input is missing
- units cannot be determined
- fiscal period cannot be determined
- source lineage is missing for material values
- WACC/Re/g assumptions are unsupported
- peer group is empty or invalid for relative valuation
- critical warnings are unresolved
- user requests guaranteed investment recommendation
- user asks to manipulate valuation to reach a desired target price

## 16. Acceptance Criteria for This Skill

A task using this skill is successful only if:

- final numbers are produced by deterministic code or approved structured inputs
- all material formulas are explicit
- all discount rates match cash flow type
- all sign conventions are checked
- all valuation outputs include warnings/errors
- sensitivity analysis exists for target price
- report numeric claims can be reconciled to artifacts
- tests cover normal and edge cases
- unresolved financial risks are clearly disclosed
- no autonomous investment advice is generated
