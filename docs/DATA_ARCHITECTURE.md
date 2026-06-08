 Thiet ke he thong du lieu cho Vietnam Pharma Equity Research Agent

## 1. Muc tieu

Tai lieu nay mo ta thiet ke du lieu toi uu cho du an **Vietnam Pharma Equity Research Agent**. He thong khong duoc thiet ke nhu mot nen tang du lieu thoi gian thuc, ma la mot **research data platform chuyen biet cho co phieu duoc/y te Viet Nam**.

Muc tieu chinh:

- Thu thap du lieu tu cac nguon Viet Nam co lien quan den doanh nghiep duoc/y te.
- Chuan hoa du lieu thanh `canonical facts` dung duoc cho phan tich va dinh gia.
- Luu vet nguon, phien ban, checksum, parser version va trang thai kiem dinh.
- Ho tro sinh bao cao co citation, valuation artifact, audit trail va human approval.
- Tranh thiet ke thua: khong dung Kafka, khong dung streaming phuc tap, khong dung data warehouse lon nhu Snowflake/BigQuery trong MVP.

Nguyen tac cot loi:

```text
Facts before narrative.
Quality before persistence.
Snapshot before report.
Incremental refresh over full recompute.
PostgreSQL/Supabase as source of truth.
Object storage for raw files and generated artifacts.
```

---

## 2. Ban chat bai toan du lieu

Du lieu nganh duoc/y te Viet Nam co do bien dong thap den trung binh. Phan lon du lieu phuc vu equity research khong thay doi theo giay/phut, ma theo ngay, quy, nam hoac khi co cong bo/catalyst moi.

Vi vay, he thong nen dung:

```text
Scheduled batch ingestion
+ manual verification
+ canonical fact store
+ research snapshot
+ incremental recompute
+ audit trail
```

Khong nen dang:

```text
Kafka-first architecture
realtime streaming
full recompute moi ngay
LLM tu doc du lieu raw va tu suy luan so lieu
```

---

## 3. Cac nhom du lieu can quan ly

| Nhom du lieu | Vi du | Do bien dong | Cach quan ly |
|---|---|---:|---|
| Reference data | Ticker, san, tan cong ty, peer group, subsector | Rat thap | YAML + bang cau hinh trong DB |
| Market data | Gia dong cua, volume, market cap, P/E, P/B | Hang ngay | Bang `market_prices` |
| Financial statements | BCTC quy/nam, income statement, balance sheet, cash flow | Theo quy/nam | `canonical_facts` sau validation |
| Annual reports | Bao cao thuong nien, bao cao quon tra | Theo nam | Object storage + `document_chunks` |
| Disclosures | Cong bo thong tin, ngha quyet, co tuc, phat hanh | Khong dau | Object storage + event table |
| News/catalysts | Tin doanh nghiep, dau thau, BHYT, regulatory notices | Khong dau | `corporate_events` + evidence chunks |
| Derived analytics | Ratios, growth, margins, peer metrics | Khi facts thay doi | Artifact hoac bang derived |
| Valuation artifacts | DCF, multiples, sensitivity, scenarios | Khi assumptions/facts/price thay doi | `valuation_results` + artifact JSON |
| Workflow/audit | Research runs, steps, approvals, eval results | Theo tung run | Workflow tables |

---

## 4. Kien truc du lieu tong the

He thong nan duoc thiet ke nhu mot **mini financial data lakehouse** gam 5 lop.

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

Luu danh muc nguon duoc phep dang.

Vi du nguon:

- Vnstock hoac API du lieu thi truong hop le.
- File CSV/golden dataset do nham kiem toan thu cong.
- Bao cao tai chinh.
- Bao cao thuong nien.
- Cong bo thong tin doanh nghiep.
- Tin tuc doanh nghiep/nganh.
- Nguon dau thau, BHYT, regulatory neu co quyen truy cap hop le.

Moi nguon can co:

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

Luu du lieu goc, khong chinh sua.

Vi du:

```text
storage/raw/
+-- market_data/
+-- financial_statements/
+-- annual_reports/
+-- disclosures/
+-- news/
+-- manual_uploads/
```

Quy tec:

- Raw file la immutable.
- Neu nguon thay doi, tao phien ban moi.
- Khong dung raw data truc tiep cho valuation/report.
- Moi raw object phoi co checksum da dedup va phat hien thay doi.

### 4.3. Parsed & Normalized Zone 

Chuyen raw data thanh cau truc thong nhat.

Nhiem vu:

- Chuan hoa ticker.
- Chuan hoa ky bao cao.
- Chuan hoa don vi va tien te.
- Map line item va taxonomy noi bo.
- Parse document thanh text/chunks.
- Chuan hoa news/disclosures thanh event records.

Vi du mapping:

```text
"Doanh thu thuon" a revenue
"Loi nhuon sau thuo" a net_income
"Tang tai san" a total_assets
"Van chi so hau" a total_equity
```

### 4.4. Canonical Financial Warehouse (quan trong nhat)

aay la lop sa that tai chinh da kiem dinh. Cha du lieu qua validation moi duoc ghi vao day.

Dang cho:

- Ratio calculation.
- Peer comparison.
- DCF/multiples.
- Numeric consistency check.
- Citation cho claim dinh luong.

Khong cho phep:

- LLM ghi truc tiep vao canonical facts.
- Sa lieu thieu source/version.
- Ghi de fact cu ma khong tao version.

### 4.5. Research Snapshot

Moi report phoi sinh tu mot snapshot da dong bang.

Snapshot ghi loi:

- Facts nao duoc dang.
- Market price ngay nao duoc dang.
- Document chunks nao duoc dang.
- Assumptions version nao duoc dang.
- Valuation artifact version nao duoc dang.

Nguyan tuc:

```text
Report khong query du lieu live truc tiep.
Report cha dac tu research_snapshot + artifacts da khoa nguon.
```

---

## 5. Tech stack da xuot

### 5.1. MVP stack

| Layer | Cong nghe | Vai tro |
|---|---|---|
| Backend API | FastAPI | API cho research run, report, approval |
| Workflow | LangGraph | Stateful multi-agent workflow |
| Schema | Pydantic v2 | Data contract va structured output |
| Database | Supabase PostgreSQL hoac PostgreSQL local | Source of truth cho metadata/facts/runs |
| Object storage | Supabase Storage hoac local filesystem | Raw files, PDFs, JSON, generated reports |
| Retrieval | PostgreSQL full-text search + pgvector | Evidence retrieval cho documents |
| Scheduler | APScheduler hoac cron | Batch refresh theo lach |
| Data processing | pandas, numpy | Normalize va financial calculations |
| Validation | Pydantic + pytest + custom checks | Schema validation va financial sanity checks |
| Reporting | Jinja2 + Markdown/HTML | Render report package |
| HITL UI | Streamlit | Giao dien duyet assumptions/report |

### 5.2. Khong dung trong MVP

| Cong nghe | Ly do chua can |
|---|---|
| Kafka | Du lieu khong realtime, volume thap, van hanh phuc tap |
| Snowflake/BigQuery | Quy mo 5a23 ma chua can data warehouse cloud lan |
| Qdrant/Weaviate | pgvector du cho MVP va de quan ly hon |
| Celery/Redis | Cha can khi batch nhieu ma hoac job dai |
| MinIO/S3 riang | Supabase Storage/local filesystem du cho giai doin dau |
| Microservices | Tang da phuc tap, khong tang chat luong report |

---

## 6. Database schema toi thieu

### 6.1. Nhom source va ingestion

```text
source_registry
source_versions
raw_objects
ingestion_runs
```

#### `source_registry`

Luu nguon du lieu duoc phep dang.

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

Luu tung phien ban du lieu lay ve.

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

Luu metadata cua file raw, khong luu file lan truc tiep trong DB.

```text
raw_object_id
storage_path
mime_type
file_size
checksum
created_at
```

#### `ingestion_runs`

Luu lich su ingest.

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

### 6.2. Nhom warehouse tai chinh

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

Bang quan trong nhat caa he thong.

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

Rang buoc dedup khuyen nghi:

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

Rang buoc dedup:

```text
unique(ticker, trade_date, source_version_id)
```

#### `financial_metrics`

Luu chi so da tinh bang code.

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

