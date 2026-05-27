# CLAUDE.md — Tiếp tục xây dựng hệ thống sinh báo cáo theo `Key report.md`

## 0. Vai trò của Claude Code

Bạn là **Senior AI/FinTech Engineering Agent** được giao nhiệm vụ tiếp tục xây dựng hệ thống `Vietnam Pharma Equity Research Agent` để output báo cáo đáp ứng đầy đủ yêu cầu trong `Key report.md`.

Mục tiêu không phải là viết lại báo cáo bằng tay. Mục tiêu là **sửa kiến trúc, schema, analytics engine, valuation engine, report renderer, citation renderer và evaluation gates** để hệ thống tự sinh được report đúng format, có bảng forecast, FCFF valuation, chỉ số tài chính, recommendation draft, rủi ro đầu tư, và citation hữu ích cho người đọc.

---

## 1. Ngữ cảnh bắt buộc

### 1.1. Tài liệu ưu tiên đọc

Đọc theo thứ tự ưu tiên sau. Không đọc toàn bộ repo nếu chưa cần.

1. `Key report.md`  
   - Đây là **output contract** quan trọng nhất cho format báo cáo cần sinh.

2. `PRD.md`  
   - Source of truth cho product constraints: canonical facts, code-first valuation, grounded report, HITL, evaluation.

3. `PROBLEM-BRIEF.md`  
   - Source of truth cho nguyên tắc kiến trúc: facts before narrative, lineage, quality gates, incremental recompute.

4. Báo cáo thử nghiệm hiện tại, ví dụ:  
   - `DHG_20260526T041246_APPROVED_run_dhg_20260526T041.md`
   - Dùng để xác định gap, không dùng làm chuẩn đúng.

5. README/spec hiện tại nếu cần tìm cấu trúc module.

### 1.2. Quy tắc context engineering

- Không load toàn bộ repo vào context.
- Chỉ đọc file liên quan trực tiếp tới phase đang làm.
- Trước khi sửa code, phải xác định:
  - file nào cần đọc,
  - file nào được phép sửa,
  - test nào phải chạy,
  - output artifact nào phải thay đổi.
- Nếu phát hiện conflict giữa docs:
  1. PRD / PROBLEM-BRIEF thắng về guardrails và architecture.
  2. `Key report.md` thắng về format output.
  3. Current generated report chỉ là baseline lỗi.

---

## 2. Non-negotiable constraints

### 2.1. Không được để LLM tự tạo số

LLM không được phép tính hoặc tự bịa:

- doanh thu dự phóng,
- lợi nhuận dự phóng,
- EPS,
- EBITDA,
- financial ratios,
- FCFF,
- WACC,
- target price,
- peer multiples,
- DCF output.

Các giá trị này phải đến từ:

1. canonical facts,
2. deterministic Python analytics/valuation engine,
3. explicit assumptions stored in structured artifact,
4. user/human-approved assumptions nếu là final report.

### 2.2. Citation phải hữu ích cho người đọc

Không được chỉ render citation kiểu:

```text
fact_id:123
source_id:abc_hash
canonical fact
```

Citation trong report phải có tối thiểu:

```text
source_title
publisher hoặc source_name
source_type
period / fiscal_year
published_date nếu có
table hoặc section nếu có
line_item_original nếu là số liệu tài chính
excerpt hoặc value_original
normalized_metric
normalized_value
unit
internal_fact_id hoặc source_version_id ở phần audit/internal lineage
```

Nếu không có `source_title` hoặc `excerpt/value_original`, citation đó không đạt chuẩn user-facing citation.

### 2.3. Không xuất APPROVED nếu chưa qua approval gate

Nếu report chưa được reviewer duyệt, filename/status không được chứa `APPROVED`.

Các trạng thái hợp lệ:

```text
draft
needs_review
approved_assumptions
approved_final
published
failed
```

Nếu assumptions mặc định chưa được duyệt, report chỉ được ghi:

```text
Draft recommendation: pending analyst approval
```

Không được trình bày như khuyến nghị đầu tư cuối cùng.

### 2.4. Không render evidence bị cắt cụt bằng dấu `...`

Report hiện tại có evidence như:

```text
Tiền và tương đương tiền: ...
```

Đây là lỗi. Evidence phải là một excerpt ngắn nhưng hoàn chỉnh, hoặc một value row hoàn chỉnh. Nếu excerpt quá dài, truncate có kiểm soát và ghi rõ bằng cơ chế renderer, không được để dấu `...` làm mất nội dung nguồn.

### 2.5. Dedup bắt buộc

Không được lặp catalyst/news giống nhau nhiều lần.

Dedup key đề xuất:

```text
ticker + normalized_title + published_date + source_url
```

Nếu không có URL:

```text
ticker + normalized_title + published_date + source_type
```

---

## 3. Mục tiêu output theo `Key report.md`

Hệ thống phải sinh được report tiếng Việt có các phần sau.

### 3.1. Khuyến nghị đầu tư

Yêu cầu:

- 5–7 dòng.
- Nêu động lực tăng trưởng.
- Nêu triển vọng đầu tư.
- Nêu rủi ro đầu tư.
- Có draft rating: `BUY`, `HOLD`, hoặc `SELL`.
- Rating phải là **draft rating**, không phải lời khuyên đầu tư cuối cùng nếu chưa qua HITL.
- Có biểu đồ hoặc chart artifact: so sánh giá cổ phiếu với VNINDEX nếu có dữ liệu.

Quy tắc rating MVP:

```text
If valuation_upside >= 20% and data_quality_pass and assumptions_approved_or_marked_review:
    draft_rating = BUY
elif -10% <= valuation_upside < 20%:
    draft_rating = HOLD
elif valuation_upside < -10%:
    draft_rating = SELL
else:
    draft_rating = NEEDS_REVIEW
```

Nếu assumptions chưa được duyệt:

```text
Draft rating: BUY/HOLD/SELL — pending analyst approval
```

### 3.2. Tổng quan doanh nghiệp

Yêu cầu:

- Tên đầy đủ.
- Lịch sử hình thành.
- Sản phẩm chính.
- Hoạt động kinh doanh chính.
- Sản phẩm đóng góp doanh thu/lợi nhuận chính nếu có evidence.
- Chiến lược mở rộng tương lai nếu có evidence.
- CAGR doanh thu.
- EBITDA.

Nếu thiếu evidence định tính, phải render:

```text
Dữ liệu hiện tại chưa đủ để kết luận về ...
```

### 3.3. Tổng quan ngành

Theo `Key report.md`, **bỏ toàn bộ mục tổng quan ngành**.

Không render mục ngành chung chung. Nếu hệ thống có industry evidence, chỉ đưa vào phần rủi ro/catalyst hoặc footnote liên quan.

### 3.4. Phân tích tình hình tài chính

#### 3.4.1. Forecast / Dự phóng

Report phải có bảng dự phóng KQKD từ năm lịch sử đến năm forecast.

Target layout:

```text
2021A, 2022A, 2023A, 2024A, 2025A, 2026F, 2027F, 2028F, 2029F, 2030F
```

Nếu dữ liệu lịch sử chỉ có 2022–2025, renderer phải:

- hoặc fail data completeness nếu `Key report` yêu cầu 2021,
- hoặc render 2021 là `N/A` kèm warning rõ ràng.

Các line item tối thiểu:

```text
doanh_thu_hoat_dong
cac_khoan_giam_tru
doanh_thu_thuan
gia_von_hang_ban
loi_nhuan_gop
doanh_thu_tai_chinh
chi_phi_tai_chinh
chi_phi_lai_vay
chi_phi_ban_hang
chi_phi_qldn
loi_nhuan_thuan_tu_hdkd
loi_nhuan_truoc_thue
chi_phi_thue_tndn
loi_nhuan_sau_thue
lnst_cong_ty_me
```

Forecast logic phải deterministic và lưu assumptions.

Ví dụ artifact:

```json
{
  "ticker": "DHG",
  "forecast_years": [2026, 2027, 2028, 2029, 2030],
  "method": "driver_based_or_ratio_based",
  "drivers": {
    "revenue_growth": {"2026F": 0.05, "2027F": 0.07},
    "gross_margin": {"method": "historical_median_adjusted"},
    "sga_to_revenue": {"method": "historical_average"},
    "tax_rate": {"method": "historical_effective_tax_rate"}
  },
  "warnings": []
}
```

