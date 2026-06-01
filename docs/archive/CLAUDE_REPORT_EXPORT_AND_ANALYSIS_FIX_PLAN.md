# Claude Code Execution Plan — Fix PDF Rendering, Chart Validity, and Analyst Narrative for Vietnam Pharma Equity Research Reports

## 0. Read This First

This file is an execution plan for Claude Code. Treat it as the single source of implementation context for fixing the current report export pipeline.

The goal is not to make the current report visually prettier first. The goal is to make the report logically correct, auditable, and export-safe before improving layout.

Do not skip phases. Do not start from visual polish. Do not allow the renderer to publish a report that contains broken Vietnamese glyphs, missing numeric values coerced to zero, invalid charts, or investment conclusions unsupported by validated data.

---

## 1. Source Materials Reviewed

Use these as the reference artifacts for this fix:

1. `DBD_report.pdf` — current generated PDF output.
2. `DBD_report.html` — current generated HTML output.
3. `mẫu 1.pdf` — Kafi-style VPB update report.
4. `mẫu 2.pdf` — VNDIRECT-style HDG update report.
5. Existing project requirements: Vietnam Pharma Equity Research Agent must be a grounded, code-first, HITL-reviewed equity research system, not an unconstrained writing bot.

Key observed pages:

- `DBD_report.pdf`: pages 1-12.
- `DBD_report.html`: generated HTML source.
- `mẫu 1.pdf`: pages 1-6.
- `mẫu 2.pdf`: pages 1-14, especially pages 1-4 and 8-9.

---

## 2. Executive Diagnosis

The current DBD report is not publishable. It is a skeleton report with several hard-fail defects:

1. Vietnamese font rendering fails in PDF.
2. Missing numeric values are rendered as `0`, especially price, target price, and upside.
3. Charts are rendered even when the report says the underlying data is missing.
4. Forecast and valuation sections contradict themselves: they say no data is available but still show forecast, DCF bridge, and sensitivity charts.
5. Quality gates contradict each other: top-level valuation reproducibility is `N/A`, while the detailed gate says `PASS`.
6. Financial commentary is mostly a restatement of numbers, not analyst reasoning.
7. Report sections do not yet follow the logic quality of the two reference reports.
8. Source coverage is only partial and heavily dependent on Tier-3 data, but the report structure still looks like a final publishable report.

The correct fix order is:

```text
1. Fix rendering safety and Vietnamese font embedding.
2. Fix missing-data semantics and stop coercing missing data to zero.
3. Add hard gates for valuation, forecast, sensitivity, peer comparison, and chart rendering.
4. Add chart artifact validation before report rendering.
5. Add analyst narrative generation based on validated facts and explicit drivers.
6. Restructure report layout using the logic of mẫu 1 and mẫu 2.
7. Add regression tests and visual/export preflight checks.
```

---

## 3. What mẫu 1 Does Well

`mẫu 1.pdf` is a compact Kafi-style VPB update report. It should be used as the reference for concise first-page investment logic and KPI-level explanation.

### 3.1 First-page structure

The first page gives the reader the investment decision immediately:

- Recommendation: `MUA`.
- Current price.
- Target price.
- Expected return.
- Trading information.
- Shares outstanding.
- 52-week range.
- Market cap.
- Beta.
- Stock price chart.
- Major shareholders.

This is useful because the reader can understand the report stance before reading detailed sections.

### 3.2 Investment thesis logic

The VPB report does not merely say profit increased. It links:

```text
LNTT growth -> credit growth -> NIM pressure -> NPL increase -> LLR decline -> risk buffer -> maintain forecast/target price.
```

It also links valuation to operating quality:

```text
ROE recovery -> P/B still below 5-year average -> asset quality uncertainty -> potential re-rating if NPL is controlled.
```

This is the level of reasoning the generated report currently lacks.

### 3.3 KPI table with explanation column

The VPB report includes a detailed table where each row contains:

- Metric.
- Prior period value.
- Current period value.
- Change.
- Explanation.

This pattern is important. It prevents the report from becoming a raw data dump. For the Vietnam Pharma project, historical financial tables should not only show revenue growth, gross margin, net margin, ROE, and ROA. They should also explain why the movement matters.

### 3.4 Risk narrative

The VPB report quantifies and names risks. Example risk axes:

- NPL rising faster than expected.
- Credit cost exceeding forecast.
- NIM declining faster than expected.
- Funding cost pressure.

For pharma reports, the equivalent risk axes should be:

- ETC tender price decline.
- API/input cost increase.
- FX pressure from imported materials.
- Slower OTC growth.
- Receivable/inventory buildup.
- Product registration, GMP, or regulatory issues.
- Tender loss or delay in hospital channel.

---

## 4. What mẫu 2 Does Well

