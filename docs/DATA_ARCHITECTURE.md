# Thiết kế hệ thống dữ liệu cho Vietnam Pharma Equity Research Agent

## 1. Mục tiêu

Tài liệu này mô tả thiết kế dữ liệu tối ưu cho dự án **Vietnam Pharma Equity Research Agent**. Hệ thống không được thiết kế như một nền tảng dữ liệu thời gian thực, mà là một **research data platform chuyên biệt cho cổ phiếu dược/y tế Việt Nam**.

Mục tiêu chính:

- Thu thập dữ liệu từ các nguồn Việt Nam có liên quan đến doanh nghiệp dược/y tế.
- Chuẩn hóa dữ liệu thành `canonical facts` dùng được cho phân tích và định giá.
- Lưu vết nguồn, phiên bản, checksum, parser version và trạng thái kiểm định.
- Hỗ trợ sinh báo cáo có citation, valuation artifact, audit trail và human approval.
- Tránh thiết kế thừa: không dùng Kafka, không dùng streaming phức tạp, không dùng data warehouse lớn như Snowflake/BigQuery trong MVP.

Nguyên tắc cốt lõi:

```text
Facts before narrative.
Quality before persistence.
Snapshot before report.
Incremental refresh over full recompute.
PostgreSQL/Supabase as source of truth.
Object storage for raw files and generated artifacts.
```

---

## 2. Bản chất bài toán dữ liệu

Dữ liệu ngành dược/y tế Việt Nam có độ biến động thấp đến trung bình. Phần lớn dữ liệu phục vụ equity research không thay đổi theo giây/phút, mà theo ngày, quý, năm hoặc khi có công bố/catalyst mới.

Vì vậy, hệ thống nên dùng:

```text
Scheduled batch ingestion
+ manual verification
+ canonical fact store
+ research snapshot
+ incremental recompute
+ audit trail
```

Không nên dùng:

```text
Kafka-first architecture
realtime streaming
full recompute mỗi ngày
LLM tự đọc dữ liệu raw và tự suy luận số liệu
```

---

## 3. Các nhóm dữ liệu cần quản lý

| Nhóm dữ liệu | Ví dụ | Độ biến động | Cách quản lý |
|---|---|---:|---|
| Reference data | Ticker, sàn, tên công ty, peer group, subsector | Rất thấp | YAML + bảng cấu hình trong DB |
| Market data | Giá đóng cửa, volume, market cap, P/E, P/B | Hằng ngày | Bảng `market_prices` |
| Financial statements | BCTC quý/năm, income statement, balance sheet, cash flow | Theo quý/năm | `canonical_facts` sau validation |
| Annual reports | Báo cáo thường niên, báo cáo quản trị | Theo năm | Object storage + `document_chunks` |
| Disclosures | Công bố thông tin, nghị quyết, cổ tức, phát hành | Không đều | Object storage + event table |
| News/catalysts | Tin doanh nghiệp, đấu thầu, BHYT, regulatory notices | Không đều | `corporate_events` + evidence chunks |
| Derived analytics | Ratios, growth, margins, peer metrics | Khi facts thay đổi | Artifact hoặc bảng derived |
| Valuation artifacts | DCF, multiples, sensitivity, scenarios | Khi assumptions/facts/price thay đổi | `valuation_results` + artifact JSON |
| Workflow/audit | Research runs, steps, approvals, eval results | Theo từng run | Workflow tables |

---

## 4. Kiến trúc dữ liệu tổng thể

Hệ thống nên được thiết kế như một **mini financial data lakehouse** gồm 5 lớp.

```text
Source Registry
    ↓
Raw Zone 
    ↓
Parsed & Normalized Zone 
    ↓
Canonical Financial Warehouse 
    ↓
Research Snapshot
    ↓
Analytics + Valuation + Report Artifacts
```

### 4.1. Source Registry

Lưu danh mục nguồn được phép dùng.

Ví dụ nguồn:

- Vnstock hoặc API dữ liệu thị trường hợp lệ.
- File CSV/golden dataset do nhóm kiểm toán thủ công.
- Báo cáo tài chính.
- Báo cáo thường niên.
- Công bố thông tin doanh nghiệp.
- Tin tức doanh nghiệp/ngành.
- Nguồn đấu thầu, BHYT, regulatory nếu có quyền truy cập hợp lệ.

Mỗi nguồn cần có:

```text
source_id
source_name
source_type
provider
base_url_or_path
reliability_tier
license_note
enabled
```

### 4.2. Raw Zone

Lưu dữ liệu gốc, không chỉnh sửa.

Ví dụ:

```text
storage/raw/
├── market_data/
├── financial_statements/
├── annual_reports/
├── disclosures/
├── news/
└── manual_uploads/
```

Quy tắc:

- Raw file là immutable.
- Nếu nguồn thay đổi, tạo phiên bản mới.
- Không dùng raw data trực tiếp cho valuation/report.
- Mỗi raw object phải có checksum để dedup và phát hiện thay đổi.

### 4.3. Parsed & Normalized Zone 

Chuyển raw data thành cấu trúc thống nhất.

Nhiệm vụ:

- Chuẩn hóa ticker.
- Chuẩn hóa kỳ báo cáo.
- Chuẩn hóa đơn vị và tiền tệ.
- Map line item về taxonomy nội bộ.
- Parse document thành text/chunks.
- Chuẩn hóa news/disclosures thành event records.

Ví dụ mapping:

```text
"Doanh thu thuần" → revenue
"Lợi nhuận sau thuế" → net_income
"Tổng tài sản" → total_assets
"Vốn chủ sở hữu" → total_equity
```

### 4.4. Canonical Financial Warehouse (quan trọng nhất)

Đây là lớp sự thật tài chính đã kiểm định. Chỉ dữ liệu qua validation mới được ghi vào đây.

Dùng cho:

- Ratio calculation.
- Peer comparison.
- DCF/multiples.
- Numeric consistency check.
- Citation cho claim định lượng.

Không cho phép:

- LLM ghi trực tiếp vào canonical facts.
- Số liệu thiếu source/version.
- Ghi đè fact cũ mà không tạo version.

### 4.5. Research Snapshot

Mỗi report phải sinh từ một snapshot đã đóng băng.

Snapshot ghi lại:

- Facts nào được dùng.
- Market price ngày nào được dùng.
- Document chunks nào được dùng.
- Assumptions version nào được dùng.
- Valuation artifact version nào được dùng.

Nguyên tắc:

```text
Report không query dữ liệu live trực tiếp.
Report chỉ đọc từ research_snapshot + artifacts đã khóa nguồn.
```

---

## 5. Tech stack đề xuất

### 5.1. MVP stack

| Layer | Công nghệ | Vai trò |
|---|---|---|
| Backend API | FastAPI | API cho research run, report, approval |
| Workflow | LangGraph | Stateful multi-agent workflow |
| Schema | Pydantic v2 | Data contract và structured output |
| Database | Supabase PostgreSQL hoặc PostgreSQL local | Source of truth cho metadata/facts/runs |
| Object storage | Supabase Storage hoặc local filesystem | Raw files, PDFs, JSON, generated reports |
| Retrieval | PostgreSQL full-text search + pgvector | Evidence retrieval cho documents |
| Scheduler | APScheduler hoặc cron | Batch refresh theo lịch |
| Data processing | pandas, numpy | Normalize và financial calculations |
| Validation | Pydantic + pytest + custom checks | Schema validation và financial sanity checks |
| Reporting | Jinja2 + Markdown/HTML | Render report package |
| HITL UI | Streamlit | Giao diện duyệt assumptions/report |

### 5.2. Không dùng trong MVP

| Công nghệ | Lý do chưa cần |
|---|---|
| Kafka | Dữ liệu không realtime, volume thấp, vận hành phức tạp |
| Snowflake/BigQuery | Quy mô 5–23 mã chưa cần data warehouse cloud lớn |
| Qdrant/Weaviate | pgvector đủ cho MVP và dễ quản lý hơn |
| Celery/Redis | Chỉ cần khi batch nhiều mã hoặc job dài |
| MinIO/S3 riêng | Supabase Storage/local filesystem đủ cho giai đoạn đầu |
| Microservices | Tăng độ phức tạp, không tăng chất lượng report |

---

## 6. Database schema tối thiểu

### 6.1. Nhóm source và ingestion

```text
source_registry
source_versions
raw_objects
ingestion_runs
```

#### `source_registry`

Lưu nguồn dữ liệu được phép dùng.

```text
source_id
source_name
source_type
provider
base_url_or_path
reliability_tier
license_note
enabled
created_at
```

#### `source_versions`

Lưu từng phiên bản dữ liệu lấy về.

```text
source_version_id
source_id
ticker
period
published_date
retrieved_at
raw_object_id
checksum
version_status
created_at
```

#### `raw_objects`

Lưu metadata của file raw, không lưu file lớn trực tiếp trong DB.

```text
raw_object_id
storage_path
mime_type
file_size
checksum
created_at
```

#### `ingestion_runs`

Lưu lịch sử ingest.

