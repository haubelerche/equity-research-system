**CẨM NANG CÔNG THỨC ĐỊNH GIÁ CỔ PHIẾU**

**Bản sạch: DCF theo trọng số 60% FCFF và 40% FCFE, kèm định giá tương đối và peer group**

Mục tiêu: dùng làm chuẩn công thức cho AI agent hỗ trợ phân tích và định giá cổ phiếu, đặc biệt với doanh nghiệp dược, hàng tiêu dùng, sản xuất và các doanh nghiệp có dòng tiền tương đối ổn định.

**Công thức định giá trọng tâm của bản này**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p>Giá mục tiêu DCF kết hợp = 60% x Giá trị/CP theo FCFF + 40% x Giá trị/CP theo FCFE</p>
<p><em>FCFF được chiết khấu bằng WACC. FCFE được chiết khấu bằng Re - chi phí vốn chủ sở hữu. Không được dùng lẫn dòng tiền và suất chiết khấu.</em></p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

*Lưu ý: Tài liệu này là khung công thức và quy trình. Khi dùng cho báo cáo thật, mọi giả định WACC, Re, g, peer multiple và forecast phải có nguồn và phải được kiểm tra thủ công.*

# Mục lục

1.  1\. Nguyên tắc định giá chính

2.  2\. Quy ước dữ liệu và kiểm tra dấu

3.  3\. Công thức DCF theo FCFF

4.  4\. Công thức DCF theo FCFE

5.  5\. Cách kết hợp 60% FCFF và 40% FCFE

6.  6\. Định giá tương đối và peer group

7.  7\. Trailing P/E, Forward P/E và cách chọn EPS

8.  8\. Bộ công thức tài chính đầy đủ cần dùng

9.  9\. Quy trình Excel / AI agent

10. 10\. Checklist kiểm toán mô hình trước khi xuất báo cáo

# 1. Nguyên tắc định giá chính

Bản sạch này chuẩn hóa mô hình định giá theo hai nhánh DCF: FCFF và FCFE. Kết quả cuối cùng của DCF được lấy theo trọng số 60% FCFF và 40% FCFE. Định giá tương đối được dùng để kiểm tra chéo, giải thích thị trường đang trả multiple nào, và giúp hiệu chỉnh giả định tăng trưởng/biên lợi nhuận nếu DCF lệch quá xa peer group.

| **Thành phần**     | **Vai trò**                                                                                    | **Suất chiết khấu**        | **Đầu ra**                                       | **Trọng số**                                               |
|--------------------|------------------------------------------------------------------------------------------------|----------------------------|--------------------------------------------------|------------------------------------------------------------|
| FCFF DCF           | Định giá toàn bộ doanh nghiệp trước khi phân bổ cho chủ nợ và cổ đông.                         | WACC                       | Enterprise Value -\> Equity Value -\> Giá trị/CP | 60%                                                        |
| FCFE DCF           | Định giá trực tiếp dòng tiền còn lại cho cổ đông thường sau CAPEX, vốn lưu động và vay/trả nợ. | Re / Cost of Equity        | Equity Value -\> Giá trị/CP                      | 40%                                                        |
| Định giá tương đối | Kiểm tra chéo bằng P/E, EV/EBITDA, P/B, P/S và peer group.                                     | Không chiết khấu dòng tiền | Giá trị hợp lý theo thị trường                   | Không bắt buộc trong công thức 60/40; dùng làm cross-check |

**Công thức quyết định cuối cùng trong mô hình DCF**

| Target Price_DCF = 0.60 x Price_FCFF + 0.40 x Price_FCFE |
|----------------------------------------------------------|

**Upside/Downside**

| Upside = Target Price_DCF / Current Market Price - 1 |
|------------------------------------------------------|

**Margin of Safety**

| Margin of Safety = Intrinsic Value / Market Price - 1 |
|-------------------------------------------------------|

# 2. Quy ước dữ liệu và kiểm tra dấu

Sai sót phổ biến nhất trong mô hình DCF là dùng sai dấu CAPEX, nợ vay, lãi vay hoặc vốn lưu động. Trước khi tính FCFF/FCFE, AI agent phải chuẩn hóa tất cả biến đầu vào theo quy ước dưới đây.

| **Biến**         | **Quy ước trong mô hình**                                        | **Nguồn thường gặp**                                        | **Kiểm tra bắt buộc**                                                                                |
|------------------|------------------------------------------------------------------|-------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| CAPEX_positive   | Luôn là số dương biểu thị tiền chi đầu tư.                       | Lưu chuyển tiền tệ: mua sắm/xây dựng TSCĐ thường là số âm.  | Nếu dữ liệu gốc là số âm thì CAPEX_positive = ABS(CAPEX_CFS).                                        |
| CAPEX_CFS        | Số theo báo cáo lưu chuyển tiền tệ, thường âm.                   | Cash flow from investing.                                   | Không dùng CFO - CAPEX_CFS nếu CAPEX_CFS đã âm, vì sẽ cộng ngược CAPEX.                              |
| Net Borrowing    | Vay ròng = tiền vay mới - tiền trả nợ gốc.                       | Lưu chuyển tiền tệ tài chính hoặc thay đổi nợ vay chịu lãi. | Nếu âm nghĩa là doanh nghiệp trả nợ ròng, làm giảm FCFE.                                             |
| Interest Expense | Chi phí lãi vay dương trong mô hình.                             | KQKD hoặc thuyết minh.                                      | Nếu nguồn ghi âm, dùng ABS(interest_expense).                                                        |
| Net Debt         | Nợ vay chịu lãi - tiền & đầu tư tài chính ngắn hạn có tính tiền. | Bảng cân đối kế toán.                                       | Nếu Net Debt âm, doanh nghiệp có net cash; khi chuyển EV sang Equity Value phải cộng phần tiền ròng. |
| Delta NWC        | NWC_t - NWC_t-1.                                                 | Bảng cân đối kế toán.                                       | Delta NWC dương làm giảm FCFF/FCFE; Delta NWC âm làm tăng dòng tiền.                                 |

