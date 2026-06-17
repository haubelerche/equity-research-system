# Trạng thái hiện hành và cập nhật dự án

Cập nhật: 2026-06-17

## Context

Tài liệu này là mốc tham chiếu hiện hành cho dự án `multi-agent-equity-research`. Nếu các ghi chú cũ trong đồ án, README hoặc tài liệu phụ mâu thuẫn với file này, ưu tiên file này trước khi mô tả kiến trúc, pipeline, dữ liệu, evaluation hoặc trạng thái sản phẩm.

Dự án hiện là một hệ thống hỗ trợ nghiên cứu cổ phiếu dược và y tế Việt Nam theo hướng có kiểm soát: dữ liệu có nguồn, định giá bằng mã chương trình, báo cáo có bằng chứng, workflow có `run_id`, artifact có checksum/manifest, và kết quả client-facing phải đi qua ranh giới phê duyệt. Không nên mô tả hệ thống như chatbot đầu tư tự do hoặc hệ đa tác tử tự trị.

## Problem Statement

Trạng thái mới của repo không còn là bản prototype, nhưng cũng không nên gọi toàn bộ hệ thống là đã đạt final production hoặc client-final tự động. Cách mô tả đúng là: core research workflow, fast render, report inventory, benchmark suite và frontend dashboard đã có trong codebase; nhiều artifact/PDF/evaluation output đã được sinh cho universe rộng hơn MVP5; tuy nhiên benchmark aggregate mới nhất trong `output/evaluation/eval_result/benchmark_suite/benchmark_suite.json` đang là một lần chạy tập trung vào plan `03` và có trạng thái `BLOCKED_BY_P0`, nên không được dùng câu “toàn hệ thống đã pass 9/10” nếu không chỉ rõ artifact nghiệm thu tương ứng.

## Technical Deep-Dive

### 1. Bản đồ năng lực hiện có

| Khu vực | Trạng thái hiện tại | Entry point/bằng chứng |
|---|---|---|
| Research runtime | `full_report` vẫn là workflow chính, do `FullReportOrchestrator` gọi `ResearchGraphRunner` với graph cố định chín stage. | `backend/orchestrator.py`, `backend/harness/runner.py`, `backend/harness/graph.py` |
| Sinh báo cáo từ UI | `/reports/{ticker}/generate` tự chọn `fast_render` nếu có snapshot và run có thể render; nếu không có thì chạy `full_pipeline`. | `backend/api.py`, `backend/orchestrator.py`, `backend/reporting/report_delivery.py` |
| Fast render | Render từ artifact đã có, không chạy lại ingestion/OCR/valuation; bản tải xuống ưu tiên Supabase `exports`, local `output/` chỉ là fallback/dev cache. | `scripts/generate_fast_report.py`, `backend/reporting/report_delivery.py`, `backend/api.py` |
| Full one-shot local | `make run-once` chạy PDF LLM gap-fill, AGM/DHCD ingest, harness draft và render local theo thứ tự cố định. | `Makefile` |
| Dữ liệu AGM/DHCD | Có thư mục `config/dataset/DHCD/` với nhiều tài liệu ĐHCĐ 2026 và các artifact ingest AGM trong `artifacts/official_sources/`. | `config/dataset/DHCD/`, `scripts/ingest_agm.py` |
| Báo cáo PDF local | Có các PDF local đã render cho một số ticker như AGP, DBD, DGW, DHG, DMC, IMP, PVD, TMP; đây là output/cache, không phải nguồn sự thật production. | `output/*_report.pdf`, `output/*_explanation.pdf` |
| Evaluation project-level | Có `scripts/run_project_evaluation.py` cho tám plan và `scripts/run_benchmark_suite.py` cho cohort benchmark. Dashboard ưu tiên `benchmark_suite` nếu tồn tại. | `backend/evaluation/project_evaluator.py`, `scripts/run_benchmark_suite.py` |
| Benchmark suite hiện hành | Có 43 thư mục ticker trong `output/evaluation/eval_result/benchmark_suite/`; aggregate hiện tại chỉ ghi plan `03`, status `fail`, publication `BLOCKED_BY_P0`. | `output/evaluation/eval_result/benchmark_suite/benchmark_suite.json` |
| Frontend | React/Vite SPA có `/reports` và `/eval`; `/eval` đọc backend evaluation artifacts, không nên mô tả là dashboard mock mặc định. | `frontend/src/`, `backend/api.py` |
| Deployment | Frontend có Vercel config; backend chạy FastAPI/Uvicorn, Docker/Railway; Supabase làm DB và object storage. | `frontend/vercel.json`, `Dockerfile`, `railway.json`, `backend/settings.py` |
| Scheduler | Airflow/Astro không còn là runtime active; news cron dùng Windows Task Scheduler gọi CLI idempotent. | `scripts/schedule_news_collection.ps1` |

