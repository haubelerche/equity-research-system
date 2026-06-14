# Dữ liệu, database và storage

Cập nhật: 2026-06-15

## Context

Dữ liệu của hệ thống đi qua ba lớp kiểm soát: Supabase PostgreSQL cho metadata/canonical facts/run state, Supabase Storage cho binary và artifacts, và các validation/reconciliation gates để quyết định fact nào được dùng trong valuation/report. Local `output/`, `storage/` và `artifacts/` chỉ nên coi là cache hoặc preview, không phải nguồn production.

## Problem Statement

Research report có rủi ro cao nếu dùng dữ liệu sống hoặc file mới nhất không gắn `run_id`. Hệ thống cần bảo đảm mỗi claim và mỗi con số có thể truy ngược về snapshot, source document, valuation artifact hoặc evidence packet cụ thể. Điều này đòi hỏi schema governance, object-key contract và manifest theo run.

## Technical Deep-Dive

### 1. Database runtime

| Thành phần | Thiết kế |
|---|---|
| Database | Supabase PostgreSQL bắt buộc |
| Driver | `psycopg2` qua `connect_with_retry` |
| Migration runner | `python -m backend.database.migrate` |
| Migration table | `public.schema_migrations` |
| Current schema | `043_cafef_financial_source_type` trong migration runner |
| Runtime minimum | `035_runs_status_auto_exported` trong `RuntimeStore` |

### 2. Schema logic

| Schema | Trách nhiệm |
|---|---|
| `ref` | Company master, universe registration, metric dictionaries, peer groups |
| `ingest` | Source documents, raw observations, document chunks |
| `fact` | Canonical facts, price history, catalyst events |
| `research` | Runs, steps, artifacts, approvals, audit events |
| `valuation` | Assumptions, valuation outputs, summaries |
| `report` | Claims, citations, gates, approvals |
| `audit` | Cost ledger và governance events |
| `news` | Whitelisted news research runs, raw articles, extracted evidence, editor outputs |

Sơ đồ ER chi tiết theo từng schema nằm ở [DATA_ARCHITECTURE_ER.md](DATA_ARCHITECTURE_ER.md). File đó là nguồn nên dùng trực tiếp cho mục 3.3 của đồ án vì nó ánh xạ các bảng Supabase vào mô hình dữ liệu chuẩn hóa, kho tài liệu, snapshot, artifact và truy vết claim.

### 3. Run state tables

| Table/khái niệm | Nội dung |
|---|---|
| `research.runs` | `run_id`, ticker, run type, status, current stage, flags, config snapshot |
| `research.run_steps` | Stage-level trace, agent name, input/output hash, duration, error |
| `research.run_artifacts` | Payload hoặc storage pointer theo `run_id`, `section_key`, version, checksum, lock flag |
| `research.run_audit_events` | Agent/tool/gate/checkpoint events |
| `research.run_approvals` | Approval decision theo stage khi có |
| `audit.cost_ledger` | Ước tính chi phí LLM theo run/step/model |

### 4. Storage buckets

| Bucket | Key mẫu | Chính sách |
|---|---|---|
| `sources` | `official_documents/{TICKER}/{YEAR}/{source_doc_id}.pdf` | Private, lưu source binary chính thức |
| `runs` | `{run_id}/manifest.json`, `{run_id}/valuation.json`, `{run_id}/evidence_pack.json` | Private, artifact theo run |
| `exports` | `approved_reports/{TICKER}/{run_id}/report.pdf` | Bucket duy nhất được phép tạo signed URL client-facing |
| `archive` | `legacy/...`, `debug/...`, `failed_runs/...` | Private archive |

### 5. Key validation

`backend/storage/layout.py` allow-list tên artifact production. Khi thêm artifact mới cho bucket `runs`, cần thêm tên vào `_RUN_ARTIFACT_NAMES` và bổ sung test storage contract. Cơ chế này giảm rủi ro path traversal, typo object path và artifact drift.

### 6. Snapshot và canonical facts

Pipeline `build_facts` chuẩn hóa raw observations thành facts có metric id, period, unit, source tier và provenance. Snapshot id là input quan trọng cho analysis, ratios, forecast và report. Nếu một dữ liệu nghiệp vụ không tồn tại hoặc không đối chiếu được, hệ thống không tự giả định; giá trị đó được biểu diễn là `null` trong artifact hoặc bản giải trình, còn các phần đủ dữ liệu vẫn tiếp tục được dùng cho phân tích.

### 7. Evidence packet

Evidence packet được ghi ở `EXPORT_GATES` và trước manifest final. Nó gom artifact refs, formula traces, evidence refs và thông tin cần cho reviewer tái kiểm tra claim/report. Nếu packet thiếu hoặc valuation có formula nhưng packet không chứa trace cần thiết, `EVIDENCE_PACKET_GATE` ghi cảnh báo và thiếu sót để đưa vào bản giải trình.

## Strategic Recommendations

| Ưu tiên | Khuyến nghị |
|---|---|
| P0 | Không dùng local file mới nhất làm input production report |
| P0 | Mọi output quan trọng phải có `run_id`, `section_key`, checksum và producer |
| P1 | Khi thêm migration, cập nhật `CURRENT_SCHEMA_VERSION` và test runner |
| P1 | Khi thêm bucket/key, cập nhật storage layout, scripts storage và tests |
| P2 | Nếu scale batch nhiều ticker, thêm queue và idempotency policy thay vì chỉ dựa thread pool |
