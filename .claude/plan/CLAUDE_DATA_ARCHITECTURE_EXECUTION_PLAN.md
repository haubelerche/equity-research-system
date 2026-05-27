# Claude Execution Plan — Xây dựng kiến trúc dữ liệu cho Vietnam Pharma Equity Research Agent

## 0. Mục tiêu

Xây dựng hệ thống dữ liệu tối giản nhưng đủ chuẩn cho dự án **Vietnam Pharma Equity Research Agent**.

Hệ thống dữ liệu phải phục vụ đúng pipeline:

```text
ingestion -> canonical facts -> valuation artifacts -> grounded report -> HITL approval
```

Đây là hệ thống dữ liệu cho **equity research ngành dược/y tế Việt Nam**, không phải realtime trading platform, không phải Kafka streaming system, không phải data warehouse doanh nghiệp quy mô lớn.

Mục tiêu chính:

1. Lưu được dữ liệu raw có version và checksum.
2. Chuẩn hóa dữ liệu tài chính thành `canonical_facts`.
3. Tách rõ dữ liệu định lượng, tài liệu bằng chứng, artifacts và workflow state.
4. Hỗ trợ data quality gate trước khi dữ liệu được dùng cho valuation.
5. Hỗ trợ research snapshot để report có thể audit và tái lập.
6. Tránh schema thừa, bảng trùng nghĩa, logic trùng lặp, và over-engineering.

---

## 1. Nguyên tắc context engineering khi làm task này

Claude phải làm theo nguyên tắc **minimal high-signal context**.

### 1.1. Chỉ đọc tài liệu cần thiết

Không đọc toàn bộ repo nếu chưa cần. Đọc theo thứ tự:

```text
1. PRD.md
2. PROBLEM-BRIEF.md
3. VN_PHARMA_DATA_ARCHITECTURE.md nếu có
4. README.md nếu cần kiểm tra cấu trúc repo hiện tại
5. Chỉ đọc file code liên quan trực tiếp đến task hiện tại
```

Không load toàn bộ thư mục `.claude/plan`, `research/third_party`, `notebooks`, hoặc toàn bộ source code nếu chưa có lý do cụ thể.

### 1.2. Ghi chú tiến độ vào file ngắn

Tạo hoặc cập nhật:

```text
.claude/EXECUTION_STATE.md
```

Nội dung tối thiểu:

```markdown
# Execution State

## Current phase

## Completed

## Decisions

## Open issues

## Tests run

## Next step
```

Không ghi log dài. Chỉ ghi quyết định kiến trúc, trạng thái task, lỗi còn mở và lệnh test đã chạy.

### 1.3. Không giữ context thừa

Sau mỗi phase, tóm tắt lại:

```text
- Đã sửa file nào
- Schema/API nào đã tạo
- Test nào đã chạy
- Vấn đề nào còn mở
```

Không nhắc lại toàn bộ nội dung docs nếu không cần.

### 1.4. Không tự mở rộng scope

Không thêm công nghệ hoặc module ngoài kế hoạch nếu không có yêu cầu rõ.

Cấm thêm trong MVP:

```text
Kafka
Redpanda
Snowflake
BigQuery
Airflow
Temporal
Celery/Redis nếu chưa cần batch queue
MinIO nếu local/Supabase Storage đủ dùng
microservices
full realtime streaming
full autonomous ingestion planner
```

---

## 2. Kiến trúc dữ liệu mục tiêu

Thiết kế cuối cùng là **mini financial research lakehouse**:

```text
Source Registry
  -> Raw Zone / Bronze
  -> Parsed-Curated Zone / Silver
  -> Canonical Financial Facts / Gold
  -> Evidence Retrieval Index
  -> Research Snapshot
  -> Analytics + Valuation Artifacts
  -> Report + Evaluation + Approval
```

### 2.1. Data categories