### 2. Luồng runtime hiện tại

```text
PREFLIGHT
-> PLAN
-> INGEST_AND_VALIDATE
-> ANALYZE
-> FORECAST_AND_VALUE
-> WRITE_REPORT
-> REVIEW
-> EXPORT_GATES
-> PUBLISH
```

| Stage | Diễn giải cập nhật |
|---|---|
| `INGEST_AND_VALIDATE` | Tái sử dụng snapshot nếu còn phù hợp và không `force_ingest`; nếu không thì chạy ingest, build facts và build index. |
| `FORECAST_AND_VALUE` | Forecast và valuation là công cụ tất định; LLM không tính target price. Peer multiples hiện có nhánh xây peer pack từ production facts và vnstock khi đủ dữ liệu. |
| `WRITE_REPORT` | Tác tử viết bản nháp từ artifact đã khóa; không được tự đọc dữ liệu sống hoặc tự bù số liệu thiếu. |
| `EXPORT_GATES` | Ghi evidence packet, chạy report quality/package validation và chỉ promote model nếu không còn blocker trọng yếu. |
| `PUBLISH` | Xác nhận publishable model, ghi evaluation artifacts và manifest; việc render PDF là bước riêng hoặc fast/full generate hook. |

### 3. Trạng thái dữ liệu và benchmark

Universe cấu hình hiện có 43 ticker trong `config/dataset/universe/pharma_vn_universe.csv`, trong đó MVP core vẫn là DHG, IMP, DMC, TRA và DBD. Benchmark suite đã được mở rộng để chạy theo cohort và có thể tổng hợp toàn universe, nhưng kết quả aggregate mới nhất trong repo đang phản ánh một lần chạy tập trung vào financial calculation plan `03`; do đó khi viết đồ án cần phân biệt:

| Phạm vi | Cách mô tả nên dùng |
|---|---|
| MVP5 | Phạm vi sâu nhất để giải thích kiến trúc, dữ liệu, định giá và báo cáo mẫu. |
| Universe 43 ticker | Phạm vi mở rộng để chứng minh khả năng chạy benchmark/cohort, nhưng không đồng nghĩa với mọi ticker đều đạt chất lượng báo cáo sâu. |
| Output PDF local | Bằng chứng render/dev cache cho một số ticker; không thay thế run manifest và Supabase export. |
| Benchmark suite hiện tại | Bằng chứng evaluation hiện hành; nếu status `BLOCKED_BY_P0`, phải trình bày như phát hiện chất lượng cần xử lý, không diễn giải thành pass. |

### 4. Ranh giới thuật ngữ cần giữ khi viết đồ án

| Thuật ngữ kỹ thuật | Cách gọi tiếng Việt nên dùng |
|---|---|
| `run_id` | Mã phiên xử lý/lần chạy |
| `snapshot_id` | Mã ảnh chụp dữ liệu đã khóa |
| `artifact` | Sản phẩm trung gian hoặc tệp kết quả theo lần chạy |
| `manifest` | Bản kê khai lần chạy |
| `gate` | Cổng kiểm định |
| `fast_render` | Kết xuất nhanh từ dữ liệu và artifact đã có |
| `full_pipeline` | Chạy trọn luồng nghiên cứu |
| `DRAFT_PUBLISHABLE` | Bản nháp đủ điều kiện kỹ thuật sau kiểm định tự động |
| `client_final` | Bản cuối dành cho người đọc sau phê duyệt hợp lệ |

## Strategic Recommendations

| Ưu tiên | Khuyến nghị |
|---|---|
| P0 | Khi viết đồ án, không dùng lại câu “nghiệm thu 9/10” như trạng thái bao trùm nếu chưa gắn với artifact cụ thể. |
| P0 | Mô tả đúng hai đường sinh báo cáo: `fast_render` từ artifact đã có và `full_pipeline` khi cần chạy lại ingestion/valuation/report. |
| P0 | Dùng benchmark suite hiện tại như bằng chứng hệ thống có cơ chế fail-closed; trạng thái `BLOCKED_BY_P0` là phát hiện, không phải lỗi tài liệu cần che đi. |
| P1 | Khi cập nhật docs tiếp theo, đồng bộ `CURRENT_SCHEMA_VERSION`, migration mới nhất và benchmark plan đang chạy. |
| P1 | Với phần luận văn, dùng MVP5 để phân tích sâu và dùng universe 43 ticker như minh họa khả năng mở rộng/batch benchmark. |
