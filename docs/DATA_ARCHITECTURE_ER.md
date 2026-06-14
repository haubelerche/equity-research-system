# Sơ đồ ER và kiến trúc dữ liệu Supabase

Cập nhật: 2026-06-15

## Context

Tài liệu này mô tả mô hình dữ liệu hiện tại trên Supabase PostgreSQL và Supabase Storage để phục vụ mục 3.3 của đồ án: thiết kế kiến trúc dữ liệu và lưu trữ. Trọng tâm là các schema đang dùng sau canonical cutover: `ref`, `ingest`, `fact`, `research`, `valuation`, `report`, `audit` và `news`. Các schema cũ đã được migrate hoặc dọn dẹp không được xem là nguồn thiết kế chính.

Supabase Storage không phải một schema quan hệ, nhưng được đưa vào sơ đồ như lớp lưu trữ object vì các bảng `ingest.source_documents` và `research.run_artifacts` chỉ lưu metadata, checksum và đường dẫn object (`storage_bucket`, `storage_path`). Thiết kế này tách rõ dữ liệu có cấu trúc trong PostgreSQL khỏi file gốc, artifact phân tích và PDF đầu ra.

## Problem Statement

Đồ án cần trình bày mô hình dữ liệu không chỉ như danh sách bảng, mà như một kiến trúc có khả năng tái lập kết quả: tài liệu nguồn tạo observation, observation được chọn thành canonical fact, canonical fact được đóng băng vào snapshot, snapshot đi vào valuation/report, claim trong report trỏ ngược về fact và source document, còn mọi artifact được gắn với `run_id`.

| Yêu cầu đồ án | Cách tài liệu này đáp ứng |
|---|---|
| 3.3.1. Mô hình dữ liệu tài chính chuẩn hóa | Mô tả `ref`, `ingest`, `fact` và quan hệ observation -> canonical fact |
| 3.3.2. Thiết kế cơ sở dữ liệu phục vụ phân tích tài chính | Mô tả `research`, `valuation`, `report` và luồng từ run đến định giá/báo cáo |
| 3.3.3. Thiết kế kho tài liệu và chỉ mục truy xuất bằng chứng | Mô tả `source_documents`, `document_chunks`, pgvector và Storage bucket `sources` |
| 3.3.4. Quản lý phiên bản dữ liệu và kết quả phân tích | Mô tả `canonical_version`, `snapshot_id`, `run_id`, `artifact_id`, checksum và manifest |
| 3.3.5. Khả năng truy vết nguồn dữ liệu và tái lập kết quả | Mô tả chuỗi citation: report claim -> canonical fact -> observation -> source document -> storage object |

## Technical Deep-Dive

### 1. Bản đồ schema hiện tại

| Schema | Vai trò | Bảng chính |
|---|---|---|
| `ref` | Dữ liệu tham chiếu ổn định | `companies`, `line_items`, `formulas`, `peer_groups`, `peer_group_members` |
| `ingest` | Đăng ký nguồn, quan sát thô, chunk tài liệu | `source_documents`, `observations`, `document_chunks`, `connector_runs` |
| `fact` | Dữ kiện chuẩn và dữ liệu thị trường | `canonical_facts`, `price_history`, `catalyst_events`, view `production_facts` |
| `research` | Runtime nghiên cứu, snapshot, artifact | `runs`, `snapshots`, `snapshot_items`, `run_artifacts`, `run_steps`, `run_audit_events`, `run_approvals` |
| `valuation` | Kết quả định giá và giả định được khai báo | `runs`, `assumptions` |
| `report` | Báo cáo, luận điểm, trích dẫn, kiểm định | `reports`, `claims`, `citation_records`, `gate_results`, `approval_records` |
| `audit` | Nhật ký quản trị và chi phí | `events`, `cost_ledger`, `schema_changes` |
| `news` | Bằng chứng tin tức whitelist | `research_runs`, `raw_articles`, `extracted_evidence`, `research_run_articles`, `editor_outputs`, `ticker_news_sources` |