```text
ingestion_run_id
job_type
source_type
ticker
started_at
finished_at
status
records_found
records_changed
error_message
```

---

### 6.2. Nhóm warehouse tài chính

```text
companies
ticker_universe
canonical_facts
market_prices
financial_metrics
peer_groups
```

#### `companies`

```text
company_id
ticker
exchange
company_name
subsector
currency
status
created_at
```

#### `ticker_universe`

```text
universe_id
ticker
enabled
priority_group
mvp_flag
notes
```

#### `canonical_facts`

Bảng quan trọng nhất của hệ thống.

```text
fact_id
ticker
metric_name
statement_type
fiscal_year
quarter
period
value
unit
currency
source_version_id
parser_version
transformation_method
confidence
validation_status
created_at
```

Ràng buộc dedup khuyến nghị:

```text
unique(ticker, metric_name, statement_type, period, source_version_id)
```

#### `market_prices`

```text
ticker
trade_date
open
high
low
close
volume
market_cap
source_version_id
created_at
```

Ràng buộc dedup:

```text
unique(ticker, trade_date, source_version_id)
```

#### `financial_metrics`

Lưu chỉ số đã tính bằng code.

```text
metric_id
ticker
period
metric_name
value
unit
input_fact_ids
calculation_method
calculation_version
created_at
```

---

### 6.3. Nhóm document/evidence retrieval

```text
documents
document_chunks
corporate_events
```

#### `documents`

```text
document_id
ticker
source_version_id
document_type
title
published_date
language
storage_path
checksum
reliability_tier
created_at
```

#### `document_chunks`

```text
chunk_id
document_id
ticker
section
chunk_text
embedding
fiscal_year
published_date
reliability_tier
checksum
created_at
```

Ràng buộc dedup:

```text
unique(document_id, checksum)
```

#### `corporate_events`

```text
event_id
ticker
event_type
event_date
title
summary
materiality_score
source_version_id
affected_sections
created_at
```

---

### 6.4. Nhóm research snapshot và artifact

```text
research_snapshots
snapshot_items
valuation_results
artifact_versions
```

#### `research_snapshots`

```text
snapshot_id
ticker
as_of_date
created_by
created_at
status
data_freshness_status
```

#### `snapshot_items`

```text
snapshot_id
item_type
item_id
source_version_id
included_reason
created_at
```

#### `valuation_results`

```text
valuation_id
snapshot_id
ticker
method
scenario
fair_value_per_share
assumptions_json
sensitivity_json
input_metric_ids
created_at
```

#### `artifact_versions`

```text
artifact_id
run_id
snapshot_id
artifact_type
storage_path
checksum
version
created_at
```

Artifact types:

```text
valuation_result
claim_ledger
source_manifest
eval_result
report_md
report_html
run_log
```

---

### 6.5. Nhóm workflow, approval và evaluation

```text
research_runs
run_steps
approval_events
evaluation_results
model_usage_logs
```

#### `research_runs`

```text
run_id
ticker
run_type
snapshot_id
status
started_at
finished_at
created_by
stop_reason
```

#### `run_steps`

```text
step_id
run_id
step_name
status
started_at
finished_at
error_message
input_summary
output_summary
```

#### `approval_events`

```text
approval_id
run_id
artifact_id
approval_type
reviewer_id
decision
comment
created_at
```

#### `evaluation_results`

```text
eval_id
run_id
snapshot_id
citation_coverage
numeric_consistency_score
hallucination_risk_score
valuation_reproducibility
final_gate_status
created_at
```

#### `model_usage_logs`

```text
usage_id
run_id
step_id
model_name
input_tokens
output_tokens
estimated_cost
latency_ms
retry_count
created_at
```

---

## 7. Data pipeline chuẩn

### 7.1. Batch ingestion pipeline

```text
Scheduler / Manual Trigger
    ↓
Connector
    ↓
Save raw object
    ↓
Compute checksum
    ↓
Dedup check
    ↓
Parse / normalize
    ↓
Validate / reconcile
    ↓
Promote to canonical store
    ↓
Update document chunks / evidence index
    ↓
Mark affected artifacts as stale
```

### 7.2. Research report pipeline

```text
User request
    ↓
Check data inventory + freshness
    ↓
Create research snapshot
    ↓
Run analytics from canonical facts
    ↓
Run valuation from analytics artifacts
    ↓
Retrieve evidence from document chunks
    ↓
Generate grounded report
    ↓
Run evaluation gates
    ↓
HITL approval
    ↓
Export report package
```

---

## 8. Dedup và versioning

### 8.1. Dedup theo checksum

Mỗi raw file/API response phải tính checksum.

```text
checksum = hash(raw_content)
```