**Chuẩn hóa CAPEX**

| CAPEX_positive = ABS(CAPEX_CFS) nếu CAPEX_CFS \< 0 |
|----------------------------------------------------|

**Công thức dòng tiền khi CAPEX trong CFS là số âm**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p>FCFE = CFO + CAPEX_CFS + Net Borrowing<br />
FCFF = CFO + Interest x (1 - Tax Rate) + CAPEX_CFS</p>
<p><em>Vì CAPEX_CFS đã âm, phép cộng CAPEX_CFS chính là trừ chi đầu tư.</em></p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**Công thức dòng tiền khi đã đổi CAPEX thành số dương**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>FCFE = CFO - CAPEX_positive + Net Borrowing<br />
FCFF = CFO + Interest x (1 - Tax Rate) - CAPEX_positive</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# 3. Công thức DCF theo FCFF

FCFF là dòng tiền tự do cho toàn bộ doanh nghiệp, tức dòng tiền thuộc về cả chủ nợ và cổ đông. Vì FCFF thuộc về toàn bộ nguồn vốn, suất chiết khấu đúng là WACC.

**FCFF từ EBIT**

| FCFF = EBIT x (1 - Tax Rate) + D&A - CAPEX_positive - Delta NWC |
|-----------------------------------------------------------------|

**FCFF từ CFO**

| FCFF = CFO + Interest Expense x (1 - Tax Rate) - CAPEX_positive |
|-----------------------------------------------------------------|

**FCFF từ CFO nếu CAPEX_CFS là số âm**

| FCFF = CFO + Interest Expense x (1 - Tax Rate) + CAPEX_CFS |
|------------------------------------------------------------|

| **Bước** | **Công thức / thao tác**                                                | **Ý nghĩa**                                                                           |
|----------|-------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| 1        | EBIT = Profit Before Tax + Interest Expense                             | Loại bỏ ảnh hưởng cấu trúc vốn để quay về lợi nhuận hoạt động trước lãi vay.          |
| 2        | Tax Rate = Tax Expense / Profit Before Tax                              | Dùng thuế suất hiệu dụng, hoặc thuế suất chuẩn nếu năm hiện tại có yếu tố bất thường. |
| 3        | NOPAT = EBIT x (1 - Tax Rate)                                           | Lợi nhuận hoạt động sau thuế, trước tác động tài trợ vốn.                             |
| 4        | FCFF = NOPAT + D&A - CAPEX_positive - Delta NWC                         | Dòng tiền tạo ra cho cả chủ nợ và cổ đông.                                            |
| 5        | Discount Rate = WACC                                                    | Phù hợp vì FCFF thuộc về toàn bộ doanh nghiệp.                                        |
| 6        | EV = PV(FCFF dự báo) + PV(Terminal Value)                               | Giá trị doanh nghiệp.                                                                 |
| 7        | Equity Value = EV - Net Debt - Minority Interest + Non-operating Assets | Chuyển từ giá trị doanh nghiệp sang giá trị vốn chủ sở hữu.                           |
| 8        | Price_FCFF = Equity Value / Diluted Shares Outstanding                  | Giá trị nội tại mỗi cổ phiếu theo FCFF.                                               |

**WACC**

| WACC = E/(D + E) x Re + D/(D + E) x Rd x (1 - Tax Rate) |
|---------------------------------------------------------|

**Cost of Equity theo CAPM mở rộng**

| Re = Rf + Beta x Equity Risk Premium + Size Premium + Company Specific Risk Premium |
|-------------------------------------------------------------------------------------|

**Cost of Debt sau thuế**

| After-tax Rd = Rd x (1 - Tax Rate) |
|------------------------------------|

**Terminal Value theo Gordon Growth cho FCFF**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p>TV_FCFF_N = FCFF_N x (1 + g) / (WACC - g)</p>
<p><em>Điều kiện bắt buộc: g &lt; WACC. Nếu g gần WACC, terminal value sẽ bị phóng đại.</em></p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**Enterprise Value theo FCFF**

| EV_FCFF = SUM\[FCFF_t / (1 + WACC)^t\] + TV_FCFF_N / (1 + WACC)^N |
|-------------------------------------------------------------------|

**Giá trị vốn chủ sở hữu theo FCFF**

| Equity Value_FCFF = EV_FCFF - Interest-bearing Debt + Cash & Short-term Investments - Minority Interest + Non-operating Investments |
|-------------------------------------------------------------------------------------------------------------------------------------|

**Giá trị mỗi cổ phiếu theo FCFF**

| Price_FCFF = Equity Value_FCFF / Diluted Shares Outstanding |
|-------------------------------------------------------------|

# 4. Công thức DCF theo FCFE