### 2. ER tổng quan toàn hệ thống

```mermaid
erDiagram
    REF_COMPANIES ||--o{ INGEST_SOURCE_DOCUMENTS : "phát hành hoặc liên quan"
    REF_COMPANIES ||--o{ INGEST_OBSERVATIONS : "có quan sát tài chính"
    REF_COMPANIES ||--o{ FACT_CANONICAL_FACTS : "có dữ kiện chuẩn"
    REF_COMPANIES ||--o{ FACT_PRICE_HISTORY : "có giá thị trường"
    REF_COMPANIES ||--o{ RESEARCH_RUNS : "được phân tích"
    REF_COMPANIES ||--o{ RESEARCH_SNAPSHOTS : "có snapshot"
    REF_COMPANIES ||--o{ VALUATION_RUNS : "được định giá"
    REF_COMPANIES ||--o{ REPORT_REPORTS : "có báo cáo"

    REF_LINE_ITEMS ||--o{ INGEST_OBSERVATIONS : "định nghĩa metric"
    REF_LINE_ITEMS ||--o{ FACT_CANONICAL_FACTS : "chuẩn hóa metric"
    REF_LINE_ITEMS ||--o{ REPORT_CLAIMS : "định danh metric được nêu"

    INGEST_SOURCE_DOCUMENTS ||--o{ INGEST_OBSERVATIONS : "cung cấp số liệu"
    INGEST_SOURCE_DOCUMENTS ||--o{ INGEST_DOCUMENT_CHUNKS : "được chia đoạn"
    INGEST_OBSERVATIONS ||--o{ FACT_CANONICAL_FACTS : "được chọn làm winner"
    FACT_CANONICAL_FACTS ||--o{ RESEARCH_SNAPSHOT_ITEMS : "được đóng băng"
    INGEST_SOURCE_DOCUMENTS ||--o{ RESEARCH_SNAPSHOT_ITEMS : "bằng chứng đi kèm"

    RESEARCH_SNAPSHOTS ||--o{ RESEARCH_SNAPSHOT_ITEMS : "bao gồm"
    RESEARCH_SNAPSHOTS ||--o{ RESEARCH_RUNS : "làm input"
    RESEARCH_RUNS ||--o{ RESEARCH_RUN_ARTIFACTS : "sinh artifact"
    RESEARCH_RUNS ||--o{ RESEARCH_RUN_STEPS : "ghi step"
    RESEARCH_RUNS ||--o{ VALUATION_RUNS : "sinh định giá"
    RESEARCH_RUNS ||--o{ REPORT_REPORTS : "sinh báo cáo"

    RESEARCH_RUN_ARTIFACTS ||--o{ VALUATION_RUNS : "lưu artifact định giá"
    RESEARCH_RUN_ARTIFACTS ||--o{ REPORT_REPORTS : "lưu PDF hoặc model"
    VALUATION_RUNS ||--o{ VALUATION_ASSUMPTIONS : "có giả định"

    REPORT_REPORTS ||--o{ REPORT_CLAIMS : "chứa luận điểm"
    REPORT_CLAIMS ||--o{ REPORT_CITATION_RECORDS : "được trích dẫn"
    FACT_CANONICAL_FACTS ||--o{ REPORT_CITATION_RECORDS : "hỗ trợ số liệu"
    INGEST_SOURCE_DOCUMENTS ||--o{ REPORT_CITATION_RECORDS : "hỗ trợ nguồn"
    REPORT_REPORTS ||--o{ REPORT_GATE_RESULTS : "có kiểm định"
```

### 3. Mô hình dữ liệu tài chính chuẩn hóa

