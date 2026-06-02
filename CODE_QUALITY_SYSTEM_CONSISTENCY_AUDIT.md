# ĐÁNH GIÁ CHẤT LƯỢNG CODE VÀ ĐỘ THỐNG NHẤT HỆ THỐNG

**Dự án:** Vietnam Pharma Equity Research Multi-Agent System  
**Mục tiêu hệ thống:** Tự động thu thập dữ liệu, kiểm chứng nguồn, tính toán định giá, sinh báo cáo phân tích cổ phiếu dược Việt Nam và xuất PDF có citation rõ ràng.  
**Trạng thái đánh giá:** Audit kiến trúc và chất lượng hệ thống dựa trên các vấn đề đã quan sát trong pipeline hiện tại, báo cáo xuất, citation, dữ liệu, valuation logic, PDF rendering và codebase organization.  
**Mức độ ưu tiên:** Cao. Đây là tài liệu định hướng dọn codebase và chuẩn hóa hệ thống trước khi tiếp tục mở rộng agent hoặc thêm tính năng mới.

---

## 1. Executive Summary

Codebase hiện tại đã có nhiều thành phần quan trọng cho một hệ thống equity research tự động: ingestion dữ liệu, xử lý tài liệu tài chính, tính toán chỉ số, định giá, citation, quality gate và xuất báo cáo. Tuy nhiên, chất lượng hệ thống chưa đạt mức ổn định do các vấn đề sau:

1. **Data provenance chưa đủ mạnh:** nhiều số liệu vẫn phụ thuộc vào nguồn API như vnstock/CafeF hoặc intermediate database mà chưa trace chắc chắn đến báo cáo chính thức, trang, bảng, dòng hoặc tài liệu gốc.
2. **Citation logic còn mơ hồ:** báo cáo cuối vẫn có nguy cơ hiển thị citation chung chung, hoặc lộ thuật ngữ nội bộ như `Tier`, `database`, `backend`, `source_version_id`.
3. **Report output chưa đạt chuẩn equity research:** PDF có nguy cơ thiếu bảng, thiếu số liệu, nhiều `N/A`, lỗi font tiếng Việt, biểu đồ không chuẩn hoặc warning dư thừa.
4. **Schema và contract cần khóa lại:** cần thống nhất tuyệt đối các khái niệm như `metric_id`, `period_type`, `source_version`, `verification_status`, `citation_id`, `report_claim`.
5. **Valuation logic cần deterministic hóa:** các công thức tài chính không được để LLM tự suy luận; phải có implementation duy nhất, kiểm thử được và trace được input/output.
6. **Agent workflow cần ràng buộc chặt hơn:** agent nên điều phối, diễn giải và tạo narrative; không nên là nơi thực hiện phép tính tài chính hoặc tự tạo số liệu.
7. **Testing hiện chưa đủ bảo vệ hệ thống:** cần bổ sung golden tests, regression tests, citation coverage tests, PDF smoke tests và end-to-end report quality gates.
8. **Codebase có rủi ro stale code/overengineering:** có dấu hiệu nhiều script, module, pipeline, artifact và logic trùng lặp do phát triển nhanh qua nhiều phase.

**Kết luận:** hệ thống chưa nên được đánh giá bằng tiêu chí “đã chạy được pipeline” mà phải đánh giá bằng tiêu chí “mỗi con số, mỗi công thức, mỗi claim và mỗi bảng trong báo cáo có thể truy vết, kiểm chứng, tái lập và xuất bản sạch hay chưa”. Hiện tại trọng tâm sửa lỗi nên là **contract stabilization → provenance/citation hardening → deterministic valuation → report rendering standardization → automated evaluation gates**.

---

## 2. Phạm vi đánh giá

Tài liệu này đánh giá codebase theo 14 nhóm chính:

1. Cấu trúc thư mục và ranh giới module
2. Schema, contract và canonical data model
3. Data ingestion và source provenance
4. Metric normalization và period consistency
5. Financial calculation và valuation logic
6. Citation, claim tracing và report provenance
7. Agent workflow và tool boundary
8. Report generation và PDF rendering
9. Testing strategy
10. Error handling và failure modes
11. Observability, logging và audit artifacts
12. Configuration management
13. Stale code, duplicate logic và overengineering
14. Security, reproducibility và production readiness

---

## 3. Rubric đánh giá

### 3.1. Mức độ nghiêm trọng

| Severity | Ý nghĩa | Hành động yêu cầu |
|---|---|---|
| P0 | Lỗi có thể làm báo cáo sai nhưng vẫn xuất bản | Block release ngay |
| P1 | Lỗi ảnh hưởng mạnh đến độ tin cậy, citation, valuation hoặc PDF output | Sửa trước khi mở rộng tính năng |
| P2 | Lỗi maintainability, duplication, khó debug | Sửa trong refactor phase |
| P3 | Lỗi style, naming, ergonomics, cleanup | Sửa dần sau khi ổn định core |

### 3.2. Tiêu chí đạt chuẩn

Một module hoặc pipeline chỉ được coi là đạt chuẩn nếu trả lời được 5 câu hỏi:

1. Dữ liệu này đến từ đâu?
2. Logic nào đã biến đổi dữ liệu này?
3. Công thức nào đã tạo ra con số này?
4. Claim nào trong report sử dụng con số này?
5. Nếu chạy lại pipeline cùng code/config/data snapshot, kết quả có tái lập được không?