`mẫu 2.pdf` is a VNDIRECT-style HDG update report. It should be used as the reference for full analyst narrative depth, forecast revision logic, valuation explanation, and driver-based thesis.

### 4.1 First-page thesis quality

The first page has a clear title thesis: `Phục hồi thận trọng`.

It then immediately gives:

- Recommendation and expected upside.
- Target price change and the reason for the change.
- Valuation multiple context.
- Financial highlights.
- Investment thesis sections.

Important pattern:

```text
Recommendation -> target price change -> reason for target price change -> financial highlights -> business driver thesis -> valuation rationale.
```

The generated DBD report currently lacks this chain. It has `UNDER_REVIEW`, price zero, target price zero, and placeholder thesis.

### 4.2 KQKD analysis pattern

The HDG report page 2 follows a strong analyst pattern:

```text
Headline: Chi phí dự phòng kéo giảm lợi nhuận dù doanh thu tăng trưởng tích cực.

Then each sub-section explains:
- business segment movement,
- metric change,
- reason,
- implication,
- near-term expectation.
```

This is the target structure for the generated report's financial performance section.

### 4.3 Forecast revision table

The HDG report page 3 includes old forecast, new forecast, percentage change, and row-level comments. This is very important for the generated report pipeline.

If the system produces forecasts, it must explain:

- what assumption changed,
- why it changed,
- which line item was affected,
- how that affects EPS, FCFF, target price, or risk rating.

If there is no validated forecast artifact, no forecast table or forecast chart should be rendered.

### 4.4 Valuation explanation

The HDG report page 8 explains:

- valuation method,
- target price,
- reason target price changed,
- discount applied,
- P/B comparison,
- recommendation rationale,
- WACC assumptions,
- SOTP/valuation bridge,
- upside and downside risks.

The generated DBD report currently says DCF data is missing, but still renders WACC, terminal growth, DCF bridge, and sensitivity. This must become impossible after the fix.

---

## 5. Current DBD Report Defect Inventory

### 5.1 Critical rendering defects

Observed defect:

```text
HTML: Công ty CP Dược Bình Định
PDF: Công ty CP D■■c Bình ■■nh
```

Root cause hypothesis:

- HTML is UTF-8 and content is correct.
- PDF renderer is likely using a non-Unicode default font such as Helvetica/WinAnsi.
- Vietnamese glyphs are not embedded or substituted correctly.

Required fix:

- Use a Unicode-capable renderer and embedded font.
- Add preflight tests that fail on broken glyphs.

### 5.2 Critical missing-data semantics defects

Observed defects:

- Current price rendered as `0`.
- Target price rendered as `0`.
- Upside rendered as `+0.0%`.
- `UNDER_REVIEW` report still displays final-looking valuation fields.

Required fix:

- Missing values must be represented as `N/A`, `Unavailable`, or `Pending Review`, not `0`.
- `0` is only allowed if the validated source explicitly reports an actual zero and the metric permits zero.

### 5.3 Critical forecast defects

Observed defects:

- Forecast section says no data is available.
- Forecast chart still renders 2025F-2029F revenue and net profit.
- Driver assumptions are marked `pending_review` but are still shown as if usable.

Required fix:

- Forecast chart requires `forecast_artifact.status == PASS` and `assumptions_approved == true`.
- Pending assumptions may be displayed only in a draft assumptions table, not used in charts, valuation, or investment conclusion.

### 5.4 Critical valuation defects

Observed defects:

- DCF section says no DCF data.
- DCF bridge still renders.
- WACC and terminal growth are shown from `valuation_result` even though valuation is unavailable.
- Current price is `0`, which makes valuation metrics invalid.

Required fix:

- DCF section must render a `Missing Valuation Inputs` block when valuation is unavailable.
- DCF bridge requires `valuation_artifact.status == PASS`.
- Sensitivity requires both `valuation_artifact.status == PASS` and `sensitivity_artifact.status == PASS`.

### 5.5 Critical sensitivity defects

Observed defects:

- Sensitivity section says no sensitivity data.
- Heatmap still renders.
- Heatmap includes zero rows/columns mixed with large target prices.
- Text claims target price sensitivity even though valuation is not valid.

Required fix:

- Do not fill missing sensitivity values with zero.
- Use `None`, `NaN`, or typed missing values internally; block render if unresolved.
- Sensitivity commentary must be generated only after sensitivity validation passes.

### 5.6 Narrative defects

Observed defect:

Current financial analysis says only:

```text
Tỷ suất sinh lời: biên gộp 47.4%, biên ròng 15.7%, ROE 16.8%, ROA 11.2% (năm 2025).
```

This is not analyst narrative. It is a metric restatement.

Required fix:

Every major table/chart must include an analyst note answering:

```text
1. What changed?
2. Why did it change?
3. Why does it matter for valuation or risk?
4. What should be monitored next?
```

### 5.7 Source and evidence defects

Observed defects:

- Data confidence is only `Medium`.
- Source coverage is around `70%`.
- Structured data depends heavily on `vnstock API (Tier 3)`.
- DBD annual report is marked as Tier 0 but still needs OCR.

Required fix:

- Tier-3-only quantitative claims must be allowed in draft mode but blocked for final publish unless reconciled or explicitly marked.
- Final reports require each quantitative claim to map to a canonical fact or validated document citation.

---

## 6. Target Report Logic After Fix

### 6.1 Page 1 — Investment Snapshot

The first page should contain:

```text
- Ticker and company name.
- Exchange.
- Report date.
- Data cutoff.
- Report status.
- Recommendation status.
- Current price.
- Target price.
- Upside/downside.
- Risk rating.
- Key financial highlights.
- 3 investment thesis bullets.
- 2-3 key risks.
- Data confidence status.
```

Rules:

- If current price is missing, render `N/A`, not `0`.
- If target price is unavailable, render `N/A`, not `0`.
- If valuation is not validated, rating must remain `UNDER_REVIEW`.
- If final publish gate has not passed, add a visible `Draft / Needs Review` banner.

### 6.2 Company Overview and Business Drivers

Required sections:

```text
- Business model summary.
- Revenue/channel mix if data exists.
- Pharma-specific driver map.
- Evidence availability per driver.
```

Pharma driver taxonomy:

```text
- ETC/hospital tender volume.
- Tender winning price.
- OTC channel growth.
- Product mix: branded generic, generic, imported/distributed products.
- API/raw material input cost.
- USD/VND FX exposure.
- Inventory days.
- Receivable days.
- GMP/regulatory status.
- Drug registration renewal/new product approval.
- BHYT/payment policy.
```

### 6.3 Historical Financial Performance

Required components:

```text
- 4-5 year financial table.
- Revenue, gross profit, EBIT/EBITDA, net income, EPS if available.
- Margin and ROE/ROA table.
- Working capital metrics if available.
- Chart only if data validation passes.
- Analyst note below each table/chart.
```

Narrative template:

```text
[Metric] changed from [old] to [new] over [period].
The movement likely reflects [driver], supported by [evidence].
This matters because [valuation/risk implication].
The next items to monitor are [monitoring items].
```

### 6.4 Forecast and Assumptions

Required components:

```text
- Assumption status table.
- Forecast table only if forecast artifact is validated.
- Forecast chart only if forecast artifact passes validation.
- Driver-to-line-item bridge.
- Analyst note explaining forecast logic.
```

Rules:

- Pending assumptions cannot drive final charts.
- Forecast rows must include source/rationale.
- If forecast is unavailable, render missing inputs and next actions only.

### 6.5 Valuation

Required components:

```text
- Valuation method selected and why.
- DCF/multiples/SOTP artifact status.
- WACC and terminal growth only if validated.
- Target price bridge only if valuation passes.
- Peer multiples only if peer data passes.
- Sensitivity matrix only if DCF passes.
- Valuation commentary.
```

Rules:

- No valuation artifact, no target price.
- No market price, no upside/downside.
- No sensitivity artifact, no sensitivity chart or sensitivity commentary.
- No peer data, no peer comparison chart.

### 6.6 Risks and Catalysts

Required components:

```text
- Catalyst table.
- Risk table.
- Quantified impact where possible.
- Monitoring data source.
- Evidence confidence.
```

Narrative quality target:

```text
Each risk/catalyst must connect to a financial line item and a valuation implication.
```

Example for pharma:

```text
If ETC tender prices decline by 5%, gross margin may compress by X bps if cost structure remains unchanged. This would reduce EBIT margin and FCFF, creating downside risk to target price. Monitor tender results and channel mix.
```

Only generate quantified impact if the calculation is backed by model or validated scenario assumptions.

### 6.7 Appendix and Audit

Required components:

```text
- Source table.
- Citation map.
- Quality gates.
- Missing data table.
- Validation warnings.
- Human review status.
- Disclaimer.
```

Rules:

- Gate summary and detailed gate table must never contradict each other.
- `PASS` must mean all required checks passed.
- `WARN` must not allow final publish unless explicitly allowed by policy.
- `N/A` means no artifact exists or the check is not applicable; it must not appear as `PASS` elsewhere.

---

## 7. Implementation Plan

## Phase 0 — Baseline Reproduction and Execution Log

### Objective

Reproduce the current DBD HTML/PDF output and create an execution log so the work does not lose context.

### Tasks

1. Locate the report generation entrypoint.
2. Locate the HTML-to-PDF renderer.
3. Locate chart generation functions.
4. Locate valuation artifact generation.
5. Locate quality gate generation.
6. Locate report section templates.
7. Generate a fresh DBD report using the current code.
8. Save baseline artifacts under a dated debug folder.
9. Create or update `REPORT_FIX_EXECUTION_LOG.md`.

