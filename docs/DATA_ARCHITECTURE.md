 Thi?t k? h? th?ng d? li?u cho Vietnam Pharma Equity Research Agent

## 1. M?c ti�u

T�i li?u n�y m� t? thi?t k? d? li?u t?i uu cho d? �n **Vietnam Pharma Equity Research Agent**. H? th?ng kh�ng du?c thi?t k? nhu m?t n?n t?ng d? li?u th?i gian th?c, m� l� m?t **research data platform chuy�n bi?t cho c? phi?u du?c/y t? Vi?t Nam**.

M?c ti�u ch�nh:

- Thu th?p d? li?u t? c�c ngu?n Vi?t Nam c� li�n quan d?n doanh nghi?p du?c/y t?.
- Chu?n h�a d? li?u th�nh `canonical facts` d�ng du?c cho ph�n t�ch v� d?nh gi�.
- Luu v?t ngu?n, phi�n b?n, checksum, parser version v� tr?ng th�i ki?m d?nh.
- H? tr? sinh b�o c�o c� citation, valuation artifact, audit trail v� human approval.
- Tr�nh thi?t k? th?a: kh�ng d�ng Kafka, kh�ng d�ng streaming ph?c t?p, kh�ng d�ng data warehouse l?n nhu Snowflake/BigQuery trong MVP.

Nguy�n t?c c?t l�i:

```text
Facts before narrative.
Quality before persistence.
Snapshot before report.
Incremental refresh over full recompute.
PostgreSQL/Supabase as source of truth.
Object storage for raw files and generated artifacts.
```

---

## 2. B?n ch?t b�i to�n d? li?u

D? li?u ng�nh du?c/y t? Vi?t Nam c� d? bi?n d?ng th?p d?n trung b�nh. Ph?n l?n d? li?u ph?c v? equity research kh�ng thay d?i theo gi�y/ph�t, m� theo ng�y, qu�, nam ho?c khi c� c�ng b?/catalyst m?i.

V� v?y, h? th?ng n�n d�ng:

```text
Scheduled batch ingestion
+ manual verification
+ canonical fact store
+ research snapshot
+ incremental recompute
+ audit trail
```

Kh�ng n�n d�ng:

```text
Kafka-first architecture
realtime streaming
full recompute m?i ng�y
LLM t? d?c d? li?u raw v� t? suy lu?n s? li?u
```

---

## 3. C�c nh�m d? li?u c?n qu?n l�

| Nh�m d? li?u | V� d? | �? bi?n d?ng | C�ch qu?n l� |
|---|---|---:|---|
| Reference data | Ticker, s�n, t�n c�ng ty, peer group, subsector | R?t th?p | YAML + b?ng c?u h�nh trong DB |
| Market data | Gi� d�ng c?a, volume, market cap, P/E, P/B | H?ng ng�y | B?ng `market_prices` |
| Financial statements | BCTC qu�/nam, income statement, balance sheet, cash flow | Theo qu�/nam | `canonical_facts` sau validation |
| Annual reports | B�o c�o thu?ng ni�n, b�o c�o qu?n tr? | Theo nam | Object storage + `document_chunks` |
| Disclosures | C�ng b? th�ng tin, ngh? quy?t, c? t?c, ph�t h�nh | Kh�ng d?u | Object storage + event table |
| News/catalysts | Tin doanh nghi?p, d?u th?u, BHYT, regulatory notices | Kh�ng d?u | `corporate_events` + evidence chunks |
| Derived analytics | Ratios, growth, margins, peer metrics | Khi facts thay d?i | Artifact ho?c b?ng derived |
| Valuation artifacts | DCF, multiples, sensitivity, scenarios | Khi assumptions/facts/price thay d?i | `valuation_results` + artifact JSON |
| Workflow/audit | Research runs, steps, approvals, eval results | Theo t?ng run | Workflow tables |

---

## 4. Ki?n tr�c d? li?u t?ng th?

H? th?ng n�n du?c thi?t k? nhu m?t **mini financial data lakehouse** g?m 5 l?p.

