# API backend

Cập nhật: 2026-06-13

## Context

Backend API dùng FastAPI và expose surface tối thiểu để tạo research run, kiểm tra trạng thái và lấy artifact metadata. API không render report client-final trực tiếp; publication/rendering vẫn bị kiểm soát bởi artifact lifecycle và approval path.

## Problem Statement

API cho agentic workflow không nên chỉ trả về "success" hoặc "failed". Consumer cần phân biệt run đang phân tích, đang valuation, đã auto-export draft, đã approved, blocked do gate hay failed do exception. Nếu status mapping không rõ, frontend hoặc operator có thể công bố nhầm draft.

## Technical Deep-Dive

### 1. App creation

`backend.api.create_app` khởi tạo:

| Thành phần | Vai trò |
|---|---|
| `RuntimeStore` | DB persistence cho runs/steps/artifacts |
| `FullReportOrchestrator` | Workflow lifecycle |
| `RunExecutor` | Thread pool submit cho run bất đồng bộ |
| Schema check | Có thể bật/tắt bằng `check_schema_on_startup` |

### 2. Endpoints

| Method | Path | Mục đích |
|---|---|---|
| `GET` | `/health` | Health check tối thiểu |
| `POST` | `/research/start` | Tạo run `full_report`, register ticker từ universe, submit executor |
| `GET` | `/research/{run_id}/status` | Trả trạng thái public của run |
| `GET` | `/research/{run_id}/artifacts` | Liệt kê artifact metadata của run |
| `GET` | `/reports/{run_id}` | Lọc artifact liên quan report/evaluation/log |

### 3. StartRunRequest

```json
{
  "ticker": "DHG",
  "run_type": "full_report",
  "objective": "Generate grounded equity research output for selected ticker.",
  "scenarios": ["base", "bull", "bear"],
  "org_id": "optional",
  "requested_by": "optional",
  "budget_policy": "standard"
}
```

API tạo `run_id` deterministic từ ticker, run type, objective và requester. Nếu create run gặp conflict nhưng run đã tồn tại, API trả lại status của run hiện có.

### 4. Public statuses

| Public status | DB status mapping tiêu biểu |
|---|---|
| `INIT` | `initialized` |
| `ANALYZING` | `running`, `data_ready`, `analysis_ready` |
| `VALUATING` | `valuation_ready` |
| `SYNTHESIZING` | `report_ready` |
| `PUBLISHED_DRAFT` | `auto_exported` |
| `PUBLISHED` | `approved` |
| `BLOCKED` | `blocked` |
| `FAILED` | `failed`, `cancelled` |

### 5. Artifact response

Artifact item gồm `artifact_id`, `artifact_type`, `section_key`, `payload`, `confidence`, `created_by_agent` và `created_at`. RuntimeStore còn lưu `storage_bucket`, `storage_path`, checksum, content type, file size và lock flag; nếu API consumer cần các field này, response schema cần được mở rộng có kiểm soát.

## Strategic Recommendations

| Vấn đề | Khuyến nghị |
|---|---|
| Frontend publication | Không hiển thị `PUBLISHED_DRAFT` như approved final |
| Polling | Poll `/research/{run_id}/status`, sau đó lấy artifacts khi status terminal |
| Approval API | Nếu cần client-final approval, thêm endpoint rõ stage/decision/reviewer và audit event |
| Artifact download | Chỉ tạo signed URL từ `exports` bucket, không expose `runs` hoặc `sources` trực tiếp |
| Idempotency | Nếu mở rộng API public, thêm idempotency key explicit thay vì chỉ deterministic run id |