FCFE là dòng tiền tự do còn lại cho cổ đông thường sau khi doanh nghiệp đã chi CAPEX, tài trợ vốn lưu động và vay/trả nợ. Vì FCFE thuộc riêng cổ đông, suất chiết khấu đúng là Re, không phải WACC.

**FCFE từ lợi nhuận sau thuế**

| FCFE = Net Income + D&A - CAPEX_positive - Delta NWC + Net Borrowing |
|----------------------------------------------------------------------|

**FCFE từ CFO**

| FCFE = CFO - CAPEX_positive + Net Borrowing |
|---------------------------------------------|

**FCFE từ CFO nếu CAPEX_CFS là số âm**

| FCFE = CFO + CAPEX_CFS + Net Borrowing |
|----------------------------------------|

| **Bước** | **Công thức / thao tác**                                    | **Ý nghĩa**                                                                     |
|----------|-------------------------------------------------------------|---------------------------------------------------------------------------------|
| 1        | Net Income = LNST thuộc cổ đông công ty mẹ                  | Dùng lợi nhuận dành cho cổ đông thường.                                         |
| 2        | Add back D&A                                                | Khấu hao là chi phí phi tiền mặt nên cộng lại.                                  |
| 3        | Trừ CAPEX_positive                                          | Chi đầu tư tài sản cố định làm giảm dòng tiền cho cổ đông.                      |
| 4        | Trừ Delta NWC                                               | Vốn bị giam vào phải thu/tồn kho làm giảm dòng tiền.                            |
| 5        | Cộng Net Borrowing                                          | Vay ròng làm tăng dòng tiền sẵn có cho cổ đông; trả nợ ròng làm giảm dòng tiền. |
| 6        | Discount Rate = Re                                          | Phù hợp vì FCFE là dòng tiền trực tiếp cho cổ đông.                             |
| 7        | Equity Value_FCFE = PV(FCFE dự báo) + PV(Terminal Value)    | FCFE tạo ra trực tiếp giá trị vốn chủ sở hữu.                                   |
| 8        | Price_FCFE = Equity Value_FCFE / Diluted Shares Outstanding | Giá trị nội tại mỗi cổ phiếu theo FCFE.                                         |

**Net Borrowing từ lưu chuyển tiền tệ**

| Net Borrowing = Proceeds from Debt Issuance - Principal Debt Repayment |
|------------------------------------------------------------------------|

**Net Borrowing xấp xỉ từ bảng cân đối kế toán**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p>Net Borrowing ≈ Interest-bearing Debt_t - Interest-bearing Debt_t-1</p>
<p><em>Cách xấp xỉ này cần kiểm tra thuyết minh nợ vay vì có thể bị ảnh hưởng bởi FX, tái phân loại ngắn hạn/dài hạn hoặc nợ thuê.</em></p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**Terminal Value theo Gordon Growth cho FCFE**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p>TV_FCFE_N = FCFE_N x (1 + g) / (Re - g)</p>
<p><em>Điều kiện bắt buộc: g &lt; Re. FCFE cuối kỳ nên là dòng tiền đã normalize, không bị bóp méo bởi vay/trả nợ bất thường.</em></p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**Equity Value theo FCFE**

| Equity Value_FCFE = SUM\[FCFE_t / (1 + Re)^t\] + TV_FCFE_N / (1 + Re)^N |
|-------------------------------------------------------------------------|

**Giá trị mỗi cổ phiếu theo FCFE**

| Price_FCFE = Equity Value_FCFE / Diluted Shares Outstanding |
|-------------------------------------------------------------|

# 5. Cách kết hợp 60% FCFF và 40% FCFE

Việc kết hợp FCFF và FCFE giúp giảm rủi ro phụ thuộc vào một góc nhìn duy nhất. FCFF ổn định hơn khi cấu trúc vốn thay đổi; FCFE phản ánh trực tiếp dòng tiền dành cho cổ đông. Với doanh nghiệp dược có nợ vay không quá cao và dòng tiền hoạt động tương đối ổn định, tỷ lệ 60% FCFF và 40% FCFE là hợp lý để cân bằng giữa giá trị doanh nghiệp và giá trị cổ đông.

**Giá trị DCF kết hợp**

| Target Price_DCF = 0.60 x Price_FCFF + 0.40 x Price_FCFE |
|----------------------------------------------------------|

**Equity Value kết hợp**

| Equity Value_DCF = 0.60 x Equity Value_FCFF + 0.40 x Equity Value_FCFE |
|------------------------------------------------------------------------|

**Giá trị mỗi cổ phiếu kết hợp**

| Target Price_DCF = Equity Value_DCF / Diluted Shares Outstanding |
|------------------------------------------------------------------|

| **Chỉ tiêu đầu ra** | **Công thức**                                     | **Ghi chú kiểm tra**                                            |
|---------------------|---------------------------------------------------|-----------------------------------------------------------------|
| Price_FCFF          | Equity Value_FCFF / Diluted Shares                | Phải đi từ EV sang Equity Value.                                |
| Price_FCFE          | Equity Value_FCFE / Diluted Shares                | Không trừ net debt lần nữa vì FCFE đã là dòng tiền cho cổ đông. |
| Target Price_DCF    | 0.60 x Price_FCFF + 0.40 x Price_FCFE             | Đây là giá mục tiêu DCF chính.                                  |
| Upside              | Target Price_DCF / Market Price - 1               | Nếu upside cao nhưng DCF nhạy với g/WACC/Re, cần ghi cảnh báo.  |
| Recommendation Band | Buy / Hold / Sell theo upside và margin of safety | Quy tắc khuyến nghị phải do người phân tích định nghĩa trước.   |

