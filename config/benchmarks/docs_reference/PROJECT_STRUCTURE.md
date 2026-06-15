# Cấu trúc dự án

Cập nhật: 2026-06-14

## Context

Repo được tổ chức quanh một backend Python, bộ script vận hành, cấu hình domain, test suite và các artifact local. Quy ước quan trọng là logic nghiệp vụ chính nằm trong `backend/`, entrypoint vận hành nằm trong `scripts/`, còn `config/` chứa policy, taxonomy, agent prompt và contract.

## Problem Statement

Một repo agentic finance có nhiều lớp dễ gây nhầm lẫn: connector, OCR, canonical facts, deterministic valuation, LLM agent, report renderer và export gate đều cùng tham gia một output cuối. Nếu không có bản đồ module rõ ràng, thay đổi nhỏ ở connector hoặc schema có thể làm hỏng downstream gates hoặc khiến báo cáo dùng artifact không đúng run.

## Technical Deep-Dive

| Đường dẫn | Trách nhiệm | Khi nào cần sửa |
|---|---|---|
| `backend/api.py` | FastAPI app, endpoint start/status/artifact/report | Khi thêm API surface hoặc thay đổi response contract |
| `backend/orchestrator.py` | Lifecycle wrapper cho workflow `full_report` | Khi thêm run type hoặc context field cấp cao |
| `backend/harness/` | Graph runner, agent registry, model adapter, gates, state, tool registry | Khi thay đổi stage, agent permission, gate hoặc LLM contract |
| `backend/analytics/` | Forecast, ratios, FCFF, FCFE, blend, multiples, sensitivity | Khi sửa logic tài chính hoặc formula trace |
| `backend/database/` | DB config, migrations, DAL, canonical schema access | Khi thay đổi schema hoặc persistence layer |
| `backend/documents/` | Official document discovery, OCR, candidate facts, promotion | Khi thêm nguồn tài liệu hoặc pipeline OCR |
| `backend/facts/` | Normalization, reconciliation, metric metadata, completeness | Khi sửa taxonomy/fact validation |
| `backend/citations/` | Claim ledger, citation map, source tier policy, driver evidence | Khi sửa provenance hoặc citation gates |
| `backend/evaluation/` | Numeric consistency, citation coverage, source provenance, Report quality | Khi thay đổi quality rubric hoặc export blockers |
| `backend/reporting/` | View model, chart builder, renderer, publisher, PDF export | Khi sửa báo cáo client-facing |
| `backend/storage/` | Supabase Storage adapter và key contract | Khi thêm bucket hoặc object path |
| `scripts/` | CLI production và admin tasks | Khi thêm thao tác vận hành có thể chạy độc lập |
| `config/agents/` | Agent YAML và prompt library | Khi sửa role, prompt, allowed tools hoặc output schema |
| `config/harness/` | Tool contracts, gate policy, run state schema, task registry | Khi sửa governance contract |
| `config/dataset/` | Universe, source catalog, taxonomy, golden facts, JSON schemas | Khi mở rộng ticker hoặc chuẩn hóa domain data |
| `config/eval/` | Dataset/query cấu hình cho evaluation benchmark | Khi thêm golden query hoặc benchmark input |
| `eval/` | Tám kế hoạch evaluation và rollout | Khi thay đổi strategy/acceptance threshold |
| `frontend/` | React/Vite SPA cho report inventory và evaluation dashboard | Khi sửa trải nghiệm người dùng hoặc API client |
| `dags/`, `astro/` | Airflow/Astro deploy kit tách khỏi app runtime | Khi sửa lịch batch/deployment |
| `scale/` | Kế hoạch mở rộng universe, batch và publication quality | Khi lập kế hoạch rollout quy mô |
| `tests/` | Unit, integration, database, documents, citations, evaluation tests | Khi thay đổi behavior hoặc bổ sung regression coverage |
| `output/` | Local render outputs và logs | Không phải source of truth production |
| `storage/` | Local cache/staging | Production artifacts thuộc Supabase Storage |
| `artifacts/` | Local/generated artifacts trong một số flow | Không nên dùng làm lookup "latest" cho production |

### Module ownership theo nhu cầu

| Nhu cầu | File/thư mục bắt đầu |
|---|---|
| Thêm ticker vào universe | `config/dataset/universe/pharma_vn_universe.csv`, `backend/universe_registration.py` |
| Thêm nguồn tài liệu chính thức | `backend/documents/connectors/`, `config/dataset/sources/source_catalog.yaml` |
| Sửa fiscal-year scope mặc định | `backend/period_scope.py`, `config/harness/export_gate_policy.yml` |
| Sửa tool của harness | `backend/harness/tool_registry.py`, `backend/harness/tools.py`, `config/harness/tool_contracts.md` |
| Sửa agent prompt | `config/agents/prompts/`, `config/agents/agents.yml` |
| Sửa định giá | `backend/analytics/`, `scripts/run_valuation.py`, tests tương ứng |
| Sửa report HTML/PDF | `backend/reporting/`, `backend/reporting/templates/` |
| Sửa export readiness | `backend/harness/gates.py`, `backend/evaluation/report_quality.py`, `config/harness/export_gate_policy.yml` |
| Sửa evaluation project-level | `backend/evaluation/project_evaluator.py`, `backend/evaluation/runtime_evaluators.py`, `eval/` |
| Sửa report inventory UI | `frontend/src/pages/ReportsPage.tsx`, `backend/api.py`, `backend/reporting/output_inventory.py` |
| Sửa evaluation dashboard | `frontend/src/pages/EvalDashboardPage.tsx`, `frontend/src/data/evalFramework.ts`, backend evaluation endpoints; `frontend/src/mock/` chỉ là fixture test/dev |

## Strategic Recommendations

| Quy tắc | Lý do |
|---|---|
| Sửa deterministic finance trong `backend/analytics/`, không sửa bằng prompt | Giữ khả năng tái lập số liệu và formula trace |
| Sửa permission tool trong registry trước, sau đó đồng bộ YAML/docs | Registry là enforcement runtime, YAML là cấu hình |
| Khi thêm artifact production, cập nhật `backend/storage/layout.py` và tests | Storage key contract đang allow-list artifact name |
| Không lấy artifact bằng glob/latest file trong production path | Run-scoped manifest và `storage_path` là nguồn tham chiếu đáng tin cậy |
