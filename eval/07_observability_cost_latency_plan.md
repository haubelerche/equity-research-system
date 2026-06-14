# Observability, Cost, And Latency Evaluation Plan

## Context

Evaluation chi co gia tri van hanh neu moi run co trace, cost, latency, retry, error va gate history. Repo da khai bao `langfuse>=4.0` va model adapter co optional tracing. Langfuse documentation mo ta evaluation nhu mot vong lap online/offline gom trace scoring, datasets, experiments, manual/automated evaluators va score analytics.

## Problem Statement

Neu khong do observability, he thong co the dat quality tren mot run don le nhung khong on dinh khi mo rong sang 53 ma. Cost-to-serve, latency OCR/retrieval/LLM/PDF va flaky external sources phai duoc xem la evaluation dimension, khong phai monitoring phu.

## Technical Deep-Dive

### 0. Current implementation alignment

| Logic hien tai | Dieu chinh trong ke hoach |
|---|---|
| Run status hien co phan biet `blocked`, `failed`, `auto_exported`, `approved` | Observability phai track status transition va blocking gate tai thoi diem chuyen trang thai |
| `PACKAGE_VALIDATION_GATE`, `REPORT_QUALITY_GATE`, `EXPORT_GATE` co `issues`, `blocking_reasons`, `severity`, `summary` | Gate telemetry phai luu du issue code va severity, khong chi boolean pass/fail |
| `authorize_client_final` raise `client_final_render_blocked:<reasons>` | Client-final render failures phai tach khoi PDF renderer failure va gan category governance |
| `model_adapter` co Langfuse optional va tests retry/tracing | Cost/latency eval phai gan trace theo `run_id`, stage va agent role |
| Post-render audit co the them display blockers vao view model | Observability phai log post-render blockers rieng de phan biet data/governance failure voi presentation failure |

### 1. Doi tuong can eval

| Doi tuong | Metrics |
|---|---|
| End-to-end run | Duration, status, blocked stage, retry count |
| LLM calls | Token input/output, cost estimate, latency, model, prompt version |
| Retrieval | Query latency, backend used, hit count, fallback rate |
| OCR/PDF extraction | Pages processed, OCR confidence, extraction failure rate |
| Database/storage | Query latency, write retry count, artifact upload failures |
| PDF rendering | Renderer backend, duration, preflight pass/fail |
| Gates | Pass/fail trend, recurring blocker categories |
| Publication readiness | Approval status, authorization blocker, snapshot mismatch, locked artifact status |
| Post-render audit | Client-final display blocker, HTML/PDF artifact path, strict preflight result |

### 2. Framework va cong nghe

| Cong nghe | Vai tro |
|---|---|
| Langfuse | Trace, score, dataset, experiment, online/offline eval |
| RuntimeStore/PostgreSQL | Run status, steps, artifacts, audit events |
| Python logging | Local diagnostics |
| Pytest performance smoke | Latency regression o muc component |
| Cost ledger trong model adapter | Cost-to-serve theo run |

### 3. Thresholds ban dau

| Metric | Threshold canh bao |
|---|---:|
| Full DHG run duration | > baseline p95 + 30% |
| LLM retry rate | > 5% calls |
| Retrieval fallback rate | > 20% queries neu embedding expected |
| OCR failure rate | > 5% pages material |
| Artifact upload failure | > 0 trong final |
| PDF render failure | > 0 trong final |
| Cost per full report | > budget guard soft limit |
| Gate flakiness | Same input, different gate result |

### 4. Evaluation artifact

```json
{
  "run_id": "string",
  "trace_url": "string",
  "duration_seconds": 0,
  "stage_durations": {},
  "llm": {
    "calls": 0,
    "tokens_input": 0,
    "tokens_output": 0,
    "estimated_cost_usd": 0.0,
    "retry_rate": 0.0
  },
  "retrieval": {
    "queries": 0,
    "p95_latency_ms": 0,
    "fallback_rate": 0.0
  },
  "blocking_gate_categories": [],
  "publication": {
    "readiness_passed": false,
    "authorization_blockers": [],
    "render_mode": "analyst_draft|client_final"
  }
}
```

## Strategic Recommendations

### 1. P0 actions

| Hanh dong | Ket qua |
|---|---|
| Moi run ghi `observability_eval.json` | Debug duoc regression theo run |
| Langfuse session id = `run_id` | Gom trace dung theo bao cao |
| Gate results co issue category | Biet loi tap trung o data, retrieval, finance hay report |

### 2. P1 actions

| Hanh dong | Ket qua |
|---|---|
| Tao Langfuse datasets tu failed traces | Bien loi production thanh regression tests |
| Chay experiments khi doi prompt/model | So sanh quality, latency va cost truoc khi deploy |
| Dashboard p50/p95/p99 latency theo stage | Xac dinh bottleneck OCR, LLM hay PDF |
