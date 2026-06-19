# Institutional Report Quality Evaluation Plan

## Context

Repo da co `backend/evaluation/report_quality.py`, `backend/reporting/publication_readiness.py`, `backend/reporting/final_report_renderer.py`, `backend/reporting/post_render_audit.py` va cac test governance moi. Vi vay report evaluation phai la aggregation layer sau cung: no khong tinh lai data hay valuation, ma xac nhan report co dat chuan cong bo noi bo va khong bypass gate.

## Problem Statement

Bao cao co the trong chuyen nghiep nhung van khong dat chuan neu thieu citation theo claim, target price khong publishable, Report quality score thap, hoac fast-render render artifact bi blocked. Report evaluation phai fail-closed va phan biet ro `draft`, `review_passed`, `publishable` va `approved`.

## Technical Deep-Dive

### 0. Current implementation alignment

| Logic hien tai | Dieu chinh trong ke hoach |
|---|---|
| `evaluate_report_quality` gom 8 sub-gates: financial model integrity, forecast reasonableness, company research depth, analyst insight, valuation completeness, citation coverage, recommendation consistency, professional presentation | Report plan phai test tung sub-gate, khong chi test tong score |
| Decision rule hien tai: `allow_export` neu score >= 85% va khong failed gate; `draft_only` neu score >= 70% nhung con fail; con lai `block_export` | Artifact `report_eval.json` phai expose `decision`, `failed_gates`, `section_scores` va raw sub-gate results |
| `report_quality_gate` fail co severity warning trong harness | Warning severity khong co nghia final duoc phep render; `PACKAGE_VALIDATION_GATE` va `publication_readiness` van fail-closed |
| `evaluate_client_final_readiness` yeu cau run `approved`, final approval `approved`, company/analyst insight packs, locked `publishable_final_report_model`, package gate pass, Report-quality allow_export score >=85, snapshot match | Blocking conditions phai them `final_report_approval_missing`, `run_not_approved:*`, `publishable_final_report_model_not_locked`, `artifact_snapshot_mismatch` |
| `FinalReportRenderer` va `ClientReportPublisher` can `ClientFinalAuthorization`; thieu hoac mismatch authorization se raise `PublicationBlockedError` | Renderer test phai verify direct client-final call bi chan khi khong co authorization |
| `post_render_audit` la lop sau render de bat loi client-final display | Report eval phai luu post-render blockers rieng, vi HTML/PDF co the fail du da pass model gate |

### 1. Doi tuong can eval

| Doi tuong | Can kiem dinh |
|---|---|
| Report model | Co du section, table, chart, source, chart/table metadata |
| Recommendation | Khong hien BUY/HOLD/SELL neu chua approved |
| Target price | Chi hien khi valuation publishable va approval cho phep |
| Narrative | Company-specific, material, khong dung chung template |
| Tables/charts | Numbered, sourced, unit ro, khong mau thuan voi artifact |
| report-quality rubric | Score >= 85% va khong failed gate |
| Thesis specificity | Thesis phai neu driver rieng cua cong ty, materiality va dieu kien bac bo |
| Risk/catalyst quality | Risk/catalyst phai co xac suat, thoi diem, financial transmission path va evidence |
| Peer/industry context | So sanh peer/nganh ve growth, margin, valuation va balance sheet |
| Sensitivity disclosure | Driver trong yeu phai co sensitivity/scenario disclosure phu hop |
| Executive summary | Phai actionable: recommendation, valuation basis, driver, risk va monitoring trigger |
| Export package | Manifest, formula traces, evidence packet, quality gate, PDF/HTML |
| Client-final authorization | Run approval, final approval, locked artifact, snapshot match, Report-quality allow_export |
| Post-render audit | HTML/PDF khong lo internal banner, generic source note, draft markers hoac forbidden display |

### 2. Framework va cong nghe

| Cong nghe | Vai tro |
|---|---|
| `backend.evaluation.report_quality` | Rubric deterministic chinh |
| `pytest` | Regression cho report model, renderer, export gate |
| LLM-as-judge | Danh gia insight depth, professional narrative, risk balance |
| HTML/PDF preflight | Kiem tra Unicode, missing sections, forbidden terms |
| Langfuse/offline eval | Luu report score theo run va prompt/model version |

### 3. report-quality rubric de xuat

| Nhom | Trong so | Dieu kien dat |
|---|---:|---|
| Completeness | 12 | Required sections, tables, charts and artifacts present |
| Thesis specificity | 12 | Company-specific thesis, material drivers, explicit disconfirming conditions |
| Financial analysis depth | 14 | Financial model integrity, ratio discussion and driver attribution pass |
| Forecast rationale | 12 | Revenue, margin, capex and NWC assumptions have traceable rationale |
| Valuation transparency | 14 | EV-to-equity bridge, WACC build-up, method status and sensitivity are clear |
| Risk/catalyst quality | 10 | Probability, timing, financial transmission path and evidence are explicit |
| Evidence integration | 10 | Claim-level citation, official source preference and formula trace are integrated |
| Peer/industry context | 6 | Peer comparison supports valuation and operating interpretation |
| Executive summary actionability | 5 | Summary supports an investment decision without reading the full appendix |
| Professional presentation | 5 | Sections, tables, charts, units and recommendation consistency pass |

### 4. Blocking conditions

| Condition | Severity |
|---|---|
| Report quality score < 85 | Critical |
| Any failed deterministic finance gate | Critical |
| Recommendation visible before approval | Critical |
| Target price visible from blocked valuation | Critical |
| Report artifact snapshot mismatch with valuation | Critical |
| Missing evidence packet or formula trace | Critical |
| PDF rendered from `report_candidate_model` as final | Critical |
| Missing numbered/sourced charts/tables | Warning in draft, critical in final |
| Recommendation/rating inconsistent with target price, market price or upside/downside | Critical |
| Sensitivity disclosure missing for valuation-critical drivers | Warning in draft, critical in final |
| Missing final approval for client-final render | Critical |
| `publishable_final_report_model` not locked | Critical |
| Report-quality gate warning treated as final pass | Critical |
| Post-render client-final audit failed | Critical |

### 5. Report evaluation artifact

```json
{
  "rubric": "report_quality_v1",
  "score": 0,
  "decision": "block_export|draft_only|allow_export",
  "failed_gates": [],
  "section_scores": {},
  "report_artifacts": {
    "html": "path",
    "pdf": "path",
    "manifest": "path"
  },
  "publication_readiness": {
    "passed": false,
    "blocking_reasons": []
  }
}
```

## Strategic Recommendations

### 1. P0 actions

| Hanh dong | Ket qua |
|---|---|
| Renderer chi chap nhan `publishable_final_report_model` | Dong fast-render bypass |
| Report footer/title phan biet `DRAFT`, `AUTO_EXPORTED`, `APPROVED` | Giam nham lan product |
| `REPORT_QUALITY_GATE` la required export gate | Score thap khong render final |
| `authorize_client_final` la bat buoc cho mode `client_final` | Tach auto-exported draft khoi client-facing final |
| Chay post-render audit trong client-final path | Bat loi hien thi ma model-level gate khong thay |

### 2. P1 actions

| Hanh dong | Ket qua |
|---|---|
| Them LLM judge cho report depth | Do company-specific analysis va thesis quality |
| Tao corpus broker-quality reports mau | Calibration voi human reviewer |
| Track score trend theo ticker/archetype | Biet template nao khong dat |