Nếu checksum không đổi:

```text
status = no_change
không parse lại
không embed lại
không tạo fact mới
```

Nếu checksum thay đổi:

```text
lưu source_version mới
parse lại source đó
validate lại facts liên quan
invalidate artifacts phụ thuộc
```

### 8.2. Dedup theo business key

Financial facts không được trùng theo business key.

Business key:

```text
ticker + metric_name + statement_type + period + source_version_id
```

Document chunks không được trùng theo:

```text
document_id + chunk_checksum
```

Market prices không được trùng theo:

```text
ticker + trade_date + source_version_id
```

### 8.3. Không update đè dữ liệu đã dùng trong report

Nếu fact đã được dùng trong một `research_snapshot`, không được sửa trực tiếp. Phải tạo version mới và để report sau dùng version mới.

---

## 9. Data quality gates

Dữ liệu chỉ được promote vào canonical store nếu qua gate.

### 9.1. Schema checks

- Đúng kiểu dữ liệu.
- Đúng ticker.
- Đúng period.
- Đúng currency/unit.
- Không thiếu trường bắt buộc.

### 9.2. Financial sanity checks

- Doanh thu không được null nếu là BCTC chính.
- Tổng tài sản phải lớn hơn 0.
- Vốn chủ sở hữu không được thiếu.
- Gross profit không được lớn hơn revenue nếu có đủ dữ liệu.
- Cash flow period phải khớp fiscal period.
- EPS không dùng nếu shares outstanding thiếu hoặc không rõ.

### 9.3. Reconciliation checks

- Subtotal và total phải khớp trong tolerance.
- Cùng một metric từ nhiều nguồn phải được so sánh.
- Nếu nguồn mâu thuẫn, không tự chọn theo LLM; phải dùng rule hoặc human review.

### 9.4. Source confidence

Gợi ý thứ tự độ tin cậy:

```text
official filings / company disclosure
> exchange disclosure
> reputable financial data provider
> reputable media
> third-party unknown
> manual unverified
```

---

## 10. Freshness policy

Dữ liệu không cần realtime, nhưng phải có freshness rule rõ ràng.

```yaml
freshness_policy:
  market_price:
    max_age_days: 1
    action_if_stale: refresh_before_report

  financial_statement:
    max_age_days: 30
    action_if_stale: check_source_before_report

  annual_report:
    max_age_days: 180
    action_if_stale: warn_only

  disclosure:
    max_age_days: 7
    action_if_stale: refresh_before_report

  news:
    max_age_days: 7
    action_if_stale: refresh_before_report

  peer_group:
    max_age_days: 180
    action_if_stale: manual_review
```

---

## 11. Lịch cập nhật dữ liệu đề xuất

| Job | Tần suất MVP | Ghi chú |
|---|---:|---|
| `refresh_market_prices` | Hằng ngày sau giờ giao dịch | Cập nhật giá và multiples |
| `check_financial_statements` | Hằng tuần; hằng ngày trong mùa báo cáo | BCTC quý/năm |
| `check_annual_reports` | Hằng tuần hoặc manual upload | BCTN theo năm |
| `check_disclosures` | Hằng ngày | Công bố thông tin có thể ảnh hưởng valuation |
| `check_news` | Hằng ngày hoặc 2–3 ngày/lần | Tin ngành dược không quá dày |
| `check_pharma_catalysts` | Hằng tuần hoặc hằng ngày nếu nguồn ổn định | Đấu thầu/BHYT/regulatory |
| `build_document_index` | Chỉ khi có document mới | Không embed lại toàn bộ |
| `generate_full_report` | Khi user yêu cầu | Không cron-generate toàn bộ report |

---

## 12. Incremental recompute

Không chạy lại toàn bộ pipeline nếu chỉ một phần dữ liệu thay đổi.

| Dữ liệu mới | Cần recompute | Không cần recompute |
|---|---|---|
| Giá mới | Market multiples, valuation spread, price chart | Business profile, annual report summary |
| BCTC mới | Ratios, growth, peer metrics, DCF | Document chunks cũ |
| Báo cáo thường niên mới | Business narrative, risk evidence, document index | Market price history |
| Công bố cổ tức/phát hành | Share count, dividend/corporate event, valuation per share | Toàn bộ financial history |
| Tin/catalyst lớn | Catalyst section, scenario assumptions, flash memo | Full report nếu materiality thấp |

Mỗi artifact cần có dependency metadata để biết khi nào stale.

---

## 13. Vai trò của Data Foundation Agent

`Data Foundation Agent` không được tự crawl hoặc tự sửa dữ liệu tùy ý. Agent này chỉ điều phối các tool dữ liệu theo config.