| **Trường hợp**                          | **Dấu hiệu**                                                        | **Cách xử lý**                                                                      |
|-----------------------------------------|---------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| Price_FCFF cao hơn rất nhiều Price_FCFE | Net borrowing thấp/âm, FCFE bị ảnh hưởng bởi trả nợ hoặc CAPEX lớn. | Kiểm tra net borrowing, CAPEX bất thường, dùng normalized FCFE trong terminal year. |
| Price_FCFE cao hơn rất nhiều Price_FCFF | Doanh nghiệp vay ròng lớn làm FCFE tăng tạm thời.                   | Không để vay nợ bất thường làm phóng đại FCFE; kiểm tra cấu trúc vốn bền vững.      |
| Hai giá trị lệch trên 25%               | Mô hình chưa nhất quán hoặc giả định tăng trưởng khác nhau.         | Chạy reconciliation và sensitivity trước khi xuất báo cáo.                          |
| Terminal value \> 70% tổng giá trị      | Mô hình phụ thuộc quá lớn vào g dài hạn.                            | Bắt buộc có sensitivity g và discount rate.                                         |

# 6. Định giá tương đối và peer group

Định giá tương đối không thay thế DCF trong bản này, nhưng là lớp kiểm tra chéo bắt buộc. Nếu DCF 60/40 cho kết quả cao hơn hoặc thấp hơn quá xa peer group, người phân tích cần kiểm tra lại giả định tăng trưởng, biên lợi nhuận, CAPEX, working capital, WACC/Re và terminal growth.

## 6.1. Quy trình chọn peer group

11. Xác định ngành và phân ngành: dược phẩm sản xuất, phân phối dược, thiết bị y tế, bệnh viện hoặc hóa dược không nên trộn lẫn nếu mô hình lợi nhuận khác nhau.

12. Chọn doanh nghiệp có sản phẩm, kênh bán hàng, quy mô doanh thu, biên lợi nhuận và vòng quay vốn tương đối tương đồng.

13. Ưu tiên cùng thị trường niêm yết. Nếu số lượng peer trong nước quá ít, có thể mở rộng sang peer khu vực nhưng phải điều chỉnh rủi ro quốc gia và thanh khoản.

14. Loại bỏ peer có EPS âm, EBITDA âm, giao dịch quá kém thanh khoản hoặc đang có sự kiện bất thường như M&A, tái cấu trúc, ghi nhận one-off lớn.

15. Dùng median thay vì average nếu mẫu nhỏ hoặc có outlier.

16. Ghi rõ ngày giá thị trường và kỳ dữ liệu tài chính dùng để tính multiple.

| **Nhóm peer gợi ý cho ngành dược Việt Nam**                              | **Mục đích sử dụng**                                | **Lưu ý**                                                                                |
|--------------------------------------------------------------------------|-----------------------------------------------------|------------------------------------------------------------------------------------------|
| DHG, IMP, TRA, DBD, DMC, OPC, MKP                                        | Peer nội địa cho P/E, P/B, EV/EBITDA.               | Cần kiểm tra thanh khoản, free-float, dữ liệu lợi nhuận bất thường và khác biệt OTC/ETC. |
| Các doanh nghiệp dược khu vực Đông Nam Á                                 | Mở rộng mẫu nếu peer Việt Nam quá ít.               | Phải điều chỉnh country risk, quy mô thị trường và chuẩn kế toán.                        |
| Không dùng chung với bệnh viện, thiết bị y tế nếu không có lý do rõ ràng | Tránh sai lệch multiple do mô hình kinh doanh khác. | Bệnh viện và phân phối dược có margin, CAPEX và working capital khác sản xuất dược.      |

**Market Capitalization**

| Market Cap = Current Share Price x Shares Outstanding |
|-------------------------------------------------------|

**Enterprise Value**

| EV = Market Cap + Interest-bearing Debt + Preferred Equity + Minority Interest - Cash & Cash Equivalents - Short-term Investments |
|-----------------------------------------------------------------------------------------------------------------------------------|

**Net Debt**

| Net Debt = Interest-bearing Debt - Cash & Cash Equivalents - Short-term Investments |
|-------------------------------------------------------------------------------------|

