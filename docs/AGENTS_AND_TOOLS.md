# Vai trò tác tử, công cụ và dịch vụ

Cập nhật: 2026-06-15

## Context

Dự án có sáu khóa cấu hình trong `config/agents/agents.yml`, nhưng không phải cả sáu khóa đó đều là **tác tử trí tuệ nhân tạo** trong runtime. Tên trường `agents` trong YAML là cơ chế cấu hình quyền, prompt, model, timeout, output schema và tool ownership; nó không tự chứng minh một thành phần là agent LLM tự trị.

Trong tài liệu chuẩn của dự án, chỉ thành phần thực sự gọi mô hình ngôn ngữ lớn để sinh phân tích, diễn giải, bản nháp hoặc phản biện mới được gọi là **tác tử trí tuệ nhân tạo**. Thành phần chỉ lập kế hoạch cố định, đọc dữ liệu, chuẩn hóa fact, chạy định giá, dựng index, kiểm tra gate hoặc render báo cáo phải được gọi đúng là **vai trò quy trình**, **công cụ tất định**, **dịch vụ tất định** hoặc **cổng kiểm định**.

## Problem Statement

Nếu gọi mọi khóa cấu hình là agent, kiến trúc sẽ bị mô tả sai ở ba điểm nghiêm trọng: thứ nhất, người đọc có thể hiểu nhầm LLM được quyền tính toán tài chính; thứ hai, tool deterministic có thể bị diễn giải như hành vi tự trị của agent; thứ ba, các gate kiểm định có thể bị nhầm với đánh giá xác suất của LLM. Trong bài toán tài chính, ba lỗi diễn giải này làm giảm auditability, tăng rủi ro numeric hallucination và khiến đồ án mô tả sai contribution kỹ thuật cốt lõi của hệ thống.

## Technical Deep-Dive

### 1. Quy tắc phân loại

| Loại thành phần | Định nghĩa chuẩn | Ví dụ trong dự án |
|---|---|---|
| Tác tử trí tuệ nhân tạo | Thành phần có lời gọi LLM trong runtime để tạo phân tích, diễn giải, draft hoặc critique có cấu trúc | `FinancialAnalysisAgent`, `ThesisReportAgent`, `SeniorCriticAgent` |
| Vai trò quy trình | Khóa cấu hình hoặc đơn vị trách nhiệm dùng để phân quyền, ghi vết và tổ chức workflow; có thể không gọi LLM | `research_manager`, `data_evidence` |
| Vai trò lai | Thành phần có một phần narrative dùng LLM nhưng phần nghiệp vụ cốt lõi là deterministic service/tool | `ForecastValuationAgent` |
| Công cụ tất định | Hàm/tool được runner gọi với input có cấu trúc và output có cấu trúc; không tự lập luận ngoài contract | `build_facts`, `run_valuation`, `read_snapshot` |
| Dịch vụ tất định | Module backend thực hiện logic ổn định, kiểm thử được, thường được tool hoặc runner gọi | forecast, valuation, report assembler, renderer |
| Cổng kiểm định | Logic kiểm tra điều kiện chất lượng, có thể chặn promotion/export; không phải agent | `VALUATION_GATE`, `CITATION_GATE`, `PACKAGE_VALIDATION_GATE` |

### 2. Phân loại sáu khóa cấu hình

