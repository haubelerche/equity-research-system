# Citation And Source Provenance Evaluation Plan

## Context

Citation evaluation trong he thong nay khong chi dem so footnote. No phai chung minh moi claim material co lineage ve fact, artifact, formula trace hoac document chunk. Repo da co `backend/citations/`, `backend/evaluation/citation_coverage.py`, `backend/evaluation/source_provenance_gates.py`, `backend/news/citation_validator.py`, `backend/reporting/citation_artifact_writer.py` va tests trong `tests/citations/`, `tests/evaluation/`, `tests/unit/test_citation_*`, `tests/unit/test_claim_ledger.py`.

## Problem Statement

Rui ro lon nhat la report co citation hinh thuc nhung khong co source provenance that. Mot citation generic nhu "du lieu tai chinh canonical" khong du de support claim dinh luong trong final report. Evaluation phai block claim material neu thieu source tier hop le, official document, reconciliation status hoac numeric consistency.

## Technical Deep-Dive

### 0. Current implementation alignment

| Logic hien tai | Dieu chinh trong ke hoach |
|---|---|
| `citation_coverage_gate` trong report quality chi cham quantitative claims va chap nhan lineage keys cu the | Claim schema phai chuan hoa cac key lineage nay va khong dua vao source title thuong |
| `workflow_export_gate` block `tier3_only_material_fact`, `missing_source_trace_for_material_claim`, `generic_citation_only`, `unresolved_major_source_discrepancy` | Citation eval artifact phai map duoc cac count nay vao report summary de export gate doc |
| Source provenance gates co tests rieng cho final source, numeric claim va catalyst evidence | CI plan phai chay `tests/evaluation/test_final_source_gates.py`, `test_numeric_claim_gates.py`, `test_catalyst_evidence_gates.py` |
| News evidence co whitelist va idempotent storage migrations | Citation plan phai tach news support khoi official financial fact support; news khong duoc thay official fact cho quantitative final claim |
| `EVIDENCE_PACKET_GATE` yeu cau evidence packet artifact co storage path | Citation pass nhung thieu packet van khong duoc client-final |

### 1. Doi tuong can eval

| Doi tuong | Cau hoi kiem dinh |
|---|---|
| Claim ledger | Tat ca material claims co `claim_id`, `claim_type`, `quantitative`, `materiality` khong |
| Citation map | Moi claim co citation key resolve duoc khong |
| Source tier | Citation co dung Tier 1/Tier 2 cho final material claim khong |
| Official source | Quantitative final claim co official document hoac reconciled official fact khong |
| Numeric consistency | Gia tri trong report co khop cited fact trong tolerance khong |
| Reconciliation status | Cited facts co `matched_official` hoac `manual_reviewed` khong |
| Catalyst evidence | Event co source document, evidence span, event type va date khong |

### 2. Framework va cong nghe

| Cong nghe | Vai tro |
|---|---|
| Custom deterministic gates | Source provenance can domain-specific policy |
| `pytest` | Regression cho source tier, citation map, final gate |
| Ragas faithfulness | Bo sung semantic groundedness cho narrative span |
| LLM-as-judge, optional | Danh gia whether evidence truly supports qualitative claim |

### 3. Gate policy

| Gate | Blocking trong final | Ghi chu |
|---|---|---|
| Citation coverage | Co | Moi quantitative/catalyst/material claim can lineage |
| Source tier validity | Co | Tier 4/unknown bi block; Tier 3-only material bi block |
| Official source requirement | Co | Ap dung cho quantitative final claim |
| Numeric consistency | Co | Sai tolerance la critical |
| Reconciliation status | Co | Material fact phai matched official hoac manual reviewed |
| Catalyst evidence validity | Co | Event thieu source/evidence/type bi block |
| Generic citation only | Co | Generic label khong du trong final |

### 4. Metrics

| Metric | Threshold final |
|---|---:|
| Quantitative citation coverage | 100% |
| Citation key resolution | 100% |
| Source ID validity | 100% |
| Official source coverage for material quantitative claims | 100% |
| Numeric mismatch rate above tolerance | 0% |
| Tier 3-only material claims | 0 |
| Generic citation labels | 0 |
| Catalyst events without evidence span | 0 |

### 5. Artifact

```json
{
  "run_id": "string",
  "ticker": "DHG",
  "claim_count": 0,
  "quantitative_claim_count": 0,
  "citation_coverage_ratio": 1.0,
  "source_tier_counts": {},
  "official_source_coverage": 1.0,
  "numeric_mismatches": [],
  "generic_citations": [],
  "export_blocked": false
}
```

## Strategic Recommendations

### 1. P0 actions

| Hanh dong | Ket qua |
|---|---|
| Bat buoc claim schema dung `quantitative: true` | Tranh loi contract voi `claim_type == quantitative` |
| Loai bo citation generic khoi final path | Citation phai tro den source/artifact cu the |
| Report renderer chi doc publishable citation map | Khong render citation tu candidate artifact chua pass |

### 2. P1 actions

| Hanh dong | Ket qua |
|---|---|
| Them evidence-support LLM judge cho qualitative claims | Bat claim dung ngu canh nhung suy dien qua nguon |
| Gan materiality level cho claim | Chi phi eval tap trung vao claim co tac dong valuation |
| Tao dashboard unsupported claim categories | Phan loai loi theo data gap, retrieval gap, agent hallucination |