---

## 4. Đánh giá tổng quan hiện trạng

| Nhóm | Đánh giá hiện tại | Rủi ro | Ưu tiên |
|---|---|---:|---:|
| Architecture boundary | Đã có nhiều module nhưng có nguy cơ chồng chéo giữa scripts, backend, agents, reports | Medium | P2 |
| Schema/contract | Cần khóa lại canonical schema, enum và FK | High | P0 |
| Data provenance | Chưa đủ trace đến source chính thức ở mức fact/page/table | Very High | P0 |
| Citation | Còn mơ hồ, có nguy cơ lộ backend term ra report | Very High | P0 |
| Valuation formula | Cần đảm bảo deterministic và single source of truth | High | P1 |
| Agent workflow | Agent/tool boundary cần rõ hơn | High | P1 |
| PDF/report output | Chưa đạt chuẩn presentation và completeness | High | P1 |
| Testing | Cần golden/regression/E2E tests đầy đủ hơn | High | P1 |
| Error handling | Có nguy cơ silent failure hoặc warning sai chỗ | High | P1 |
| Observability | Có audit artifacts nhưng cần phân tầng rõ internal/audit/final | Medium | P2 |
| Stale code | Có rủi ro do nhiều phase implement nhanh | Medium | P2 |
| Reproducibility | Cần gắn code/config/data/model/prompt version | High | P1 |

---

# 5. Findings chi tiết

## 5.1. Architecture Boundary

### Hiện trạng

Hệ thống đã hình thành nhiều lớp chức năng:

```text
source acquisition
  -> document parsing
  -> data ingestion
  -> fact normalization
  -> verification/reconciliation
  -> valuation
  -> citation mapping
  -> report generation
  -> PDF rendering
  -> evaluation gate
```

Tuy nhiên, do phát triển theo nhiều vòng sửa lỗi, codebase có khả năng tồn tại nhiều script hoặc module cùng làm một nhiệm vụ, ví dụ:

- script ingest tự động
- script debug coverage
- script run research
- module parser PDF
- connector CafeF/vnstock
- report generator
- citation audit
- quality gate

Nếu các module này không có contract chung, pipeline sẽ dễ rơi vào trạng thái “chạy được nhưng không kiểm soát được logic”.

### Rủi ro

- Một logic nghiệp vụ bị implement ở nhiều nơi.
- Pipeline chính và pipeline test/debug dùng logic khác nhau.
- Thêm ticker mới cần sửa nhiều file.
- Report output phụ thuộc vào thứ tự chạy script thay vì state chính thức.

### Khuyến nghị

Chuẩn hóa kiến trúc theo ranh giới sau:

```text
backend/
  documents/        # download, classify, parse PDF/OCR, extract table
  data/             # canonical facts, source versions, ingestion inventory
  verification/     # reconcile facts against official sources
  finance/          # deterministic ratios, forecast, valuation formulas
  citations/        # claim-to-source mapping
  reports/          # section model, table model, chart model, render input
  pdf/              # PDF rendering only
  agents/           # orchestration and narrative, no raw formula implementation
  eval/             # gates, audits, regression checks

scripts/
  ingest_official_documents.py
  run_research_pipeline.py
  audit_codebase.py
  audit_report_output.py

tests/
  unit/
  integration/
  golden/
  regression/
  e2e/
```

### Done When

- Mỗi module có README ngắn hoặc docstring mô tả responsibility.
- Không có function “god function” chạy toàn bộ pipeline và chứa business logic rời rạc.
- Tất cả pipeline step dùng chung contract model.
- Không có duplicate implementation cho cùng một financial formula hoặc citation rule.

---

## 5.2. Schema, Contract và Canonical Data Model

### Hiện trạng

Đây là vùng rủi ro cao nhất. Hệ thống tài chính cần schema cứng để tránh agent hoặc script hiểu sai dữ liệu. Những khái niệm cần chuẩn hóa gồm:

- `ticker`
- `company_id`
- `fiscal_year`
- `period_type`
- `metric_id`
- `statement_type`
- `value`
- `unit`
- `currency`
- `source_document_id`
- `source_version_id`
- `verification_status`
- `citation_id`
- `claim_id`

Nếu vẫn còn nhiều biến thể như sau, đây là lỗi consistency nghiêm trọng:

```text
period = "year"
period = "FY"
period = "annual"
period = "fiscal_year"
```

hoặc:

```text
revenue
net_revenue
sales
revenue.net
doanh_thu_thuan
```

### Rủi ro

- Quarter data lẫn vào FY report.
- Valuation dùng sai metric.
- Citation map không trace đúng source.
- Report hiển thị đúng tên nhưng dùng sai số.
- Quality gate passed vì kiểm tra sai contract hoặc thiếu field.

### Khuyến nghị

Tạo canonical contract bắt buộc:

```python
class FinancialFact(BaseModel):
    ticker: str
    fiscal_year: int
    period_type: Literal["FY"]
    metric_id: str
    statement_type: Literal["income_statement", "balance_sheet", "cash_flow"]
    value: Decimal
    unit: Literal["VND", "thousand_VND", "million_VND", "billion_VND"]
    source_document_id: str
    source_version_id: str
    parser_version: str
    verification_status: Literal[
        "official_matched",
        "api_matched",
        "mismatch",
        "missing_source",
        "manual_review_required"
    ]
```