Mỗi thay đổi bất thường phải có explanation:

```text
2026F gross margin giảm do assumption giá vốn/doanh thu tăng từ X% lên Y%, dựa trên median lịch sử hoặc user assumption.
```

Không được để LLM tự chọn số forecast.

#### 3.4.2. Bảng cân đối kế toán dự phóng

Tối thiểu render các chỉ tiêu chính:

```text
tai_san_ngan_han
tai_san_dai_han
tong_tai_san
no_phai_tra
von_chu_so_huu
tong_nguon_von
```

Phải có balance check:

```text
tong_tai_san == tong_nguon_von
```

Nếu lệch vượt tolerance, evaluation phải fail.

#### 3.4.3. Chỉ số tài chính

Report phải có bảng chỉ số tài chính cho lịch sử và forecast nếu đủ dữ liệu.

Tối thiểu:

```text
cash_conversion_cycle
profit_growth
revenue_growth
market_cap
eps
pe
pb
ps
p_cash_flow
ev_ebitda
bvps
debt_to_equity
roe
roa
gross_margin
net_margin
```

Yêu cầu:

- Tính bằng code.
- Có abnormal movement detector.
- Nếu chỉ số biến động bất thường, report phải giải thích.

Abnormal rule MVP:

```text
abs(current - previous) > 25% relative change
or margin change > 5 percentage points
or ratio sign flips
or forecast reverses historical trend materially
```

### 3.5. Định giá FCFF

Report phải dùng mô hình FCFF.

Công thức chuẩn:

```text
FCFF = EBIT(1 - T) + Depreciation - CAPEX - ΔNWC
```

Bảng FCFF phải có:

```text
EBIT
EBIT(1-t)
Depreciation
CAPEX
ΔNWC
FCFF
PV(CF)
Terminal Value
PV(Terminal Value)
Enterprise Value
Net Debt
Equity Value
Shares Outstanding
Target Price
```

Thông số định giá phải có:

```text
WACC
risk_free_rate
beta
expected_market_return
cost_of_equity
cost_of_debt nếu có
tax_rate
terminal_growth_rate
target_price
```

Nếu WACC/Beta/rf/Rm là default hoặc giả định chưa được duyệt, phải đánh dấu:

```text
assumption_status: default_unapproved
```

Không được render valuation như final investment conclusion nếu assumptions chưa approved.

### 3.6. Rủi ro đầu tư

Report phải có phần rủi ro theo format bảng hoặc bullet chuyên nghiệp.

Các rủi ro chỉ được render khi có evidence hoặc khi được đánh dấu là generic risk.

Mỗi risk nên có:

```text
risk_name
risk_type
impact_level
likelihood
source_or_basis
mitigation_or_monitoring_indicator
```

Nếu rủi ro là generic ngành nhưng không có evidence trực tiếp, ghi:

```text
Generic sector risk — cần kiểm chứng bằng nguồn ngành hoặc công bố doanh nghiệp trước khi publish.
```

---

## 4. Gap hiện tại cần sửa

Báo cáo thử nghiệm hiện tại có các lỗi chính:

1. Chỉ có số lịch sử 2022–2025, chưa có forecast 2026F–2030F đúng format.
2. Chưa có bảng KQKD forecast đầy đủ.
3. Chưa có bảng cân đối kế toán forecast đúng chuẩn.
4. Bảng chỉ số tài chính chưa đủ các năm forecast.
5. DCF hiện tại dùng assumptions mặc định, chưa có FCFF table đầy đủ theo `Key report.md`.
6. Citation chỉ ghi `fact_id` và `source_id`, không hữu ích cho người dùng.
7. Evidence bị cắt bằng `...`.
8. Catalyst/news bị duplicate.
9. File/status có thể ghi `APPROVED` trong khi nội dung nói chưa được duyệt.
10. Có mục ngành chung chung trong khi `Key report.md` yêu cầu bỏ tổng quan ngành.

---

## 5. Kiến trúc triển khai cần giữ

Hệ thống vẫn giữ kiến trúc:

```text
5 logical agents
+ deterministic data/analytics/valuation tools
+ report section workers
+ evaluation gates
```

Không thêm agent mới nếu không cần.

Các module deterministic không phải agent:

```text
retriever
calculator
forecast engine
valuation engine
citation evaluator
numeric consistency evaluator
report renderer
pdf/html exporter
```

---

## 6. Kế hoạch thực hiện theo phase

### Phase 0 — Audit repo và lập execution checklist

Mục tiêu:

- Xác định các file hiện đang sinh report, valuation, citation, forecast.
- Không sửa code lớn ở phase này.

Việc cần làm:

1. Đọc `Key report.md`, `PRD.md`, `PROBLEM-BRIEF.md`.
2. Tìm các file liên quan:
   - report template,
   - renderer,
   - valuation engine,
   - ratio/analytics engine,
   - citation renderer,
   - evaluation gates,
   - report generation script.
3. Tạo hoặc cập nhật file:

```text
.claude/EXECUTION_STATE.md
```

Ghi:

```text
current_gap_summary
files_to_modify
files_to_avoid
planned_phases
test_plan
open_questions
```

Acceptance criteria:

- Có execution checklist rõ.
- Chưa thay đổi behavior khi chưa xác định được files chính.

---

### Phase 1 — Report output contract

Mục tiêu:

Tạo structured contract để report renderer sinh đúng format `Key report.md`.

Cần thêm hoặc sửa schema:

```text
ReportPackage
ReportSection
InvestmentRecommendation
CompanyOverviewSection
ForecastIncomeStatementTable
ForecastBalanceSheetTable
FinancialRatioTable
FCFFValuationTable
RiskTable
UserFacingCitation
EvidenceItem
ReportQualityGateResult
```

Yêu cầu:

- Mỗi section có `status`: `complete`, `partial`, `insufficient_data`, `needs_review`.
- Mỗi section có `required_evidence_types`.
- Mỗi numeric table có `source_fact_ids` hoặc `source_citation_ids`.
- Mỗi forecast table có `assumption_ids`.

Acceptance criteria:

- Schema import được.
- Unit tests validate minimal report package.
- Không đổi logic tính toán ở phase này.

---

### Phase 2 — User-facing citation contract

Mục tiêu:

Sửa citation để người đọc thấy được nguồn thật, không chỉ database ID.

Cần implement:

```text
UserFacingCitation
CitationRenderer
CitationUsefulnessEvaluator
```

Citation phải render được dạng:

```markdown
[^DHG-REV-2025]: Báo cáo tài chính DHG 2025, Bảng kết quả kinh doanh, dòng "Doanh thu thuần". Giá trị gốc: 5.267,0 tỷ VND. Chuẩn hóa: revenue.net = 5.267,0 tỷ VND. Internal lineage: fact_id=..., source_version_id=...
```

Rule fail:

- Citation chỉ có `fact_id` → fail.
- Citation chỉ có hash `source_id` → fail.
- Citation không có `source_title` → fail.
- Qualitative claim không có excerpt/source basis → fail hoặc render `insufficient evidence`.

Acceptance criteria:

- Generated DHG report không còn footnote kiểu chỉ `canonical fact` + hash.
- `citation_usefulness_score >= 0.85`.
- Không có evidence bị cắt cụt bằng `...`.

---

### Phase 3 — Forecast engine cho KQKD và bảng cân đối

Mục tiêu:

Tạo forecast deterministic 2026F–2030F dựa trên historical facts và assumptions.

Cần implement/sửa:

```text
analytics/forecasting.py
analytics/forecast_assumptions.py
schemas/forecasting.py
evaluation/forecast_eval.py
```

Forecast methods MVP:

1. Historical CAGR / median growth.
2. Ratio-to-revenue method cho cost/revenue items.
3. Historical average/median margin.
4. Explicit override từ `valuation_assumptions.yaml` nếu có.

Output artifacts:

```text
forecast_income_statement.json
forecast_balance_sheet.json
forecast_assumptions.json
forecast_warnings.json
```

Balance sheet rule:

```text
total_assets ≈ total_liabilities + equity
```

Acceptance criteria:

- Có bảng KQKD forecast đến 2030F.
- Có bảng cân đối forecast selected line items.
- Có explanation cho forecast driver.
- Không có forecast number do LLM tạo.
- Nếu thiếu data, output phải rõ `insufficient_data`, không bịa số.

---

### Phase 4 — Financial ratio engine mở rộng

Mục tiêu:

Sinh bảng chỉ số tài chính theo `Key report.md`.

Cần tính:

```text
cash_conversion_cycle
profit_growth
revenue_growth
market_cap
eps
pe
pb
ps
p_cash_flow
ev_ebitda
bvps
debt_to_equity
roe
roa
gross_margin
net_margin
```

Cần implement abnormal movement detector:

```text
ratio_abnormality_report.json
```

Report phải nêu bằng chữ lý do chỉ số thay đổi bất thường, nhưng explanation phải dựa vào computed metrics/assumptions/evidence.

Acceptance criteria:

- Bảng ratio có historical + forecast columns nếu đủ data.
- Abnormal movement được flag.
- Không có blank cells không giải thích.

---

### Phase 5 — FCFF valuation engine theo đúng `Key report.md`

Mục tiêu:

Thay hoặc mở rộng DCF hiện tại thành FCFF model có bảng chi tiết.

Cần implement/sửa:

```text
analytics/dcf.py
analytics/fcff.py
schemas/valuation.py
evaluation/valuation_eval.py
```

Bảng bắt buộc:

```text
EBIT
EBIT(1-t)
Depreciation
CAPEX
ΔNWC
FCFF
PV(CF)
Terminal Value
PV(Terminal Value)
Enterprise Value
Net Debt
Equity Value
Shares Outstanding
Target Price
```

WACC assumptions:

```text
risk_free_rate
beta
expected_market_return
cost_of_equity
cost_of_debt
tax_rate
debt_weight
equity_weight
wacc
terminal_growth_rate
```

Rule:

- `terminal_growth_rate < WACC`.
- Nếu WACC quá thấp/cao, warning.
- Nếu beta/rf/Rm default, mark `default_unapproved`.
- Target price phải trace được về FCFF table.

Acceptance criteria:

- FCFF table render trong report.
- Valuation artifact reproducible.
- Unit tests pass with expected FCFF formula.
- Report không kết luận mạnh nếu assumptions chưa approved.

---

### Phase 6 — Report template theo `Key report.md`

Mục tiêu:

Sửa Jinja/Markdown template để report đúng section.

Target section order:

```text
1. Khuyến nghị đầu tư
2. Tổng quan doanh nghiệp
3. Phân tích tình hình tài chính
   3.1 Forecast KQKD
   3.2 Forecast Bảng cân đối kế toán
   3.3 Chỉ số tài chính và giải thích biến động
4. Định giá FCFF
5. Rủi ro đầu tư
6. Phụ lục nguồn, assumptions, formulas, internal lineage
```

Không render `Tổng quan ngành` nếu đang chạy mode `key_report_mode`.

Report phải có:

- bảng forecast KQKD,
- bảng balance sheet forecast,
- bảng financial ratios,
- bảng FCFF DCF,
- WACC/rf/beta/Rm/target price,
- user-facing citations,
- warnings nếu thiếu evidence,
- disclaimer.

Acceptance criteria:

- Output markdown match checklist của `Key report.md`.
- Không có generic industry section.
- Không có citation chỉ là database ID.

---

### Phase 7 — Evaluation gates cho Key Report Compliance

Mục tiêu:

Không cho report pass nếu chưa đạt yêu cầu.

Cần implement:

```text
evaluation/key_report_compliance_eval.py
evaluation/citation_usefulness_eval.py
evaluation/forecast_completeness_eval.py
evaluation/valuation_completeness_eval.py
evaluation/status_consistency_eval.py
```

Gate fail nếu:

1. Thiếu section bắt buộc.
2. Thiếu forecast 2026F–2030F và không có insufficient data warning.
3. Thiếu FCFF table.
4. Thiếu WACC/rf/beta/Rm/target price.
5. Citation chỉ là `fact_id` hoặc hash.
6. Có `...` trong evidence excerpt.
7. Có duplicate catalyst/news.
8. Filename/status chứa `APPROVED` nhưng approval record không có.
9. Có claim qualitative không có evidence hoặc fallback warning.
10. Có valuation final conclusion khi assumptions `default_unapproved`.