### Suggested log format

```markdown
# Report Fix Execution Log

## Baseline
- command:
- generated html path:
- generated pdf path:
- observed broken glyphs: yes/no
- observed zero price: yes/no
- observed invalid charts: yes/no
- current failing tests:

## Phase Status
- Phase 0: pending / done
- Phase 1: pending / done
- Phase 2: pending / done
...
```

### Acceptance Criteria

- Baseline DBD report can be regenerated.
- Current failure modes are documented with file paths.
- The execution log exists before code changes.

---

## Phase 1 — PDF Rendering and Vietnamese Font Preflight

### Objective

Guarantee Vietnamese text renders correctly in exported PDF.

### Tasks

1. Identify current renderer. If it is `xhtml2pdf`, treat it as unsafe for Vietnamese unless Unicode font embedding is proven.
2. Prefer one of these renderer paths:
   - Playwright/Chromium HTML-to-PDF.
   - Docker/Linux WeasyPrint with fontconfig and Unicode fonts.
3. Configure report CSS with a Unicode font stack:

```css
font-family: "Noto Sans", "DejaVu Sans", "Arial Unicode MS", Arial, sans-serif;
```

4. Ensure fonts are installed in the runtime environment.
5. Ensure the chosen renderer embeds or correctly references Unicode fonts.
6. Add a PDF preflight utility.
7. Add tests for Vietnamese glyph preservation.

### Required preflight checks

The report export must fail if any of the following is true:

```text
- Extracted PDF text contains "■".
- Extracted PDF text loses Vietnamese words: "Dược", "Bình Định", "Trạng thái", "Luận điểm", "Định giá".
- Font inspection shows only Helvetica/WinAnsi for body text.
- Rendered screenshot visibly contains missing-glyph boxes.
```

### Suggested tests

```text
tests/reporting/test_pdf_vietnamese_font_rendering.py
```

Test cases:

```text
- test_pdf_export_preserves_vietnamese_text
- test_pdf_export_rejects_missing_glyph_boxes
- test_pdf_export_uses_unicode_font_or_passes_render_sample
```

### Acceptance Criteria

- Generated PDF no longer contains broken Vietnamese glyphs.
- HTML and PDF preserve the same Vietnamese content.
- PDF export fails fast if font preflight fails.

---

## Phase 2 — Missing Numeric Semantics and No-Zero Coercion

### Objective

Stop the system from converting missing values into zero.

### Tasks

1. Search for code patterns that coerce values:

```text
or 0
fillna(0)
default=0
get(..., 0)
price = 0
np.nan_to_num
```

2. Replace unsafe coercion with typed missing values.
3. Add a small domain object or utility for render-safe numeric fields.

Suggested model:

```python
@dataclass(frozen=True)
class ReportValue:
    value: Decimal | float | int | None
    status: Literal["valid", "missing", "not_applicable", "pending_review", "invalid"]
    unit: str | None = None
    source_ref: str | None = None
    reason: str | None = None
```

4. Update formatting functions:

```text
valid -> formatted number
missing -> N/A
pending_review -> Pending review
invalid -> Invalid
not_applicable -> N/A
```

5. Add metric-specific zero rules.

### Zero allowed only when

```text
- The source explicitly reports zero.
- The metric is semantically allowed to be zero.
- The value has source_ref and validation_status == PASS.
```

### Zero not allowed for these fields unless explicitly validated

```text
- current_price
- target_price
- upside_downside
- market_cap
- shares_outstanding
- revenue
- gross_profit
- net_income
- EPS
- P/E
- EV/EBITDA
- WACC
- terminal_growth
```

### Suggested tests

```text
tests/reporting/test_missing_numeric_semantics.py
```

Test cases:

```text
- test_missing_current_price_renders_na_not_zero
- test_missing_target_price_renders_na_not_zero
- test_missing_upside_renders_na_not_zero_percent
- test_missing_values_do_not_enter_valuation_math
- test_actual_zero_requires_source_ref_and_passed_validation
```

### Acceptance Criteria

- Current price missing renders `N/A`, not `0`.
- Target price missing renders `N/A`, not `0`.
- Upside missing renders `N/A`, not `+0.0%`.
- Missing values do not propagate into valuation or chart calculations.

---

## Phase 3 — Artifact Status Contract

### Objective

Make report rendering depend on validated artifacts, not raw objects or partially available dataframes.

### Required artifacts

Define or standardize these artifacts if not already present:

```text
- financial_history_artifact
- ratio_artifact
- working_capital_artifact
- forecast_artifact
- assumption_artifact
- valuation_artifact
- sensitivity_artifact
- peer_comparison_artifact
- chart_artifact
- narrative_artifact
- citation_map_artifact
- quality_gate_artifact
```

### Required status enum