```text
Source Registry
    ?
Raw Zone 
    ?
Parsed & Normalized Zone 
    ?
Canonical Financial Warehouse 
    ?
Research Snapshot
    ?
Analytics + Valuation + Report Artifacts
```

### 4.1. Source Registry

Luu danh m?c ngu?n du?c ph�p d�ng.

V� d? ngu?n:

- Vnstock ho?c API d? li?u th? tru?ng h?p l?.
- File CSV/golden dataset do nh�m ki?m to�n th? c�ng.
- B�o c�o t�i ch�nh.
- B�o c�o thu?ng ni�n.
- C�ng b? th�ng tin doanh nghi?p.
- Tin t?c doanh nghi?p/ng�nh.
- Ngu?n d?u th?u, BHYT, regulatory n?u c� quy?n truy c?p h?p l?.

M?i ngu?n c?n c�:

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

Luu d? li?u g?c, kh�ng ch?nh s?a.

V� d?:

```text
storage/raw/
+-- market_data/
+-- financial_statements/
+-- annual_reports/
+-- disclosures/
+-- news/
+-- manual_uploads/
```

Quy t?c:

- Raw file l� immutable.
- N?u ngu?n thay d?i, t?o phi�n b?n m?i.
- Kh�ng d�ng raw data tr?c ti?p cho valuation/report.
- M?i raw object ph?i c� checksum d? dedup v� ph�t hi?n thay d?i.

### 4.3. Parsed & Normalized Zone 

Chuy?n raw data th�nh c?u tr�c th?ng nh?t.

Nhi?m v?:

- Chu?n h�a ticker.
- Chu?n h�a k? b�o c�o.
- Chu?n h�a don v? v� ti?n t?.
- Map line item v? taxonomy n?i b?.
- Parse document th�nh text/chunks.
- Chu?n h�a news/disclosures th�nh event records.

V� d? mapping:

```text
"Doanh thu thu?n" ? revenue
"L?i nhu?n sau thu?" ? net_income
"T?ng t�i s?n" ? total_assets
"V?n ch? s? h?u" ? total_equity
```

### 4.4. Canonical Financial Warehouse (quan tr?ng nh?t)

��y l� l?p s? th?t t�i ch�nh d� ki?m d?nh. Ch? d? li?u qua validation m?i du?c ghi v�o d�y.

D�ng cho:

- Ratio calculation.
- Peer comparison.
- DCF/multiples.
- Numeric consistency check.
- Citation cho claim d?nh lu?ng.

Kh�ng cho ph�p:

- LLM ghi tr?c ti?p v�o canonical facts.
- S? li?u thi?u source/version.
- Ghi d� fact cu m� kh�ng t?o version.

### 4.5. Research Snapshot

M?i report ph?i sinh t? m?t snapshot d� d�ng bang.

Snapshot ghi l?i:

- Facts n�o du?c d�ng.
- Market price ng�y n�o du?c d�ng.
- Document chunks n�o du?c d�ng.
- Assumptions version n�o du?c d�ng.
- Valuation artifact version n�o du?c d�ng.

Nguy�n t?c:

```text
Report kh�ng query d? li?u live tr?c ti?p.
Report ch? d?c t? research_snapshot + artifacts d� kh�a ngu?n.
```

---

## 5. Tech stack d? xu?t

### 5.1. MVP stack

| Layer | C�ng ngh? | Vai tr� |
|---|---|---|
| Backend API | FastAPI | API cho research run, report, approval |
| Workflow | LangGraph | Stateful multi-agent workflow |
| Schema | Pydantic v2 | Data contract v� structured output |
| Database | Supabase PostgreSQL ho?c PostgreSQL local | Source of truth cho metadata/facts/runs |
| Object storage | Supabase Storage ho?c local filesystem | Raw files, PDFs, JSON, generated reports |
| Retrieval | PostgreSQL full-text search + pgvector | Evidence retrieval cho documents |
| Scheduler | APScheduler ho?c cron | Batch refresh theo l?ch |
| Data processing | pandas, numpy | Normalize v� financial calculations |
| Validation | Pydantic + pytest + custom checks | Schema validation v� financial sanity checks |
| Reporting | Jinja2 + Markdown/HTML | Render report package |
| HITL UI | Streamlit | Giao di?n duy?t assumptions/report |