| Nhóm dữ liệu | Ví dụ | Store chính |
|---|---|---|
| Reference data | companies, ticker universe, peer groups | PostgreSQL/Supabase |
| Raw source data | PDF, CSV, JSON API payload, HTML | Object storage/local filesystem |
| Structured financial data | revenue, net income, assets, equity, cash flow | `canonical_facts` |
| Market data | OHLCV, price, volume, market cap | `market_prices` |
| Document evidence | annual report, disclosure, news chunks | `document_chunks` + pgvector optional |
| Derived artifacts | ratios, DCF, multiples, sensitivity | artifact JSON + metadata table |
| Workflow state | research runs, steps, approval, eval | PostgreSQL/Supabase |

### 2.2. Non-goal

Không xây data warehouse lớn. Không xây streaming pipeline. Không dùng vector DB cho số liệu tài chính chính. Không để LLM tạo hoặc sửa financial facts.

---

## 3. Tech stack bắt buộc cho dữ liệu

### 3.1. MVP stack

```text
Python 3.11+
FastAPI
Pydantic v2
SQLAlchemy 2.x
Alembic
PostgreSQL hoặc Supabase Postgres
Local filesystem hoặc Supabase Storage cho raw/artifacts
pandas/numpy cho processing
pytest cho tests
APScheduler hoặc cron cho scheduled refresh
pgvector optional cho document chunks
```

### 3.2. Quy tắc chọn storage

| Dữ liệu | Lưu ở đâu | Lý do |
|---|---|---|
| PDF/CSV/JSON raw | object storage/local filesystem | Không nhét file lớn vào DB |
| Source metadata | DB | Cần query, lineage, dedup |
| Canonical facts | DB | Source of truth cho valuation |
| Market prices | DB | Time-series nhẹ, query dễ |
| Document chunks | DB + optional pgvector | Retrieval có metadata filter |
| Report artifacts | file + DB metadata | Dễ export, dễ audit |
| Research runs | DB | Cần retry/resume/status |

---

## 4. Schema tối thiểu cần xây

Không tạo bảng nếu chưa có use case rõ. Bắt đầu với các bảng sau.

### 4.1. `companies`

Lưu thông tin doanh nghiệp trong universe.

Fields tối thiểu:

```text
company_id PK
ticker unique
exchange
company_name
sector
subsector
currency
is_active
created_at
updated_at
```

### 4.2. `peer_groups`

Lưu peer group có version nhẹ.

```text
peer_group_id PK
ticker
peer_ticker
peer_group_name
valid_from
valid_to nullable
created_at
```

Unique constraint:

```text
(ticker, peer_ticker, peer_group_name, valid_from)
```

### 4.3. `source_registry`

Danh mục nguồn được phép ingest.

```text
source_registry_id PK
source_name
source_type
provider
base_url nullable
reliability_tier
license_note nullable
is_active
created_at
```

`source_type` enum:

```text
market_data
financial_statement
annual_report
disclosure
news
regulatory
tender
manual_golden_dataset
```

### 4.4. `source_versions`

Mỗi lần lấy dữ liệu tạo một version.

```text
source_version_id PK
source_registry_id FK
ticker nullable
source_type
source_uri nullable
raw_path
checksum
retrieved_at
published_date nullable
period nullable
fiscal_year nullable
quarter nullable
parser_version nullable
status
created_at
```

Unique constraint chống duplicate:

```text
(source_registry_id, ticker, checksum)
```

### 4.5. `ingestion_runs`

Theo dõi từng job ingest.

```text
ingestion_run_id PK
job_type
source_type
ticker nullable
started_at
finished_at nullable
status
records_found
records_changed
error_message nullable
created_at
```

### 4.6. `canonical_facts`

Bảng quan trọng nhất. Chỉ dữ liệu đã qua quality gate mới ghi vào đây.

```text
fact_id PK
ticker
metric_name
statement_type
period
fiscal_year
quarter nullable
value numeric
unit
currency
source_version_id FK
parser_version
transformation_method
confidence
validation_status
created_at
updated_at
```