```text
PASS
WARN
FAIL
N_A
PENDING_REVIEW
BLOCKED
```

### Artifact contract

Each artifact must include:

```text
artifact_id
artifact_type
ticker
period_range
created_at
source_refs
input_artifact_ids
validation_status
validation_errors
validation_warnings
is_publishable
```

### Rendering policy

```text
Renderer must not compute finance.
Renderer must not create charts.
Renderer must not infer missing values.
Renderer only displays validated artifacts and placeholders.
```

### Suggested tests

```text
tests/reporting/test_report_artifact_status_contract.py
```

Test cases:

```text
- test_renderer_blocks_valuation_section_when_valuation_artifact_missing
- test_renderer_blocks_forecast_chart_when_forecast_artifact_pending_review
- test_renderer_blocks_sensitivity_when_dcf_not_passed
- test_renderer_does_not_compute_financial_metrics_inline
```

### Acceptance Criteria

- Report rendering is fully artifact-driven.
- Missing artifacts produce explicit missing-input blocks.
- No chart or valuation section is rendered from incomplete data.

---

## Phase 4 — Chart Validation Layer

### Objective

Prevent inaccurate, contradictory, or misleading charts from entering the report.

### Required `ChartSpec`

Implement or standardize:

```python
@dataclass(frozen=True)
class ChartSpec:
    chart_id: str
    title: str
    chart_type: str
    source_artifact_id: str
    metrics: list[str]
    units: dict[str, str]
    period_range: list[str]
    min_observation_count: int
    null_policy: Literal["block", "drop", "annotate"]
    axis_policy: dict
    citation_policy: str
    required_upstream_status: Literal["PASS", "WARN_ALLOWED"]
```

### Required chart validation rules

```text
- No NaN/Inf in plotted data.
- No automatic fill missing with zero.
- Minimum valid observation count must be met.
- Chart title must match plotted metrics.
- Axis label must match unit.
- Multi-axis charts must define units for each axis.
- Forecast chart requires validated forecast artifact.
- DCF bridge requires validated valuation artifact.
- Sensitivity heatmap requires validated sensitivity artifact.
- P/E chart requires valid price and valid EPS.
- Peer chart requires peer_comparison_artifact.status == PASS.
```

### Chart-specific rules

#### C1 Revenue mix

Render only if segment revenue data exists and totals reconcile.

#### C2 Revenue and EBITDA/EBIT trend

Render only if revenue and EBITDA/EBIT exist for at least 3 periods. Title must specify EBITDA or EBIT, not both ambiguously.

#### C3 EPS and P/E

Render only if EPS and market price are available for required periods. If P/E cannot be calculated, show EPS-only chart or block P/E line.

#### C4 Margin and ROE

Render only if gross margin, net margin, and ROE have at least 3 valid periods.

#### C5 Forecast

Render only if forecast artifact passes and assumptions are approved.

#### C6 Valuation bridge

Render only if valuation artifact passes.

#### C7 Sensitivity heatmap

Render only if DCF and sensitivity artifacts pass. Missing cells must not be zero-filled.

### Suggested tests

```text
tests/reporting/test_chart_validation.py
```

Test cases:

```text
- test_chart_rejects_nan_inf
- test_chart_rejects_missing_filled_as_zero
- test_forecast_chart_requires_approved_assumptions
- test_dcf_bridge_requires_passed_valuation
- test_sensitivity_requires_passed_dcf
- test_pe_chart_requires_valid_price_and_eps
- test_chart_title_matches_metrics
```

### Acceptance Criteria

- Invalid charts are blocked before HTML/PDF rendering.
- Placeholder text clearly explains why a chart is unavailable.
- No report shows a chart while the section says data is missing.

---

## Phase 5 — Quality Gate Consistency

### Objective

Make report gate results internally consistent and enforce publish blocking.

### Tasks

1. Centralize gate computation.
2. Remove duplicated gate status logic in templates.
3. Define gate severity rules.
4. Ensure summary and detailed gate tables read from the same object.
5. Add final publish policy.

### Required gates

```text
- Data Availability Gate
- Source Coverage Gate
- Numeric Consistency Gate
- Fact Reconciliation Gate
- Forecast Assumption Approval Gate
- Valuation Reproducibility Gate
- Chart Validation Gate
- Narrative Grounding Gate
- Vietnamese PDF Render Gate
- Human Review Gate
```

### Publish policy

```text
If any critical gate == FAIL -> do not export final PDF.
If any critical gate == BLOCKED -> do not export final PDF.
If Human Review == PENDING -> export draft only, with visible draft banner.
If Source Coverage < threshold -> export draft only, not final.
If Valuation Reproducibility != PASS -> do not show target price, upside, or final recommendation.
```

### Suggested tests

```text
tests/reporting/test_quality_gate_consistency.py
```

Test cases:

```text
- test_gate_summary_and_detail_cannot_disagree
- test_valuation_na_cannot_be_detail_pass
- test_final_export_blocked_when_human_review_pending
- test_target_price_hidden_when_valuation_not_passed
- test_draft_banner_visible_when_publish_blocked
```

### Acceptance Criteria

- No `N/A` in summary and `PASS` in details for the same quality item.
- The report cannot present final recommendation when validation is incomplete.
- Gate status is deterministic and test-covered.

---

## Phase 6 — Analyst Narrative Engine

### Objective

Generate analyst-style commentary under each major table/chart using validated data and explicit evidence.

### Do not let the LLM invent causes

Narrative generation must be grounded in:

```text
- validated financial facts,
- abnormal movement flags,
- driver taxonomy,
- source snippets/citations,
- approved assumptions,
- valuation artifact,
- risk/catalyst artifact.
```

### Required narrative structure

Each major section must answer:

```text
1. What changed?
2. Why did it change?
3. Why does it matter?
4. What should be monitored next?
```

### Required output schema

```python
@dataclass(frozen=True)
class AnalystNote:
    section_id: str
    headline: str
    bullets: list[AnalystBullet]
    confidence: Literal["high", "medium", "low"]
    source_refs: list[str]
    missing_evidence: list[str]
    publishable: bool

@dataclass(frozen=True)
class AnalystBullet:
    metric: str | None
    observation: str
    driver: str | None
    implication: str
    monitor: str | None
    source_refs: list[str]
```

### Minimum narrative requirements by section

#### Company overview

```text
- Explain business model.
- Explain main revenue channels.
- Explain which pharma drivers matter most.
- Flag missing segment data.
```

#### Historical financials

```text
- Explain revenue trend.
- Explain margin trend.
- Explain profitability trend.
- Explain working capital or cash flow trend if available.
```

#### Forecast

```text
- Explain base revenue growth assumption.
- Explain margin assumption.
- Explain CAPEX/NWC assumption.
- Explain which assumptions are pending review.
```

#### Valuation

```text
- Explain method.
- Explain value bridge.
- Explain sensitivity.
- Explain why rating/target price is blocked if valuation is incomplete.
```

#### Risks and catalysts

```text
- Explain each risk/catalyst as driver -> financial line item -> valuation impact.
```

### Narrative examples

Bad output:

```text
Biên gộp 47.4%, biên ròng 15.7%, ROE 16.8%, ROA 11.2%.
```

Good output style:

```text
Biên gộp giảm từ 49.4% năm 2022 xuống 47.4% năm 2025, cho thấy áp lực lên giá bán hoặc chi phí đầu vào đang tăng dần. Với doanh nghiệp dược có tỷ trọng ETC cao, biến động này cần được đối chiếu với kết quả đấu thầu, cơ cấu kênh bán và giá nguyên liệu nhập khẩu. Nếu biên gộp tiếp tục giảm, FCFF sẽ nhạy cảm hơn với giả định tăng trưởng doanh thu và kiểm soát vốn lưu động. Cần theo dõi kết quả đấu thầu ETC, USD/VND và biến động giá API.
```

Only generate this if facts and evidence support it. Otherwise, generate a lower-confidence note that explicitly says what evidence is missing.

### Suggested tests

```text
tests/reporting/test_analyst_narrative_engine.py
```

Test cases:

```text
- test_narrative_not_metric_restatement_only
- test_narrative_contains_change_cause_implication_monitor
- test_narrative_requires_source_refs_for_quantitative_claims
- test_low_evidence_narrative_flags_missing_evidence
- test_unapproved_assumptions_do_not_become_final_thesis
```

### Acceptance Criteria

- Each major table/chart has an analyst note.
- Quantitative claims in notes have source refs.
- Unsupported causal claims are either blocked or marked as missing evidence.
- Narrative quality is closer to mẫu 1 and mẫu 2.

---

## Phase 7 — Report Template Restructure

### Objective

Restructure generated report sections to follow the analytical flow of the reference reports.

### Target structure

```text
Page 1 — Investment Snapshot
1. Recommendation / Review status
2. Current price / target price / expected return
3. Data confidence and publish status
4. Key financial highlights
5. Investment thesis bullets
6. Key risks
7. Mini price chart and trading info if available

Section 2 — Company Overview and Business Drivers
1. Business model
2. Revenue/channel mix
3. Pharma driver map
4. Evidence availability

Section 3 — Historical Financial Performance
1. Financial summary table
2. Ratio table
3. Charts C2-C4 if valid
4. Analyst notes

Section 4 — Forecast and Assumptions
1. Assumption status
2. Forecast table if valid
3. Forecast chart if valid
4. Driver-to-line-item bridge
5. Analyst notes

Section 5 — Valuation
1. Valuation method
2. Valuation assumptions
3. Target price bridge if valid
4. Sensitivity if valid
5. Peer comparison if valid
6. Analyst notes

Section 6 — Catalysts and Risks
1. Catalyst table
2. Risk table
3. Quantified impact if supported
4. What to monitor

Appendix — Audit and Sources
1. Citation map
2. Source table
3. Quality gate table
4. Missing-data table
5. Disclaimer
```

