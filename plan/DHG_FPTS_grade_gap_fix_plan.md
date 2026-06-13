# Kế hoạch sửa báo cáo DHG để tiệm cận chuẩn phân tích FPTS

## 1. Context

Tài liệu này đối chiếu hai đầu ra:

1. `DHG_fast_report.pdf`: báo cáo do hệ thống tạo cho Công ty CP Dược Hậu Giang (DHG).
2. `Bao_cao_cap_nhat_dinh_gia_CTCP_Duoc_Trang_thiet_bi_y_te_Binh_Dinh_HSX_DBD_0400ba27 (1).pdf`: báo cáo mẫu của FPTS cho DBD.

Hai báo cáo khác mã cổ phiếu nên không đối chiếu số liệu DHG với số liệu DBD. Mục tiêu đối chiếu là đánh giá **chuẩn nghề nghiệp**: cấu trúc lập luận, độ sâu phân tích ngành dược, chất lượng mô hình tài chính, tính tái lập của định giá, citation, kiểm soát lỗi số liệu và mức độ chuyên nghiệp của bản xuất PDF.

## 2. Kết luận kiểm định

`DHG_fast_report` đã tốt hơn một bản nháp thô vì có khung báo cáo, giá mục tiêu, bảng tài chính, bảng độ nhạy, rủi ro và disclaimer. Tuy nhiên, nếu so với chuẩn FPTS thì báo cáo hiện tại vẫn chưa đạt mức equity research chuyên nghiệp.

Vấn đề cốt lõi không nằm ở giao diện PDF mà nằm ở **financial model, evidence layer, forecast driver và validation gate**. Báo cáo hiện có thể gây hiểu nhầm vì nhìn giống báo cáo phân tích thật nhưng nhiều số liệu chưa được giải thích, chưa có citation đủ chi tiết và chưa chứng minh được logic định giá.

### Đánh giá tổng thể

| Trục đánh giá | DHG_fast_report | FPTS sample | Kết luận |
|---|---|---|---|
| Cấu trúc báo cáo | Có khung 7 trang nhưng còn ngắn, lặp ý, thiếu nhiều phần chuyên nghiệp | 17 trang, bố cục đầy đủ từ thesis, hoạt động, dự phóng, định giá, lịch sử khuyến nghị, phụ lục | DHG mới đạt mức draft |
| Phân tích doanh nghiệp | Mô tả ETC/OTC chung chung, thiếu sản phẩm/kênh/thị phần riêng của DHG | Bóc tách kênh ETC/OTC, nhóm thuốc, thị phần, EU-GMP, API, đấu thầu | Thiếu company-specific analysis |
| Dự phóng | Dùng giả định phẳng: doanh thu +4%, biên gộp 47,2%, SG&A 20% | Dự phóng theo kênh, sản phẩm, catalyst, EU-GMP, API, thị phần | Forecast quá cơ học |
| Mô hình tài chính | Có nhiều bất thường: lợi nhuận 2026 tăng 53,9% khi doanh thu chỉ tăng 4%; nhiều dòng bảng cân đối bị để trống | Có P&L, CĐKT, tỷ số, working capital, valuation bridge | Cần chặn export nếu chưa reconcile |
| Định giá | Gần như chỉ có FCFF DCF + sensitivity, nhưng lại ghi FCFF/FCFE trong nguồn | FCFF và FCFE riêng biệt, trọng số 50:50, WACC bridge, equity value bridge | Valuation artifact chưa đủ |
| Citation | Nguồn chung chung, không có claim-level citation | Nguồn gắn vào bảng/biểu đồ/phụ lục, có official source | Không đạt chuẩn audit |
| Trình bày | Biểu đồ nhỏ, thiếu đánh số, có đoạn lặp, trạng thái mâu thuẫn | Bảng/biểu đồ chuyên nghiệp, có hệ thống đánh số | Cần renderer standard |