Tất cả module downstream chỉ được đọc `FinancialFact`, không đọc raw dictionary.

### Done When

- `period_type` chỉ nhận `FY` trong MVP.
- `metric_id` khớp 100% với financial metric dictionary.
- Database có FK/unique constraints cho fact/source/citation.
- Không còn field tự do kiểu `data`, `result`, `metadata` không có schema.
- Pipeline fail fast nếu contract không hợp lệ.

---

## 5.3. Data Ingestion và Source Provenance

### Hiện trạng

Hệ thống đã có hướng đi đúng khi bổ sung official documents, OCR path, CafeF connector và reconciliation. Tuy nhiên vấn đề cốt lõi vẫn là: báo cáo không được phép dựa trên “data có trong database” nếu database không chứng minh được số liệu đó đến từ tài liệu nào.

Cần phân biệt ba loại nguồn:

1. **Official source:** báo cáo thường niên, báo cáo tài chính kiểm toán, công bố từ doanh nghiệp/sở giao dịch.
2. **Secondary source:** CafeF, Vietstock, FiinGroup, API provider, vnstock wrapper.
3. **Derived source:** dữ liệu đã được parse, normalize, aggregate hoặc tính toán từ nguồn khác.

### Rủi ro

- API trả dữ liệu sai hoặc thay đổi format nhưng pipeline vẫn ingest.
- Parser đọc sai bảng PDF nhưng không bị phát hiện.
- Số liệu trong report không chứng minh được nguồn gốc.
- Hệ thống hallucinate hoặc fallback nhưng vẫn xuất báo cáo.

### Khuyến nghị

Mỗi fact phải có lineage tối thiểu:

```text
fact_id
metric_id
value
fiscal_year
source_document_id
source_url_or_path
source_type
document_title
document_date
page_number/table_name/raw_label/raw_value
parser_name/parser_version
extraction_confidence
verification_status
```

Không nên để final report claim dựa trên fact có trạng thái:

```text
missing_source
api_only
manual_review_required
mismatch
```

trừ khi report ghi rõ đây là dữ liệu chưa được xác nhận. Với báo cáo equity research chuẩn, các fact định lượng quan trọng nên yêu cầu `official_matched` hoặc tối thiểu `secondary_matched_with_audit`.

### Done When

- Mỗi số liệu trong bảng tài chính trace được đến source document.
- API source không được xem là nguồn xác minh cuối cùng nếu không có reconciliation.
- Ingestion lưu raw payload, normalized value và transformation log.
- Có inventory tài liệu cho từng ticker/năm.
- Missing document không bị biến thành warning trong final PDF; nó phải là audit issue hoặc gate failure.

---

## 5.4. Metric Normalization và Period Consistency

### Hiện trạng

Dự án có yêu cầu rõ: chỉ dùng dữ liệu FY 2021-2025, không dùng quarter data trừ khi aggregate có kiểm soát. Đây là constraint rất quan trọng nhưng dễ bị phá vỡ nếu connector trả dữ liệu theo nhiều format.

### Rủi ro

- Lẫn `2025Q4` vào `2025FY`.
- Dữ liệu TTM hoặc quarterly bị dùng cho annual valuation.
- Growth YoY bị tính giữa quarter và year.
- Báo cáo hiển thị đủ cột nhưng thực chất dữ liệu không đồng nhất.

### Khuyến nghị

Thiết lập hard rule:

```text
MVP report only accepts period_type = FY.
Quarterly data must be rejected unless explicitly aggregated by a deterministic aggregation module.
No downstream valuation/report module may consume raw quarter facts.
```

Cần có validator:

```python
def validate_fy_only_dataset(facts: list[FinancialFact]) -> None:
    for fact in facts:
        assert fact.period_type == "FY"
        assert 2021 <= fact.fiscal_year <= 2025
```

### Done When

- Không còn `Q1/Q2/Q3/Q4` trong final report dataset.
- Có test bắt lỗi nếu quarterly fact lọt vào valuation input.
- Fiscal year coverage được kiểm tra trước khi report generation.
- Các missing FY facts được report trong audit artifact, không che giấu bằng `N/A` trong final PDF.

---

## 5.5. Financial Calculation và Valuation Logic

### Hiện trạng

Hệ thống đã có các module tính toán như ratios, FCFF, FCFE, DCF, multiples, debt schedule, dividend schedule, forecasting. Tuy nhiên cần kiểm tra nghiêm ngặt rằng công thức không bị phân tán hoặc tự sinh bởi LLM.

### Rủi ro

- Cùng một ratio được tính ở nhiều file với công thức khác nhau.
- FCFF/FCFE dùng input thiếu nhưng vẫn trả kết quả.
- Debt forecast bị `N/A` nhưng valuation vẫn chạy.
- Terminal value hoặc sensitivity matrix không trace được giả định.
- LLM giải thích kết quả dựa trên số liệu chưa được tool xác nhận.

### Khuyến nghị

Tạo `finance/formula_registry.py` hoặc `config/formula_registry.yaml` làm nguồn chuẩn duy nhất:

```yaml
fcff:
  formula: "EBIT * (1 - tax_rate) + depreciation_amortization - capex - delta_nwc"
  required_inputs:
    - EBIT
    - tax_rate
    - depreciation_amortization
    - capex
    - delta_nwc
  output_unit: "VND"
  fail_if_missing: true
```