Unique constraint chống trùng fact:

```text
(ticker, metric_name, statement_type, period, source_version_id)
```

Không ghi fact nếu:

```text
source_version_id missing
unit missing
currency missing
validation_status != accepted
confidence < configured threshold
```

### 4.7. `market_prices`

```text
price_id PK
ticker
trade_date
open
high
low
close
volume
market_cap nullable
source_version_id FK
created_at
```

Unique constraint:

```text
(ticker, trade_date, source_version_id)
```

### 4.8. `document_chunks`

Dùng cho evidence retrieval.

```text
chunk_id PK
source_version_id FK
ticker nullable
document_type
section nullable
chunk_index
chunk_text
embedding nullable
fiscal_year nullable
published_date nullable
reliability_tier
checksum
created_at
```

Unique constraint:

```text
(source_version_id, chunk_index, checksum)
```

Không dùng `document_chunks` làm nguồn chính cho số liệu tài chính. Số liệu chính phải nằm ở `canonical_facts`.

### 4.9. `data_quality_reports`

```text
dq_report_id PK
ticker
scope
source_version_id nullable
completeness_score
missing_fields jsonb
conflicting_values jsonb
stale_sources jsonb
warnings jsonb
pass_gate boolean
created_at
```

### 4.10. `research_snapshots`

Đóng băng dữ liệu tại thời điểm tạo report.

```text
snapshot_id PK
ticker
as_of_date
created_by nullable
status
data_freshness_status
created_at
```

### 4.11. `snapshot_items`

Liệt kê các fact/source/chunk/artifact được dùng trong snapshot.

```text
snapshot_item_id PK
snapshot_id FK
item_type
item_id
source_version_id nullable
included_reason
created_at
```

Unique constraint:

```text
(snapshot_id, item_type, item_id)
```

### 4.12. `artifact_versions`

Lưu metadata cho valuation/report/eval artifacts.

```text
artifact_id PK
run_id nullable
snapshot_id nullable
artifact_type
artifact_path
checksum
created_at
created_by nullable
status
```

`artifact_type` enum:

```text
valuation_result
fundamental_analysis
claim_ledger
source_manifest
eval_result
report_md
report_html
run_log
```

### 4.13. `research_runs`

```text
run_id PK
ticker
run_type
snapshot_id nullable
status
started_at
finished_at nullable
error_message nullable
created_at
```

### 4.14. `run_steps`

```text
run_step_id PK
run_id FK
step_name
status
started_at
finished_at nullable
input_summary jsonb nullable
output_summary jsonb nullable
error_message nullable
created_at
```

### 4.15. `approval_events`

```text
approval_event_id PK
run_id FK
artifact_id nullable
approval_type
approved_by nullable
decision
comment nullable
created_at
```

`approval_type`:

```text
assumptions
final_report
manual_data_override
```

### 4.16. `evaluation_results`

```text
evaluation_result_id PK
run_id FK
artifact_id nullable
eval_type
score numeric nullable
pass_gate boolean
metrics jsonb
warnings jsonb
created_at
```

### 4.17. `model_usage_logs`

```text
model_usage_id PK
run_id nullable
step_name
model_name
input_tokens
output_tokens
cost_estimate
latency_ms
stop_reason nullable
created_at
```

---

## 5. Dedup rules

### 5.1. Source-level dedup

Nếu cùng `source_registry_id`, `ticker`, `checksum` đã tồn tại thì không tạo version mới.

Action:

```text
mark ingestion result = no_change
không parse lại
không embed lại
không recompute
```

### 5.2. Fact-level dedup

Nếu cùng:

```text
ticker + metric_name + statement_type + period + source_version_id
```

đã tồn tại, không insert trùng.

Nếu cùng fact logic nhưng khác source version, giữ cả hai nhưng đánh dấu conflict nếu value khác vượt tolerance.