Acceptance criteria:

- `key_report_compliance_score >= 0.90` cho DHG golden report.
- `publish_gate = fail` nếu chưa có final approval.
- `draft_gate = pass` nếu report đủ để reviewer đọc.

---

### Phase 8 — Tests và golden report

Mục tiêu:

Tạo regression tests để không tái xuất lỗi cũ.

Cần test:

```text
test_user_facing_citations.py
test_forecast_income_statement.py
test_forecast_balance_sheet.py
test_financial_ratio_table.py
test_fcff_valuation.py
test_key_report_compliance.py
test_status_consistency.py
test_dedup_events.py
```

Commands:

```bash
pytest backend/tests/unit -q
pytest backend/tests/integration -q
pytest backend/tests/golden -q
python backend/scripts/generate_report.py --ticker DHG --mode key_report --output artifacts/reports
python backend/scripts/run_eval.py --ticker DHG --latest
```

Acceptance criteria:

- Critical unit tests pass.
- DHG report regenerated.
- New `eval_result.json` includes key report compliance metrics.
- No file marked approved without approval artifact.

---

## 7. Required final artifacts

Sau khi hoàn thành, hệ thống phải sinh được package:

```text
artifacts/
├── reports/{run_id}_{ticker}_report.md
├── reports_html/{run_id}_{ticker}_report.html
├── tables/{run_id}_{ticker}_forecast_income_statement.json
├── tables/{run_id}_{ticker}_forecast_balance_sheet.json
├── tables/{run_id}_{ticker}_financial_ratios.json
├── valuation_results/{run_id}_{ticker}_fcff_valuation_result.json
├── claim_ledgers/{run_id}_{ticker}_claim_ledger.json
├── citations/{run_id}_{ticker}_user_facing_citations.json
├── source_manifests/{run_id}_{ticker}_source_manifest.json
├── eval_results/{run_id}_{ticker}_eval_result.json
└── run_logs/{run_id}_{ticker}_run_log.json
```

---

## 8. Definition of Done

Task chỉ được coi là hoàn thành khi:

1. Report sinh ra đáp ứng các phần chính trong `Key report.md`.
2. Không còn citation chỉ ghi `fact_id/source_id` trong phần người dùng đọc.
3. Có bảng forecast KQKD đến 2030F hoặc warning rõ nếu thiếu dữ liệu.
4. Có bảng cân đối kế toán forecast selected line items.
5. Có bảng financial ratios đầy đủ.
6. Có FCFF DCF table với công thức `EBIT(1-T)+Dep-CAPEX-ΔNWC`.
7. Có WACC/rf/beta/Rm/target price.
8. Có rủi ro đầu tư theo bảng hoặc bullet có evidence/basis.
9. Không render tổng quan ngành trong key report mode.
10. Không có `APPROVED` nếu chưa có approval record.
11. Evaluation gate phát hiện được các lỗi cũ.
12. Tests liên quan pass.
13. Claude cập nhật `.claude/EXECUTION_STATE.md` với:
    - files changed,
    - tests run,
    - known limitations,
    - remaining work.

---

## 9. Reporting format cho Claude sau mỗi phase

Sau mỗi phase, trả lời theo format:

```text
Phase completed: <phase name>
Files changed:
- ...
Tests run:
- ...
Artifacts generated:
- ...
Quality gates:
- ...
Remaining gaps:
- ...
Next phase:
- ...
```

Không trả lời chung chung. Không nói “done” nếu chưa chạy test hoặc chưa generate artifact.

---

## 10. Important implementation notes

- Nếu dữ liệu thiếu, không bịa. Render `insufficient_data`.
- Nếu assumptions default, mark `default_unapproved`.
- Nếu chưa có approval, output chỉ là draft.
- Nếu source không user-visible, không được coi là citation đạt chuẩn.
- Nếu qualitative section không có evidence, chuyển sang warning hoặc needs review.
- Nếu một module chỉ render/tính toán/validate, không biến nó thành agent mới.
- Ưu tiên sửa pipeline và contract trước khi polish văn phong.
