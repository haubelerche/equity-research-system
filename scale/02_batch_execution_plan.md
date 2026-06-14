# Batch Execution Plan

## Context

`backend/batch.py` hien co kha nang submit universe runs theo danh sach ticker, nhung co thiet ke toi thieu: doc toan bo universe, tuy chon `--limit`, tao run id deterministic, va submit vao executor. Thiet ke nay phu hop smoke test nhung chua du de van hanh 52 ticker co kiem soat.

## Problem Statement

Batch scale can giai quyet bon van de: chon dung ticker, gioi han tai nguyen, resume an toan, va quan sat duoc failure. Neu khong co cac control nay, mot lan batch co the tao nhieu run trung lap, tieu ton token vao ticker chua ready, va de lai artifact kho audit.

## Technical Deep-Dive

### Required CLI Expansion

De xuat nang cap batch runner voi cac tham so:

```text
python -m backend.batch \
  --tickers IMP,DMC,TRA,DBD \
  --segment pharma \
  --exclude DHG \
  --max-concurrency 3 \
  --max-cost-usd 25 \
  --mode draft_only \
  --resume failed \
  --readiness-min-score 70 \
  --dry-run
```

| Option | Muc dich | Default de xuat |
|---|---|---|
| `--tickers` | Chay subset ro rang | empty, dung universe filter |
| `--segment` | Loc theo `pharma`, `healthcare_services`, `medical_equipment`, `medical_distribution` | all |
| `--exclude` | Loai ticker nhu DHG khi da co pilot | empty |
| `--max-concurrency` | Giam DB contention va LLM rate-limit | 2-3 |
| `--max-cost-usd` | Chan batch khi vuot budget | theo settings |
| `--mode` | `data_refresh`, `draft_only`, `full_report`, `client_final` | `draft_only` |
| `--resume` | `none`, `failed`, `blocked`, `all` | `failed` |
| `--readiness-min-score` | Khong submit ticker chua dat readiness | 70 |
| `--dry-run` | In danh sach run va estimated cost, khong submit | false |

### Batch Lifecycle

```text
load universe
-> apply ticker/segment/exclude filters
-> load readiness records
-> reject below readiness threshold
-> estimate cost and runtime
-> create batch manifest
-> submit bounded concurrent runs
-> poll status
-> classify failure reasons
-> write batch summary artifact
```

### Batch Manifest

Moi batch nen ghi manifest:

```yaml
batch_manifest:
  batch_id:
  created_at:
  requested_by:
  mode:
  filters:
    tickers:
    segment:
    exclude:
    readiness_min_score:
  budget:
    max_cost_usd:
    estimated_cost_usd:
  execution:
    max_concurrency:
    resume_policy:
  run_ids:
  rejected_tickers:
    ticker:
    reason:
  status_summary:
```

### Failure Taxonomy

| Failure Class | Example Reason | Owner |
|---|---|---|
| `data_blocked` | Missing financial statements, stale snapshot | Data ingestion |
| `archetype_blocked` | Non-pharma ticker using pharma driver model | Modeling |
| `valuation_blocked` | Missing debt, cash, shares, WACC decomposition | Valuation |
| `citation_blocked` | Quantitative claims without lineage | Evidence/report |
| `publication_blocked` | Missing approval or publishable artifact | Governance |
| `runtime_failed` | DB/network/render exception | Platform |

## Strategic Recommendations

1. Mac dinh batch scale nen la `draft_only`, khong phai `client_final`.
2. Khong cho phep batch all-universe neu khong co `--dry-run` truoc.
3. Moi wave nen co `batch_summary.json` va `batch_summary.md`.
4. Khi mot ticker fail, he thong can ghi failure class va blocking reasons thay vi chi ghi exception string.
5. Concurrency nen bat dau tu 2-3 run song song, sau do moi tang khi DB, LLM rate limit va renderer on dinh.