| **Multiple**   | **Công thức**           | **Khi nên dùng**                                                                                         | **Lỗi thường gặp**                                                                |
|----------------|-------------------------|----------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------|
| Trailing P/E   | Current Price / EPS_TTM | Doanh nghiệp lợi nhuận ổn định, muốn biết thị trường đang trả bao nhiêu cho lợi nhuận 12 tháng gần nhất. | Dùng EPS năm cũ khi lợi nhuận đang thay đổi mạnh.                                 |
| Forward P/E    | Current Price / EPS_FY1 | Định giá cổ phiếu có lợi nhuận dự báo, thường dùng trong báo cáo phân tích.                              | Dùng EPS forecast không có mô hình hoặc không kiểm tra one-off.                   |
| EV/EBITDA      | EV / EBITDA             | So sánh doanh nghiệp khác cấu trúc vốn, hữu ích cho sản xuất/dược nếu EBITDA ổn định.                    | Không trừ/cộng net debt đúng khi chuyển ra giá trị cổ phiếu.                      |
| EV/EBIT        | EV / EBIT               | Khi khấu hao/CAPEX có ý nghĩa lớn và muốn gần lợi nhuận hoạt động hơn EBITDA.                            | Bỏ qua khác biệt tuổi tài sản và chính sách khấu hao.                             |
| P/B            | Current Price / BVPS    | Dùng phụ, nhất là doanh nghiệp có ROE ổn định hoặc ngành tài chính.                                      | Không nên là phương pháp chính cho dược nếu tài sản vô hình/brand/R&D quan trọng. |
| P/S            | Market Cap / Revenue    | Dùng khi lợi nhuận bị bóp méo tạm thời nhưng doanh thu còn ý nghĩa.                                      | Không phản ánh biên lợi nhuận.                                                    |
| Dividend Yield | DPS / Current Price     | Dùng kiểm tra thêm với doanh nghiệp trả cổ tức tiền mặt ổn định.                                         | Không thay thế định giá nếu chính sách cổ tức thay đổi.                           |

# 7. Trailing P/E, Forward P/E và cách chọn EPS

P/E phải được tách thành trailing và forward. Không nên chỉ ghi P/E = Price / EPS mà không nói EPS thuộc kỳ nào. Với cổ phiếu dược có lợi nhuận ổn định, trailing P/E dùng để quan sát thị trường hiện tại; forward P/E dùng để định giá mục tiêu.

**EPS cơ bản**

| EPS = (Net Income Attributable to Common Shareholders - Preferred Dividends) / Weighted Average Common Shares |
|---------------------------------------------------------------------------------------------------------------|

**EPS pha loãng**

| Diluted EPS = Net Income Attributable to Common Shareholders / Diluted Weighted Average Shares |
|------------------------------------------------------------------------------------------------|

**EPS TTM**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>EPS_TTM = EPS của 4 quý gần nhất cộng lại<br />
hoặc EPS_TTM = Net Income_TTM / Weighted Average Shares_TTM</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**Trailing P/E**

| Trailing P/E = Current Share Price / EPS_TTM |
|----------------------------------------------|

**Forward P/E**

| Forward P/E = Current Share Price / EPS_FY1 |
|---------------------------------------------|

**Giá mục tiêu theo Forward P/E**

| Target Price_PE = Target Forward P/E x EPS_FY1 |
|------------------------------------------------|

**Giá mục tiêu theo P/E nhiều năm**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p>Target Price_PE_2Y = Target Forward P/E x EPS_FY2 / (1 + Re)</p>
<p><em>Có thể dùng khi định giá theo lợi nhuận năm thứ hai nhưng cần chiết khấu về hiện tại.</em></p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

| **Loại EPS**   | **Công thức**                                            | **Dùng khi nào**                                        | **Ghi chú**                                               |
|----------------|----------------------------------------------------------|---------------------------------------------------------|-----------------------------------------------------------|
| EPS reported   | Theo báo cáo tài chính                                   | Dùng để đối chiếu nhanh.                                | Có thể chứa one-off.                                      |
| EPS normalized | (Net Income - One-off gains + One-off losses) / Shares   | Dùng cho P/E hợp lý nếu có thu nhập/chi phí bất thường. | Nên giải thích từng khoản điều chỉnh.                     |
| EPS_TTM        | Lợi nhuận 4 quý gần nhất / cổ phiếu bình quân            | Dùng cho trailing P/E.                                  | Tốt hơn EPS năm cũ nếu đã có báo cáo quý mới.             |
| EPS_FY1        | LNST dự phóng năm tới / cổ phiếu bình quân pha loãng     | Dùng cho forward P/E và target price.                   | Phải gắn với mô hình forecast doanh thu, margin, chi phí. |
| EPS_FY2        | LNST dự phóng năm thứ hai / cổ phiếu bình quân pha loãng | Dùng khi thị trường định giá trước chu kỳ hồi phục.     | Nên chiết khấu về hiện tại.                               |

**Target P/E từ peer group**

| Target P/E = Median Forward P/E_peer x (1 + Premium/Discount Adjustment) |
|--------------------------------------------------------------------------|

**Premium/Discount Adjustment gợi ý**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th><p>Adjustment = a x ROE_gap + b x Growth_gap + c x Margin_gap - d x Liquidity_discount - e x Governance/Risk_discount</p>
<p><em>Không nên máy móc. Với báo cáo thật, chỉ cần giải thích định tính và dùng range P/E bear/base/bull.</em></p></th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**P/E valuation theo kịch bản**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>Bear Price = EPS_FY1 x P/E_bear<br />
Base Price = EPS_FY1 x P/E_base<br />
Bull Price = EPS_FY1 x P/E_bull</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# 8. Bộ công thức tài chính đầy đủ cần dùng

Phần này là bộ công thức chuẩn cho worksheet hoặc AI agent. Có thể dùng làm dictionary để kiểm tra logic trước khi sinh báo cáo.

