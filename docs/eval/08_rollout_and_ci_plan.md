# Evaluation Rollout And CI Plan

## Context

Repo da co nhieu tests nhung chua co mot evaluation rollout ro rang cho data, RAG, finance, agent va report. Ke hoach nay sap xep thu tu trien khai theo rui ro va dependency, tranh viec them LLM judge truoc khi deterministic gates fail-closed.

## Problem Statement

Neu trien khai evaluation sai thu tu, he thong co the co diem judge cao trong khi data/valuation sai. Do do rollout phai bat dau tu deterministic blockers, sau do moi den semantic RAG/LLM metrics va dashboard.

## Technical Deep-Dive

### 0. Current implementation alignment

| Da co trong repo | Con phai dua vao rollout |
|---|---|
| `backend/evaluation/governance.py` cho decomposition, bridge, forecast sanity, valuation reproduction | Dung lam shared rule layer cho finance/report eval artifacts |
| `backend/reporting/publication_readiness.py` fail-closed client-final authorization | Dua `tests/unit/test_publication_readiness.py` vao CI governance bat buoc |
| `tests/evaluation/test_client_final_governance.py` cho forecast decomposition, bridge, valuation method policy | Dua vao finance-regression hoac evaluation-gates job |
| `tests/unit/test_export_gate.py` da test sensitivity v2, gate skipped/failed/blocking behavior | CI phai chay de bao ve final export gate |
| `tests/unit/test_package_validation_gate.py` da test aggregate package validation | CI phai chay cung report-quality tests |
| `auto_exported` da la status rieng voi public mapping `PUBLISHED_DRAFT` | Rollout phai khong dung `auto_exported` nhu approval final |

### 1. Rollout phases

| Phase | Muc tieu | Output |
|---|---|---|
| P0.1 | Dong governance gap | Export fail-closed, no fast-render bypass, client-final authorization required |
| P0.2 | Chuan hoa deterministic eval packets | `data_quality`, `financial_eval`, `citation_eval`, `report_eval` |
| P0.3 | CI regression cho core gates | Unit/evaluation tests pass trong PR |
| P1.1 | RAG golden benchmark | `rag_golden_queries.yaml`, hit-rate@k, Ragas pilot |
| P1.2 | Langfuse trace and dataset loop | Trace scores, failed trace datasets |
| P1.3 | LLM judge for narrative and agent | DeepEval/OpenAI Evals calibrated rubric |
| P2 | Archetype-aware evaluation | Separate thresholds for pharma, distributor, hospital, equipment |
| P3 | Universe scaling readiness | Batch eval across pilot basket before the full active universe |

### 2. CI gate matrix

| CI job | Scope | Block merge |
|---|---|---|
| `unit-core` | `tests/unit/` core deterministic tests | Yes |
| `evaluation-gates` | `tests/evaluation/ tests/citations/ tests/reconciliation/ tests/unit/test_package_validation_gate.py tests/unit/test_publication_readiness.py` | Yes |
| `finance-regression` | DCF, ratios, debt, dividend, sensitivity, valuation workings, governance invariants | Yes |
| `report-render-smoke` | HTML/PDF smoke, post-render audit, authorization-required client-final render | Yes if renderer required |
| `rag-golden` | Golden retrieval set | Warn in P1, block in P2 |
| `llm-judge-offline` | Small calibrated report/agent dataset | Warn initially, block after calibration |
| `integration-db` | Supabase/PostgreSQL live tests | Scheduled or protected branch |

### 3. Acceptance thresholds by maturity

| Layer | P0 threshold | P1 threshold | P2 threshold |
|---|---:|---:|---:|
| Data critical failures | 0 | 0 | 0 |
| Finance critical failures | 0 | 0 | 0 |
| Citation coverage final | 100% | 100% | 100% |
| Report quality score | >= 85 | >= 85 | >= 90 for published |
| RAG hit-rate@5 | Measured only | >= 90% | >= 95% |
| Ragas faithfulness | Measured only | >= 0.85 | >= 0.90 |
| Agent role adherence | Measured only | >= 0.85 | >= 0.90 |
| Cost per report | Baseline | <= baseline + 15% | Budgeted by archetype |

### 4. Proposed dependencies

| Dependency | When to add | Reason |
|---|---|---|
| `pandera` | P1 data contract | DataFrame validation before normalization |
| `ragas` | P1 retrieval eval | RAG metrics and synthetic/golden evaluation |
| `deepeval` | P1 or P2 narrative/agent eval | Custom LLM-as-judge rubric in Python CI |
| `hypothesis` | P1 finance robustness | Property-based formula tests |

## Strategic Recommendations

### 1. Immediate checklist

| Step | Owner layer | Done when |
|---|---|---|
| Create evaluation docs | Planning | `docs/eval/` folder exists with scoped plans |
| Make export path fail-closed | Reporting/governance | Blocked/failed/unapproved run cannot render final PDF |
| Add run-scoped eval packet manifest | Harness | All eval artifacts listed by `run_id` |
| Seed negative fixtures | Evaluation | Known bad report/data/valuation fails reliably |
| Pilot on DHG and DBD | Product QA | Both pass deterministic gates before universe expansion |
| Enforce `auto_exported` vs `approved` semantics | Product/governance | Draft export does not satisfy client-final authorization |

### 2. Strategic constraint

Khong nen mo rong sang full active universe cho den khi P0 fail-closed governance, financial deterministic gates, citation source provenance va Report quality deu pass tren it nhat hai ticker pilot dai dien. Mo rong som se lam tang chi phi debug va che mo nguyen nhan loi giua data gap, archetype mismatch, retrieval failure va valuation failure.