### 6.3. Nhom document/evidence retrieval

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

Rang buoc dedup:

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

### 6.4. Nhom research snapshot va artifact

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

### 6.5. Nhom workflow, approval va evaluation

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

## 7. Data pipeline chuan

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

## 8. Dedup va versioning

### 8.1. Dedup theo checksum

Moi raw file/API response phoi tinh checksum.

```text
checksum = hash(raw_content)
```

Neu checksum khong doi:

```text
status = no_change
khong parse loi
khong embed loi
khong tao fact moi
```

Neu checksum thay doi:

```text
luu source_version moi
parse loi source da
validate loi facts lien quan
invalidate artifacts pha thuoc
```

### 8.2. Dedup theo business key

Financial facts khong duoc trang theo business key.

Business key:

```text
ticker + metric_name + statement_type + period + source_version_id
```

Document chunks khong duoc trang theo:

```text
document_id + chunk_checksum
```

Market prices khong duoc trang theo:

```text
ticker + trade_date + source_version_id
```

### 8.3. Khong update da du lieu da dung trong report

Neu fact da duoc dung trong mot `research_snapshot`, khong duoc saa truc tiep. Phoi tao version moi va da report sau dung version moi.

---

## 9. Data quality gates

Du lieu cha duoc promote vao canonical store neu qua gate.

### 9.1. Schema checks

- aang kieu du lieu.
- aang ticker.
- aang period.
- aang currency/unit.
- Khong thieu truong bat buoc.

### 9.2. Financial sanity checks

- Doanh thu khong duoc null neu la BCTC chinh.
- Tang tai san phoi lan hon 0.
- Van chi so hau khong duoc thieu.
- Gross profit khong duoc lan hon revenue neu co da du lieu.
- Cash flow period phoi khap fiscal period.
- EPS khong dung neu shares outstanding thieu hoac khong ro.

### 9.3. Reconciliation checks

- Subtotal va total phoi khap trong tolerance.
- Cang mot metric tu nhieu nguon phoi duoc so sanh.
- Neu nguon mau thuon, khong tu chan theo LLM; phoi dung rule hoac human review.

### 9.4. Source confidence

Goi a tha tu da tin cay:

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

Du lieu khong can realtime, nhung phoi co freshness rule ro rang.

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

## 11. Lach cap nhat du lieu da xuot

| Job | Tan suot MVP | Ghi chu |
|---|---:|---|
| `refresh_market_prices` | Hang ngay sau gie giao dich | Cap nhat gia va multiples |
| `check_financial_statements` | Hang tuon; hang ngay trong mua bao cao | BCTC quy/nam |
| `check_annual_reports` | Hang tuon hoac manual upload | BCTN theo nam |
| `check_disclosures` | Hang ngay | Cong bo thong tin co the anh huong valuation |
| `check_news` | Hang ngay hoac 2-3 ngay/lan | Tin nganh duoc khong quy day |
| `check_pharma_catalysts` | Hang tuon hoac hang ngay neu nguon an dinh | aau thau/BHYT/regulatory |
| `build_document_index` | Cha khi co document moi | Khong embed loi toan ba |
| `generate_full_report` | Khi user yau cau | Khong cron-generate toan ba report |

---

## 12. Incremental recompute

Khong chay loi toan ba pipeline neu cha mot phan du lieu thay doi.

| Du lieu moi | Can recompute | Khong can recompute |
|---|---|---|
| Gia moi | Market multiples, valuation spread, price chart | Business profile, annual report summary |
| BCTC moi | Ratios, growth, peer metrics, DCF | Document chunks cu |
| Bao cao thuong nien moi | Business narrative, risk evidence, document index | Market price history |
| Cong bo co tuc/phat hanh | Share count, dividend/corporate event, valuation per share | Toan bo financial history |
| Tin/catalyst lan | Catalyst section, scenario assumptions, flash memo | Full report neu materiality thap |

Moi artifact can co dependency metadata de biet khi nao stale.

---

## 13. Vai tro caa Data Foundation Agent

`Data Foundation Agent` khong duoc tu crawl hoac tu saa du lieu tay a. Agent nay cha dieu phoi cac tool du lieu theo config.