| **Chỉ tiêu**          | **Công thức chuẩn**                                                       | **Ghi chú**                                       |
|-----------------------|---------------------------------------------------------------------------|---------------------------------------------------|
| CAGR                  | (Ending Value / Beginning Value)^(1 / n) - 1                              | Tăng trưởng kép. n là số kỳ chuyển tiếp.          |
| YoY Revenue Growth    | (Revenue_t - Revenue_t-1) / Revenue_t-1                                   | Tăng trưởng doanh thu cùng kỳ.                    |
| YoY Net Income Growth | (NI_t - NI_t-1) / NI_t-1                                                  | Tăng trưởng lợi nhuận cùng kỳ.                    |
| Gross Margin          | Gross Profit / Revenue                                                    | Biên lợi nhuận gộp.                               |
| EBIT Margin           | EBIT / Revenue                                                            | Biên lợi nhuận hoạt động trước lãi vay và thuế.   |
| Net Margin            | Net Income / Revenue                                                      | Biên lợi nhuận ròng.                              |
| ROA                   | Net Income / Average Total Assets                                         | Nên dùng tổng tài sản bình quân.                  |
| ROE                   | Net Income Attributable to Parent / Average Equity Attributable to Parent | Nên dùng VCSH bình quân thuộc cổ đông công ty mẹ. |
| ROIC                  | NOPAT / Average Invested Capital                                          | Hữu ích để so với WACC.                           |
| Current Ratio         | Current Assets / Current Liabilities                                      | Khả năng thanh toán hiện thời.                    |
| Quick Ratio           | (Current Assets - Inventory) / Current Liabilities                        | Thanh toán nhanh.                                 |
| Cash Ratio            | (Cash + Short-term Investments) / Current Liabilities                     | Thanh toán bằng tiền.                             |

| **Chỉ tiêu**          | **Công thức chuẩn**                                                                        | **Ghi chú**                                                                           |
|-----------------------|--------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| Debt/Equity           | Interest-bearing Debt / Equity                                                             | Nên dùng nợ vay chịu lãi thay vì toàn bộ nợ phải trả khi phân tích đòn bẩy tài chính. |
| Net Debt/Equity       | Net Debt / Equity                                                                          | Thể hiện đòn bẩy sau khi trừ tiền.                                                    |
| DSO                   | Average Accounts Receivable / Revenue x 365                                                | Số ngày thu tiền bình quân.                                                           |
| DIO                   | Average Inventory / COGS x 365                                                             | Số ngày tồn kho bình quân.                                                            |
| DPO                   | Average Accounts Payable / COGS x 365                                                      | Số ngày trả tiền bình quân.                                                           |
| Cash Conversion Cycle | DSO + DIO - DPO                                                                            | Chu kỳ chuyển đổi tiền mặt.                                                           |
| Fixed Asset Turnover  | Revenue / Average Net PP&E                                                                 | Hiệu quả sử dụng TSCĐ.                                                                |
| Asset Turnover        | Revenue / Average Total Assets                                                             | Hiệu quả sử dụng tổng tài sản.                                                        |
| EBIT                  | Profit Before Tax + Interest Expense                                                       | Dùng interest expense dạng số dương.                                                  |
| EBITDA                | EBIT + Depreciation & Amortization                                                         | Lợi nhuận trước lãi vay, thuế, khấu hao.                                              |
| NOPAT                 | EBIT x (1 - Tax Rate)                                                                      | Lợi nhuận hoạt động sau thuế.                                                         |
| Operating NWC         | AR + Inventory + Other Operating Current Assets - AP - Other Operating Current Liabilities | Loại tiền, đầu tư tài chính và nợ vay.                                                |

| **Chỉ tiêu**        | **Công thức chuẩn**                                           | **Ghi chú**                              |
|---------------------|---------------------------------------------------------------|------------------------------------------|
| Delta NWC           | Operating NWC_t - Operating NWC_t-1                           | Delta dương làm giảm dòng tiền.          |
| CAPEX_positive      | ABS(CAPEX_CFS) nếu CAPEX_CFS âm                               | Chuẩn hóa chi đầu tư về số dương.        |
| FCFF                | EBIT x (1 - T) + D&A - CAPEX_positive - Delta NWC             | Chiết khấu bằng WACC.                    |
| FCFE                | Net Income + D&A - CAPEX_positive - Delta NWC + Net Borrowing | Chiết khấu bằng Re.                      |
| WACC                | E/(D+E) x Re + D/(D+E) x Rd x (1-T)                           | Dùng cho FCFF.                           |
| Re                  | Rf + Beta x ERP + Size Premium + Specific Risk Premium        | Dùng cho FCFE.                           |
| Terminal Value FCFF | FCFF_N x (1+g) / (WACC-g)                                     | Điều kiện g \< WACC.                     |
| Terminal Value FCFE | FCFE_N x (1+g) / (Re-g)                                       | Điều kiện g \< Re.                       |
| Price_FCFF          | Equity Value_FCFF / Diluted Shares                            | Sau khi chuyển EV về Equity Value.       |
| Price_FCFE          | Equity Value_FCFE / Diluted Shares                            | FCFE ra trực tiếp Equity Value.          |
| Target Price DCF    | 0.60 x Price_FCFF + 0.40 x Price_FCFE                         | Giá mục tiêu DCF chính của tài liệu này. |
| Trailing P/E        | Current Price / EPS_TTM                                       | P/E 12 tháng gần nhất.                   |

| **Chỉ tiêu** | **Công thức chuẩn**     | **Ghi chú**                       |
|--------------|-------------------------|-----------------------------------|
| Forward P/E  | Current Price / EPS_FY1 | P/E dự phóng năm tới.             |
| EV/EBITDA    | EV / EBITDA             | So sánh enterprise value.         |
| P/B          | Current Price / BVPS    | Dùng kiểm tra thêm với ROE.       |
| P/S          | Market Cap / Revenue    | Dùng phụ khi lợi nhuận biến động. |

