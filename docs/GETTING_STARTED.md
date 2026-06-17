# Hướng dẫn bắt đầu

Cập nhật: 2026-06-17

## Context

Dự án vận hành một pipeline nghiên cứu cổ phiếu có kiểm soát cho nhóm dược và y tế Việt Nam. Đường chạy production hiện tại là `scripts/run_research.py`, đi qua `FullReportOrchestrator` và `ResearchGraphRunner`. Đường `scripts/generate_fast_report.py` chỉ render lại báo cáo từ artifact đã tồn tại; nó không chạy ingestion, không chạy OCR và không tạo valuation mới.

## Problem Statement

Người mới dễ mắc ba lỗi cấu hình có tác động lớn: dùng PostgreSQL local dù runtime đang khóa Supabase-only, dùng transaction pooler port `6543` thay vì session pooler port `5432`, hoặc chạy fast renderer trước khi có run đã tạo `publishable_final_report_model`. Các lỗi này không phải lỗi báo cáo, mà là lỗi lifecycle và môi trường.

## Technical Deep-Dive

### 1. Điều kiện tối thiểu

| Thành phần | Yêu cầu |
|---|---|
| Python | Python 3.10 trở lên; Dockerfile dùng `python:3.11-slim` |
| Database | Supabase PostgreSQL, không dùng `localhost`, `127.0.0.1`, `db` hoặc host ngoài Supabase |
| Storage | Supabase Storage với service-role key và các bucket `sources`, `runs`, `exports`, `archive` |
| LLM | `OPENAI_API_KEY` cho production model adapter và embeddings khi cần |
| OCR | Tesseract, Vietnamese language pack, Poppler nếu xử lý PDF scan |

### 2. Cài dependency local

```powershell
pip install -r requirements.txt
```

Nếu chạy OCR local trên Windows, cần bảo đảm Tesseract và Poppler tồn tại trong PATH hoặc được cấu hình theo cách tương thích với `pytesseract` và `pdf2image`.

### 3. Tạo `.env`

Sao chép `.env.example` thành `.env`, sau đó cấu hình các biến bắt buộc:

```env
DATABASE_URL=postgresql://postgres.your-project:your-password@aws-0-your-region.pooler.supabase.com:5432/postgres
OPENAI_API_KEY=sk-...
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
DEFAULT_MODEL_NAME=gpt-5-mini
FALLBACK_MODEL=gpt-5-nano
```

Lưu ý kỹ thuật: `DATABASE_URL` phải trỏ tới Supabase session pooler hoặc host Supabase tương thích. Module `backend.database.config.require_database_url` chủ động từ chối host local và host không thuộc Supabase.

### 4. Chạy migrations

```powershell
python -m backend.database.migrate --check
python -m backend.database.migrate
python -m backend.database.migrate --version
```

`backend.database.migrate.CURRENT_SCHEMA_VERSION` hiện yêu cầu `043_cafef_financial_source_type`, trong khi thư mục migration đã có các migration mới hơn tới `045_agm_resolutions` và `RuntimeStore` yêu cầu tối thiểu `035_runs_status_auto_exported`. Vì vậy `--check` có thể vẫn liệt kê migration chưa chạy dù API chỉ kiểm schema floor thấp hơn. Nếu API hoặc CLI báo schema out of date, chạy lại migration runner thay vì chạy thủ công từng file SQL.

### 5. Chạy tự động một lần từ đầu tới cuối

Khi đã có PDF báo cáo tài chính chính thức trong `data/official_documents/<TICKER>/<YEAR>/source_document.pdf` và tài liệu ĐHCĐ trong `config/dataset/DHCD/`, dùng một lệnh sau để chạy đầy đủ PDF LLM gap-fill, AGM ingest, research harness và render:

```powershell
make run-once TICKER=DHG FROM_YEAR=2021 TO_YEAR=2025 REPORT_MODE=standard
```

Target này tạo hoặc cập nhật các artifact kiểm toán chính: `artifacts/official_sources/DHG_pdf_llm_result.json`, `artifacts/official_sources/DHG_agm_result.json`, run-scoped facts/forecast/valuation/report artifacts, `output/DHG_report.pdf`, `output/DHG_explanation.pdf` và `output/DHG_valuation_workings.md` khi valuation workings khả dụng.

### 6. Chạy full research pipeline

```powershell
$env:PYTHONUTF8 = "1"
python scripts/run_research.py --ticker DHG --from-year 2021 --to-year 2025 --ocr --draft
```