### Template policy

- Do not show final-looking valuation fields if valuation is incomplete.
- Do not show blank sections without actionability.
- If a section is blocked, show why and what input is required.
- Draft reports must have a visible draft/review banner.

### Suggested tests

```text
tests/reporting/test_report_template_sections.py
```

Test cases:

```text
- test_snapshot_hides_target_price_when_valuation_blocked
- test_blocked_section_shows_missing_inputs
- test_major_sections_have_analyst_notes_or_explicit_block_reason
- test_report_has_appendix_with_sources_and_quality_gates
```

### Acceptance Criteria

- Report structure follows reference-report logic.
- Blocked sections are explicit, not contradictory.
- The report reads like an equity research draft, not a raw metric dump.

---

## Phase 8 — Source Coverage and Citation Enforcement

### Objective

Ensure every important quantitative claim is grounded or explicitly flagged.

### Tasks

1. Classify report claims:

```text
- quantitative fact
- derived metric
- forecast assumption
- valuation output
- qualitative business claim
- risk/catalyst claim
```

2. Enforce citation requirements by claim type.
3. Add citation map to appendix.
4. Add missing evidence table.
5. Block final publish when critical claims lack citation.

### Required citation policy

```text
Quantitative fact -> canonical fact or source document.
Derived metric -> formula artifact + input facts.
Forecast assumption -> approved assumption artifact + rationale.
Valuation output -> valuation artifact.
Business/catalyst claim -> document chunk or trusted source.
Risk impact -> scenario artifact or calculation artifact.
```

### Suggested tests

```text
tests/reporting/test_citation_enforcement.py
```

Test cases:

```text
- test_quantitative_claim_requires_citation
- test_derived_metric_requires_formula_and_input_refs
- test_forecast_claim_requires_approved_assumption
- test_valuation_claim_requires_valuation_artifact
- test_final_publish_blocked_by_missing_critical_citations
```

### Acceptance Criteria

- Final report has 100% citation coverage for quantitative claims.
- Draft report can show missing evidence, but must label it clearly.
- No unsupported investment conclusion is allowed.

---

## Phase 9 — Regression Test Suite and Golden Fixtures

### Objective

Prevent future regressions in report export, chart validity, and narrative logic.

### Required fixtures

Create minimal fixtures for DBD:

```text
tests/fixtures/reporting/dbd_valid_minimal_facts.json
tests/fixtures/reporting/dbd_missing_market_price.json
tests/fixtures/reporting/dbd_missing_valuation.json
tests/fixtures/reporting/dbd_pending_assumptions.json
tests/fixtures/reporting/dbd_invalid_sensitivity_nan.json
tests/fixtures/reporting/dbd_tier3_only_sources.json
```

### Required integration tests

```text
tests/integration/test_dbd_report_export_pipeline.py
```

Test cases:

```text
- test_dbd_draft_export_succeeds_with_visible_review_banner
- test_dbd_final_export_blocked_when_critical_gates_fail
- test_dbd_pdf_has_no_broken_vietnamese_glyphs
- test_dbd_report_does_not_render_invalid_forecast_chart
- test_dbd_report_does_not_render_invalid_valuation_chart
- test_dbd_report_quality_gates_are_consistent
- test_dbd_report_contains_analyst_notes_for_valid_sections
```

### Optional visual regression

If the project already supports image snapshots:

```text
- Render PDF pages to PNG.
- Compare against baseline with tolerance.
- Fail on large unexpected layout changes.
- Specifically inspect page 1 and key chart pages.
```

### Acceptance Criteria

- Unit tests cover each failure mode.
- Integration test covers DBD end-to-end draft export.
- Final export is blocked when data or validation is incomplete.

---

## Phase 10 — Final Manual Review Checklist

Before closing the task, run a manual review on generated DBD output.

### PDF rendering checklist

```text
[ ] No broken Vietnamese glyphs.
[ ] Company name renders correctly.
[ ] Headings render correctly.
[ ] Tables render correctly.
[ ] No clipped text.
[ ] No chart overlap.
[ ] No unreadable labels.
```

### Data logic checklist

```text
[ ] Missing price is not zero.
[ ] Missing target price is not zero.
[ ] Missing upside is not +0.0%.
[ ] Forecast chart is hidden if forecast is invalid.
[ ] Valuation bridge is hidden if valuation is invalid.
[ ] Sensitivity is hidden if sensitivity is invalid.
[ ] Peer comparison is hidden if peer data is invalid.
```

### Narrative checklist

