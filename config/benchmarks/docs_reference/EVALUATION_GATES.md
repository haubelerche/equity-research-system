# Evaluation gates và quality governance

Cập nhật: 2026-06-14

## Context

Evaluation gates là lớp reliability cốt lõi của hệ thống. Agent được phép sinh narrative, còn client-final bị kiểm soát bằng deterministic gates, source provenance, formula trace, evidence packet, institutional report-quality rubric và publication authorization. Gate output phải có `gate`, `passed`, `status`, `severity`, `issues`, `blocking_reasons` và `summary`.

## Problem Statement

Trong workflow agentic, false pass nguy hiểm hơn fail-fast vì nó tạo cảm giác báo cáo đã an toàn trong khi số liệu, nguồn hoặc recommendation chưa đủ điều kiện. Vì vậy hệ thống cần nhiều gate nhỏ chuyên biệt và một package validation gate tổng hợp trước publishable model.

## Technical Deep-Dive

### 0. Completion alignment

Các kế hoạch chi tiết trong [`../eval/`](../eval/) đã được sử dụng làm khung nghiệm thu cho data reliability, RAG, financial calculation, citation provenance, agent workflow, report quality, observability và rollout/CI. Tài liệu này là contract vận hành của gates; thư mục `eval/` cung cấp nền tảng mở rộng và regression workflow sau trạng thái 9/10.

| Contract nghiệm thu | Ý nghĩa vận hành |
|---|---|
| `auto_exported` chỉ là publishable draft | Không được xem là client-facing final hoặc analyst-approved report |
| `approved` cộng với `final_report_approval` là điều kiện client-final | Final render phải đi qua `authorize_client_final` |
| `publishable_final_report_model` phải locked và cùng `snapshot_id` với valuation | Chặn render từ candidate/stale artifact |
| `PACKAGE_VALIDATION_GATE` phải pass | Tool permission, manifest, formula trace, evidence packet, report quality và export blockers đều đạt đối với MVP5 |
| Report-quality `decision` phải là `allow_export` và score >= 85 | `draft_only` hoặc `block_export` không được client-final |
| Post-render audit có thể bổ sung blocker hiển thị | Model pass không bảo đảm HTML/PDF final không có lỗi trình bày |

### 1. Gate trong harness

| Gate | Mục tiêu |
|---|---|
| `DATA_QUALITY_GATE` | Snapshot, period scope, coverage, core keys, source validation, reconciliation |
| `FINANCIAL_ANALYST_GATE` | Agent analysis có traceable metric refs, period refs và input refs |
| `FORECAST_QUALITY_GATE` | Driver forecast đầy đủ và các quality checks đạt |
| `VALUATION_GATE` | Valuation components, metadata, assumptions và sensitivity có đủ |
| `VALUATION_RECONCILIATION_GATE` | Reconcile FCFF/FCFE, WACC/g, upside, recommendation |
| `REPORT_ASSEMBLY_GATE` | Report model assemble được từ artifacts/specs |
| `REPORT_COMPLETENESS_GATE` | Sections, tables và charts bắt buộc có đủ |
| `SENIOR_CRITIC_GATE` | Critic decision, scorecard và findings đạt ngưỡng |
| `CITATION_GATE` | Source tier và numeric claim support đạt yêu cầu |
| `TOOL_PERMISSION_GATE` | Tool calls có permission metadata |
| `ARTIFACT_MANIFEST_GATE` | Artifact refs quan trọng có storage path |
| `FORMULA_TRACE_GATE` | Valuation có formula trace hợp lệ |
| `EVIDENCE_PACKET_GATE` | Evidence packet tồn tại và chứa formula trace cần thiết |
| `PACKAGE_VALIDATION_GATE` | Aggregate gate trước promotion final |
| `EXPORT_GATE` | Block nếu upstream gate fail hoặc report/valuation/evaluation có blocker |

### 1.1. Client-final authorization gate

Client-final rendering không chỉ phụ thuộc vào report model. `backend/reporting/publication_readiness.py` đánh giá readiness bằng các điều kiện fail-closed sau:

| Điều kiện | Blocking reason khi thiếu |
|---|---|
| Run tồn tại, ticker khớp và status là `approved` | `run_missing`, `run_ticker_mismatch`, `run_not_approved:*` |
| Approval cuối luồng cho `final_report` có decision `approved` | `final_report_approval_missing` |
| Có `company_research_pack` và `analyst_insight_pack` không rỗng | `company_research_pack_missing`, `analyst_insight_pack_missing` |
| Có `publishable_final_report_model` locked | `publishable_final_report_model_missing`, `publishable_final_report_model_not_locked` |
| `quality_gate.PACKAGE_VALIDATION_GATE.passed == True` | `package_validation_not_passed` |
| `report_quality_evaluation` pass, `decision == allow_export`, score >= 85 | `report_quality_not_publishable` |
| Report và valuation cùng `snapshot_id` | `artifact_snapshot_id_missing`, `artifact_snapshot_mismatch` |