```mermaid
erDiagram
    REF_COMPANIES {
        varchar ticker PK
        text company_name_vi
        text company_name_en
        varchar exchange
        text sector
        text subsector
        char currency
        boolean is_active
    }

    REF_LINE_ITEMS {
        varchar line_item_code PK
        varchar statement_type
        text display_name_vi
        text display_name_en
        varchar canonical_unit
        boolean is_derived
        boolean is_active
    }

    INGEST_SOURCE_DOCUMENTS {
        varchar source_doc_id PK
        varchar ticker FK
        varchar source_type
        smallint source_tier
        text source_uri
        text source_title
        smallint fiscal_year
        varchar fiscal_period
        char checksum
        text storage_bucket
        text storage_path
        jsonb metadata_json
    }

    INGEST_OBSERVATIONS {
        bigserial observation_id PK
        varchar ticker FK
        varchar period
        varchar period_type
        varchar metric FK
        numeric value
        varchar unit
        char currency
        varchar source_doc_id FK
        smallint source_tier
        varchar extraction_method
        numeric confidence
    }

    FACT_CANONICAL_FACTS {
        varchar fact_id PK
        varchar ticker FK
        varchar period
        varchar period_type
        varchar canonical_version
        varchar metric FK
        numeric value
        varchar unit
        char currency
        bigint selected_observation_id FK
        varchar selection_policy
        numeric confidence
        varchar quality_status
        varchar reconciliation_status
        varchar official_document_id FK
    }

    REF_COMPANIES ||--o{ INGEST_SOURCE_DOCUMENTS : "có nguồn"
    REF_COMPANIES ||--o{ INGEST_OBSERVATIONS : "có observation"
    REF_LINE_ITEMS ||--o{ INGEST_OBSERVATIONS : "định nghĩa metric"
    INGEST_SOURCE_DOCUMENTS ||--o{ INGEST_OBSERVATIONS : "sinh observation"
    INGEST_OBSERVATIONS ||--o{ FACT_CANONICAL_FACTS : "được chọn"
    INGEST_SOURCE_DOCUMENTS ||--o{ FACT_CANONICAL_FACTS : "xác minh official"
    REF_LINE_ITEMS ||--o{ FACT_CANONICAL_FACTS : "chuẩn hóa metric"
```

Mô hình này dùng `ingest.observations` làm vùng candidate facts và `fact.canonical_facts` làm nguồn sự thật tài chính chuẩn hóa. Một chỉ tiêu tài chính không được ghi trực tiếp từ báo cáo vào bảng canonical; nó phải đi qua observation, có source tier, phương pháp trích xuất, confidence và chính sách chọn winner. Khi dữ liệu không tồn tại hoặc không đủ căn cứ, pipeline nghiệp vụ ghi `null` ở artifact/bản giải trình thay vì bịa một row trong `canonical_facts`.

### 4. Thiết kế cơ sở dữ liệu phục vụ phân tích tài chính

```mermaid
erDiagram
    RESEARCH_RUNS {
        varchar run_id PK
        varchar ticker FK
        varchar run_type
        text objective
        varchar status
        varchar current_stage
        varchar snapshot_id FK
        jsonb request_json
        jsonb config_snapshot_json
        jsonb flags_json
        jsonb progress_json
        timestamptz created_at
        timestamptz finished_at
    }

    RESEARCH_SNAPSHOTS {
        varchar snapshot_id PK
        varchar ticker FK
        varchar canonical_version
        date as_of_date
        smallint from_year
        smallint to_year
        jsonb periods_json
        integer facts_count
        varchar status
    }

    RESEARCH_SNAPSHOT_ITEMS {
        bigserial id PK
        varchar snapshot_id FK
        varchar item_type
        varchar fact_id FK
        text item_ref
        varchar source_doc_id FK
        text included_reason
    }

    VALUATION_RUNS {
        varchar valuation_run_id PK
        varchar research_run_id FK
        varchar snapshot_id FK
        varchar ticker FK
        varchar method
        varchar model_version
        varchar status
        varchar artifact_id FK
        numeric target_price_vnd
        numeric upside_pct
        text blend_formula
    }

    VALUATION_ASSUMPTIONS {
        bigserial id PK
        varchar valuation_run_id FK
        varchar assumption_key
        numeric assumption_value
        text assumption_text
        varchar source
        varchar approved_by
    }

    RESEARCH_RUNS }o--|| RESEARCH_SNAPSHOTS : "khóa snapshot"
    RESEARCH_SNAPSHOTS ||--o{ RESEARCH_SNAPSHOT_ITEMS : "đóng băng dữ liệu"
    FACT_CANONICAL_FACTS ||--o{ RESEARCH_SNAPSHOT_ITEMS : "fact được dùng"
    RESEARCH_RUNS ||--o{ VALUATION_RUNS : "sinh valuation"
    RESEARCH_SNAPSHOTS ||--o{ VALUATION_RUNS : "làm input"
    VALUATION_RUNS ||--o{ VALUATION_ASSUMPTIONS : "khai báo giả định"
```

