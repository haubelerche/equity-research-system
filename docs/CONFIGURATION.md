# Cấu hình hệ thống

Cập nhật: 2026-06-13

## Context

Cấu hình runtime lấy chủ yếu từ biến môi trường và được gom trong `backend/settings.py`, `backend/database/config.py`, `backend/storage/supabase_adapter.py` và các file policy trong `config/`. Hệ thống ưu tiên cấu hình rõ ràng, fail-fast khi thiếu Supabase DB hoặc service-role key, và không dùng fallback local database.

## Problem Statement

Rủi ro cấu hình lớn nhất là lệch pha giữa template, code và kỳ vọng vận hành. `.env.example` vẫn có nội dung nhắc `ANTHROPIC_API_KEY`, trong khi production model adapter hiện dùng OpenAI; README cũ có chỗ nhắc PostgreSQL local, trong khi `require_database_url` khóa Supabase-only. Nếu không chuẩn hóa tài liệu, operator có thể cấp secret sai hoặc dựng môi trường không thể chạy pipeline.

## Technical Deep-Dive

### 1. Biến môi trường bắt buộc

| Biến | Vai trò | Nguồn đọc |
|---|---|---|
| `DATABASE_URL` | Supabase PostgreSQL DSN; phải trỏ tới host `.supabase.com` hoặc `.supabase.co` | `backend.database.config.require_database_url` |
| `OPENAI_API_KEY` | Gọi OpenAI Chat Completions và embeddings khi cần | `backend/harness/model_adapter.py`, retrieval/chunking |
| `SUPABASE_URL` | Base URL cho Supabase Storage REST API | `backend/storage/supabase_adapter.py` |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key cho bucket private | `backend/storage/supabase_adapter.py` |

### 2. Biến môi trường khuyến nghị

| Biến | Giá trị mặc định | Ý nghĩa |
|---|---|---|
| `DEFAULT_MODEL_NAME` hoặc `DEFAULT_MODEL` | `gpt-5-mini` | Model mặc định cho agent adapter |
| `FALLBACK_MODEL` | `gpt-5-nano` | Model nhẹ cho fallback hoặc tác vụ chi phí thấp |
| `WORKER_POOL_SIZE` | `4` | Số worker bất đồng bộ cho API executor |
| `DEFAULT_BUDGET_POLICY` | `standard` | Nhãn policy chi phí |
| `SOFT_BUDGET_USD` | `2.0` | Ngưỡng cảnh báo chi phí model |
| `HARD_BUDGET_USD` | `5.0` | Ngưỡng dừng budget guard |
| `ENABLE_AGENTIC_LOOPS` | `1` | Cờ bật vòng agentic nếu code path dùng đến |
| `LANGFUSE_PUBLIC_KEY` | rỗng | Bật tracing nếu đi cùng secret |
| `LANGFUSE_SECRET_KEY` | rỗng | Bật tracing nếu đi cùng public key |
| `LANGFUSE_BASE_URL` | tùy môi trường | Endpoint Langfuse |

### 3. Supabase PostgreSQL

`DATABASE_URL` phải dùng Supabase. Host local bị từ chối trực tiếp để tránh tình trạng test local chạy được nhưng production pipeline mất referential integrity, schema hoặc storage metadata.

Khuyến nghị dùng session pooler port `5432`. Transaction pooler port `6543` có xác suất lỗi cao hơn với long-running pipeline vì connection có thể bị recycle giữa migration, ingestion và artifact write.

### 4. Supabase Storage

Adapter dùng REST API trực tiếp, không dùng Supabase Python SDK. Các bucket bắt buộc:

| Bucket | Mục đích |
|---|---|
| `sources` | PDF/source binary chính thức, bất biến theo ticker/năm/source id |
| `runs` | Artifact theo `run_id`: manifest, valuation, evidence, report model, quality gate |
| `exports` | Báo cáo đã được approve hoặc xuất bản cho client |
| `archive` | Legacy, debug, failed run artifacts |

### 5. Model và provider

Production adapter hiện dùng OpenAI. `anthropic>=0.40` và `ANTHROPIC_API_KEY` đang là dấu vết legacy hoặc dependency dự phòng chưa nối vào runtime production chính. Không nên yêu cầu operator cấp Anthropic key nếu chưa có adapter và test tương ứng.

### 6. Docker

Dockerfile cài Python dependencies, Tesseract OCR, Vietnamese OCR data, Poppler, libpq và compiler toolchain. Entrypoint chạy migrations trước, sau đó chạy `scripts/run_research.py` với `TICKER`, `FROM_YEAR`, `TO_YEAR` và `ENABLE_OCR`.

```powershell
docker compose up --build
```

### 7. Encoding

Khi chạy local trên Windows, đặt UTF-8 để tránh mojibake trong log/report:

```powershell
$env:PYTHONUTF8 = "1"
```

## Strategic Recommendations

| Ưu tiên | Hành động | Lý do |
|---|---|---|
| P0 | Cập nhật `.env.example` để phản ánh OpenAI là production provider hiện tại | Tránh operator cấp sai secret và hiểu sai runtime |
| P0 | Không nới lỏng Supabase-only guard nếu chưa có kế hoạch local schema parity | Local DB dễ làm sai migration, bucket metadata và source provenance |
| P1 | Chuẩn hóa dependency còn thiếu trong `requirements.txt` như `vnstock`, `requests`, `beautifulsoup4`, `apscheduler`, `pdfkit`, `pypdf` nếu các code path đó là production | Môi trường sạch sẽ fail import nếu chỉ dựa vào dependency bắc cầu |
| P1 | Thêm smoke test Docker cho migration, OCR và render PDF | Giảm rủi ro image build được nhưng không xuất được report |
