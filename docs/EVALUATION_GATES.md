# Evaluation gates và quality governance

Cập nhật: 2026-06-13

## Context

Evaluation gates là lớp reliability cốt lõi của hệ thống. Agent được phép sinh narrative, nhưng xuất bản bị kiểm soát bằng deterministic gates, source provenance, formula trace, evidence packet và FPTS-grade rubric. Gate output phải có `gate`, `passed`, `status`, `severity`, `issues`, `blocking_reasons` và `summary`.

## Problem Statement

Trong workflow agentic, false pass nguy hiểm hơn fail-fast vì nó tạo cảm giác báo cáo đã an toàn trong khi số liệu, nguồn hoặc recommendation chưa đủ điều kiện. Vì vậy hệ thống cần nhiều gate nhỏ chuyên biệt và một package validation gate tổng hợp trước publishable model.

## Technical Deep-Dive

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

### 2. FPTS grade

`backend/evaluation/fpts_grade.py` chấm theo rubric 100 điểm:

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

Gate `severity="critical"` đặt run thành `blocked` ngay trong `_record_gate`. Một số gate như `SENIOR_CRITIC_GATE`, `FPTS_GRADE_GATE` hoặc `PACKAGE_VALIDATION_GATE` có thể dùng warning severity nhưng vẫn ảnh hưởng aggregate decision. Khi debug, cần đọc cả `passed`, `severity`, `blocking_reasons` và `issues`, không chỉ đọc boolean.

## Strategic Recommendations

| Hành động | Yêu cầu kiểm thử |
|---|---|
| Thêm gate mới | Unit test pass/fail/warning và integration vào package validation nếu là export blocker |
| Sửa ngưỡng FPTS | Test score boundary 69/70/84/85 |
| Sửa citation policy | Test Tier 3-only, generic citation và unsupported numeric claims |
| Sửa valuation gate | Test formula trace, WACC/g, target price và recommendation reconciliation |
| Sửa report sections | Test report completeness và renderer không tạo final khi thiếu section |