Điểm thiết kế cốt lõi là `snapshot_id`. Hệ thống không định giá trực tiếp trên dữ liệu sống; một lần chạy nghiên cứu phải khóa snapshot, sau đó định giá và báo cáo đều dùng cùng snapshot. Điều này làm cho kết quả có thể tái lập, vì cùng `run_id` có thể truy lại cấu hình, snapshot, facts, giả định định giá và artifact.

### 5. Thiết kế kho tài liệu và chỉ mục truy xuất bằng chứng

```mermaid
erDiagram
    INGEST_SOURCE_DOCUMENTS {
        varchar source_doc_id PK
        varchar ticker FK
        varchar source_type
        smallint source_tier
        text source_uri
        char checksum
        text storage_bucket
        text storage_path
        text content_type
        bigint file_size_bytes
        timestamptz uploaded_at
    }

    INGEST_DOCUMENT_CHUNKS {
        bigserial chunk_id PK
        varchar source_doc_id FK
        integer chunk_index
        text chunk_text
        integer page_number
        text section_title
        char content_hash
        text embedding_model
        vector embedding
    }

    NEWS_RAW_ARTICLES {
        bigserial article_id PK
        text source_name
        varchar source_domain
        text source_url
        text canonical_url
        varchar content_hash
        text title
        text raw_text
        timestamptz published_at
    }

    NEWS_EXTRACTED_EVIDENCE {
        bigserial evidence_id PK
        bigint article_id FK
        text topic
        varchar ticker
        text claim
        text evidence_text
        varchar confidence
        text source_url
    }

    INGEST_SOURCE_DOCUMENTS ||--o{ INGEST_DOCUMENT_CHUNKS : "chia đoạn"
    NEWS_RAW_ARTICLES ||--o{ NEWS_EXTRACTED_EVIDENCE : "trích bằng chứng"
```

`ingest.document_chunks` là lớp truy xuất bằng chứng cho tài liệu chính thức, có `embedding vector(1536)` và chỉ mục HNSW phục vụ tìm kiếm ngữ nghĩa. `news.extracted_evidence` là lớp bằng chứng tin tức đã whitelist, tách khỏi fact tài chính để tránh trộn dữ kiện định lượng kiểm toán với tín hiệu tin tức.

| Bucket Supabase Storage | Bảng metadata trỏ tới | Nội dung | Quy tắc chính |
|---|---|---|---|
| `sources` | `ingest.source_documents` | PDF báo cáo tài chính, báo cáo thường niên, disclosure, tài liệu IR | PostgreSQL lưu checksum và object key, không lưu binary |
| `runs` | `research.run_artifacts` | Snapshot, valuation JSON, evidence pack, manifest, model báo cáo, PDF giải trình | Mọi object phải gắn `run_id` |
| `exports` | Artifact xuất bản client-facing | PDF chính thức hoặc bản xuất được chia sẻ | Dùng signed URL khi cần phân phối |
| `archive` | Không phải nguồn production chính | Debug, legacy, failed runs | Chỉ phục vụ điều tra và lưu trữ |