### 2. Report quality

`backend/evaluation/report_quality.py` chấm theo rubric 100 điểm:

| Nhóm điểm | Trọng số |
|---|---:|
| Data correctness | 25 |
| Financial model integrity | 25 |
| Domain depth | 15 |
| Valuation transparency | 15 |
| Citation quality | 10 |
| Professional presentation | 10 |

Quyết định:

| Điều kiện | Decision |
|---|---|
| Score >= 85 và không fail gate | `allow_export` |
| Score >= 70 nhưng còn fail | `draft_only` |
| Score < 70 | `block_export` |

### 3. Export blockers

`workflow_export_gate` block khi có các tình huống như:

| Blocker | Ý nghĩa |
|---|---|
| `missing_source_trace_for_material_claim` | Claim trọng yếu không có nguồn traceable |
| `tier3_only_material_fact` | Fact trọng yếu chỉ dựa Tier 3 |
| `unresolved_major_source_discrepancy` | Chênh lệch nguồn chưa xử lý |
| `missing_formula_trace` | Không tái lập được valuation |
| `missing_forecast_driver` | Forecast thiếu driver |
| `unresolved_na_in_valuation` | Valuation còn input NA |
| `generic_citation_only` | Citation quá chung |
| `llm_only_evaluation_pass` | Pass chỉ do LLM, thiếu deterministic evidence |
| `report_not_linked_to_valuation_snapshot` | Report và valuation không cùng snapshot |
| `required_harness_gate_missing` | Gate bắt buộc chưa chạy |

### 4. Severity semantics

`severity` là metadata chẩn đoán, đồng thời gate bắt buộc được dùng làm điều kiện promotion vào publishable artifact. Một số tool-level blocking reason được chuyển thành exception và làm run `failed`; các blocker có tính chất chất lượng làm run `blocked` hoặc ngăn tạo `publishable_final_report_model`. Client-final authorization đọc trực tiếp package/report-quality/governance artifacts để fail-closed. Khi debug, cần đọc cả `passed`, `severity`, `blocking_reasons`, `issues`, trạng thái run và publication readiness, không chỉ đọc boolean.

### 5. Evaluation artifacts đã nghiệm thu

`backend/evaluation/run_evaluation.py` tạo tám artifact theo research run: `data_quality.json`, `retrieval_eval.json`, `financial_eval.json`, `citation_eval.json`, `agent_eval.json`, `report_eval.json`, `publication_readiness.json` và `observability_eval.json`. `backend/evaluation/project_evaluator.py` là harness riêng ở cấp repository, chạy tám plan trong `eval/`, thực thi test scope và không suy diễn metric run-specific từ test pass.

| Artifact | Ngưỡng 9/10 đã đạt cho MVP5 |
|---|---|
| `data_quality.json` | Core metric coverage >= 95% và official reconciliation >= 95% |
| `retrieval_eval.json` | Hit-rate@5 >= 90%, MRR >= 0.75, source-tier hit >= 90%, faithfulness >= 0.90 |
| `financial_eval.json` | FCFF, FCFE, blend, multiples, sensitivity và accounting invariants pass |
| `citation_eval.json` | Quantitative material claim citation coverage = 100% |
| `agent_eval.json` | Tool permission compliance = 100%, schema validity và run log đầy đủ |
| `report_eval.json` | Report quality score >= 85 và decision `allow_export` |
| `publication_readiness.json` | `DRAFT_PUBLISHABLE` cho MVP5; client-final vẫn yêu cầu approval |
| `observability_eval.json` | Manifest, cost ledger, run log và artifact lineage đầy đủ |

## Strategic Recommendations

| Hành động | Yêu cầu kiểm thử |
|---|---|
| Thêm gate mới | Unit test pass/fail/warning và integration vào package validation nếu là export blocker |
| Sửa ngưỡng report quality | Test score boundary 69/70/84/85 |
| Sửa citation policy | Test Tier 3-only, generic citation và unsupported numeric claims |
| Sửa valuation gate | Test formula trace, WACC/g, target price và recommendation reconciliation |
| Sửa report sections | Test report completeness và renderer không tạo final khi thiếu section |