## 3. Những lỗi nghiêm trọng cần sửa trước

### P0-1. Lợi nhuận và EPS 2026 tăng bất thường nhưng không có bridge giải thích

Trong `DHG_fast_report`, doanh thu 2026F chỉ tăng từ 5.267 tỷ đồng lên 5.480 tỷ đồng, tương đương +4,0%, nhưng lợi nhuận ròng tăng từ 852 tỷ đồng lên 1.312 tỷ đồng, tương đương +53,9%; EPS điều chỉnh tăng từ 6.308 VND lên 10.033 VND, tương đương +59,1%.

Đây là tín hiệu lỗi mô hình hoặc thiếu giải thích nghiêm trọng. Nếu lợi nhuận tăng mạnh như vậy, báo cáo bắt buộc phải có:

- margin bridge từ doanh thu đến lợi nhuận gộp;
- SG&A bridg
e;
- giải thích vì sao chi phí bán hàng và quản lý giảm mạnh;
- giải thích one-off hoặc normalization nếu năm cơ sở có yếu tố bất thường;
- đối chiếu với kế hoạch kinh doanh và lịch sử lợi nhuận;
- tác động của thuế, tài chính, lợi nhuận khác.

Hiện báo cáo chỉ nói chung về API, SG&A và ETC, không đủ để bảo vệ mức tăng lợi nhuận này.

**Rule cần thêm:** Nếu tăng trưởng LNST hoặc EPS vượt quá 2 lần tăng trưởng doanh thu, hệ thống phải tạo `profit_bridge_required=true`. Nếu không có bridge được chứng minh bằng artifact, block export.

### P0-2. Biên EBIT và EBITDA nhảy mạnh nhưng không có luận giải

Bảng định giá cho thấy EBITDA margin tăng từ 22,5% năm 2025 lên 29,2% từ 2026 trở đi, EBIT margin tăng từ 20,3% lên 27,2%. Trong khi đó, biên gộp lại giảm nhẹ từ 47,6% xuống 47,2%. Như vậy toàn bộ cải thiện lợi nhuận đến từ chi phí vận hành, tài chính hoặc line-item mapping, nhưng báo cáo không có bridge rõ ràng.

Dòng `Chi phí bán hàng và quản lý` giảm từ -1.438 tỷ đồng năm 2025 xuống -1.096 tỷ đồng năm 2026 trong khi doanh thu tăng. Đây là giả định rất mạnh và cần bằng chứng riêng.

**Rule cần thêm:** Nếu EBIT margin tăng trên 300 điểm cơ bản một năm mà biên gộp không tăng tương ứng, báo cáo phải sinh `operating_leverage_bridge`. Nếu không có, block export.

### P0-3. Bảng cân đối kế toán và dòng tiền chưa reconcile

Phụ lục DHG có nhiều ô trống ở các dòng nợ, nợ ròng, tổng nợ phải trả, EV/EBITDA và EV/Doanh thu trong giai đoạn dự phóng. Trong khi đó báo cáo vẫn xuất valuation DCF và tính giá mục tiêu. Đây là không đạt chuẩn vì FCFF/FCFE cần cash, debt, working capital, capex và equity bridge.

Ngoài ra, báo cáo có dòng cổ tức dự phóng nhưng `Suất sinh lợi cổ tức` lại bằng 0. Nếu tổng tỷ suất lợi nhuận lớn hơn upside từ giá mục tiêu, hệ thống cần giải thích phần cổ tức được cộng vào như thế nào.

**Rule cần thêm:** Không được xuất bản valuation nếu thiếu bất kỳ trường nào: cash, debt, net debt, shares, FCFF, terminal value, present value, equity value, target price.

### P0-4. Ghi FCFF/FCFE nhưng không có mô hình FCFE thực sự