### 5.3. Chunk-level dedup

Nếu cùng `source_version_id + chunk_index + checksum`, không insert trùng.

Nếu tài liệu mới có checksum không đổi, không chunk lại.

### 5.4. Artifact-level dedup

Artifact có cùng checksum không cần ghi lại file mới, nhưng có thể tạo metadata link nếu thuộc run khác.

---

## 6. Data quality gates

### 6.1. Gate trước canonical facts

Một financial fact chỉ được promote vào `canonical_facts` khi:

```text
schema hợp lệ
source_version_id tồn tại
metric_name map được vào taxonomy
period hợp lệ
unit/currency rõ ràng
value parse được thành numeric
không vi phạm sanity rule nghiêm trọng
confidence >= threshold
```

### 6.2. Sanity rules tối thiểu

```text
revenue không âm nếu là annual revenue
assets > 0
equity không null
cash and equivalents >= 0 nếu có
gross_profit <= revenue nếu cùng kỳ
fiscal_year nằm trong khoảng hợp lệ
currency = VND cho doanh nghiệp Việt Nam trừ khi source nói khác
unit phải được chuẩn hóa
```

### 6.3. Conflict handling

Nếu nhiều nguồn cho cùng metric/kỳ nhưng giá trị khác nhau vượt tolerance:

```text
không tự chọn âm thầm
ghi vào data_quality_reports.conflicting_values
đánh dấu needs_review
không dùng fact đó cho valuation nếu chưa resolve
```

---

## 7. Research snapshot policy

Report không được sinh trực tiếp từ live database.

Luồng bắt buộc:

```text
canonical_facts + market_prices + document_chunks + assumptions
  -> create research_snapshot
  -> analytics/valuation đọc từ snapshot
  -> report đọc từ valuation/artifacts/evidence trong snapshot
```

Snapshot phải ghi rõ:

```text
facts nào được dùng
source_versions nào được dùng
chunks nào được dùng
market price ngày nào được dùng
assumptions version nào được dùng
```

Khi dữ liệu mới xuất hiện, report cũ không bị ghi đè. Chỉ đánh dấu artifact cũ là stale nếu cần.

---

## 8. Incremental recompute policy

Không full recompute nếu chỉ một phần dữ liệu thay đổi.

| Dữ liệu thay đổi | Recompute |
|---|---|
| market price | multiples, market context, valuation spread |
| financial statement | ratios, growth, valuation, snapshot freshness |
| annual report | document chunks, evidence index, business/risk narrative |
| disclosure/news | catalyst events, flash memo, affected narrative sections |
| peer group | peer metrics, relative valuation |

Không tự generate full report theo cron. Full report chỉ chạy khi user request hoặc reviewer yêu cầu.

---

## 9. Scheduler policy

MVP dùng APScheduler hoặc cron.

Không dùng Kafka.

Suggested jobs:

```text
refresh_market_prices: daily after market close
check_financial_statements: weekly, daily in reporting season
check_disclosures: daily
check_news: daily or every 2-3 days
check_pharma_catalysts: weekly/daily depending source stability
build_document_index: only when document source_version changed
run_data_quality: after ingest/parse
```

Mọi scheduled job phải ghi vào `ingestion_runs`.

---

## 10. File/module implementation plan

Claude phải triển khai theo thứ tự. Không nhảy phase.

### Phase 0 — Repo audit nhẹ

Goal: xác định cấu trúc hiện tại, không sửa code lớn.

Read only:

```text
README.md
PRD.md
PROBLEM-BRIEF.md
VN_PHARMA_DATA_ARCHITECTURE.md if present
backend/app/core/config.py if exists
backend/app/schemas/* if exists
backend/app/dataops/* if exists
```

Output:

```text
.claude/EXECUTION_STATE.md
short audit summary
list of files to create/update
```

Do not:

```text
Không đọc toàn bộ repo
Không refactor
Không thêm dependencies
```

### Phase 1 — Database migrations

Goal: tạo schema database tối thiểu.

Files allowed:

```text
backend/app/db/base.py
backend/app/db/session.py
backend/app/db/models.py
backend/alembic/*
alembic.ini
```

Tasks:

```text
add SQLAlchemy models
add Alembic migration
add unique constraints
add indexes for ticker/period/source_version_id
```

Acceptance:

```text
alembic upgrade head works
DB tables created
unique constraints present
no business logic in models
```

### Phase 2 — Pydantic data contracts

Files allowed:

```text
backend/app/schemas/data_sources.py
backend/app/schemas/financial_facts.py
backend/app/schemas/snapshots.py
backend/app/schemas/artifacts.py
backend/app/schemas/evaluation.py
```

Tasks:

```text
create SourceRecord / SourceVersion schema
create CanonicalFact schema
create DocumentChunk schema
create ResearchSnapshot schema
create ArtifactVersion schema
create DataQualityReport schema
```

Acceptance:

```text
pydantic validation tests pass
field names align with DB models
no LLM calls
```

### Phase 3 — Storage and checksum utilities

Files allowed:

```text
backend/app/dataops/storage.py
backend/app/dataops/checksum.py
backend/tests/unit/test_checksum.py
backend/tests/unit/test_storage.py
```

Tasks:

```text
save raw payload/file
compute sha256 checksum
return raw_path
support local filesystem storage
```

Acceptance:

```text
same content -> same checksum
different content -> different checksum
storage write/read tests pass
```

### Phase 4 — Ingestion run and source version service

Files allowed:

```text
backend/app/dataops/ingestion.py
backend/app/dataops/source_versions.py
backend/tests/unit/test_source_versions.py
backend/tests/integration/test_ingestion_run.py
```

Tasks:

```text
create ingestion_run
create or reuse source_version by checksum
skip parse if checksum unchanged
record no_change/changed/error status
```

Acceptance:

```text
duplicate raw source does not create duplicate source_version
ingestion status is recorded
idempotency tests pass
```

### Phase 5 — Canonical fact writer

Files allowed:

```text
backend/app/dataops/canonical_facts.py
backend/app/dataops/normalization.py
backend/tests/unit/test_canonical_facts.py
backend/tests/unit/test_normalization.py
```

Tasks:

```text
map raw line items to canonical metric_name
normalize period/unit/currency
write accepted facts only
prevent duplicate facts
flag conflicts
```

Acceptance:

```text
same fact not duplicated
invalid fact rejected
conflict recorded
normalization tests pass
```

### Phase 6 — Data quality gates

Files allowed:

```text
backend/app/dataops/quality_checks.py
backend/app/evaluation/data_eval.py
backend/tests/unit/test_data_quality.py
```

Tasks:

```text
completeness checks
missing field checks
financial sanity checks
stale source checks
conflict checks
write data_quality_reports
```

Acceptance:

```text
missing revenue fails gate
assets <= 0 fails gate
conflict above tolerance becomes needs_review
```

### Phase 7 — Document chunks and evidence index

Files allowed:

```text
backend/app/retrieval/chunking.py
backend/app/retrieval/indexing.py
backend/app/retrieval/retriever.py
backend/tests/unit/test_chunking.py
backend/tests/unit/test_retriever.py
```

Tasks:

```text
chunk document text with metadata
store document_chunks
optional embedding field, but do not require external embedding in unit tests
metadata-first retrieval by ticker/source_type/year
keyword fallback retrieval
```

Acceptance:

```text
chunks dedup by checksum
retrieval filters by ticker
retrieval does not return wrong ticker evidence
```

### Phase 8 — Research snapshot service

Files allowed:

```text
backend/app/dataops/snapshots.py
backend/tests/unit/test_snapshots.py
backend/tests/integration/test_snapshot_creation.py
```