### 5.2. Kh�ng d�ng trong MVP

| C�ng ngh? | L� do chua c?n |
|---|---|
| Kafka | D? li?u kh�ng realtime, volume th?p, v?n h�nh ph?c t?p |
| Snowflake/BigQuery | Quy m� 5�23 m� chua c?n data warehouse cloud l?n |
| Qdrant/Weaviate | pgvector d? cho MVP v� d? qu?n l� hon |
| Celery/Redis | Ch? c?n khi batch nhi?u m� ho?c job d�i |
| MinIO/S3 ri�ng | Supabase Storage/local filesystem d? cho giai do?n d?u |
| Microservices | Tang d? ph?c t?p, kh�ng tang ch?t lu?ng report |

---

## 6. Database schema t?i thi?u

### 6.1. Nh�m source v� ingestion

```text
source_registry
source_versions
raw_objects
ingestion_runs
```

#### `source_registry`

Luu ngu?n d? li?u du?c ph�p d�ng.

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

Luu t?ng phi�n b?n d? li?u l?y v?.

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

Luu metadata c?a file raw, kh�ng luu file l?n tr?c ti?p trong DB.

```text
raw_object_id
storage_path
mime_type
file_size
checksum
created_at
```

#### `ingestion_runs`

Luu l?ch s? ingest.

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

### 6.2. Nh�m warehouse t�i ch�nh

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

B?ng quan tr?ng nh?t c?a h? th?ng.

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

R�ng bu?c dedup khuy?n ngh?:

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

R�ng bu?c dedup:

```text
unique(ticker, trade_date, source_version_id)
```

#### `financial_metrics`

Luu ch? s? d� t�nh b?ng code.

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

### 6.3. Nh�m document/evidence retrieval

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

R�ng bu?c dedup:

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

### 6.4. Nh�m research snapshot v� artifact

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

### 6.5. Nh�m workflow, approval v� evaluation

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

## 7. Data pipeline chu?n

### 7.1. Batch ingestion pipeline

```text
Scheduler / Manual Trigger
    ?
Connector
    ?
Save raw object
    ?
Compute checksum
    ?
Dedup check
    ?
Parse / normalize
    ?
Validate / reconcile
    ?
Promote to canonical store
    ?
Update document chunks / evidence index
    ?
Mark affected artifacts as stale
```

### 7.2. Research report pipeline

```text
User request
    ?
Check data inventory + freshness
    ?
Create research snapshot
    ?
Run analytics from canonical facts
    ?
Run valuation from analytics artifacts
    ?
Retrieve evidence from document chunks
    ?
Generate grounded report
    ?
Run evaluation gates
    ?
HITL approval
    ?
Export report package
```

---

## 8. Dedup v� versioning

### 8.1. Dedup theo checksum

M?i raw file/API response ph?i t�nh checksum.

```text
checksum = hash(raw_content)
```

N?u checksum kh�ng d?i:

```text
status = no_change
kh�ng parse l?i
kh�ng embed l?i
kh�ng t?o fact m?i
```

N?u checksum thay d?i:

```text
luu source_version m?i
parse l?i source d�
validate l?i facts li�n quan
invalidate artifacts ph? thu?c
```

### 8.2. Dedup theo business key

Financial facts kh�ng du?c tr�ng theo business key.

Business key:

```text
ticker + metric_name + statement_type + period + source_version_id
```

Document chunks kh�ng du?c tr�ng theo:

```text
document_id + chunk_checksum
```

Market prices kh�ng du?c tr�ng theo:

```text
ticker + trade_date + source_version_id
```

### 8.3. Kh�ng update d� d? li?u d� d�ng trong report