Mỗi calculation result cần có metadata:

```text
formula_id
formula_version
input_fact_ids
assumption_ids
output_value
calculation_timestamp
validation_status
```

### Done When

- Không có công thức tài chính implement trùng ở nhiều nơi.
- Tất cả valuation output trace được về input facts và assumptions.
- Nếu thiếu input trọng yếu, module raise error thay vì trả `None` hoặc `N/A` âm thầm.
- Unit tests cover từng công thức.
- Golden tests cover ít nhất một ticker/năm với số liệu đã kiểm chứng.

---

## 5.6. Citation, Claim Tracing và Report Provenance

### Hiện trạng

Citation là điểm yếu lớn của hệ thống hiện tại. Một báo cáo equity research không chỉ cần citation ở cuối section; cần claim-level citation cho các nhận định định lượng và sự kiện quan trọng.

Ví dụ claim:

```text
Doanh thu DHG năm 2024 tăng 6.2% so với năm 2023.
```

Claim này phải trace được đến:

```text
revenue.net 2024
revenue.net 2023
formula: yoy_growth
source document 2024
source document 2023
```

### Rủi ro

- Citation chung chung như “vnstock” không đủ tin cậy.
- Citation không map đúng claim.
- Citation lộ ID nội bộ gây rối cho người đọc.
- Report có số liệu nhưng citation không chứng minh được source.
- Quality gate passed dù citation coverage thấp.

### Khuyến nghị

Thiết kế citation theo 3 tầng:

```text
Internal citation record
  -> Audit citation artifact
  -> User-facing citation string
```

Không để report cuối hiển thị:

```text
Tier 3
source_version_id
database
backend
quality gate
LLM verifier
```

Thay vào đó, report cuối nên hiển thị dạng:

```text
Nguồn: Báo cáo tài chính hợp nhất kiểm toán DHG 2024, Bảng kết quả kinh doanh, trang X.
```

Hoặc trong footnote:

```text
DHG, Báo cáo thường niên 2024, BCTC hợp nhất kiểm toán, bảng KQKD.
```

### Done When

- Mỗi quantitative claim có ít nhất một citation cụ thể.
- Citation map có thể truy ngược claim -> fact -> source document.
- Không còn citation chỉ ghi “database”, “vnstock”, “Tier 3”.
- PDF chỉ hiển thị citation sạch cho người đọc tài chính.
- Audit artifact vẫn lưu đầy đủ backend metadata cho developer.

---

## 5.7. Agent Workflow và Tool Boundary

### Hiện trạng

Hệ thống có định hướng multi-agent nhưng cần tránh overengineering. Với bài toán equity research, agent không nên thay thế deterministic services. Agent chỉ nên điều phối, kiểm tra, tổng hợp narrative và nêu nhận định.

### Rủi ro

- Agent tự tính toán số liệu bằng natural language.
- Agent tự tạo citation text không dựa trên citation map.
- Agent tự sửa missing data bằng suy đoán.
- Agent roles bị chồng chéo: DataAgent, ResearchAgent, AuditorAgent cùng làm một việc.
- Workflow không có state transition rõ.

### Khuyến nghị

Tách rõ vai trò:

```text
Data Service       -> fetch/parse/normalize facts
Verification       -> reconcile facts against sources
Finance Engine     -> ratios/forecast/valuation
Citation Engine    -> claim-to-source map
Report Engine      -> render clean report model
LLM/Agent Layer    -> narrative, synthesis, critique, orchestration
Audit Layer        -> block unsafe output
```

Agent chỉ được gọi tool qua contract:

```text
get_verified_facts(ticker, years)
calculate_ratios(facts)
calculate_valuation(facts, assumptions)
build_citation_map(claims, facts)
audit_report(report_model)
```

### Done When

- Agent không trực tiếp parse raw PDF, tính formula hoặc ghi DB nếu không qua service/tool.
- Mỗi tool có input/output schema.
- Agent message/tool call được log.
- Có state machine hoặc workflow graph rõ ràng.
- AuditAgent không chỉ “đọc report rồi pass”, mà kiểm tra artifact có cấu trúc.

---

## 5.8. Report Generation và PDF Rendering

### Hiện trạng

Report output hiện có nhiều vấn đề cần ưu tiên sửa:

- Thiếu bảng hoặc bảng không đầy đủ như mẫu chuẩn.
- `N/A` xuất hiện nhiều.
- Warning nội bộ lộ ra báo cáo cuối.
- Font tiếng Việt và layout PDF chưa ổn định.
- Chart có nguy cơ sai label, sai scale hoặc lỗi render.
- Report chưa kể được “câu chuyện của con số” như báo cáo phân tích chuyên nghiệp.

### Rủi ro

- Người đọc tài chính không tin báo cáo.
- Báo cáo trông giống debug output hơn là equity report.
- Dữ liệu thiếu bị trình bày như một phần bình thường thay vì audit failure.
- PDF renderer phụ thuộc môi trường gây lỗi deploy.

### Khuyến nghị

Tách report thành model trung gian trước khi render PDF:

```python
class ReportModel(BaseModel):
    company_profile: Section
    investment_thesis: Section
    financial_summary: TableSection
    valuation: ValuationSection
    risk_factors: Section
    appendix: Section
    citations: list[UserFacingCitation]
```

PDF renderer chỉ nhận `ReportModel`, không gọi lại DB, agent hoặc valuation logic.