### 6. Quản lý phiên bản dữ liệu và kết quả phân tích

```mermaid
erDiagram
    RESEARCH_RUNS {
        varchar run_id PK
        varchar ticker FK
        varchar idempotency_key
        varchar snapshot_id FK
        jsonb config_snapshot_json
        varchar current_stage
        varchar status
    }

    RESEARCH_RUN_ARTIFACTS {
        varchar artifact_id PK
        varchar run_id FK
        varchar artifact_type
        text storage_bucket
        text storage_path
        char checksum
        boolean is_locked
        integer version
        varchar section_key
        jsonb payload_json
        jsonb evidence_refs_json
        numeric confidence
        varchar created_by_agent
    }

    RESEARCH_RUN_STEPS {
        bigserial id PK
        varchar run_id FK
        varchar step_name
        varchar agent_name
        varchar status
        text input_hash
        text output_hash
        jsonb metadata_json
        text error_message
    }

    RESEARCH_RUN_AUDIT_EVENTS {
        bigserial id PK
        varchar run_id FK
        varchar actor
        varchar action
        text rule_reason
        text policy_reason
        jsonb payload_json
    }

    AUDIT_EVENTS {
        bigserial id PK
        varchar event_type
        varchar actor
        varchar run_id
        varchar target_table
        text target_id
        jsonb payload_json
    }

    RESEARCH_RUNS ||--o{ RESEARCH_RUN_ARTIFACTS : "version artifact"
    RESEARCH_RUNS ||--o{ RESEARCH_RUN_STEPS : "trace step"
    RESEARCH_RUNS ||--o{ RESEARCH_RUN_AUDIT_EVENTS : "runtime audit"
    RESEARCH_RUNS ||--o{ AUDIT_EVENTS : "governance audit"
```

Quản lý phiên bản được thực hiện ở ba tầng. Tầng dữ liệu dùng `canonical_version` trong `fact.canonical_facts` và `research.snapshots`. Tầng runtime dùng `run_id`, `idempotency_key`, `config_snapshot_json` và `snapshot_id`. Tầng artifact dùng `artifact_id`, `artifact_type`, `version`, `checksum`, `is_locked`, `storage_bucket` và `storage_path`.

### 7. Khả năng truy vết nguồn dữ liệu và tái lập kết quả

```mermaid
erDiagram
    REPORT_REPORTS {
        varchar report_id PK
        varchar run_id FK
        varchar ticker FK
        varchar report_type
        varchar report_mode
        varchar status
        varchar pdf_artifact_id FK
    }

    REPORT_CLAIMS {
        varchar claim_id PK
        varchar report_id FK
        varchar section
        text claim_text
        varchar claim_type
        varchar ticker FK
        varchar period
        varchar metric FK
        numeric value_mentioned
        varchar unit
    }

    REPORT_CITATION_RECORDS {
        varchar citation_id PK
        varchar claim_id FK
        varchar fact_id FK
        varchar source_doc_id FK
        bigint chunk_id
        varchar support_type
        smallint source_tier
        varchar validation_status
    }

    REPORT_GATE_RESULTS {
        bigserial id PK
        varchar report_id FK
        varchar gate_name
        varchar status
        varchar severity
        integer issue_count
        jsonb issues_json
    }

    REPORT_REPORTS ||--o{ REPORT_CLAIMS : "chứa claim"
    REPORT_CLAIMS ||--o{ REPORT_CITATION_RECORDS : "được chứng minh"
    FACT_CANONICAL_FACTS ||--o{ REPORT_CITATION_RECORDS : "fact hỗ trợ"
    INGEST_SOURCE_DOCUMENTS ||--o{ REPORT_CITATION_RECORDS : "source hỗ trợ"
    REPORT_REPORTS ||--o{ REPORT_GATE_RESULTS : "kiểm định"
```