Báo cáo DHG ghi nguồn tham khảo là “Mô hình định giá FCFF/FCFE và độ nhạy WACC × tăng trưởng dài hạn”, nhưng phần định giá chỉ thể hiện FCFF DCF và bảng sensitivity WACC × g. Không có bảng FCFE, không có equity cash flow, không có thay đổi nợ vay, cổ tức hoặc payout logic phục vụ FCFE.

**Rule cần thêm:** Nếu report text nhắc đến FCFE, artifact phải có `fcfe_model`. Nếu không có, text phải tự động đổi thành “FCFF DCF” và không được ghi FCFF/FCFE.

### P0-5. Recommendation logic không nhất quán

Trang đầu ghi:

- Giá mục tiêu: 106.752 VND;
- Giá hiện tại: 93.700 VND;
- Tỷ lệ tăng/giảm: +13,9%;
- Tổng tỷ suất lợi nhuận: +18,7%;
- Khuyến nghị: NẮM GIỮ;
- Trạng thái: ĐANG XEM XÉT;
- Dự thảo: khuyến nghị và giá mục tiêu chưa được công bố chính thức.

Một báo cáo không nên vừa trình bày recommendation chính thức vừa ghi đang xem xét/dự thảo. Nếu đã là draft, recommendation nên là `DRAFT / NOT APPROVED`. Nếu đã approved, không nên còn trạng thái “ĐANG XEM XÉT”.

**Rule cần thêm:** Recommendation phải được sinh từ policy rõ ràng:

```text
if approval_status != approved:
    visible_recommendation = "ĐANG RÀ SOÁT"
else:
    visible_recommendation = recommendation_from_upside_policy
```

Ngoài ra, nếu upside + dividend return vượt ngưỡng BUY nội bộ, nhưng khuyến nghị vẫn là HOLD, hệ thống phải giải thích threshold hoặc yêu cầu reviewer xác nhận.

## 4. Những thiếu sót lớn so với FPTS

### 4.1. Thiếu company-specific research pack

FPTS không chỉ nói DBD là công ty dược. Báo cáo của họ bóc tách:

- cơ cấu doanh thu theo kênh ETC và OTC;
- nhóm sản phẩm chủ lực;
- tỷ trọng sản phẩm tự sản xuất;
- thị phần theo nhóm thuốc;
- giá trị trúng thầu;
- tác động API;
- tiến độ EU-GMP;
- kế hoạch kinh doanh;
- kết quả 9M/3Q;
- phụ lục hoạt chất và giá sản phẩm.

DHG_fast_report mới chỉ nói DHG có ETC/OTC, API, GMP-EU và tỷ giá ở mức khái quát. Báo cáo chưa có bảng nào chứng minh:

- DHG có doanh thu theo kênh nào;
- kênh nào tăng/giảm;
- nhóm sản phẩm nào đóng góp chính;
- thị phần hoặc lợi thế cạnh tranh là gì;
- catalyst riêng của DHG trong giai đoạn dự phóng là gì;
- kết quả đấu thầu hoặc đăng ký thuốc ảnh hưởng thế nào.

**Việc cần làm:** Tạo `company_research_pack` cho từng ticker trước khi viết báo cáo.

Schema đề xuất:

```yaml
company_research_pack:
  ticker:
  company_profile:
  business_segments:
  revenue_by_channel:
  revenue_by_product_group:
  tender_metrics:
  market_share:
  capacity_and_factory_status:
  regulatory_and_gmp_status:
  api_exposure:
  distribution_network:
  peer_positioning:
  catalysts:
  risks:
  source_map:
```

### 4.2. Dự phóng chưa theo driver

DHG_fast_report dùng công thức đều:

- doanh thu tăng 4,0% mỗi năm;
- biên gộp giữ 47,2%;
- SG&A bằng 20,0% doanh thu;
- capex bằng 3,4% doanh thu;
- thuế suất 11,9%;
- WACC 13,8%;
- tăng trưởng dài hạn 3,0%.