Cần có rule:

```text
No backend warnings in final PDF.
No raw IDs in final PDF.
No unexplained N/A in final PDF.
No chart without source dataset.
No table without completeness check.
```

### Done When

- PDF không lỗi font tiếng Việt.
- Tất cả bảng tài chính quan trọng đầy đủ số liệu hoặc có graceful omission có giải thích trong audit artifact.
- Chart có test render và dữ liệu nguồn rõ.
- Final PDF sạch warning nội bộ.
- Report có narrative tài chính: growth driver, margin, cash flow, balance sheet, valuation, risk, catalyst.

---

## 5.9. Testing Strategy

### Hiện trạng

Hệ thống đã có một số unit tests và OCR-related tests theo các phase trước. Tuy nhiên với equity research pipeline, unit test riêng lẻ chưa đủ. Cần test theo artifact và theo chất lượng báo cáo.

### Rủi ro

- Parser sửa một chỗ làm hỏng extraction nhưng unit test không bắt.
- Quality gate luôn passed do kiểm tra quá nông.
- PDF lỗi layout nhưng test vẫn xanh.
- Citation thiếu nhưng report vẫn xuất.
- Dữ liệu quarter lọt vào FY report.

### Khuyến nghị

Bổ sung các lớp test:

#### Unit tests

```text
metric normalization
period validation
ratio formulas
DCF/FCFF/FCFE formulas
citation formatting
source trust classification
```

#### Integration tests

```text
PDF -> extracted rows -> canonical facts
API payload -> normalized facts -> source lineage
verified facts -> valuation output
claims -> citation map -> report model
report model -> PDF
```

#### Golden tests

```text
DHG official report 2021/2022/2023/2024/2025
Expected canonical facts manually verified
Expected ratios calculated from known inputs
Expected citation coverage for quantitative claims
```

#### Regression tests

```text
No quarterly facts in FY report
No backend terms in final PDF
No generic vnstock-only citations in final report
No silent N/A in valuation-critical tables
No PDF font corruption for Vietnamese text
```

#### E2E release gate

```text
run full pipeline for DHG
verify source coverage
verify formula correctness
verify citation coverage
verify PDF render
verify no internal warning leakage
```

### Done When

- CI fails if report contains backend terms.
- CI fails if final report has quantitative claims without citation.
- CI fails if valuation uses missing critical inputs.
- CI fails if FY dataset contains quarterly facts.
- CI stores audit artifacts for every report run.

---

## 5.10. Error Handling và Failure Modes

### Hiện trạng

Một hệ thống tài chính không được phép fail silently. Các lỗi như thiếu source, parser không đọc được bảng, citation không map được, valuation input thiếu phải được phân loại rõ.

### Rủi ro

Các pattern nguy hiểm:

```python
except Exception:
    pass
```

```python
except Exception:
    return None
```

```python
value = parsed_value or "N/A"
```

Các pattern này làm report có vẻ hoàn chỉnh nhưng thực chất che giấu lỗi.

### Khuyến nghị

Tạo error taxonomy:

```text
DocumentNotFoundError
PdfParsingError
OcrRuntimeUnavailableError
MetricMappingError
PeriodValidationError
SourceVerificationError
CitationCoverageError
ValuationInputError
ReportCompletenessError
PdfRenderingError
```

Phân biệt:

```text
Recoverable warning -> audit artifact
Blocking error       -> stop final report export
User-facing note     -> chỉ dùng nếu cần trong appendix, không phải debug warning
```

### Done When

- Không có broad `except` nuốt lỗi.
- Missing critical input block valuation/report.
- Warning nội bộ không xuất hiện trong final PDF.
- Error object có code, message, severity, affected module, affected artifact.

---

## 5.11. Observability, Logging và Audit Artifacts

### Hiện trạng

Hệ thống đã sinh nhiều artifact audit như citation map, quality gate, approval file, report draft. Đây là hướng tốt nhưng cần chuẩn hóa để không bị loãng và không lẫn với final report.

### Rủi ro

- Có nhiều artifact nhưng không biết artifact nào là source of truth.
- Audit file quá verbose nhưng không phục vụ debugging thực tế.
- Log nội bộ bị đưa vào final report.
- Không trace được một report được tạo từ run nào.

### Khuyến nghị

Mỗi pipeline run nên có thư mục artifact chuẩn:

```text
runs/{run_id}/
  manifest.json
  raw_sources/
  normalized_facts.json
  verification_report.json
  valuation_inputs.json
  valuation_outputs.json
  citation_map.json
  report_model.json
  quality_gate.json
  final_report.md
  final_report.pdf
```

`manifest.json` cần chứa:

```text
run_id
code_commit
config_version
prompt_version
model_version
ticker
years
source_documents
pipeline_status
created_at
```

### Done When

- Mỗi report PDF map được về một run_id.
- Audit artifact có cấu trúc ổn định.
- Final report không chứa developer logs.
- Có thể tái chạy pipeline từ manifest hoặc snapshot tương đương.

---

## 5.12. Configuration Management

### Hiện trạng

Một số logic hiện có thể đang hardcode trong script hoặc module: provider priority, metric mapping, source trust tier, report section, valuation assumption, PDF layout rule.

### Rủi ro

- Thêm ticker mới cần sửa code.
- Thay đổi report template ảnh hưởng valuation logic.
- Source trust rule nằm rải rác.
- Prompt/agent policy không versioned.