Chuỗi truy vết chuẩn:

```text
report.reports.report_id
-> report.claims.claim_id
-> report.citation_records.fact_id
-> fact.canonical_facts.selected_observation_id
-> ingest.observations.source_doc_id
-> ingest.source_documents.storage_bucket + storage_path
```

Với định giá, chuỗi tái lập tương ứng là:

```text
research.runs.run_id
-> research.runs.snapshot_id
-> research.snapshot_items.fact_id
-> valuation.runs.valuation_run_id
-> valuation.assumptions
-> research.run_artifacts.artifact_id
```

Hai chuỗi này cho phép người đọc kiểm tra lại một con số trong báo cáo từ PDF, claim, canonical fact, observation, tài liệu nguồn, cho đến object gốc trong Supabase Storage. Nếu một dữ kiện không có trong nguồn hợp lệ, hệ thống không tạo fact giả; kết quả nghiệp vụ tương ứng được ghi `null` trong artifact/bản giải trình và được đưa vào cảnh báo chất lượng.

### 8. Schema tin tức và bằng chứng bổ trợ

```mermaid
erDiagram
    NEWS_RESEARCH_RUNS {
        varchar research_run_id PK
        varchar user_id
        text topic
        varchar ticker
        text company_name
        jsonb keywords
        jsonb allowed_domains
        varchar status
    }

    NEWS_TICKER_NEWS_SOURCES {
        bigserial id PK
        varchar ticker
        text source_name
        varchar source_domain
        varchar source_type
        text source_url
        int priority
        boolean is_cron_enabled
    }

    NEWS_RAW_ARTICLES {
        bigserial article_id PK
        varchar source_domain
        text source_url
        text canonical_url
        varchar content_hash
        text title
        text raw_text
        varchar crawl_status
    }

    NEWS_EXTRACTED_EVIDENCE {
        bigserial evidence_id PK
        bigint article_id FK
        varchar ticker
        text claim
        text evidence_text
        varchar confidence
    }

    NEWS_RESEARCH_RUN_ARTICLES {
        bigserial id PK
        varchar research_run_id FK
        bigint article_id FK
        numeric relevance_score
        boolean selected
    }

    NEWS_EDITOR_OUTPUTS {
        bigserial id PK
        varchar research_run_id FK
        text title
        text report_markdown
        integer citation_count
        varchar status
    }

    NEWS_RESEARCH_RUNS ||--o{ NEWS_RESEARCH_RUN_ARTICLES : "xem xét article"
    NEWS_RAW_ARTICLES ||--o{ NEWS_RESEARCH_RUN_ARTICLES : "được chọn"
    NEWS_RAW_ARTICLES ||--o{ NEWS_EXTRACTED_EVIDENCE : "sinh evidence"
    NEWS_RESEARCH_RUNS ||--o{ NEWS_EDITOR_OUTPUTS : "sinh output"
```

Schema `news` không thay thế `fact`. Nó chỉ cung cấp evidence bổ trợ cho catalyst, bối cảnh ngành và sự kiện doanh nghiệp. Ràng buộc whitelist ở `news.raw_articles.source_domain` giúp giảm rủi ro lấy tin từ nguồn không được phép.

### 9. Schema tham chiếu, dữ liệu thị trường và audit