Đây là forecast cơ học. FPTS dự phóng theo driver: kênh ETC, kênh OTC, dòng thuốc ung thư, kháng sinh, dung dịch thẩm phân, EU-GMP, giá thầu, API, giá bán và thị phần.

**Việc cần làm:** Thay forecast phẳng bằng driver-based forecast.

Schema đề xuất:

```yaml
forecast_driver_model:
  revenue:
    by_channel:
      ETC:
        base_revenue:
        price_growth:
        volume_growth:
        tender_win_rate:
        policy_adjustment:
      OTC:
        base_revenue:
        pharmacy_chain_penetration:
        traditional_channel_growth:
    by_product_group:
      product_group:
        base_revenue:
        growth_driver:
        evidence:
  gross_margin:
    product_mix_effect:
    api_cost_effect:
    fx_effect:
    pricing_effect:
  opex:
    selling_expense_ratio:
    admin_expense_ratio:
    one_off_adjustments:
  capex_depreciation:
    capex_plan:
    depreciation_schedule:
  working_capital:
    receivable_days:
    inventory_days:
    payable_days:
  tax_and_financing:
    effective_tax_rate:
    debt_schedule:
    interest_rate:
```

### 4.3. Thiếu valuation bridge chuyên nghiệp

FPTS đưa valuation theo FCFE và FCFF, trọng số 50:50, hiển thị WACC, cost of debt, cost of equity, beta, risk-free rate, risk premium, terminal growth, forecast horizon, PV of cash flows, cash, debt, equity value và shares.

DHG_fast_report chỉ hiển thị target price và sensitivity. Người đọc không biết:

- FCFF từng năm là bao nhiêu;
- terminal value chiếm bao nhiêu % enterprise value;
- PV forecast period và PV terminal value là bao nhiêu;
- cash/debt được cộng/trừ thế nào;
- cổ phiếu lưu hành chính xác là bao nhiêu;
- WACC 13,8% được tính từ đâu;
- terminal growth 3,0% có hợp lý với ngành dược Việt Nam không.

**Việc cần làm:** Bắt buộc xuất `valuation_bridge`.

Schema tối thiểu:

```yaml
valuation_bridge:
  method:
  forecast_years:
  wacc:
    risk_free_rate:
    equity_risk_premium:
    beta:
    cost_of_equity:
    pre_tax_cost_of_debt:
    tax_rate:
    target_debt_weight:
    target_equity_weight:
  fcff_table:
    revenue:
    ebit:
    tax:
    nopat:
    depreciation:
    capex:
    delta_nwc:
    fcff:
    discount_factor:
    pv_fcff:
  terminal_value:
    terminal_growth:
    terminal_fcff:
    terminal_value:
    pv_terminal_value:
    terminal_value_share_of_ev:
  equity_bridge:
    enterprise_value:
    cash_and_equivalents:
    short_term_investments:
    debt:
    minority_interest:
    equity_value:
    diluted_shares:
    target_price:
```

### 4.4. Thiếu peer comparison

Một báo cáo ngành dược chuyên nghiệp cần cho thấy DHG đang giao dịch đắt/rẻ so với nhóm so sánh phù hợp. DHG_fast_report có P/E, P/B, EV/FCF nhưng chỉ tự so với chính nó qua thời gian, không có peer.

**Việc cần làm:** Thêm peer set:

```yaml
peer_comparison:
  ticker:
  peer_group:
    - IMP
    - DMC
    - TRA
    - DBD
    - PME
  metrics:
    revenue_growth:
    gross_margin:
    net_margin:
    ROE:
    ROA:
    net_cash_or_net_debt:
    P/E:
    EV/EBITDA:
    P/B:
  conclusion:
```

### 4.5. Citation chưa đạt chuẩn audit

Nguồn hiện tại đang ở mức “Báo cáo tài chính công ty; tính toán của nhóm phân tích”. Đây chưa phải citation có thể audit. Chuẩn của hệ thống phải cao hơn cả báo cáo PDF truyền thống vì hệ thống AI cần chứng minh provenance.