Tasks:

```text
create snapshot for ticker/as_of_date
include selected canonical_facts, market_prices, document_chunks
write snapshot_items
block snapshot if critical data missing unless allow_partial=True
```

Acceptance:

```text
snapshot is reproducible
snapshot_items are unique
report workflow can reference snapshot_id
```

### Phase 9 — Scheduler jobs

Files allowed:

```text
backend/app/jobs/scheduler.py
backend/app/jobs/data_refresh_jobs.py
backend/scripts/run_data_job.py
backend/tests/unit/test_jobs_config.py
```

Tasks:

```text
define job registry
implement manual CLI trigger
add APScheduler optional wiring
record ingestion_runs
```

Acceptance:

```text
manual job can run for one ticker
job writes ingestion_run
no Kafka/Celery required
```

### Phase 10 — Integration with research workflow

Files allowed:

```text
backend/app/agents/data_foundation.py
backend/app/workflows/state.py
backend/app/workflows/gates.py
backend/tests/integration/test_data_foundation_agent.py
```

Tasks:

```text
Data Foundation Agent checks data inventory
creates/loads latest research snapshot
returns DataSnapshot/DataQualityReport
stops workflow if data quality fails
```

Acceptance:

```text
workflow cannot proceed with failed data quality gate
workflow can proceed with valid snapshot
agent does not modify financial facts directly
```

### Phase 11 — Documentation and final verification

Files allowed:

```text
specs/DATA_ARCHITECTURE.md
README.md only if small update is needed
.claude/EXECUTION_STATE.md
```

Tasks:

```text
document final architecture
document schema summary
document scheduler policy
document data quality gates
document how to run tests and migrations
```

Acceptance:

```text
pytest critical tests pass
alembic upgrade head works
data architecture doc matches implementation
no out-of-scope tech added
```

---

## 11. Testing strategy

### 11.1. Unit tests

Required:

```text
test_checksum.py
test_source_versions.py
test_canonical_facts.py
test_normalization.py
test_data_quality.py
test_chunking.py
test_snapshots.py
```

### 11.2. Integration tests

Required:

```text
test_ingestion_run.py
test_snapshot_creation.py
test_data_foundation_agent.py
```

### 11.3. Golden test

Use 1 ticker first, preferably `DHG`.

Goal:

```text
raw sample -> source_version -> canonical_facts -> quality gate -> snapshot
```

Do not require full report generation in data architecture phase.

---

## 12. Definition of done

Data architecture implementation is complete when:

```text
1. Database schema exists with migrations.
2. Source versioning and checksum-based dedup work.
3. Canonical facts can be written and queried.
4. Invalid facts do not enter canonical store.
5. Data quality reports are generated.
6. Document chunks can be stored and retrieved by metadata.
7. Research snapshots can freeze facts/sources/chunks.
8. Ingestion jobs are idempotent.
9. Data Foundation Agent can consume snapshot instead of raw live data.
10. Tests pass for critical data path.
11. No Kafka, Snowflake, Airflow, or unnecessary infra added.
```

---

## 13. Final instruction for Claude

Implement this plan phase by phase.

Before each phase:

```text
- Read only the files listed for that phase.
- Restate the phase goal in 3-5 bullet points.
- List files you will modify.
```

During each phase:

```text
- Keep changes small.
- Prefer deterministic Python over LLM logic.
- Do not alter agent architecture unless the phase explicitly permits it.
- Do not create duplicate modules with overlapping responsibilities.
```

After each phase:

```text
- Run relevant tests.
- Update .claude/EXECUTION_STATE.md.
- Summarize completed changes.
- State next recommended phase.
```

If requirements conflict, follow this priority order:

```text
1. PRD.md
2. PROBLEM-BRIEF.md
3. VN_PHARMA_DATA_ARCHITECTURE.md
4. This execution plan
5. README.md
6. Existing code conventions
```

