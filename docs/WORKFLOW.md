# Workflow nghiên cứu full report

Cập nhật: 2026-06-14

## Context

Workflow production là `full_report`, được điều phối bởi `FullReportOrchestrator` và thực thi bởi `ResearchGraphRunner`. Graph là graph cố định, không phải hệ agent tự route tự do. Runtime cập nhật trạng thái trong `research.runs`, ghi từng step vào `research.run_steps`, lưu artifact metadata trong `research.run_artifacts`, và đẩy object production vào Supabase Storage.

## Problem Statement

Trong bài toán tài chính, agentic workflow phải giảm xác suất hallucination và false pass. Vì vậy pipeline không cho agent tự quyết định thứ tự stage, không cho LLM tính toán valuation, và không cho report renderer tự tìm artifact mới nhất bằng filesystem glob. Mỗi stage phải có input, output, gate và trace đủ để tái lập hoặc chặn run.

## Technical Deep-Dive

### 1. Stage sequence

| Thứ tự | Stage | Vai trò | Output trọng yếu |
|---:|---|---|---|
| 1 | `PREFLIGHT` | Kiểm tra run type, ticker, schema, agent config, tool policy, model env | Fail-fast nếu môi trường không hợp lệ |
| 2 | `PLAN` | Tạo research plan deterministic | `research_plan` |
| 3 | `INGEST_AND_VALIDATE` | Tái dùng snapshot nếu còn fresh hoặc chạy auto ingest, build facts, build index | `auto_ingest`, `build_facts`, `index`, `snapshot_id` |
| 4 | `ANALYZE` | Đọc snapshot/ratios, gọi FinancialAnalysisAgent, xây company research pack | `financial_analysis`, `company_research_pack` |
| 5 | `FORECAST_AND_VALUE` | Chạy deterministic forecast, valuation, read-back artifact, lock research artifacts | `forecast_model`, `valuation`, `valuation_read`, `research_lock` |
| 6 | `WRITE_REPORT` | Gọi ThesisReportAgent và ReportAssembler | `report_draft`, `report_candidate_model` |
| 7 | `REVIEW` | Chạy completeness gate, quality evaluator, SeniorCriticAgent, citation gate | `quality`, `critic_review`, `review_passed_report_model` |
| 8 | `EXPORT_GATES` | Ghi evidence packet, chạy Report quality và package validation diagnostics, promote locked model | `report_quality_evaluation`, `quality_gate`, `publishable_final_report_model` |
| 9 | `PUBLISH` | Xác nhận publishable model, ghi run-scoped evaluation artifacts và manifest; không render HTML/PDF | `evaluation_packet`, `manifest.json`, trạng thái `auto_exported` |

### 2. Trạng thái runtime

| DB status | Public status | Ý nghĩa |
|---|---|---|
| `initialized` | `INIT` | Run đã tạo nhưng chưa chạy |
| `running`, `data_ready`, `analysis_ready` | `ANALYZING` | Đang ingest/analyze hoặc đã có phân tích |
| `valuation_ready` | `VALUATING` | Đã chạy valuation hoặc đang qua chặng valuation |
| `report_ready` | `SYNTHESIZING` | Đã có report model hoặc đang review/export gate |
| `auto_exported` | `PUBLISHED_DRAFT` | Runtime đã tạo publishable draft sau gate tự động |
| `approved` | `PUBLISHED` | Có approval cuối luồng |
| `blocked` | `BLOCKED` | Gate nghiêm trọng hoặc thiếu artifact bắt buộc |
| `failed` | `FAILED` | Exception hoặc lỗi hạ tầng không kiểm soát được |

### 3. Artifact lifecycle

Mỗi stage ghi artifact ref và checkpoint. Artifact production phải gắn với `run_id`, `section_key`, `version`, `checksum`, `producer`, `storage_bucket` và `storage_path` khi có object trong storage. `PUBLISH` không render PDF; nó chỉ xác nhận `publishable_final_report_model` đã tồn tại và ghi manifest.

### 4. Boundary giữa full pipeline và fast render

| Đường chạy | Có ingest? | Có valuation mới? | Có LLM agent? | Có render HTML/PDF? |
|---|---:|---:|---:|---:|
| `scripts/run_research.py` | Có hoặc reuse snapshot | Có | Có | Không render PDF ở `PUBLISH` |
| `scripts/generate_fast_report.py` | Không | Không | Không | Có, từ artifact đã có |

### 5. Blocking semantics

Trong runner hiện tại, `_record_gate` chỉ ghi diagnostic vào `gate_results`; nó không tự chuyển run sang `blocked` dựa trên `severity`. Run chuyển thành `failed` khi stage/tool raise exception, và chuyển thành `blocked` tại `PUBLISH` nếu không có publishable model. Client-final vẫn fail-closed ở `authorize_client_final`, nơi package validation, report quality, approval, locked model và snapshot match được enforce.

Các gate quan trọng gồm `DATA_QUALITY_GATE`, `FORECAST_QUALITY_GATE`, `VALUATION_GATE`, `VALUATION_RECONCILIATION_GATE`, `REPORT_ASSEMBLY_GATE`, `REPORT_COMPLETENESS_GATE`, `SENIOR_CRITIC_GATE`, `CITATION_GATE`, `REPORT_QUALITY_GATE`, `PACKAGE_VALIDATION_GATE` và `EXPORT_GATE`. Nếu yêu cầu một gate phải chặn trước `auto_exported`, cần thêm enforcement tường minh trong runner; chỉ đặt `severity="critical"` là chưa đủ.

## Strategic Recommendations

| Ranh giới | Khuyến nghị |
|---|---|
| Stage mới | Chỉ thêm khi có artifact contract, gate contract và tests tương ứng |
| Resume/retry | Ưu tiên checkpoint và explicit artifact refs; không suy luận từ file mới nhất |
| Report publication | Tách `auto_exported` draft với `approved` final để bảo vệ sản phẩm client-facing |
| Batch scale | Cần queue bền vững nếu mở rộng nhiều ticker; thread pool hiện phù hợp cho quy mô nhỏ hoặc API prototype |