### Khuyến nghị

Đưa các phần sau vào config versioned:

```text
metric dictionary
formula registry
provider priority
source trust policy
report template
citation display policy
quality gate thresholds
valuation assumption defaults
PDF layout theme
```

Ví dụ:

```text
config/
  metrics/financial_metric_dictionary.yaml
  formulas/formula_registry.yaml
  sources/source_trust_policy.yaml
  reports/equity_report_template.yaml
  eval/quality_gates.yaml
  agents/agent_registry.yaml
  pdf/layout_theme.yaml
```

### Done When

- Không hardcode ticker-specific logic trong core pipeline.
- Config có version và changelog.
- Tests load cùng config production.
- Agent prompt/config được lưu, versioned và trace vào run manifest.

---

## 5.13. Stale Code, Duplicate Logic và Overengineering

### Hiện trạng

Do dự án đã trải qua nhiều phase sửa lỗi, nhiều khả năng tồn tại:

- script cũ không còn dùng
- debug artifact còn nằm trong repo
- duplicate function
- legacy pipeline
- naming cũ như Tier/quality gate/approval logic không còn phù hợp với final report
- multiple report templates
- nhiều cách ingest dữ liệu khác nhau

### Rủi ro

- Claude Code hoặc developer sửa nhầm file cũ.
- Test xanh nhưng pipeline production dùng đường khác.
- Context bị loãng, lost-in-the-middle.
- Chi phí maintain tăng nhanh.

### Khuyến nghị

Chạy audit:

```text
import graph analysis
entrypoint analysis
duplicate function detection
unused file detection
config reference scan
report output term scan
```

Phân loại file:

```text
KEEP      -> core production path
MERGE     -> có logic cần giữ nhưng trùng
DEPRECATE -> còn tham khảo nhưng không gọi trong pipeline
DELETE    -> stale/debug/obsolete
```

### Done When

- Có `CODEBASE_MAP.md` cập nhật.
- Có danh sách entrypoint chính thức.
- Không còn nhiều pipeline production cạnh tranh nhau.
- Duplicate formula/report/citation logic được gom về single source of truth.

---

## 5.14. Security, Reproducibility và Production Readiness

### Hiện trạng

Dự án có kết nối dữ liệu, database, API provider, possibly LLM API và PDF/OCR runtime. Đây là vùng cần quản trị production sớm.

### Rủi ro

- Secret lộ trong repo/log.
- Runtime OCR/PDF khác nhau giữa Windows/Linux.
- Output không reproducible do model/prompt/config không versioned.
- Ingest chạy lại tạo duplicate data.
- Provider thay đổi schema làm pipeline sai ngầm.

### Khuyến nghị

Bắt buộc có:

```text
.env.example without secrets
secret scan in CI
provider contract tests
idempotent ingestion
runtime dependency check
Dockerfile or reproducible environment
run manifest with versions
```

### Done When

- Không có secret trong repo.
- Ingest cùng ticker/năm chạy lại không tạo duplicate facts.
- PDF/OCR runtime có health check.
- Report output trace được code/config/data/model/prompt version.

---

# 6. Các lỗi cần ưu tiên sửa

## P0 — Block release

| ID | Lỗi | Tác động | Hành động |
|---|---|---|---|
| P0-01 | Số liệu không trace được đến source chính thức | Báo cáo không đáng tin | Bắt buộc fact-level provenance |
| P0-02 | Citation chung chung hoặc mơ hồ | Claim không kiểm chứng được | Build claim-level citation map |
| P0-03 | Quality gate passed dù citation/data yếu | Gate mất ý nghĩa | Viết lại gate theo artifact có cấu trúc |
| P0-04 | FY/quarter có nguy cơ lẫn nhau | Sai phân tích YoY/valuation | Enforce FY-only validator |
| P0-05 | Missing critical valuation input nhưng report vẫn xuất | Sai định giá | Fail fast khi thiếu input trọng yếu |

## P1 — Sửa trước khi mở rộng tính năng

| ID | Lỗi | Tác động | Hành động |
|---|---|---|---|
| P1-01 | PDF lỗi font/layout/bảng | Output không đạt chuẩn | Chuẩn hóa report model và renderer |
| P1-02 | Warning nội bộ lộ ra final PDF | Báo cáo thiếu chuyên nghiệp | Tách internal/audit/final output |
| P1-03 | Công thức tài chính phân tán | Kết quả không nhất quán | Formula registry + single implementation |
| P1-04 | Agent tự tính/suy đoán số liệu | Hallucination risk | Tool boundary bắt buộc |
| P1-05 | Test chưa đủ regression/golden | Lỗi cũ quay lại | Bổ sung golden/E2E gates |

## P2 — Refactor maintainability

| ID | Lỗi | Tác động | Hành động |
|---|---|---|---|
| P2-01 | Stale scripts/debug files | Dễ sửa nhầm | Codebase map + delete/merge plan |
| P2-02 | Duplicate metric/valuation/citation logic | Lệch logic | Consolidate modules |
| P2-03 | Config hardcode | Khó mở rộng | Versioned config layer |
| P2-04 | Artifact naming không chuẩn | Khó audit | Standard run directory |
| P2-05 | Logging thiếu cấu trúc | Khó debug | Structured logs + manifest |

---

# 7. Quality Gates đề xuất

