# Bộ tài liệu dự án

Cập nhật: 2026-06-13

## Context

Thư mục `docs/` là nguồn tham chiếu chính cho dự án `multi-agent-equity-research`. Dự án là hệ thống nghiên cứu cổ phiếu ngành dược và y tế Việt Nam theo hướng evidence-grounded, deterministic valuation và controlled agentic workflow. Tài liệu này không thay thế code; nó mô tả các ranh giới vận hành, luồng dữ liệu, API, storage contract, agent/tool policy và các cổng kiểm định để người mới có thể hiểu, chạy, kiểm tra và mở rộng hệ thống mà không phá vỡ các giả định kiểm soát rủi ro.

## Problem Statement

Trước khi bổ sung bộ tài liệu này, `docs/` mới có tài liệu kiến trúc và tech stack, trong khi các chủ đề vận hành thiết yếu vẫn phân tán trong `README.md`, `config/`, `backend/`, `scripts/` và test suite. Thiếu hụt này tạo rủi ro onboarding sai, cấu hình sai Supabase, nhầm lẫn giữa full pipeline và fast render, hiểu sai vai trò của LLM trong valuation, và bỏ qua các export gates khi tạo báo cáo.

## Technical Deep-Dive

| Tài liệu | Phạm vi | Độc giả chính |
|---|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | Kiến trúc tổng thể, phân loại agent/service/gate, luồng chín chặng | Kiến trúc sư, reviewer, người bảo trì workflow |
| [TECHSTACK.md](TECHSTACK.md) | Runtime, framework, dependency, database, OCR, reporting, observability | DevOps, backend engineer, người dựng môi trường |
| [GETTING_STARTED.md](GETTING_STARTED.md) | Cài đặt nhanh, migrate DB, chạy research run, render report | Người mới vào dự án |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Bản đồ thư mục, module ownership, nơi cần sửa theo từng nhu cầu | Developer |
| [CONFIGURATION.md](CONFIGURATION.md) | Biến môi trường, model policy, Supabase, OCR, Langfuse, budget | Operator, DevOps |
| [WORKFLOW.md](WORKFLOW.md) | Pipeline `full_report`, stage semantics, state transition, artifact lifecycle | Backend engineer, product/QA |
| [AGENTS_AND_TOOLS.md](AGENTS_AND_TOOLS.md) | Sáu vai trò agent, tool registry, permission, LLM boundary | AI engineer, prompt engineer |
| [DATA_AND_STORAGE.md](DATA_AND_STORAGE.md) | Supabase PostgreSQL, migrations, canonical facts, storage buckets, artifacts | Data engineer, backend engineer |
| [SOURCES_AND_INGESTION.md](SOURCES_AND_INGESTION.md) | Nguồn dữ liệu, official documents, OCR, source tier, snapshot reuse | Data ops, analyst |
| [VALUATION.md](VALUATION.md) | Forecast, FCFF, FCFE, blend, sensitivity, formula trace, valuation gates | Quant/financial engineer |
| [REPORTING.md](REPORTING.md) | Report assembly, HTML/PDF render, fast report path, approval boundary | Reporting engineer, analyst |
| [EVALUATION_GATES.md](EVALUATION_GATES.md) | Numeric, citation, source provenance, FPTS grade, export gate | QA, reviewer |
| [API.md](API.md) | FastAPI endpoints, request/response models, status mapping | API consumer, frontend/backend integrator |
| [TESTING_AND_OPERATIONS.md](TESTING_AND_OPERATIONS.md) | Test strategy, smoke tests, runbook, failure triage, deployment notes | QA, DevOps, maintainer |

## Strategic Recommendations

| Ưu tiên | Khuyến nghị | Lý do |
|---|---|---|
| P0 | Đọc `GETTING_STARTED.md` trước khi chạy pipeline lần đầu | Tài liệu này nêu rõ Supabase-only runtime và thứ tự migrate/run/render |
| P0 | Dùng `WORKFLOW.md` và `EVALUATION_GATES.md` khi sửa harness | Hai tài liệu này mô tả stage contract và điều kiện block export |
| P1 | Cập nhật `TECHSTACK.md` mỗi khi thêm dependency production | Tech stack hiện có một số điểm lệch giữa import thực tế và `requirements.txt` |
| P1 | Cập nhật `DATA_AND_STORAGE.md` cùng lúc với migration hoặc storage key mới | Artifact reproducibility phụ thuộc trực tiếp vào schema và storage contract |
| P2 | Thêm diagram chi tiết hơn nếu xây giao diện hoặc batch platform | Hiện tài liệu ưu tiên vận hành code-first hơn là mô phỏng UI/product roadmap |
