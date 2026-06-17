# Bộ tài liệu dự án

Cập nhật: 2026-06-17

## Context

Thư mục `docs/` là nguồn tham chiếu chính cho dự án `multi-agent-equity-research` ở trạng thái codebase hiện hành. Dự án là hệ thống nghiên cứu cổ phiếu ngành dược và y tế Việt Nam theo hướng evidence-grounded, deterministic valuation và controlled agentic workflow. Tài liệu này không thay thế code; nó mô tả các ranh giới vận hành, luồng dữ liệu, API, storage contract, agent/tool policy, benchmark suite và các cổng kiểm định để người mới có thể hiểu, chạy, kiểm tra, mở rộng hệ thống và sử dụng làm dữ liệu viết đồ án.

## Problem Statement

Sau đợt nâng cấp, `docs/` được tổ chức như một bộ hồ sơ vận hành và viết đồ án, nhưng phải đọc cùng trạng thái artifact hiện tại. Trọng tâm tài liệu là giúp người đọc không nhầm `DRAFT_PUBLISHABLE` với client-final, không xem LLM là nguồn sự thật tài chính, không diễn giải full-universe benchmark như chất lượng sâu tương đương MVP5, và không dùng các câu nghiệm thu cũ nếu benchmark aggregate mới nhất đang báo `BLOCKED_BY_P0`.

## Technical Deep-Dive

| Tài liệu | Phạm vi | Độc giả chính |
|---|---|---|
| [CURRENT_STATE_AND_UPDATES.md](CURRENT_STATE_AND_UPDATES.md) | Trạng thái code hiện hành, benchmark mới nhất, ranh giới runtime/frontend/evaluation | Tất cả thành viên dự án |
| [THESIS_HANDOFF.md](THESIS_HANDOFF.md) | Thesis framing và cách trình bày contribution; cần đối chiếu với trạng thái mới trước khi trích số liệu nghiệm thu | Thesis writer, architect, product owner |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Kiến trúc tổng thể, phân loại agent/service/gate, luồng chín chặng | Kiến trúc sư, reviewer, người bảo trì workflow |
| [TECHSTACK.md](TECHSTACK.md) | Runtime, framework, dependency, database, OCR, reporting, observability | DevOps, backend engineer, người dựng môi trường |
| [GETTING_STARTED.md](GETTING_STARTED.md) | Cài đặt nhanh, migrate DB, chạy research run, render report | Người mới vào dự án |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Bản đồ thư mục, module ownership, nơi cần sửa theo từng nhu cầu | Developer |
| [CONFIGURATION.md](CONFIGURATION.md) | Biến môi trường, model policy, Supabase, OCR, Langfuse, budget | Operator, DevOps |
| [WORKFLOW.md](WORKFLOW.md) | Pipeline `full_report`, stage semantics, state transition, artifact lifecycle | Backend engineer, product/QA |
| [AGENTS_AND_TOOLS.md](AGENTS_AND_TOOLS.md) | Phân loại vai trò cấu hình, tác tử LLM, tool, service, gate và LLM boundary | AI engineer, prompt engineer |
| [DATA_AND_STORAGE.md](DATA_AND_STORAGE.md) | Supabase PostgreSQL, migrations, canonical facts, storage buckets, artifacts | Data engineer, backend engineer |
| [DATA_ARCHITECTURE_ER.md](DATA_ARCHITECTURE_ER.md) | Sơ đồ ER Supabase theo schema, lineage dữ liệu, snapshot, artifact, citation và mapping vào mục 3.3 đồ án | Thesis writer, data architect |
| [SOURCES_AND_INGESTION.md](SOURCES_AND_INGESTION.md) | Nguồn dữ liệu, official documents, OCR, source tier, snapshot reuse | Data ops, analyst |
| [VALUATION.md](VALUATION.md) | Forecast, FCFF, FCFE, blend, sensitivity, formula trace, valuation gates | Quant/financial engineer |
| [REPORTING.md](REPORTING.md) | Report assembly, PDF render, HTML trung gian kỹ thuật, fast report path, approval boundary | Reporting engineer, analyst |
| [EVALUATION_GATES.md](EVALUATION_GATES.md) | Numeric, citation, source provenance, Report quality, export gate | QA, reviewer |
| [eval/README.md](eval/README.md) | Evaluation baseline cho data, RAG, finance, citation, agent, report quality, observability và CI | Architect, QA, product owner |
| [API.md](API.md) | FastAPI endpoints, request/response models, status mapping | API consumer, frontend/backend integrator |
| [TESTING_AND_OPERATIONS.md](TESTING_AND_OPERATIONS.md) | Test strategy, smoke tests, runbook, failure triage, deployment notes | QA, DevOps, maintainer |

## Strategic Recommendations

| Ưu tiên | Khuyến nghị | Lý do |
|---|---|---|
| P0 | Đọc `CURRENT_STATE_AND_UPDATES.md` trước khi dùng sơ đồ hoặc kế hoạch cũ | Tài liệu này ghi rõ trạng thái benchmark hiện hành và ranh giới draft/client-final |
| P0 | Dùng `THESIS_HANDOFF.md` như nguồn narrative, nhưng đối chiếu với benchmark/output mới nhất trước khi ghi trạng thái nghiệm thu | Tránh đưa vào đồ án các câu đã outdate so với codebase hiện tại |
| P0 | Dùng `WORKFLOW.md` và `EVALUATION_GATES.md` khi sửa harness | Hai tài liệu này mô tả stage contract, kiểm định chất lượng và cảnh báo xuất bản |
| P1 | Dùng `docs/eval/` và `config/benchmarks/` khi mở rộng evaluation mới | Bộ kế hoạch và dataset benchmark là regression baseline hiện tại |
| P1 | Cập nhật `TECHSTACK.md` mỗi khi thêm dependency production | Tech stack là một phần bằng chứng tái lập của đồ án |
| P1 | Cập nhật `DATA_AND_STORAGE.md` cùng lúc với migration hoặc storage key mới | Artifact reproducibility phụ thuộc trực tiếp vào schema và storage contract |
| P2 | Thêm diagram chi tiết hơn nếu xây batch platform production | Residual roadmap 1/10 nằm ở queue bền vững, SLA và CI/CD đa môi trường |