## 7.1. Data Quality Gate

Gate này chạy trước valuation.

Điều kiện pass:

```text
- Ticker hợp lệ
- Coverage đủ FY yêu cầu
- Không có quarter fact trong FY dataset
- Mỗi critical metric có source_document_id
- Mỗi source_document_id tồn tại trong document inventory
- Verification status đạt ngưỡng tối thiểu
```

Critical metrics tối thiểu:

```text
revenue.net
gross_profit.total
operating_profit.ebit
net_income.parent
total_assets.total
equity.total
cash_and_equivalents.total
debt.total
operating_cash_flow.total
capex.total
```

## 7.2. Formula Quality Gate

Gate này chạy sau valuation.

Điều kiện pass:

```text
- Tất cả formula_id tồn tại trong formula registry
- Required inputs không thiếu
- Output không NaN/inf/None
- Unit/currency nhất quán
- Assumptions có source hoặc rationale
- Sensitivity matrix có input range rõ ràng
```

## 7.3. Citation Quality Gate

Gate này chạy trước report finalization.

Điều kiện pass:

```text
- Mỗi quantitative claim có citation
- Mỗi citation map được đến fact/source
- Không có generic source như "database" hoặc "vnstock" trong final citation
- Không có internal ID trong user-facing citation
- Citation coverage đạt 100% cho bảng và claim định lượng trọng yếu
```

## 7.4. Report Quality Gate

Gate này chạy trước PDF export.

Điều kiện pass:

```text
- Không có backend warning trong final report
- Không có thuật ngữ Tier/source_version_id/database/backend trong final report
- Không có unexplained N/A trong bảng trọng yếu
- Tất cả bảng bắt buộc tồn tại
- Tất cả chart có source dataset
- Narrative có investment thesis, financial analysis, valuation, risks, catalyst
```

## 7.5. PDF Quality Gate

Gate này chạy sau PDF render.

Điều kiện pass:

```text
- Font tiếng Việt render đúng
- Bảng không overflow
- Chart không vỡ layout
- Page count hợp lý
- Không có blank page bất thường
- Header/footer/citation formatting ổn định
```

---

# 8. Kế hoạch sửa theo phase cho Claude Code

## Phase 0 — Freeze production path và contract baseline

### Mục tiêu

Xác định đường chạy chính thức của hệ thống và khóa schema/contract trước khi sửa code.

### Việc cần làm

1. Liệt kê toàn bộ entrypoint hiện có.
2. Chọn một entrypoint production duy nhất cho report generation.
3. Tạo `CODEBASE_MAP.md` mô tả module, entrypoint, artifact.
4. Tạo hoặc cập nhật canonical models:
   - `FinancialFact`
   - `SourceDocument`
   - `VerifiedFact`
   - `ValuationInput`
   - `ValuationOutput`
   - `ReportClaim`
   - `CitationRecord`
   - `ReportModel`
5. Thêm validator bắt buộc cho FY-only dataset.

### Acceptance Criteria

- Có một pipeline chính thức từ ingest đến PDF.
- Tất cả downstream module dùng canonical model.
- Pipeline fail nếu input không đúng contract.

---

## Phase 1 — Data provenance hardening

### Mục tiêu

Đảm bảo mỗi fact định lượng có nguồn rõ ràng.

### Việc cần làm

1. Chuẩn hóa bảng/source model cho official documents.
2. Gắn source metadata vào từng extracted fact.
3. Lưu raw label/raw value/page/table khi parse PDF/OCR.
4. Tách `api_source`, `official_source`, `derived_source`.
5. Thêm reconciliation status.
6. Chặn report nếu fact critical chỉ có API source mà chưa verify.

### Acceptance Criteria

- Mỗi critical fact trace được đến source.
- API-only fact không được dùng cho final claim nếu không có policy cho phép.
- Có `verification_report.json` cho mỗi run.

---

## Phase 2 — Citation engine rewrite

### Mục tiêu

Chuyển từ section-level/generic citation sang claim-level citation.

### Việc cần làm

1. Tạo `ReportClaim` schema.
2. Extract hoặc generate claims từ report model.
3. Map mỗi claim định lượng đến fact/formula/source.
4. Tạo `citation_map.json` chuẩn.
5. Tạo citation formatter cho final PDF.
6. Thêm scanner chặn backend terms trong final report.

### Acceptance Criteria

- 100% quantitative claims có citation.
- Final PDF không hiện `Tier`, `database`, `backend`, `source_version_id`.
- Citation audit artifact vẫn giữ metadata kỹ thuật cho developer.

---

## Phase 3 — Deterministic finance engine

### Mục tiêu

Đảm bảo mọi phép tính tài chính được thực hiện bằng deterministic code, không phải LLM.

### Việc cần làm

1. Gom công thức vào `formula_registry`.
2. Xác định required inputs cho từng formula.
3. Xóa duplicate implementations.
4. Thêm `CalculationResult` metadata.
5. Viết unit tests cho ratios, FCFF, FCFE, DCF, multiples.
6. Chặn valuation nếu missing input trọng yếu.

### Acceptance Criteria

- Một công thức chỉ có một implementation.
- Valuation output trace được input facts và assumptions.
- Không còn `N/A` silent trong valuation-critical output.

---

## Phase 4 — Report model và PDF standardization

### Mục tiêu

