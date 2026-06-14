# Report Quality Gate And Publication Plan For Scale

## Context

Mo rong ticker chi an toan neu publish path fail-closed. He thong hien da co `backend/evaluation/report_quality.py`, artifact lifecycle voi `report_candidate_model`, `review_passed_report_model`, `publishable_final_report_model`, va fast render path chi nen dung artifact da locked.

## Problem Statement

Khi so ticker tang, xac suat co ticker loi data, loi model hoac loi citation tang manh. Neu gate chi canh bao ma khong chan, mot batch scale se tao ra nhieu report trong co ve hop le nhung thieu ky luat phan tich. Dieu nay lam tang product liability va chi phi review con nguoi.

## Technical Deep-Dive

### Publication States

| State | Meaning | Allowed Output |
|---|---|---|
| `data_blocked` | Du lieu can thiet khong du | Readiness report only |
| `draft_only` | Co the tao draft noi bo nhung chua du publish | Draft HTML/PDF co watermark noi bo |
| `under_review` | Da co report candidate va evaluation summary | Reviewer package |
| `approved` | Human approval va gates pass | Publishable final model |
| `published` | Export da duoc ghi vao approved exports | Client-facing PDF |

### Gate Policy

| Report Quality Score | Failed Blocking Gates | Decision |
|---:|---|---|
| >= 85 | none | `allow_export` |
| 70-84 | any or none | `draft_only` |
| < 70 | any | `block_export` |

### Required Blocking Gates

| Gate | Blocks When |
|---|---|
| Financial model integrity | Balance sheet, EPS, dividend, net debt or FCFF bridge does not reconcile |
| Forecast reasonableness | Profit/EPS/margin jump lacks bridge, or driver model is too thin |
| Company research depth | Required archetype evidence is missing |
| Analyst insight | Catalyst/event insight lacks materiality and financial transmission |
| Valuation completeness | WACC, FCFF table, terminal value or EV-to-equity bridge missing |
| Citation coverage | Quantitative claims lack fact/artifact/calculation lineage |
| Recommendation consistency | Recommendation visible before approval or state mismatch |
| Professional presentation | Missing required sections, chart/table metadata or sources |

### Artifact Lifecycle

```text
report_draft
-> report_candidate_model
-> review_passed_report_model
-> publishable_final_report_model
-> exported client PDF
```

Rules:

1. No artifact before export gates should be named `final`.
2. `publishable_final_report_model` must be locked.
3. Fast render must reject runs without locked `publishable_final_report_model`.
4. Client-final render must require human approval and snapshot consistency.
5. Every batch summary must show which gate blocked each ticker.

## Strategic Recommendations

1. Treat the report-quality evaluator as a production gate, not only a scoring report.
2. Store evaluation JSON per ticker per run to support longitudinal improvement.
3. For scale waves, optimize the distribution of failure reasons before optimizing PDF layout.
4. Do not hide failed valuation components in prose; if FCFE is blocked, report must say FCFF reference only or remain draft.
