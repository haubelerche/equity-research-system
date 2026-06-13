# Agents và tools

Cập nhật: 2026-06-13

## Context

Dự án sử dụng sáu vai trò agent trong `config/agents/agents.yml`, nhưng không phải cả sáu đều là agent LLM tự trị. Runtime thực thi theo graph cố định; tool permission được enforce bởi `backend.harness.tool_registry.ToolRegistry`; prompt chỉ là lớp hướng dẫn nội dung.

## Problem Statement

Nếu coi mọi vai trò là tác tử tự trị, hệ thống sẽ dễ bị thiết kế sai: giao quyền tính toán cho LLM, cho agent tự chọn tool ngoài registry, hoặc để report writer tự phát minh số liệu khi thiếu artifact. Trong tài chính, cách làm này làm tăng rủi ro numeric hallucination và làm giảm auditability.

## Technical Deep-Dive

### 1. Vai trò agent

| Agent ID | Role | Model | Tools | Phân loại runtime |
|---|---|---|---|---|
| `research_manager` | `ResearchManagerAgent` | `gpt-5-mini` | Không có | Planner deterministic trong code path hiện tại |
| `data_evidence` | `DataEvidenceAgent` | `gpt-5-mini` | `auto_ingest`, `build_facts`, `build_index` | Vai trò sở hữu tool dữ liệu; tool deterministic là chính |
| `financial_analysis` | `FinancialAnalysisAgent` | `gpt-5-mini` | `read_snapshot`, `read_ratio_artifact` | LLM diễn giải dữ liệu đã khóa |
| `forecast_valuation` | `ForecastValuationAgent` | `gpt-5-mini` | `run_forecast`, `run_valuation`, `read_valuation_artifact` | Lai: forecast/valuation deterministic, narrative có thể dùng LLM |
| `thesis_report` | `ThesisReportAgent` | `gpt-5-mini` | Không có | LLM tổng hợp report draft từ artifacts |
| `senior_critic` | `SeniorCriticAgent` | `gpt-5-mini` | `evaluate_report_quality` | LLM critic sau deterministic evaluator |

### 2. Tool registry

| Tool | Owner | Permission | Blocking semantics |
|---|---|---|---|
| `auto_ingest` | `data_evidence` | `read_write_artifact` | Acquisition không tự block; source gates downstream block fact chưa verify |
| `build_facts` | `data_evidence` | `read_write_artifact` | Block khi snapshot, coverage, core keys, reconciliation hoặc source validation fail |
| `build_index` | `data_evidence` | `read_write_artifact` | Hỗ trợ citation coverage và evidence refs |
| `read_snapshot` | `financial_analysis` | `read_only` | Block analysis khi snapshot không có |
| `read_ratio_artifact` | `financial_analysis` | `read_only` | Block analysis khi ratios không derive được |
| `run_forecast` | `forecast_valuation` | `read_write_artifact` | Block forecast gate khi thiếu driver/schedule |
| `run_valuation` | `forecast_valuation` | `read_write_artifact` | Block valuation gate khi thiếu formula, FCFF/FCFE, assumption hoặc sensitivity |
| `read_valuation_artifact` | `forecast_valuation` | `read_only` | Block valuation review nếu path thiếu hoặc không đọc được |
| `evaluate_report_quality` | `senior_critic` | `read_only` | Block export nếu quality evaluation có critical fail |

### 3. Execution context

Agent nhận `AgentExecutionContext`, không nhận raw graph state. Context gồm `run_id`, ticker, stage, task, allowed tools, input artifact refs, input artifacts, evidence packet path, relevant gate results và known limitations. Thiết kế này giới hạn bề mặt prompt injection và buộc agent viết trong phạm vi artifact đã được stage trước tạo ra.

### 4. Non-negotiable boundaries

| Boundary | Quy tắc |
|---|---|
| Financial math | LLM không tính lại doanh thu, lợi nhuận, WACC, FCFF, FCFE, target price hoặc sensitivity |
| Tool access | Agent chỉ được gọi tool nếu tool thuộc `allowed_tools` và owner khớp registry |
| Artifact access | Agent dùng artifact refs explicit; không tự scan filesystem |
| Missing evidence | Agent phải ghi limitation hoặc evidence request; không được bù số liệu bằng narrative |
| Final approval | SeniorCriticAgent không thay thế human approval và không override deterministic gate |

## Strategic Recommendations

| Hành động | Kiểm soát bắt buộc |
|---|---|
| Thêm tool mới | Cập nhật `ToolRegistry`, agent YAML, tool contract docs và unit tests policy |
| Sửa prompt | Giữ output schema và citation discipline; không đưa quyền tính toán tài chính vào prompt |
| Thêm agent mới | Chứng minh stage mới tạo giá trị vượt chi phí latency/cost và có gate kiểm tra output |
| Tối ưu cost | Ưu tiên deterministic summary và artifact compression trước khi giảm model một cách mù quáng |