# 9. Quy trình Excel / AI agent

Để AI agent không chỉ viết báo cáo mà còn tính đúng mô hình định giá, nên tách thành các worksheet hoặc module sau.

| **Sheet / Module**    | **Nội dung**                                                                 | **Công thức / đầu ra chính**                                       |
|-----------------------|------------------------------------------------------------------------------|--------------------------------------------------------------------|
| 01_Raw_Data           | BCTC gốc: KQKD, CĐKT, LCTT, giá thị trường, số cổ phiếu.                     | Không tính toán; chỉ lưu dữ liệu và nguồn.                         |
| 02_Normalized_Data    | Chuẩn hóa đơn vị, kỳ, dấu âm/dương, nợ vay, tiền, CAPEX.                     | CAPEX_positive, interest expense positive, net debt.               |
| 03_Ratios             | Tính margin, ROA, ROE, DSO, DIO, DPO, CCC, đòn bẩy.                          | Bộ ratio chuẩn.                                                    |
| 04_Forecast           | Dự phóng doanh thu, biên lợi nhuận, thuế, D&A, CAPEX, NWC, nợ vay.           | Forecast IS/BS/CF.                                                 |
| 05_FCFF_DCF           | Tính FCFF, WACC, TV, EV, Equity Value, Price_FCFF.                           | FCFF DCF.                                                          |
| 06_FCFE_DCF           | Tính FCFE, Re, TV, Equity Value, Price_FCFE.                                 | FCFE DCF.                                                          |
| 07_DCF_Blend          | Kết hợp 60% FCFF và 40% FCFE.                                                | Target Price_DCF.                                                  |
| 08_Peer_Group         | Tập hợp peer, giá, market cap, EV, EPS, EBITDA, ROE, growth.                 | Peer median, outlier flags.                                        |
| 09_Relative_Valuation | Tính P/E, EV/EBITDA, P/B, P/S và target price theo multiple.                 | Target Price_PE, Target Price_EV/EBITDA, Relative Valuation Range. |
| 10_Sensitivity        | Sensitivity WACC/g, Re/g, P/E/EPS, EV/EBITDA/EBITDA.                         | Bear/Base/Bull.                                                    |
| 11_QA_Checks          | Kiểm tra sign convention, formula consistency, terminal value, peer quality. | Pass/Fail + warning messages.                                      |
| 12_Report_Output      | Bảng kết quả để đưa vào báo cáo.                                             | Target Price, Upside, key assumptions, warning.                    |

**Logic kiểm tra CAPEX cho AI agent**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>IF CAPEX_CFS &lt; 0 THEN CAPEX_positive = ABS(CAPEX_CFS)<br />
ELSE CAPEX_positive = CAPEX_CFS</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**Logic cảnh báo sai công thức FCFE**

| IF CAPEX_CFS \< 0 AND Formula contains "CFO - CAPEX_CFS" THEN Warning = "Sai dấu CAPEX: đang cộng ngược chi đầu tư" |
|---------------------------------------------------------------------------------------------------------------------|

**Logic cảnh báo terminal value**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>TV_weight = PV_Terminal_Value / Total_Valuation<br />
IF TV_weight &gt; 70% THEN Warning = "Terminal value chiếm tỷ trọng cao, cần sensitivity"</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**Logic cảnh báo lệch FCFF/FCFE**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>Spread = ABS(Price_FCFF / Price_FCFE - 1)<br />
IF Spread &gt; 25% THEN Warning = "FCFF và FCFE lệch lớn, cần kiểm tra net borrowing/CAPEX/NWC"</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

# 10. Checklist kiểm toán mô hình trước khi xuất báo cáo

| **Nhóm kiểm tra** | **Câu hỏi QA**                                                    | **Điều kiện pass**                                                         |
|-------------------|-------------------------------------------------------------------|----------------------------------------------------------------------------|
| FCFF/FCFE         | Có ghi rõ dòng tiền nào dùng WACC và dòng tiền nào dùng Re không? | Không được dùng FCFE với WACC hoặc FCFF với Re.                            |
| CAPEX             | CAPEX đã được chuẩn hóa thành số dương chưa?                      | Nếu dùng CAPEX_CFS âm thì phải cộng CAPEX_CFS vào CFO.                     |
| Net Borrowing     | FCFE có cộng vay ròng không?                                      | Nếu doanh nghiệp trả nợ ròng, Net Borrowing âm.                            |
| Net Debt          | FCFF có chuyển EV sang Equity Value đúng không?                   | Equity Value = EV - debt + cash, không được quên tiền mặt.                 |
| Terminal Growth   | g có nhỏ hơn WACC/Re không?                                       | Nếu không, mô hình bị lỗi toán học.                                        |
| Terminal Value    | PV terminal value có vượt 70% tổng giá trị không?                 | Nếu có, phải có sensitivity và cảnh báo.                                   |
| WACC              | Có nguồn cho Rf, beta, ERP, Rd, tax rate không?                   | Không dùng default nếu không ghi rõ.                                       |
| Re                | Cost of equity có dùng cho FCFE không?                            | FCFE bắt buộc chiết khấu bằng Re.                                          |
| Peer Group        | Có ít nhất 4-6 peer hợp lệ hoặc giải thích vì sao mẫu nhỏ không?  | Loại EPS âm/EBITDA âm nếu dùng P/E hoặc EV/EBITDA.                         |
| P/E               | Có phân biệt trailing P/E và forward P/E không?                   | Forward P/E nên dùng cho target price.                                     |
| EV/EBITDA         | Có bridge EV -\> Equity Value -\> Price không?                    | Không lấy EV/EBITDA x EBITDA rồi chia cổ phiếu ngay nếu chưa trừ net debt. |
| Output            | Có hiển thị Target Price_DCF = 60% FCFF + 40% FCFE không?         | Kết quả cuối phải đúng trọng số.                                           |
| Disclaimers       | Có cảnh báo báo cáo tự động và cần chuyên gia phê duyệt không?    | Bắt buộc với AI agent tài chính.                                           |