N?u fact d� du?c d�ng trong m?t `research_snapshot`, kh�ng du?c s?a tr?c ti?p. Ph?i t?o version m?i v� d? report sau d�ng version m?i.

---

## 9. Data quality gates

D? li?u ch? du?c promote v�o canonical store n?u qua gate.

### 9.1. Schema checks

- ��ng ki?u d? li?u.
- ��ng ticker.
- ��ng period.
- ��ng currency/unit.
- Kh�ng thi?u tru?ng b?t bu?c.

### 9.2. Financial sanity checks

- Doanh thu kh�ng du?c null n?u l� BCTC ch�nh.
- T?ng t�i s?n ph?i l?n hon 0.
- V?n ch? s? h?u kh�ng du?c thi?u.
- Gross profit kh�ng du?c l?n hon revenue n?u c� d? d? li?u.
- Cash flow period ph?i kh?p fiscal period.
- EPS kh�ng d�ng n?u shares outstanding thi?u ho?c kh�ng r�.

### 9.3. Reconciliation checks

- Subtotal v� total ph?i kh?p trong tolerance.
- C�ng m?t metric t? nhi?u ngu?n ph?i du?c so s�nh.
- N?u ngu?n m�u thu?n, kh�ng t? ch?n theo LLM; ph?i d�ng rule ho?c human review.

### 9.4. Source confidence

G?i � th? t? d? tin c?y:

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

D? li?u kh�ng c?n realtime, nhung ph?i c� freshness rule r� r�ng.

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

## 11. L?ch c?p nh?t d? li?u d? xu?t

| Job | T?n su?t MVP | Ghi ch� |
|---|---:|---|
| `refresh_market_prices` | H?ng ng�y sau gi? giao d?ch | C?p nh?t gi� v� multiples |
| `check_financial_statements` | H?ng tu?n; h?ng ng�y trong m�a b�o c�o | BCTC qu�/nam |
| `check_annual_reports` | H?ng tu?n ho?c manual upload | BCTN theo nam |
| `check_disclosures` | H?ng ng�y | C�ng b? th�ng tin c� th? ?nh hu?ng valuation |
| `check_news` | H?ng ng�y ho?c 2�3 ng�y/l?n | Tin ng�nh du?c kh�ng qu� d�y |
| `check_pharma_catalysts` | H?ng tu?n ho?c h?ng ng�y n?u ngu?n ?n d?nh | �?u th?u/BHYT/regulatory |
| `build_document_index` | Ch? khi c� document m?i | Kh�ng embed l?i to�n b? |
| `generate_full_report` | Khi user y�u c?u | Kh�ng cron-generate to�n b? report |

---

## 12. Incremental recompute

Kh�ng ch?y l?i to�n b? pipeline n?u ch? m?t ph?n d? li?u thay d?i.

| D? li?u m?i | C?n recompute | Kh�ng c?n recompute |
|---|---|---|
| Gi� m?i | Market multiples, valuation spread, price chart | Business profile, annual report summary |
| BCTC m?i | Ratios, growth, peer metrics, DCF | Document chunks cu |
| B�o c�o thu?ng ni�n m?i | Business narrative, risk evidence, document index | Market price history |
| C�ng b? c? t?c/ph�t h�nh | Share count, dividend/corporate event, valuation per share | To�n b? financial history |
| Tin/catalyst l?n | Catalyst section, scenario assumptions, flash memo | Full report n?u materiality th?p |

M?i artifact c?n c� dependency metadata d? bi?t khi n�o stale.

---

## 13. Vai tr� c?a Data Foundation Agent

`Data Foundation Agent` kh�ng du?c t? crawl ho?c t? s?a d? li?u t�y �. Agent n�y ch? di?u ph?i c�c tool d? li?u theo config.

Nhi?m v?:

1. Nh?n `ResearchPlan` t? Orchestrator.
2. Ki?m tra data inventory c?a ticker.
3. Ki?m tra freshness theo t?ng source.
4. N?u thi?u/stale, g?i d�ng connector/job.
5. L?y canonical facts m?i nh?t.
6. L?y evidence chunks li�n quan.
7. T?o `DataSnapshot` ho?c `ResearchSnapshot`.
8. T?o `DataQualityReport`.
9. N?u fail gate, d?ng ho?c chuy?n human review.

Kh�ng du?c:

- T? s?a s? li?u thi?u ngu?n.
- T? forecast s? li?u c�n thi?u.
- T? ch?n ngu?n ngo�i allowlist.
- T? k?t lu?n doanh nghi?p t?t/x?u.
- Ghi v�o canonical facts khi chua qua validation.

---

## 14. Report package v� artifact storage

M?i research run sinh m?t report package.

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

DB ch? luu metadata v� `storage_path`, kh�ng luu to�n b? n?i dung artifact l?n trong b?ng.

---

## 15. Th? t? tri?n khai t?i uu

### Phase 1 � Data foundation t?i thi?u

- T?o PostgreSQL/Supabase schema.
- T?o `source_registry`, `source_versions`, `raw_objects`, `canonical_facts`.
- Ingest golden dataset cho 5 m� MVP ho?c �t nh?t 3 m� d?u.
- Implement checksum dedup.
- Implement validation co b?n.

### Phase 2 � Financial warehouse

- Chu?n h�a financial statements th�nh canonical facts.
- T?o `market_prices`.
- T?o `financial_metrics` b?ng code.
- T?o unit tests cho ratios v� metrics.

### Phase 3 � Evidence retrieval

- T?o `documents` v� `document_chunks`.
- Chunk documents theo metadata.
- D�ng PostgreSQL full-text search tru?c.
- Th�m pgvector khi c?n semantic search.

### Phase 4 � Research snapshot

- T?o `research_snapshots` v� `snapshot_items`.
- Report/valuation ch? d?c t? snapshot.
- T?o artifact versioning.

### Phase 5 � Evaluation v� HITL

- T?o `evaluation_results`, `approval_events`, `model_usage_logs`.
- Ch?n export n?u fail citation/numeric/valuation gate.
- Luu approval history theo artifact version.

---

## 16. Quy?t d?nh thi?t k? cu?i c�ng

### N�n l�m

- D�ng PostgreSQL/Supabase l�m source of truth.
- Luu raw files trong object storage/local filesystem.
- D�ng checksum d? dedup.
- D�ng canonical facts cho m?i ph�p t�nh t�i ch�nh.
- D�ng research snapshot tru?c khi sinh report.
- D�ng incremental recompute.
- D�ng pgvector ch? cho evidence retrieval, kh�ng cho s? li?u ch�nh.
- D�ng cron/APScheduler cho batch refresh.

### Kh�ng n�n l�m trong MVP

- Kh�ng d�ng Kafka.
- Kh�ng d�ng Snowflake/BigQuery.
- Kh�ng d�ng microservices.
- Kh�ng cron-generate full report m?i ng�y cho m?i ticker.
- Kh�ng d? LLM ghi ho?c s?a financial facts.
- Kh�ng embed to�n b? financial table r?i d? LLM t�m s?.
- Kh�ng update d� fact d� du?c d�ng trong report.

---

## 17. K?t lu?n

H? th?ng d? li?u c?a d? �n n�n l� m?t **mini financial research lakehouse** cho ng�nh du?c/y t? Vi?t Nam, kh�ng ph?i realtime streaming platform.

Thi?t k? t?i uu l�:

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

Ki?n tr�c n�y d? m?nh d? d?m b?o:

- D? li?u kh�ng b? tr�ng l?p.
- M?i s? li?u c� ngu?n v� version.
- B�o c�o c� th? t�i l?p.
- Valuation kh�ng ph? thu?c v�o LLM.
- Claim d?nh lu?ng c� citation.
- Workflow c� th? resume/retry/review.
- H? th?ng kh�ng b? ph?c t?p qu� m?c so v?i b?n ch?t d? li?u ng�nh du?c Vi?t Nam.