Nhiem vu:

1. Nhan `ResearchPlan` tu Orchestrator.
2. Kiem tra data inventory caa ticker.
3. Kiem tra freshness theo tang source.
4. Neu thieu/stale, goi dung connector/job.
5. Lay canonical facts moi nhat.
6. Lay evidence chunks lien quan.
7. Tao `DataSnapshot` hoac `ResearchSnapshot`.
8. Tao `DataQualityReport`.
9. Neu fail gate, deng hoac chuyen human review.

Khong duoc:

- Tu saa so lieu thieu nguon.
- Tu forecast so lieu can thieu.
- Tu chan nguon ngoai allowlist.
- Tu kat luon doanh nghiep tat/xau.
- Ghi vao canonical facts khi chua qua validation.

---

## 14. Report package va artifact storage

Moi research run sinh mot report package.

```text
artifacts/
+-- reports/{run_id}_{ticker}_report.md
+-- reports_html/{run_id}_{ticker}_report.html
+-- valuation_results/{run_id}_{ticker}_valuation_result.json
+-- claim_ledgers/{run_id}_{ticker}_claim_ledger.json
+-- source_manifests/{run_id}_{ticker}_source_manifest.json
+-- eval_results/{run_id}_{ticker}_eval_result.json
+-- run_logs/{run_id}_{ticker}_run_log.json
```

DB cha luu metadata va `storage_path`, khong luu toan ba noi dung artifact lan trong bang.

---

## 15. Tha tu trien khai toi uu

### Phase 1 a Data foundation toi thieu

- Tao PostgreSQL/Supabase schema.
- Tao `source_registry`, `source_versions`, `raw_objects`, `canonical_facts`.
- Ingest golden dataset cho 5 ma MVP hoac at nhat 3 ma dau.
- Implement checksum dedup.
- Implement validation co ban.

### Phase 2 a Financial warehouse

- Chuan hoa financial statements thanh canonical facts.
- Tao `market_prices`.
- Tao `financial_metrics` bang code.
- Tao unit tests cho ratios va metrics.

### Phase 3 a Evidence retrieval

- Tao `documents` va `document_chunks`.
- Chunk documents theo metadata.
- Dang PostgreSQL full-text search truoc.
- Tham pgvector khi can semantic search.

### Phase 4 a Research snapshot

- Tao `research_snapshots` va `snapshot_items`.
- Report/valuation cha dac tu snapshot.
- Tao artifact versioning.

### Phase 5 a Evaluation va HITL

- Tao `evaluation_results`, `approval_events`, `model_usage_logs`.
- Chan export neu fail citation/numeric/valuation gate.
- Luu approval history theo artifact version.

---

## 16. Quyet dinh thiet ke cuoi cang

### Nan lam

- Dang PostgreSQL/Supabase lam source of truth.
- Luu raw files trong object storage/local filesystem.
- Dang checksum da dedup.
- Dang canonical facts cho moi phap tanh tai chinh.
- Dang research snapshot truoc khi sinh report.
- Dang incremental recompute.
- Dang pgvector cha cho evidence retrieval, khong cho so lieu chinh.
- Dang cron/APScheduler cho batch refresh.

### Khong nen lam trong MVP

- Khong dung Kafka.
- Khong dung Snowflake/BigQuery.
- Khong dung microservices.
- Khong cron-generate full report moi ngay cho moi ticker.
- Khong da LLM ghi hoac saa financial facts.
- Khong embed toan ba financial table roi da LLM tam sa.
- Khong update da fact da duoc dung trong report.

---

## 17. Kat luon

He thong du lieu caa du an nan la mot **mini financial research lakehouse** cho nganh duoc/y te Viet Nam, khong phai realtime streaming platform.

Thiet ke toi uu la:

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

Kien truc nay da manh da dam bao:

- Du lieu khong ba trang lop.
- Moi so lieu co nguon va version.
- Bao cao co the tai lop.
- Valuation khong pha thuoc vao LLM.
- Claim dinh luong co citation.
- Workflow co the resume/retry/review.
- He thong khong ba phuc tap qua muc so voi ban chat du lieu nganh duoc Viet Nam.