# 11. Gợi ý áp dụng cho cổ phiếu ngành dược

Với doanh nghiệp dược niêm yết, mô hình nên ưu tiên FCFF vì doanh nghiệp thường có dòng tiền hoạt động ổn định, nhu cầu CAPEX/nhà máy/GMP rõ ràng và cấu trúc vốn không phải yếu tố tạo giá trị chính. FCFE vẫn hữu ích để nhìn trực tiếp dòng tiền cho cổ đông, nhất là khi công ty có net cash, chính sách cổ tức ổn định hoặc thay đổi nợ vay đáng kể. Vì vậy, trọng số 60% FCFF và 40% FCFE là cách tiếp cận cân bằng.

| **Phương pháp** | **Vai trò với ngành dược**                                                                                                   | **Khuyến nghị dùng**                                   |
|-----------------|------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------|
| FCFF DCF        | Định giá dòng tiền hoạt động dài hạn, phản ánh CAPEX, working capital, biên lợi nhuận và tăng trưởng ngành.                  | Phương pháp chính, trọng số 60%.                       |
| FCFE DCF        | Kiểm tra dòng tiền còn lại cho cổ đông sau vay/trả nợ; hữu ích với công ty net cash hoặc trả cổ tức đều.                     | Phương pháp chính thứ hai, trọng số 40%.               |
| Forward P/E     | Thị trường thường định giá cổ phiếu dược theo lợi nhuận ổn định và kỳ vọng EPS năm tới.                                      | Cross-check quan trọng nhất trong định giá tương đối.  |
| EV/EBITDA       | So sánh doanh nghiệp có cấu trúc vốn khác nhau; hữu ích nếu EBITDA ổn định.                                                  | Cross-check phụ.                                       |
| P/B             | Không phải phương pháp chính vì giá trị thương hiệu, hệ thống phân phối và giấy phép/GMP không phản ánh đầy đủ trên sổ sách. | Dùng phụ kèm ROE.                                      |
| Dividend Yield  | Dược thường có cổ tức tiền mặt đều hơn nhiều ngành tăng trưởng cao.                                                          | Dùng để kiểm tra mức hấp dẫn với nhà đầu tư phòng thủ. |

# 12. Mẫu bảng kết quả nên xuất trong báo cáo

| **Phương pháp**         | **Giá trị/CP**                                                                                 | **Trọng số** | **Đóng góp vào giá mục tiêu** | **Ghi chú**                                                  |
|-------------------------|------------------------------------------------------------------------------------------------|--------------|-------------------------------|--------------------------------------------------------------|
| FCFF DCF                | Price_FCFF                                                                                     | 60%          | 0.60 x Price_FCFF             | Chiết khấu bằng WACC; chuyển EV sang Equity Value.           |
| FCFE DCF                | Price_FCFE                                                                                     | 40%          | 0.40 x Price_FCFE             | Chiết khấu bằng Re; không trừ net debt lần nữa.              |
| Target Price_DCF        | 0.60 x Price_FCFF + 0.40 x Price_FCFE                                                          | 100%         | Target Price_DCF              | Giá mục tiêu chính.                                          |
| Forward P/E cross-check | EPS_FY1 x Target Forward P/E                                                                   | N/A          | So sánh với Target Price_DCF  | Nếu lệch lớn, kiểm tra lại forecast và peer multiple.        |
| EV/EBITDA cross-check   | (EBITDA_FY1 x Target EV/EBITDA - Net Debt - Minority Interest + Non-operating Assets) / Shares | N/A          | So sánh với Target Price_DCF  | Không dùng làm kết quả chính nếu chưa có peer group đủ mạnh. |

**Kết luận định giá chuẩn**

<table>
<colgroup>
<col style="width: 100%" />
</colgroup>
<thead>
<tr class="header">
<th>Target Price_DCF = 0.60 x Price_FCFF + 0.40 x Price_FCFE<br />
Upside = Target Price_DCF / Market Price - 1<br />
Decision = Based on Upside, Margin of Safety, Risk Rating and Analyst Approval</th>
</tr>
</thead>
<tbody>
</tbody>
</table>

**Ghi chú cuối:** Định giá tương đối không nên được dùng máy móc để thay thế DCF. Nó là công cụ kiểm tra thị trường, xác nhận mức multiple hợp lý, và phát hiện trường hợp mô hình DCF quá lạc quan hoặc quá thận trọng. Với AI agent, mọi báo cáo có giả định mặc định, peer group thiếu dữ liệu hoặc warning chưa xử lý phải được gắn nhãn Draft / Needs Analyst Review.