Tách nội dung báo cáo khỏi renderer và đảm bảo PDF đạt chuẩn trình bày.

### Việc cần làm

1. Tạo `ReportModel` trung gian.
2. Định nghĩa required sections và required tables.
3. Tạo table completeness validator.
4. Tạo chart dataset validator.
5. Chuẩn hóa font tiếng Việt.
6. Xóa warning/debug text khỏi final PDF.
7. Thêm PDF smoke test.

### Acceptance Criteria

- PDF không lỗi tiếng Việt.
- Bảng đầy đủ theo template.
- Không có warning nội bộ trong final PDF.
- Chart render đúng và trace được dataset.

---

## Phase 5 — Test suite và CI gates

### Mục tiêu

Biến các lỗi từng gặp thành regression tests bắt buộc.

### Việc cần làm

1. Tạo golden fixtures cho DHG.
2. Thêm regression tests:
   - no quarterly facts in FY report
   - no generic citation
   - no backend terms in PDF
   - no silent N/A in critical tables
   - no missing citation for quantitative claims
3. Thêm E2E test cho một report mẫu.
4. Lưu audit artifacts trong CI.
5. Thêm release checklist.

### Acceptance Criteria

- CI fail nếu citation yếu.
- CI fail nếu data lineage thiếu.
- CI fail nếu PDF có backend term.
- CI fail nếu valuation input thiếu nhưng report vẫn xuất.

---

# 9. Checklist audit nhanh cho codebase

## 9.1. Architecture

- [ ] Có một production pipeline duy nhất.
- [ ] Module boundary rõ.
- [ ] Không có circular dependency nghiêm trọng.
- [ ] Không có god function chứa toàn bộ logic.
- [ ] Script debug không bị dùng trong production.

## 9.2. Data

- [ ] Mỗi fact có canonical `metric_id`.
- [ ] Dataset final chỉ chứa `period_type = FY`.
- [ ] Mỗi critical fact có source.
- [ ] Có verification status.
- [ ] Ingestion idempotent.

## 9.3. Finance

- [ ] Công thức nằm trong registry.
- [ ] Required inputs được kiểm tra.
- [ ] Không dùng LLM để tính toán.
- [ ] Không có duplicate formula implementation.
- [ ] Output có metadata trace.

## 9.4. Citation

- [ ] Mỗi quantitative claim có citation.
- [ ] Citation trace được đến fact/source.
- [ ] Không có citation chung chung.
- [ ] Không lộ backend terms.
- [ ] Citation formatter tách audit-facing và user-facing.

## 9.5. Report/PDF

- [ ] PDF render đúng tiếng Việt.
- [ ] Bảng không overflow.
- [ ] Chart đúng dataset.
- [ ] Không có warning nội bộ.
- [ ] Không có unexplained `N/A` trong bảng trọng yếu.

## 9.6. Tests

- [ ] Unit tests cho formulas.
- [ ] Integration tests cho ingestion -> facts.
- [ ] Golden tests cho DHG.
- [ ] Regression tests cho lỗi đã gặp.
- [ ] E2E test cho report generation.

## 9.7. Observability

- [ ] Có run manifest.
- [ ] Có audit artifacts chuẩn.
- [ ] Có structured logs.
- [ ] Report map được về run_id.
- [ ] Có code/config/model/prompt version.

---

# 10. Tiêu chuẩn kết luận sau refactor

Sau khi hoàn thành các phase trên, hệ thống chỉ được coi là đạt chuẩn nếu:

1. **Data correctness:** số liệu trọng yếu có nguồn chính thức hoặc nguồn đã được verify rõ.
2. **Formula correctness:** mọi công thức tài chính chạy bằng deterministic code và có test.
3. **Citation correctness:** mọi claim định lượng có citation cụ thể, không mơ hồ.
4. **Report completeness:** bảng, biểu đồ và narrative đầy đủ theo mẫu equity research.
5. **Output cleanliness:** PDF không lộ warning, backend terms hoặc artifact kỹ thuật.
6. **Reproducibility:** một report có thể tái lập từ run manifest.
7. **Maintainability:** codebase không còn stale path/duplicate logic lớn.
8. **Scalability:** thêm ticker mới không cần sửa core code.
9. **Reliability:** pipeline fail fast khi dữ liệu/citation/formula không đạt chuẩn.
10. **Latency/cost sanity:** agent/model call chỉ dùng cho phần thực sự cần reasoning/narrative, không dùng để thay thế deterministic computation.

---

# 11. Kết luận cuối cùng

Chất lượng code hiện tại không nên được đánh giá theo số lượng module đã build hoặc pipeline có chạy được hay không. Với hệ thống tài chính tự động, tiêu chuẩn đúng phải là:

```text
Một báo cáo chỉ được xuất khi dữ liệu, công thức, citation, narrative và PDF output đều có thể kiểm chứng độc lập.
```

Ưu tiên kỹ thuật trước mắt không phải là thêm agent mới hoặc làm report dài hơn, mà là khóa lại nền móng:

```text
canonical contract
+ fact-level provenance
+ deterministic finance engine
+ claim-level citation
+ clean report model
+ strict quality gates
```

Nếu chưa làm xong các phần này, hệ thống có thể tạo ra báo cáo nhìn có vẻ hoàn chỉnh nhưng vẫn có rủi ro sai ở những điểm quan trọng nhất: số liệu, nguồn, công thức và diễn giải tài chính.