Mỗi claim định lượng phải có:

```yaml
claim_id:
claim_text:
metric:
value:
unit:
period:
ticker:
source_type:
source_uri:
source_page:
source_line_or_table:
fact_id:
artifact_id:
calculation_path:
confidence:
```

Ví dụ claim “doanh thu 2025 đạt 5.267 tỷ đồng” phải trỏ về fact record hoặc BCTC cụ thể, không chỉ ghi “BCTC công ty”.

## 5. Các lỗi trình bày và chuyên nghiệp hóa

### 5.1. Trạng thái báo cáo không rõ

Không nên vừa có `NẮM GIỮ`, vừa có `ĐANG XEM XÉT`, vừa có “Dự thảo”. Cần thống nhất:

- `DRAFT`: chưa hiển thị khuyến nghị chính thức;
- `UNDER_REVIEW`: có target price nội bộ nhưng watermark rõ;
- `APPROVED`: có khuyến nghị chính thức;
- `PUBLISHED`: có disclaimer, reviewer, timestamp, artifact version.

### 5.2. Biểu đồ còn nhỏ và thiếu vai trò phân tích

Biểu đồ trong DHG_fast_report khó đọc, nhãn nhỏ, thiếu đánh số, thiếu nguồn cụ thể. Biểu đồ phải phục vụ luận điểm, không chỉ trang trí.

Chart spec tối thiểu:

```yaml
chart_id:
chart_title:
section:
data_source:
data_table:
x_axis:
y_axis:
unit:
footnote:
narrative_link:
```

### 5.3. Lặp đoạn và ngôn ngữ còn giống template

Nhiều đoạn trong báo cáo lặp lại: mô tả ETC/OTC, API, SG&A, WACC xuất hiện ở nhiều phần với ý gần giống nhau. FPTS viết theo cấu trúc tiến triển: tổng quan -> cập nhật -> driver -> dự phóng -> định giá -> rủi ro. Hệ thống cần tránh việc mỗi section tự sinh lại cùng một narrative.

**Việc cần làm:** Report Writer chỉ được nhận section-specific evidence pack và section objective. Không cho model viết lại cùng một thesis ở nhiều section.

### 5.4. Không nên dùng thuật ngữ không thống nhất

Báo cáo dùng `GMP-EU`, trong khi chuẩn thông dụng trong báo cáo mẫu là `EU-GMP`. Cần normalize thuật ngữ ngành dược.

## 6. Kiến trúc sửa lỗi đề xuất

### Epic 1. Evidence-first report assembly

Mục tiêu: báo cáo không được viết từ prompt chung, mà phải viết từ evidence pack và artifacts đã khóa.

Deliverables:

- `source_registry`
- `fact_registry`
- `claim_registry`
- `citation_map`
- `artifact_manifest`
- `report_evidence_pack`

Acceptance criteria:

- 100% số liệu trên report có `fact_id` hoặc `artifact_id`.
- Mọi bảng tài chính có source table hoặc calculation artifact.
- Không có claim định lượng nếu không có source.

### Epic 2. Financial model reconciliation gate

Mục tiêu: không xuất báo cáo nếu mô hình tài chính chưa khớp.

Checks bắt buộc:

```text
revenue = sum(revenue_segments) nếu có segment model
gross_profit = revenue - cogs
EBITDA = EBIT + D&A
net_income = PBT - tax - minority_interest
EPS = net_income_to_parent / diluted_shares
assets = liabilities + equity
net_debt = interest_bearing_debt - cash_and_equivalents - short_term_investments
FCFF = NOPAT + D&A - capex - delta_NWC
target_price = equity_value / diluted_shares
total_return = upside + dividend_yield
```

Blocker rules:

- Không cho export nếu forecast debt/cash bị blank nhưng valuation dùng enterprise value.
- Không cho export nếu cổ tức > 0 nhưng dividend yield = 0.
- Không cho export nếu EPS growth lệch với net income growth mà không do share count.
- Không cho export nếu EBIT margin nhảy bất thường mà không có bridge.

### Epic 3. Forecast driver engine cho ngành dược

Mục tiêu: thay dự phóng phẳng bằng dự phóng theo driver.

Implementation:

1. Xây `pharma_driver_taxonomy`.
2. Bắt buộc forecast doanh thu theo tối thiểu 2 lớp:
   - kênh: ETC, OTC, export/other nếu có;
   - nhóm sản phẩm hoặc mảng kinh doanh.
3. Biên gộp phải có driver:
   - product mix;
   - API cost;
   - tỷ giá;
   - giá bán/trúng thầu.
4. SG&A phải tách:
   - selling expenses;
   - admin expenses;
   - tender/channel expenses;
   - one-off items.
5. Capex phải gắn với kế hoạch nhà máy, nâng chuẩn, mở rộng công suất.

### Epic 4. Valuation artifact chuẩn FCFF/FCFE

Mục tiêu: định giá có thể tái lập.

Implementation:

- Tách `fcff_valuation_artifact`.
- Tách `fcfe_valuation_artifact` nếu thật sự dùng FCFE.
- Nếu chỉ dùng FCFF, report không được nhắc FCFE.
- Thêm WACC decomposition.
- Thêm target price bridge.
- Thêm sensitivity theo WACC × terminal growth.
- Thêm optional scenario: bear/base/bull.

Acceptance criteria:

- Người đọc có thể tái tính target price từ bảng công bố.
- Terminal value share of EV phải được hiển thị.
- Nếu terminal value > 70% EV, report phải cảnh báo độ nhạy cao.

### Epic 5. Professional report template

Mục tiêu: template 12-16 trang có cấu trúc tương đương chuẩn sell-side.

Cấu trúc đề xuất:

1. Trang bìa
   - analyst/reviewer placeholder;
   - ngày báo cáo;
   - giá hiện tại, giá mục tiêu, upside, total return;
   - thông tin giao dịch;
   - price chart vs VNIndex;
   - investment thesis headline;
   - key risks;
   - key monitoring points.

2. Tổng quan doanh nghiệp
   - business model;
   - revenue mix;
   - product/channel mix;
   - market position;
   - key cost driver;
   - regulatory status.

3. Cập nhật kết quả kinh doanh
   - quý gần nhất;
   - lũy kế năm;
   - so với kế hoạch;
   - doanh thu theo kênh;
   - margin bridge.

4. Driver ngành và catalyst
   - đấu thầu ETC;
   - API;
   - tỷ giá;
   - GMP/EU-GMP;
   - BHYT/regulatory;
   - peer/market share.

5. Dự phóng
   - doanh thu theo kênh/sản phẩm;
   - lợi nhuận gộp;
   - SG&A;
   - EBIT/LNST;
   - capex/working capital.

6. Định giá và khuyến nghị
   - FCFF/FCFE hoặc FCFF-only;
   - WACC bridge;
   - equity bridge;
   - sensitivity;
   - recommendation rationale.

7. Rủi ro và yếu tố theo dõi

8. Lịch sử khuyến nghị, nếu có

9. Phụ lục tài chính
   - P&L;
   - balance sheet;
   - cash flow;
   - ratios;
   - working capital days.

10. Evidence appendix
    - source list;
    - citation map;
    - artifact versions.

### Epic 6. Report quality evaluator

Tạo evaluator chấm báo cáo theo rubric 100 điểm.

Rubric đề xuất:

| Nhóm | Trọng số | Điều kiện |
|---|---:|---|
| Data correctness | 25 | Số liệu khớp fact/model artifact |
| Financial model integrity | 25 | P&L, CĐKT, CF, valuation reconcile |
| Domain depth | 15 | Có ETC/OTC, sản phẩm, API, regulatory, catalyst |
| Valuation transparency | 15 | Có WACC, FCFF/FCFE, bridge, sensitivity |
| Citation quality | 10 | Claim-level citation |
| Professional presentation | 10 | Không lặp, chart/table rõ, trạng thái nhất quán |

Export policy:

```text
score >= 85: allow export
70 <= score < 85: export draft only, watermark NEEDS_REVIEW
score < 70: block export
```

## 7. Test cases cần thêm ngay

### Test 1. Profit growth sanity

Input:

```yaml
revenue_growth_2026: 4.0%
net_income_growth_2026: 53.9%
eps_growth_2026: 59.1%
```

Expected:

```yaml
status: fail
reason: profit_growth_requires_bridge
export_allowed: false
```

### Test 2. EBIT margin bridge

Input:

```yaml
ebit_margin_2025: 20.3%
ebit_margin_2026: 27.2%
gross_margin_2025: 47.6%
gross_margin_2026: 47.2%
```

Expected:

```yaml
status: fail
reason: ebit_margin_jump_without_gross_margin_support
required_artifact: operating_leverage_bridge
```

### Test 3. FCFE naming integrity

Input:

```yaml
report_mentions_fcfe: true
fcfe_artifact_exists: false
```

Expected:

```yaml
status: fail
reason: report_mentions_missing_valuation_method
```

### Test 4. Dividend consistency

Input:

```yaml
dividend_forecast_positive: true
dividend_yield_reported: 0
total_return_includes_dividend: true
```

Expected:

```yaml
status: fail
reason: dividend_yield_total_return_inconsistent
```

### Test 5. Balance sheet completeness

Input:

```yaml
forecast_assets_exists: true
forecast_equity_exists: true
forecast_liabilities_blank: true
```

Expected:

```yaml
status: fail
reason: balance_sheet_incomplete
```

### Test 6. Citation coverage

Input:

```yaml
quantitative_claims: 100
claims_with_fact_or_artifact_id: 80
```

Expected:

```yaml
status: fail
reason: citation_coverage_below_threshold
threshold: 100% for quantitative claims
```

### Test 7. Recommendation status consistency

Input:

```yaml
approval_status: under_review
visible_recommendation: HOLD
target_price_visible: true
```

Expected:

```yaml
status: warn_or_fail
reason: recommendation_visible_before_approval
```

## 8. Implementation plan

### Phase 1. Stop bad reports from exporting

Priority: P0.

Tasks:

1. Add `FinancialModelIntegrityGate`.
2. Add `ValuationCompletenessGate`.
3. Add `CitationCoverageGate`.
4. Add `RecommendationConsistencyGate`.
5. Add `ForecastReasonablenessGate`.
6. Mark current DHG report as `NEEDS_REVIEW`, not `APPROVED`.

Exit criteria:

- DHG_fast_report hiện tại phải bị fail vì profit/EPS growth jump, missing FCFE artifact, incomplete forecast debt/cash, dividend inconsistency and generic citation.

### Phase 2. Rebuild deterministic financial model

Priority: P0/P1.

Tasks:

1. Build canonical P&L, balance sheet and cash flow schedules.
2. Compute NOPAT, D&A, capex, ΔNWC, FCFF by code.
3. Compute WACC by code from explicit assumptions.
4. Compute equity bridge by code.
5. Generate valuation artifact before report writing.
6. Report writer only reads artifact; it cannot invent financial facts.

Exit criteria:

- Target price can be recomputed exactly from JSON artifact.
- No manual number in narrative unless it exists in artifact.

### Phase 3. Build DHG-specific research pack

Priority: P1.

Tasks:

1. Ingest annual reports, quarterly reports, investor docs, HOSE disclosures.
2. Extract revenue/product/channel data where available.
3. Extract major product groups, distribution network, factory/capacity, regulatory status.
4. Extract tender/BHYT/regulatory events relevant to DHG.
5. Build peer group.
6. Store every extracted fact with metadata and source.

