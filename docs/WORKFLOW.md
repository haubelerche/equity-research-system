# Workflow nghiên cứu full report

Cập nhật: 2026-06-17

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
| 8 | `EXPORT_GATES` | Ghi evidence packet, chạy Report quality và package validation bắt buộc, chặn promotion nếu blocker còn tồn tại | `report_quality_evaluation`, `quality_gate`, `publishable_final_report_model` |
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

### 4. Boundary giữa ingestion bổ sung, full pipeline và fast render

| Đường chạy | Có PDF LLM gap-fill? | Có AGM/DHCD driver ingest? | Có valuation mới? | Có LLM agent? | Có render HTML/PDF? |
|---|---:|---:|---:|---:|---:|
| `scripts/ingest_pdf_llm.py` | Có | Không | Không | Có, chỉ để extract fact/evidence | Không |
| `scripts/ingest_agm.py` | Không | Có | Không | Có, chỉ để extract nghị quyết/driver | Không |
| `scripts/run_research.py` | Có hoặc reuse qua tool ingest nội bộ, tùy dữ liệu/run policy | Đọc driver đã ingest | Có | Có | Không render PDF ở `PUBLISH` |
| `scripts/generate_fast_report.py` | Không | Không | Không | Không | Có, từ artifact đã có |
| `POST /reports/{ticker}/generate` | Tùy route | Tùy route | Tùy route | Tùy route | Có nếu đi `fast_render`, hoặc chạy full rồi render/store |
| `make run-once` | Có | Có | Có | Có | Có |

`make run-once TICKER=DHG FROM_YEAR=2021 TO_YEAR=2025 REPORT_MODE=standard` là convenience target cho vận hành một ticker theo thứ tự cố định: PDF LLM gap-fill, AGM/DHCD ingest, full harness với OCR/draft, sau đó render local. Target này không thay đổi semantics của từng script; nó chỉ giảm lỗi thao tác khi cần tái chạy đầy đủ một lần.

Trong API, `POST /reports/{ticker}/generate` kiểm tra snapshot sẵn sàng và run có đủ artifact để render. Nếu có, request được gắn `generate_mode=fast_render` và `source_run_id`; orchestrator render từ run nguồn rồi upload report/explanation vào Supabase `exports`. Nếu không có run renderable, request đi qua `full_pipeline`. Vì vậy nút “generate” trên frontend không đồng nghĩa lúc nào cũng crawl lại dữ liệu hoặc chạy lại valuation.

### 5. Blocking semantics

Trong trạng thái vận hành hiện tại, gate bắt buộc không chỉ là metadata quan sát mà là điều kiện promotion của artifact downstream. Run chuyển thành `failed` khi stage/tool raise exception, chuyển thành `blocked` khi gate bắt buộc hoặc artifact bắt buộc không đạt, và chỉ được đặt `auto_exported` khi `publishable_final_report_model`, package validation, report quality, formula trace, evidence packet, tool permission và snapshot consistency đều đạt. Client-final vẫn fail-closed ở `authorize_client_final`, nơi approval, locked model và snapshot match được enforce thêm một lần.

Các gate quan trọng gồm `DATA_QUALITY_GATE`, `FORECAST_QUALITY_GATE`, `VALUATION_GATE`, `VALUATION_RECONCILIATION_GATE`, `REPORT_ASSEMBLY_GATE`, `REPORT_COMPLETENESS_GATE`, `SENIOR_CRITIC_GATE`, `CITATION_GATE`, `REPORT_QUALITY_GATE`, `PACKAGE_VALIDATION_GATE` và `EXPORT_GATE`. Khi viết đồ án, chỉ nên kết luận một ticker hoặc cohort đạt `DRAFT_PUBLISHABLE` nếu artifact evaluation hiện hành của phạm vi đó thực sự pass.

## Strategic Recommendations

| Ranh giới | Khuyến nghị |
|---|---|
| Stage mới | Chỉ thêm khi có artifact contract, gate contract và tests tương ứng |
| Resume/retry | Ưu tiên checkpoint và explicit artifact refs; không suy luận từ file mới nhất |
| Report publication | Tách `auto_exported` draft với `approved` final để bảo vệ sản phẩm client-facing |
| Batch scale | Queue bền vững là residual roadmap 1/10 khi mở rộng SLA production; thread pool và batch CLI đã đủ cho nghiệm thu MVP5 |