`--draft` bật `auto_approve_assumptions` và `auto_approve_final` trong policy để phục vụ development/test. Với báo cáo client-final, không nên coi draft mode là phê duyệt chuyên gia. Nếu cần AGM/DHCD driver hoặc PDF LLM gap-fill mới nhất, chạy `scripts/ingest_agm.py` và `scripts/ingest_pdf_llm.py` trước, hoặc dùng `make run-once`.

### 7. Render nhanh từ artifact đã có

```powershell
python scripts/generate_fast_report.py --ticker DHG --mode analyst_draft
```

Hoặc với client-final:

```powershell
python scripts/generate_fast_report.py --ticker DHG --mode client_final
```

`client_final` yêu cầu run đã được approve và snapshot mới nhất khớp authorization. Nếu không có ready snapshot hoặc không có run phù hợp, script dừng sớm để tránh render báo cáo từ artifact cũ.

### 8. Chạy API local

```powershell
python -m uvicorn backend.api:app --host 0.0.0.0 --port 8010
```

API dùng `RuntimeStore`, `RunExecutor` và `FullReportOrchestrator`; endpoint `/research/start` tạo run bất đồng bộ qua thread pool.

### 9. Chạy frontend

```powershell
cd frontend
npm install
npm run dev
```

Vite chạy tại `http://localhost:5173` và proxy `/reports`, `/research` sang backend tại cổng `8000`. Nếu backend chạy theo ví dụ cổng `8010` ở trên, cần đồng bộ cổng proxy hoặc chạy Uvicorn tại `8000`.

Production-like:

```powershell
cd frontend
npm run build
cd ..
python -m uvicorn backend.api:app --host 0.0.0.0 --port 8010
```

Khi `frontend/dist/index.html` tồn tại, FastAPI phục vụ SPA sau các API routes. Route `/eval` đọc evaluation packet và artifacts trực tiếp từ backend; dữ liệu mẫu chỉ còn phục vụ development/test.

### 10. Chạy evaluation và benchmark suite

```powershell
python scripts/run_project_evaluation.py --ticker DHG --output-dir output/evaluation/eval_result
```

Harness project-level chạy tuần tự tám evaluation plan, thực thi test scope tương ứng và tạo packet fail-closed cho một ticker. Để đánh giá theo cohort hoặc toàn universe, dùng benchmark suite:

```powershell
python scripts/run_benchmark_suite.py --cohort mvp5_validated
python scripts/run_benchmark_suite.py --cohort full_universe --reuse-existing
python scripts/run_benchmark_suite.py --plans 03 --reuse-existing
```

`/eval` trên frontend ưu tiên đọc `output/evaluation/eval_result/benchmark_suite/benchmark_suite.json` nếu file này tồn tại. Kết quả mới nhất trong repo có thể là một lần chạy tập trung vào một plan cụ thể, ví dụ plan `03`, nên khi dùng cho đồ án phải ghi rõ phạm vi plan/cohort và trạng thái `publication_status` thay vì mặc định kết luận toàn bộ hệ thống đã pass.

## Strategic Recommendations

| Tình huống | Lệnh nên dùng | Ghi chú kiểm soát |
|---|---|---|
| Khởi tạo DB mới | `python -m backend.database.migrate` | Không chạy migration thủ công bằng copy/paste |
| Chạy một ticker từ ingestion bổ sung tới PDF | `make run-once TICKER=DHG FROM_YEAR=2021 TO_YEAR=2025 REPORT_MODE=standard` | Chạy PDF LLM, AGM, harness và render theo thứ tự cố định |
| Tạo research artifact mới | `python scripts/run_research.py --ticker DHG --from-year 2022 --to-year 2025` | Đây là đường production cho full pipeline |
| Xuất bản thử nhanh | `python scripts/generate_fast_report.py --ticker DHG --mode analyst_draft` | Chỉ dùng artifact đã có |
| Kiểm tra OCR runtime | `python scripts/check_ocr_runtime.py` | Cần trước khi ingest PDF scan |
| Chạy evaluation một ticker | `python scripts/run_project_evaluation.py --ticker DHG` | Tạo tám artifact project-level fail-closed |
| Chạy benchmark cohort | `python scripts/run_benchmark_suite.py --cohort mvp5_validated` | Tạo artifact theo ticker và aggregate suite |
| Chạy test toàn bộ | `python -m pytest -q tests` | Một số integration test cần DB hoặc network hợp lệ |