Exit criteria:

- Report contains DHG-specific drivers, not only generic pharma terms.

### Phase 4. Upgrade report template

Priority: P1/P2.

Tasks:

1. Redesign cover page.
2. Add executive thesis box.
3. Add business overview with segment table.
4. Add operating update with quarter/year table.
5. Add forecast driver pages.
6. Add valuation bridge page.
7. Add appendix financial statements.
8. Add evidence appendix.
9. Add chart/table rendering standards.

Exit criteria:

- Report reaches 12-16 pages for full report.
- Every chart/table has number, title, unit, source and narrative link.

### Phase 5. Build FPTS-grade evaluation harness

Priority: P1.

Tasks:

1. Store FPTS-style checklist as evaluation rubric.
2. Compare every generated report against the checklist.
3. Produce JSON eval output.
4. Attach eval summary to each run.
5. Add regression tests using DHG report as negative sample.

Exit criteria:

- System can say exactly why a report failed.
- Evaluator catches the same issues documented in this plan.

## 9. Acceptance criteria for FPTS-grade output

A generated report is considered acceptable only if:

1. It contains company-specific business analysis.
2. It contains quarterly or latest-period update.
3. It contains driver-based forecast, not flat percentage assumptions only.
4. It contains complete financial statements or clearly scoped model tables.
5. It contains valuation bridge from FCFF/FCFE to target price.
6. It contains WACC decomposition.
7. It contains sensitivity table.
8. It contains peer comparison or explains why peer comparison is unavailable.
9. Every quantitative claim has claim-level citation or artifact lineage.
10. It has no unexplained profit/EPS jump.
11. It has no incomplete balance sheet if balance sheet is shown.
12. Recommendation, target price and approval status are internally consistent.
13. Charts and tables are readable, numbered and sourced.
14. Report quality evaluator score >= 85/100.

## 10. Prompt ngắn cho coding agent

```text
You are a senior financial workflow engineer and backend architect.

Audit and refactor the report generation pipeline so that generated Vietnam pharma equity reports meet FPTS-grade analytical discipline.

Use DHG_fast_report.pdf as the negative regression sample. The current report must fail export gates because it has:
- 2026 net income +53.9% and EPS +59.1% while revenue is only +4.0%;
- EBIT margin jump from 20.3% to 27.2% without margin bridge;
- FCFF/FCFE wording without a real FCFE artifact;
- incomplete forward balance sheet/debt/cash fields;
- dividend forecast inconsistent with dividend yield and total return;
- generic source labels instead of claim-level citations;
- under-review status shown together with a visible recommendation.

Implement:
1. FinancialModelIntegrityGate
2. ForecastReasonablenessGate
3. ValuationCompletenessGate
4. CitationCoverageGate
5. RecommendationConsistencyGate
6. Driver-based pharma forecast artifact
7. Valuation bridge artifact with FCFF table, WACC decomposition, terminal value, EV-to-equity bridge
8. FPTS-grade report template and evaluation rubric

Do not solve this by only changing text or PDF layout. Fix the data artifacts, model validation, citation map and report assembly contract first. The report writer must only narrate from locked artifacts and evidence packs.
```

## 11. Product decision

Không nên đặt mục tiêu “copy giao diện FPTS”. Mục tiêu đúng là đạt **kỷ luật phân tích tương đương FPTS**:

- số liệu có nguồn;
- mô hình có thể tái lập;
- forecast có driver;
- định giá có bridge;
- rủi ro có cơ chế truyền dẫn tài chính;
- báo cáo không xuất nếu số liệu không khớp;
- người review biết chính xác báo cáo sai ở đâu.

Chỉ sau khi lõi tài chính và evidence layer đạt chuẩn mới nên tối ưu layout PDF.