| YAML key | Role class trong config | Tên gọi chuẩn trong đồ án | Phân loại đúng | Hành vi runtime |
|---|---|---|---|---|
| `research_manager` | `ResearchManagerAgent` | Vai trò lập kế hoạch nghiên cứu | Vai trò quy trình / dịch vụ lập kế hoạch tất định | Kế hoạch nghiên cứu được tạo theo graph và policy cố định; không nên mô tả như agent tự điều phối hệ thống. |
| `data_evidence` | `DataEvidenceAgent` | Vai trò sở hữu công cụ dữ liệu và bằng chứng | Vai trò quy trình sở hữu tool deterministic | Runner gọi trực tiếp `auto_ingest`, `build_facts`, `build_index`; vai trò này quản trị quyền công cụ, không phải agent LLM tự thu thập dữ liệu. |
| `financial_analysis` | `FinancialAnalysisAgent` | Tác tử phân tích tài chính | Tác tử trí tuệ nhân tạo | Đọc snapshot và ratio artifact đã khóa, sau đó sinh phân tích tài chính có cấu trúc; không được tính lại số liệu. |
| `forecast_valuation` | `ForecastValuationAgent` | Vai trò dự phóng và định giá | Vai trò lai | `run_forecast` và `run_valuation` là deterministic tools; LLM chỉ được dùng cho diễn giải giả định hoặc narrative, không tạo target price. |
| `thesis_report` | `ThesisReportAgent` | Tác tử viết luận điểm và bản nháp báo cáo | Tác tử trí tuệ nhân tạo | Tạo report draft từ facts, valuation, analysis và evidence đã khóa; không được tự phát minh claim hoặc số liệu thiếu nguồn. |
| `senior_critic` | `SeniorCriticAgent` | Tác tử phản biện cấp cao | Tác tử trí tuệ nhân tạo kết hợp evaluator tất định | Tạo critique/findings dựa trên report và artifacts; không thay thế report-quality gate, package gate hoặc human approval. |

Kết luận phân loại: hệ thống có ba tác tử LLM rõ ràng, một vai trò lai, và hai vai trò quy trình không nên gọi là agent trong mô tả học thuật hoặc sản phẩm.

### 3. Công cụ trong registry

| Tool | Owner config key | Bản chất kỹ thuật | Permission | Blocking semantics |
|---|---|---|---|---|
| `auto_ingest` | `data_evidence` | Công cụ thu thập/tái sử dụng nguồn dữ liệu và tài liệu | `read_write_artifact` | Acquisition không tự chứng minh fact hợp lệ; source và data gates quyết định downstream readiness. |
| `build_facts` | `data_evidence` | Công cụ chuẩn hóa, reconcile và promote canonical facts | `read_write_artifact` | Block khi snapshot, coverage, core keys, reconciliation hoặc source validation không đạt. |
| `build_index` | `data_evidence` | Công cụ xây chỉ mục retrieval/evidence | `read_write_artifact` | Hỗ trợ citation coverage, RAG evaluation và evidence refs; không sinh narrative. |
| `read_snapshot` | `financial_analysis` | Công cụ đọc dữ liệu đã đóng băng | `read_only` | Block analysis khi snapshot không tồn tại hoặc không đúng scope. |
| `read_ratio_artifact` | `financial_analysis` | Công cụ đọc tỷ số tài chính đã tính sẵn | `read_only` | Block analysis khi ratio artifact thiếu hoặc không derive được. |
| `run_forecast` | `forecast_valuation` | Công cụ/dịch vụ dự phóng deterministic | `read_write_artifact` | Block forecast gate khi thiếu driver, schedule hoặc assumption trace. |
| `run_valuation` | `forecast_valuation` | Công cụ/dịch vụ định giá deterministic | `read_write_artifact` | Block valuation gate khi thiếu FCFF/FCFE, formula trace, assumption, sensitivity hoặc reconciliation. |
| `read_valuation_artifact` | `forecast_valuation` | Công cụ đọc artifact định giá đã khóa | `read_only` | Block valuation review nếu path thiếu, checksum lệch hoặc artifact không đọc được. |
| `evaluate_report_quality` | `senior_critic` | Công cụ đánh giá report-quality deterministic | `read_only` | Block export nếu quality evaluation có critical fail hoặc score dưới policy threshold. |

`Owner config key` chỉ là khóa kiểm soát quyền trong registry. Nó không có nghĩa owner đó là agent LLM trong mọi stage.

### 4. Dịch vụ tất định liên quan

| Dịch vụ | Vai trò | Không nên gọi là |
|---|---|---|
| Fixed research planner | Tạo research plan từ run context, universe policy và graph cố định | Agent tự lập kế hoạch |
| Fact normalization/reconciliation | Chuẩn hóa raw observations thành canonical facts có provenance | Agent dữ liệu tự suy luận số liệu |
| Forecast service | Tạo forecast bằng driver, schedule và assumption policy | LLM dự phóng tài chính |
| Valuation service | Tính FCFF, FCFE, blend, multiples, sensitivity và formula trace | Agent định giá |
| Report assembler | Kiểm tra và lắp report model từ draft, chart/table specs và artifact refs | Agent viết lại báo cáo |
| PDF/HTML renderer | Kết xuất view model thành HTML/PDF | Agent xuất bản |
| Runtime evaluation writer | Ghi tám evaluation artifacts và packet tổng hợp | LLM judge quyết định publish |