Nhiệm vụ:

1. Nhận `ResearchPlan` từ Orchestrator.
2. Kiểm tra data inventory của ticker.
3. Kiểm tra freshness theo từng source.
4. Nếu thiếu/stale, gọi đúng connector/job.
5. Lấy canonical facts mới nhất.
6. Lấy evidence chunks liên quan.
7. Tạo `DataSnapshot` hoặc `ResearchSnapshot`.
8. Tạo `DataQualityReport`.
9. Nếu fail gate, dừng hoặc chuyển human review.

Không được:

- Tự sửa số liệu thiếu nguồn.
- Tự forecast số liệu còn thiếu.
- Tự chọn nguồn ngoài allowlist.
- Tự kết luận doanh nghiệp tốt/xấu.
- Ghi vào canonical facts khi chưa qua validation.

---

## 14. Report package và artifact storage

Mỗi research run sinh một report package.

```text
artifacts/
├── reports/{run_id}_{ticker}_report.md
├── reports_html/{run_id}_{ticker}_report.html
├── valuation_results/{run_id}_{ticker}_valuation_result.json
├── claim_ledgers/{run_id}_{ticker}_claim_ledger.json
├── source_manifests/{run_id}_{ticker}_source_manifest.json
├── eval_results/{run_id}_{ticker}_eval_result.json
└── run_logs/{run_id}_{ticker}_run_log.json
```

DB chỉ lưu metadata và `storage_path`, không lưu toàn bộ nội dung artifact lớn trong bảng.

---

## 15. Thứ tự triển khai tối ưu

### Phase 1 — Data foundation tối thiểu

- Tạo PostgreSQL/Supabase schema.
- Tạo `source_registry`, `source_versions`, `raw_objects`, `canonical_facts`.
- Ingest golden dataset cho 5 mã MVP hoặc ít nhất 3 mã đầu.
- Implement checksum dedup.
- Implement validation cơ bản.

### Phase 2 — Financial warehouse

- Chuẩn hóa financial statements thành canonical facts.
- Tạo `market_prices`.
- Tạo `financial_metrics` bằng code.
- Tạo unit tests cho ratios và metrics.

### Phase 3 — Evidence retrieval

- Tạo `documents` và `document_chunks`.
- Chunk documents theo metadata.
- Dùng PostgreSQL full-text search trước.
- Thêm pgvector khi cần semantic search.

### Phase 4 — Research snapshot

- Tạo `research_snapshots` và `snapshot_items`.
- Report/valuation chỉ đọc từ snapshot.
- Tạo artifact versioning.

### Phase 5 — Evaluation và HITL

- Tạo `evaluation_results`, `approval_events`, `model_usage_logs`.
- Chặn export nếu fail citation/numeric/valuation gate.
- Lưu approval history theo artifact version.

---

## 16. Quyết định thiết kế cuối cùng

### Nên làm

- Dùng PostgreSQL/Supabase làm source of truth.
- Lưu raw files trong object storage/local filesystem.
- Dùng checksum để dedup.
- Dùng canonical facts cho mọi phép tính tài chính.
- Dùng research snapshot trước khi sinh report.
- Dùng incremental recompute.
- Dùng pgvector chỉ cho evidence retrieval, không cho số liệu chính.
- Dùng cron/APScheduler cho batch refresh.

### Không nên làm trong MVP

- Không dùng Kafka.
- Không dùng Snowflake/BigQuery.
- Không dùng microservices.
- Không cron-generate full report mỗi ngày cho mọi ticker.
- Không để LLM ghi hoặc sửa financial facts.
- Không embed toàn bộ financial table rồi để LLM tìm số.
- Không update đè fact đã được dùng trong report.

---

## 17. Kết luận

Hệ thống dữ liệu của dự án nên là một **mini financial research lakehouse** cho ngành dược/y tế Việt Nam, không phải realtime streaming platform.

Thiết kế tối ưu là:

```text
PostgreSQL/Supabase
+ object storage
+ scheduled batch ingestion
+ canonical facts
+ document evidence index
+ research snapshot
+ artifact versioning
+ evaluation/HITL audit
```

Kiến trúc này đủ mạnh để đảm bảo:

- Dữ liệu không bị trùng lặp.
- Mọi số liệu có nguồn và version.
- Báo cáo có thể tái lập.
- Valuation không phụ thuộc vào LLM.
- Claim định lượng có citation.
- Workflow có thể resume/retry/review.
- Hệ thống không bị phức tạp quá mức so với bản chất dữ liệu ngành dược Việt Nam.
