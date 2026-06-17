# Testing và vận hành

Cập nhật: 2026-06-17

## Context

Test suite bao phủ analytics, gates, reporting, citations, documents, database, storage và harness. Vận hành production phụ thuộc vào Supabase DB, Supabase Storage, OpenAI credentials, OCR runtime nếu ingest PDF scan, và rendering dependencies nếu xuất PDF.

## Problem Statement

Hệ thống có nhiều failure mode: schema out of date, source connector fail, OCR thiếu binary, storage network reset, LLM env thiếu, valuation gate fail, citation gate fail hoặc PDF renderer lỗi font. Runbook cần giúp phân biệt lỗi hạ tầng với lỗi chất lượng dữ liệu/báo cáo.

## Technical Deep-Dive

### 1. Lệnh test canonical

```powershell
python -m pytest -q tests
```

Hoặc qua Makefile:

```powershell
make test
make audit
```

`make audit` hiện chạy một subset liên quan workflow, tool registry, report assembler, production gates và model adapter diagnostics.

### 2. Nhóm test theo thư mục

| Thư mục | Phạm vi |
|---|---|
| `tests/unit/` | Analytics, gates, report, storage contract, adapters, validators |
| `tests/evaluation/` | Numeric claim gates, Report quality, source gates |
| `tests/documents/` | Official document connectors và auto ingest |
| `tests/database/` | DB connection/store retry |
| `tests/storage/` | Request retry và storage behavior |
| `tests/citations/` | Source tier, evidence, citation evaluation |
| `tests/integration/` | Connector/live integration, cần môi trường hợp lệ |

### 3. Smoke tests trước khi chạy pipeline

| Kiểm tra | Lệnh | Kỳ vọng |
|---|---|---|
| Migrations pending | `python -m backend.database.migrate --check` | Liệt kê pending hoặc báo không còn pending |
| Schema version | `python -m backend.database.migrate --version` | Có version mới nhất |
| OCR runtime | `python scripts/check_ocr_runtime.py` | Tesseract/Poppler/Python packages sẵn sàng |
| Unit tests gates | `python -m pytest -q tests/unit/test_production_gates.py tests/evaluation/test_report_quality.py` | Pass |
| Client-final governance | `python -m pytest -q tests/evaluation/test_client_final_governance.py tests/unit/test_publication_readiness.py tests/unit/test_package_validation_gate.py tests/unit/test_export_gate.py` | Pass; `auto_exported` không được xem là approved final |
| Project evaluation | `python scripts/run_project_evaluation.py --ticker DHG --output-dir output/evaluation/eval_result` | Tạo tám plan artifacts và `evaluation_packet.json`; thiếu runtime evidence vẫn fail-closed |
| Benchmark suite | `python scripts/run_benchmark_suite.py --cohort mvp5_validated` | Tạo artifact theo ticker và aggregate suite; đọc `publication_status` trước khi kết luận pass/fail |
| Frontend | `cd frontend; npm test; npm run build` | Vitest pass và Vite production build thành công |
| Static SPA serving | `python -m pytest -q tests/api/test_static_serving.py` | API routes được ưu tiên trước SPA fallback |
| Full run draft | `python scripts/run_research.py --ticker DHG --from-year 2022 --to-year 2025 --draft` | Terminal status không `failed`; nếu `blocked`, đọc gate reasons |

### 4. Failure triage

| Triệu chứng | Nguyên nhân có xác suất cao | Bước xử lý |
|---|---|---|
| `DATABASE_URL is required` | `.env` thiếu hoặc không được load | Kiểm tra `.env`, shell env và working directory |
| `Local PostgreSQL is disabled` | Dùng host local | Đổi sang Supabase PostgreSQL |
| `Schema version mismatch` | Chưa chạy migrations | Chạy `python -m backend.database.migrate` |
| Storage 401/403 | Service-role key thiếu/sai | Kiểm tra `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` |
| Storage 404 khi đọc artifact | Artifact chưa được upload hoặc key không thuộc contract | Kiểm tra run manifest và `run_artifacts` |
| `publishable_final_report_model_missing` | Export gates không promote model | Đọc `quality_gate` và gate results |
| `client_final_render_blocked:*` | Thiếu approval, package validation, Report-quality allow_export, locked model hoặc snapshot match | Đọc `publication_readiness` và artifacts `report_quality_evaluation`, `quality_gate`, `publishable_final_report_model`, `valuation` |
| Eval dashboard không tải live data | Backend evaluation endpoint, proxy hoặc artifact path lỗi | Kiểm tra `/eval/framework`, `/eval/artifacts/{artifact_name}`, network proxy và run evaluation artifacts |
| Fast report không tìm thấy run | Chưa có locked publishable model hoặc mode yêu cầu approved | Chạy full pipeline hoặc approval flow phù hợp |
| PDF mojibake | Font/renderer issue | Kiểm tra WeasyPrint, fallback renderer và Unicode fonts |

### 5. Observability

Khi có Langfuse credentials, model adapter dùng drop-in OpenAI tracing và flush ở cuối run. Nếu không có credentials, runtime tiếp tục không tracing. Audit events trong DB vẫn là nguồn local đáng tin cậy cho stage/tool/gate trace.

### 6. Deployment notes

Docker image chạy migrations rồi chạy pipeline. Điều này phù hợp batch/job container, nhưng không phải API server long-running mặc định. Nếu muốn chạy API service, cần command riêng như:

```powershell
python -m uvicorn backend.api:app --host 0.0.0.0 --port 8010
```

Nếu deploy frontend lên Vercel, hãy đặt `Root Directory` = `frontend/` để Vercel dùng đúng `frontend/vercel.json`.
Backend FastAPI nên deploy ở runtime khác, không ghép chung vào Vercel static hosting của SPA.

## Strategic Recommendations

| Ưu tiên | Hành động |
|---|---|
| Done | Test environment đã có regression baseline cho import smoke, unit tests, gates tests, migration dry-run, project evaluation và benchmark suite |
| P0 | Chạy PDF render smoke trong container thật nếu PDF là deliverable bắt buộc |
| P1 | Tách Docker command cho `worker`, `api` và `one-shot research job` |
| Done | Dependency manifest đã khai báo trực tiếp crawler, vnstock, PDF fallback, pypdf và evaluation stack cần cho nghiệm thu |
| P2 | Thêm dashboard trạng thái run/gate/artifact nếu vận hành nhiều ticker |