### 5. Cổng kiểm định không phải agent

| Gate | Bản chất | Vai trò governance |
|---|---|---|
| `DATA_QUALITY_GATE` | Cổng kiểm định dữ liệu | Chặn snapshot/fact chưa đủ coverage, reconciliation hoặc source validation. |
| `FORECAST_QUALITY_GATE` | Cổng kiểm định forecast | Kiểm tra driver support, schedule completeness và consistency. |
| `VALUATION_GATE` | Cổng kiểm định định giá | Kiểm tra FCFF/FCFE, assumptions, sensitivity và metadata. |
| `VALUATION_RECONCILIATION_GATE` | Cổng đối chiếu định giá | Đối chiếu target price, recommendation, upside và valuation components. |
| `CITATION_GATE` | Cổng kiểm định trích dẫn | Chặn claim thiếu source, generic citation hoặc Tier-3-only material fact. |
| `REPORT_QUALITY_GATE` | Cổng chất lượng báo cáo | Chấm rubric institutional report quality và quyết định draft/export readiness. |
| `PACKAGE_VALIDATION_GATE` | Cổng kiểm định gói publishable | Kiểm tra manifest, evidence packet, formula trace, tool permission và export blockers. |
| `EXPORT_GATE` | Cổng xuất bản | Tổng hợp blocker trước khi tạo locked publishable model. |

Các gate này là deterministic governance hoặc evaluator có rule rõ ràng. Chúng không phải tác tử phản biện, không phải human reviewer và không phải LLM-as-judge có quyền override.

### 6. Execution context

Khi một tác tử LLM thực sự được gọi, nó nhận `AgentExecutionContext`, không nhận raw graph state. Context gồm `run_id`, ticker, stage, task, allowed tools, input artifact refs, input artifacts, evidence packet path, relevant gate results và known limitations. Thiết kế này giới hạn bề mặt prompt injection và buộc tác tử viết trong phạm vi artifact đã được stage trước tạo ra.

Đối với vai trò quy trình hoặc tool deterministic, context vận hành là input có cấu trúc từ runner/tool contract, không phải prompt mở. Vì vậy không nên dùng ngôn ngữ như “DataEvidenceAgent quyết định dữ liệu nào đúng” hoặc “ForecastValuationAgent tính giá mục tiêu bằng LLM”; cách nói đúng là runner gọi công cụ dữ liệu/định giá tất định và gate kiểm định kết quả.

### 7. Non-negotiable boundaries

| Boundary | Quy tắc |
|---|---|
| Financial math | LLM không tính lại doanh thu, lợi nhuận, WACC, FCFF, FCFE, target price hoặc sensitivity. |
| Tool access | Tác tử chỉ được gọi tool nếu tool thuộc `allowed_tools` và owner khớp registry. |
| Artifact access | Tác tử dùng artifact refs explicit; không tự scan filesystem hoặc chọn file mới nhất. |
| Missing evidence | Tác tử phải ghi limitation hoặc evidence request; không được bù số liệu bằng narrative. |
| Gate authority | Gate deterministic và package validation có quyền chặn cao hơn LLM critique. |
| Final approval | `SeniorCriticAgent` không thay thế human approval và không override deterministic gates. |

## Strategic Recommendations

| Hành động | Kiểm soát bắt buộc |
|---|---|
| Thêm tool mới | Cập nhật `ToolRegistry`, owner config key, tool contract docs và unit tests policy. |
| Sửa prompt | Giữ output schema và citation discipline; không đưa quyền tính toán tài chính vào prompt. |
| Thêm tác tử LLM mới | Chứng minh stage mới cần reasoning ngôn ngữ, có output schema, có gate kiểm tra và có cost/latency justification. |
| Thêm dịch vụ deterministic mới | Đặt trong module nghiệp vụ phù hợp, viết unit test và expose qua tool contract nếu runner cần gọi. |
| Viết đồ án | Dùng thuật ngữ “vai trò cấu hình” cho sáu YAML keys; chỉ gọi `financial_analysis`, `thesis_report`, `senior_critic` là tác tử LLM rõ ràng. |