```mermaid
erDiagram
    REF_FORMULAS {
        varchar formula_id PK
        text formula_name
        text formula_group
        text function_name
        text formula_text
        varchar output_unit
        varchar version
        boolean is_active
    }

    REF_PEER_GROUPS {
        varchar peer_group_id PK
        text peer_group_name
        text sector
        text description
    }

    REF_PEER_GROUP_MEMBERS {
        varchar peer_group_id PK
        varchar ticker PK
        text enabled_methods
        boolean is_active
    }

    FACT_PRICE_HISTORY {
        varchar ticker PK
        date trade_date PK
        numeric open
        numeric high
        numeric low
        numeric close
        numeric adjusted_close
        bigint volume
        numeric market_cap
        varchar source_doc_id FK
    }

    FACT_CATALYST_EVENTS {
        varchar event_id PK
        varchar ticker FK
        varchar event_type
        text title
        timestamptz occurred_at
        date effective_date
        varchar materiality_hint
        varchar causality_level
        varchar source_doc_id FK
        numeric confidence
        varchar validation_status
    }

    AUDIT_COST_LEDGER {
        bigserial id PK
        varchar run_id
        varchar step_name
        varchar model_name
        integer prompt_tokens
        integer completion_tokens
        numeric cost_usd
        varchar budget_policy
    }

    AUDIT_SCHEMA_CHANGES {
        bigserial id PK
        varchar migration_version
        timestamptz applied_at
        text description
    }

    REF_PEER_GROUPS ||--o{ REF_PEER_GROUP_MEMBERS : "gồm thành viên"
    REF_COMPANIES ||--o{ REF_PEER_GROUP_MEMBERS : "thuộc peer group"
    REF_COMPANIES ||--o{ FACT_PRICE_HISTORY : "có lịch sử giá"
    REF_COMPANIES ||--o{ FACT_CATALYST_EVENTS : "có sự kiện"
    INGEST_SOURCE_DOCUMENTS ||--o{ FACT_PRICE_HISTORY : "nguồn giá"
    INGEST_SOURCE_DOCUMENTS ||--o{ FACT_CATALYST_EVENTS : "nguồn sự kiện"
    RESEARCH_RUNS ||--o{ AUDIT_COST_LEDGER : "ghi chi phí"
```

`ref.formulas` là registry công thức, không phải nơi lưu kết quả tính toán. `ref.peer_groups` và `ref.peer_group_members` hỗ trợ định giá so sánh bằng bội số. `fact.price_history` lưu dữ liệu thị trường theo ngày; `fact.catalyst_events` lưu sự kiện có khả năng ảnh hưởng đến luận điểm đầu tư. `audit.cost_ledger` và `audit.schema_changes` phục vụ governance, kiểm soát chi phí và chứng minh lịch sử thay đổi schema.

## Strategic Recommendations

| Mục đồ án | Sơ đồ nên dùng | Luận điểm cần nhấn mạnh |
|---|---|---|
| 3.3.1 | Mô hình dữ liệu tài chính chuẩn hóa | Observation là vùng ứng viên; canonical fact là nguồn chuẩn; không có dữ liệu thì không sinh fact giả |
| 3.3.2 | Thiết kế cơ sở dữ liệu phục vụ phân tích tài chính | `run_id` và `snapshot_id` là trục tái lập phân tích |
| 3.3.3 | Thiết kế kho tài liệu và chỉ mục truy xuất bằng chứng | PostgreSQL lưu metadata/chunk/vector; Storage lưu binary/artifact |
| 3.3.4 | Quản lý phiên bản dữ liệu và kết quả phân tích | `canonical_version`, `snapshot_id`, `artifact_id`, checksum và `version` kiểm soát drift |
| 3.3.5 | Khả năng truy vết nguồn dữ liệu và tái lập kết quả | Claim trong báo cáo truy ngược được tới fact, observation, source document và object gốc |

Kết luận: thiết kế dữ liệu của dự án không phải một kho JSON rời rạc, mà là một data lineage graph có khóa chính ổn định, khóa ngoại rõ ràng, object-key contract và cơ chế snapshot theo `run_id`. Cấu trúc này phục vụ trực tiếp ba mục tiêu: định giá có thể tái lập, báo cáo có thể kiểm chứng và thiếu sót dữ liệu được giải trình minh bạch thay vì bị che bằng giả định ngầm.