```text
[ ] Historical financial section explains trend, not just numbers.
[ ] Forecast section explains assumptions or says what is missing.
[ ] Valuation section explains method or why valuation is blocked.
[ ] Risks/catalysts connect driver to financial impact.
[ ] Unsupported claims are not presented as facts.
```

### Gate checklist

```text
[ ] Gate summary and details are consistent.
[ ] Human review pending creates draft status.
[ ] Final publish blocked if critical gates fail.
[ ] Citation coverage is clearly reported.
[ ] Source tiers are visible.
```

---

## 8. Implementation Guardrails for Claude Code

### 8.1 Do not do these

```text
- Do not patch the PDF text after rendering.
- Do not replace broken glyphs manually.
- Do not use 0 as fallback for missing financial data.
- Do not generate charts inside the HTML/PDF template.
- Do not let LLM-generated text invent causes for financial movement.
- Do not mark valuation PASS when no valuation artifact exists.
- Do not export final report while Human Review is pending.
- Do not optimize visual style before fixing gates and contracts.
```

### 8.2 Always do these

```text
- Keep report rendering artifact-driven.
- Use typed missing values.
- Validate charts before rendering.
- Centralize quality gate status.
- Add tests before or with each fix.
- Update REPORT_FIX_EXECUTION_LOG.md after each phase.
- Commit changes phase by phase if using git.
```

### 8.3 Anti-lost-in-the-middle protocol

Before each phase, Claude must restate:

```text
Current phase:
Files to inspect:
Files expected to change:
Tests to add/update:
Exit criteria:
```

After each phase, Claude must report:

```text
Changed files:
Tests run:
Pass/fail result:
Remaining blockers:
Next phase:
```

Do not proceed to the next phase if the phase acceptance criteria fail, unless explicitly documenting a blocker and creating a follow-up task.

---

## 9. Suggested File/Module Targets

Claude must discover actual paths before editing. These are likely target areas based on project behavior:

```text
report generation entrypoint:
- scripts/generate_report.py
- scripts/run_research.py
- backend/reporting/*
- backend/reports/*

HTML/PDF renderer:
- backend/reporting/export_pdf.py
- backend/reporting/renderers.py
- backend/reports/pdf_export.py
- any usage of xhtml2pdf, pisa, weasyprint, playwright, pdfkit

Templates:
- templates/report*.html
- backend/reporting/templates/*
- backend/reports/templates/*

Charts:
- backend/reporting/charts.py
- backend/visualization/*
- backend/charts/*

Valuation:
- backend/valuation/*
- backend/analytics/*

Quality gates:
- backend/evaluation/*
- backend/quality/*
- approval_gate.py
```

Discovery commands:

```bash
grep -R "xhtml2pdf\|pisa\|weasyprint\|playwright\|pdfkit" -n .
grep -R "fillna(0)\|or 0\|get(.*0)\|nan_to_num\|current_price.*0\|target_price.*0" -n backend scripts tests
grep -R "Valuation Reproducibility\|Source Coverage\|Human Review\|Numeric Consistency" -n .
grep -R "C1\|C2\|C3\|C4\|C5\|C6\|C7\|Sensitivity\|DCF Equity Value Bridge" -n .
```

---

## 10. Definition of Done

The task is complete only when all conditions below are met:

```text
[ ] DBD PDF renders Vietnamese correctly.
[ ] Missing current price, target price, and upside are not shown as zero.
[ ] Forecast chart is blocked unless forecast artifact passes.
[ ] Valuation bridge is blocked unless valuation artifact passes.
[ ] Sensitivity heatmap is blocked unless sensitivity artifact passes.
[ ] Quality gate summary and details are consistent.
[ ] Each major section has either analyst narrative or explicit missing-input explanation.
[ ] Quantitative claims have citations or are flagged as missing evidence.
[ ] Draft/final export distinction is enforced.
[ ] Unit tests and integration tests cover the original defects.
[ ] REPORT_FIX_EXECUTION_LOG.md documents implementation and verification.
```

---

## 11. Expected Final Behavior for Current DBD State

Given the current DBD input state appears incomplete:

```text
- Source coverage around 70%.
- Data confidence Medium.
- Annual report still needs OCR.
- Human review pending.
- Valuation incomplete.
- Market price appears missing or invalid.
```

The corrected report should behave as follows:

```text
- Export as DRAFT only.
- Show Vietnamese correctly.
- Show current price as N/A if missing.
- Show target price as N/A.
- Show upside as N/A.
- Keep rating as UNDER_REVIEW.
- Hide DCF bridge.
- Hide sensitivity heatmap.
- Hide forecast chart if assumptions are pending.
- Display missing inputs and next actions.
- Provide analyst notes only where supported by validated facts.
- Show source coverage and OCR/reconciliation gaps clearly.
```

This is the correct outcome. A truthful draft is better than a polished but misleading final report.
