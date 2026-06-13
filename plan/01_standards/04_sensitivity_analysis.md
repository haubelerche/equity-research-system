**HƯỚNG DẪN ĐÁNH GIÁ SENSITIVITY ANALYSIS**

**Áp dụng cho mô hình định giá cổ phiếu: 60% FCFF + 40% FCFE**

Tài liệu này là hướng dẫn thực hành để xây dựng, đọc và kiểm tra phân tích độ nhạy trong mô hình định giá cổ phiếu. Trọng tâm là DCF kết hợp FCFF và FCFE, sau đó mở rộng sang định giá tương đối bằng P/E, EV/EBITDA, P/B và P/S.

| **Mục tiêu sử dụng:** Giúp người phân tích và AI agent biết biến nào cần kiểm tra, công thức nào phải nhất quán, cách đọc bảng sensitivity và khi nào phải cảnh báo kết quả định giá chưa đáng tin cậy. |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

*Phiên bản: 1.0 \| Ngôn ngữ: Vietnamese \| Đối tượng: Equity Research, Financial Modeling, AI Valuation Agent*

# MỤC LỤC TÓM TẮT

| **Mục** | **Nội dung chính**                                              |
|---------|-----------------------------------------------------------------|
| 1       | Khái niệm sensitivity analysis và vai trò trong định giá        |
| 2       | Bộ công thức DCF 60% FCFF + 40% FCFE                            |
| 3       | Ma trận sensitivity cho FCFF, FCFE và target price kết hợp      |
| 4       | Sensitivity cho định giá tương đối: P/E, EV/EBITDA, P/B, P/S    |
| 5       | Cách đọc kết quả: upside/downside, margin of safety, elasticity |
| 6       | Checklist kiểm toán mô hình cho AI agent                        |
| 7       | Template Excel và quy tắc cảnh báo lỗi                          |

# 1. KHÁI NIỆM VÀ VAI TRÒ

Sensitivity Analysis, hay phân tích độ nhạy, là kỹ thuật kiểm tra mức độ thay đổi của kết quả định giá khi một hoặc nhiều giả định đầu vào thay đổi. Trong định giá cổ phiếu, kết quả thường rất nhạy với WACC, Re, terminal growth, biên lợi nhuận, CAPEX, vốn lưu động, target P/E và EPS forward.

- Không dùng sensitivity để “làm đẹp” giá mục tiêu; dùng để hiểu rủi ro mô hình.

- Không chỉ trình bày bảng số; phải diễn giải biến nào làm giá trị thay đổi mạnh nhất.

- Không được dùng sensitivity để che giấu giả định chưa có nguồn. Các giả định trọng yếu vẫn cần được phê duyệt.

- Với AI agent, sensitivity là lớp kiểm soát chất lượng bắt buộc trước khi xuất target price.

## 1.1. Các loại phân tích độ nhạy nên có

| **Loại phân tích**  | **Mục đích**                                          | **Ví dụ áp dụng**                            |
|---------------------|-------------------------------------------------------|----------------------------------------------|
| One-way sensitivity | Thay đổi một biến, giữ nguyên các biến còn lại        | WACC từ 8% đến 12%                           |
| Two-way sensitivity | Thay đổi đồng thời hai biến chính                     | WACC x terminal growth                       |
| Scenario analysis   | Tạo bộ giả định Bear/Base/Bull                        | Doanh thu, margin, CAPEX, WACC cùng thay đổi |
| Tornado chart       | Xếp hạng biến tác động lớn nhất đến giá trị           | Revenue growth, EBIT margin, WACC, g         |
| Break-even analysis | Tìm ngưỡng giả định để target price bằng market price | P/E cần thiết hoặc WACC hòa vốn              |

# 2. BỘ CÔNG THỨC DCF 60% FCFF + 40% FCFE

Mô hình trung tâm sử dụng hai cách tiếp cận dòng tiền: FCFF định giá toàn bộ doanh nghiệp, FCFE định giá trực tiếp phần thuộc cổ đông. Kết quả DCF cuối cùng được lấy theo trọng số 60% FCFF và 40% FCFE.

| **Target Price DCF kết hợp:** Target Price_DCF = 60% x Price_FCFF + 40% x Price_FCFE                              |
|-------------------------------------------------------------------------------------------------------------------|
| FCFF phải chiết khấu bằng WACC. FCFE phải chiết khấu bằng Re / Cost of Equity. Không được dùng lẫn discount rate. |

## 2.1. Công thức FCFF DCF

| **FCFF từ EBIT:** FCFF_t = EBIT_t x (1 - Tax Rate_t) + D&A_t - CAPEX_t - Delta NWC_t |
|--------------------------------------------------------------------------------------|

| **FCFF từ CFO:** FCFF_t = CFO_t + Interest Expense_t x (1 - Tax Rate_t) - CAPEX_t                                                                                       |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Công thức này dùng khi CFO đã trừ chi phí lãi vay. CAPEX nên được đưa vào dưới dạng số dương. Nếu CAPEX trên CFS là số âm, dùng CFO + CAPEX_CFS + Interest x (1 - Tax). |

| **Giá trị doanh nghiệp từ FCFF:** EV_FCFF = Sum\[FCFF_t / (1 + WACC)^t\] + TV_FCFF / (1 + WACC)^n |
|---------------------------------------------------------------------------------------------------|

| **Terminal Value FCFF:** TV_FCFF = FCFF_n x (1 + g) / (WACC - g)         |
|--------------------------------------------------------------------------|
| Điều kiện bắt buộc: WACC \> g. Nếu WACC \<= g, mô hình phải báo INVALID. |

| **Equity Value từ FCFF:** Equity Value_FCFF = EV_FCFF - Net Debt + Non-operating Assets - Minority Interest |
|-------------------------------------------------------------------------------------------------------------|

| **Price từ FCFF:** Price_FCFF = Equity Value_FCFF / Diluted Shares Outstanding |
|--------------------------------------------------------------------------------|

## 2.2. Công thức FCFE DCF

| **FCFE từ lợi nhuận ròng:** FCFE_t = Net Income_t + D&A_t - CAPEX_t - Delta NWC_t + Net Borrowing_t |
|-----------------------------------------------------------------------------------------------------|

| **FCFE từ CFO:** FCFE_t = CFO_t - CAPEX_t + Net Borrowing_t                |
|----------------------------------------------------------------------------|
| Nếu CAPEX_CFS là số âm, dùng FCFE = CFO_t + CAPEX_CFS_t + Net Borrowing_t. |

| **Net Borrowing:** Net Borrowing_t = New Interest-bearing Debt_t - Debt Repayment_t                      |
|----------------------------------------------------------------------------------------------------------|
| Có thể tính gần đúng bằng Delta Debt_t nếu dữ liệu vay/trả nợ chi tiết không có, nhưng cần gắn cảnh báo. |

| **Equity Value từ FCFE:** Equity Value_FCFE = Sum\[FCFE_t / (1 + Re)^t\] + TV_FCFE / (1 + Re)^n |
|-------------------------------------------------------------------------------------------------|

| **Terminal Value FCFE:** TV_FCFE = FCFE_n x (1 + g) / (Re - g) |
|----------------------------------------------------------------|
| Điều kiện bắt buộc: Re \> g.                                   |

| **Price từ FCFE:** Price_FCFE = Equity Value_FCFE / Diluted Shares Outstanding |
|--------------------------------------------------------------------------------|

## 2.3. Công thức WACC và Re

| **WACC:** WACC = E/(D+E) x Re + D/(D+E) x Rd x (1 - Tax Rate) |
|---------------------------------------------------------------|

| **Cost of Equity theo CAPM:** Re = Rf + Beta x Equity Risk Premium + Size Premium + Liquidity Premium + Country Risk Premium |
|------------------------------------------------------------------------------------------------------------------------------|

| **Cost of Debt sau thuế:** After-tax Rd = Rd x (1 - Tax Rate) |
|---------------------------------------------------------------|

| **Lưu ý:** Nếu công ty có nợ vay thấp, FCFF và FCFE có thể cho kết quả gần nhau. Nếu chính sách vay nợ thay đổi mạnh, FCFE sẽ nhạy hơn và cần kiểm tra Net Borrowing cẩn thận. |
|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## 2.4. Quy ước dấu bắt buộc

| **Khoản mục**           | **Quy ước khuyến nghị**              | **Công thức áp dụng**                                           |
|-------------------------|--------------------------------------|-----------------------------------------------------------------|
| CAPEX model input       | Nhập là số dương                     | FCF = ... - CAPEX                                               |
| CAPEX từ CFS            | Thường là số âm                      | FCF = CFO + CAPEX_CFS                                           |
| COGS, SG&A, Tax expense | Có thể là số âm trong dữ liệu gốc    | Nên dùng giá trị tuyệt đối hoặc chuẩn hóa trước khi tính margin |
| Net Debt                | Debt - Cash & Short-term Investments | Equity Value = EV - Net Debt                                    |
| Cash surplus            | Tiền mặt vượt nhu cầu vận hành       | Có thể cộng vào Equity Value nếu tách khỏi hoạt động lõi        |

# 3. SENSITIVITY CHO FCFF DCF

FCFF DCF nên có tối thiểu ba nhóm sensitivity: discount rate, terminal growth và operational drivers. Bảng quan trọng nhất là WACC x terminal growth vì terminal value thường chiếm tỷ trọng lớn trong enterprise value.

## 3.1. Ma trận WACC x Terminal Growth

| **Ô giá trị trong bảng:** Price_FCFF(WACC_i, g_j) = Equity Value_FCFF(WACC_i, g_j) / Shares |
|---------------------------------------------------------------------------------------------|

| **WACC \\ g** | **2.0%** | **2.5%** | **3.0%** | **3.5%** | **4.0%** |
|---------------|----------|----------|----------|----------|----------|
| 8.0%          | Price    | Price    | Price    | Price    | Price    |
| 9.0%          | Price    | Price    | Price    | Price    | Price    |
| 10.0%         | Price    | Price    | Base     | Price    | Price    |
| 11.0%         | Price    | Price    | Price    | Price    | Price    |
| 12.0%         | Price    | Price    | Price    | Price    | Price    |

| **Cách đọc:** Nếu giá trị thay đổi quá mạnh chỉ vì WACC thay đổi 1%, cần diễn giải rằng mô hình phụ thuộc lớn vào discount rate. Nếu terminal value chiếm trên 70% EV, phải gắn cảnh báo. |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## 3.2. Sensitivity operational drivers cho FCFF

| **Driver**     | **Công thức liên quan**                  | **Tác động lên FCFF**                                         | **Gợi ý range**                |
|----------------|------------------------------------------|---------------------------------------------------------------|--------------------------------|
| Revenue Growth | Revenue_t = Revenue_t-1 x (1 + Growth_t) | Tăng doanh thu làm tăng EBIT nếu margin ổn định               | Base ± 1%-3%                   |
| EBIT Margin    | EBIT_t = Revenue_t x EBIT Margin_t       | Tác động trực tiếp đến NOPAT                                  | Base ± 0.5%-2%                 |
| Tax Rate       | NOPAT = EBIT x (1 - Tax)                 | Thuế cao làm giảm FCFF                                        | Theo thuế suất thực tế ± 1%-3% |
| D&A / Sales    | D&A_t = Revenue_t x D&A/Sales            | Tăng D&A làm tăng dòng tiền nhưng cũng phản ánh CAPEX quá khứ | Theo lịch khấu hao             |
| CAPEX / Sales  | CAPEX_t = Revenue_t x CAPEX/Sales        | CAPEX cao làm giảm FCFF                                       | Base ± 1%-3% doanh thu         |
| NWC / Sales    | NWC_t = Revenue_t x NWC/Sales            | NWC tăng làm giảm FCFF                                        | Base ± 1%-3% doanh thu         |

## 3.3. Kiểm tra tỷ trọng terminal value

| **Terminal Value Weight:** TV Weight = PV(Terminal Value) / Enterprise Value_FCFF |
|-----------------------------------------------------------------------------------|

| **Mức TV Weight** | **Đánh giá**   | **Hành động**                                                            |
|-------------------|----------------|--------------------------------------------------------------------------|
| \< 50%            | Tốt            | Mô hình ít phụ thuộc vào terminal value                                  |
| 50% - 70%         | Chấp nhận được | Cần giải thích WACC và g                                                 |
| \> 70%            | Rủi ro cao     | Bắt buộc cảnh báo và chạy thêm sensitivity                               |
| \> 85%            | Rất rủi ro     | Không nên kết luận target price nếu không có luận cứ tăng trưởng dài hạn |

# 4. SENSITIVITY CHO FCFE DCF

FCFE DCF nhạy với Re, terminal growth, CAPEX, vốn lưu động và đặc biệt là Net Borrowing. Nếu dữ liệu vay/trả nợ không rõ, FCFE có thể nhiễu mạnh hơn FCFF.

## 4.1. Ma trận Re x Terminal Growth

| **Ô giá trị trong bảng:** Price_FCFE(Re_i, g_j) = Equity Value_FCFE(Re_i, g_j) / Shares |
|-----------------------------------------------------------------------------------------|

| **Re \\ g** | **2.0%** | **2.5%** | **3.0%** | **3.5%** | **4.0%** |
|-------------|----------|----------|----------|----------|----------|
| 9.0%        | Price    | Price    | Price    | Price    | Price    |
| 10.0%       | Price    | Price    | Price    | Price    | Price    |
| 11.0%       | Price    | Price    | Base     | Price    | Price    |
| 12.0%       | Price    | Price    | Price    | Price    | Price    |
| 13.0%       | Price    | Price    | Price    | Price    | Price    |

## 4.2. Sensitivity riêng cho Net Borrowing

| **Net Borrowing sensitivity:** FCFE_t = CFO_t - CAPEX_t + Net Borrowing_t |
|---------------------------------------------------------------------------|

| **Trường hợp**              | **Net Borrowing giả định**        | **Cách hiểu**                                                     |
|-----------------------------|-----------------------------------|-------------------------------------------------------------------|
| Deleveraging                | Âm                                | Doanh nghiệp trả nợ ròng; FCFE giảm trong ngắn hạn                |
| Stable leverage             | Gần 0 hoặc theo tỷ lệ nợ mục tiêu | FCFE phản ánh dòng tiền vận hành sau đầu tư                       |
| Leveraging up               | Dương                             | Doanh nghiệp vay thêm; FCFE tăng nhưng rủi ro tài chính cũng tăng |
| Không có dữ liệu vay/trả nợ | Dùng Delta Debt hoặc đặt bằng 0   | Phải gắn cảnh báo: Net Borrowing approximated                     |

## 4.3. Khi nào FCFE đáng tin cậy hơn?

- Công ty có cấu trúc vốn ổn định và chính sách vay/trả nợ rõ ràng.

- Có dữ liệu chi tiết về vay mới, trả nợ gốc và cổ tức.

- Dòng tiền cổ đông là trọng tâm phân tích, ví dụ doanh nghiệp trả cổ tức đều hoặc ít thay đổi vốn vay.

- Không phù hợp nếu Net Borrowing biến động bất thường hoặc do tái cấu trúc tài chính một lần.

# 5. SENSITIVITY CHO TARGET PRICE KẾT HỢP 60/40

Sau khi có Price_FCFF và Price_FCFE, target price DCF được tính bằng trọng số 60/40. Cần chạy sensitivity cho cả hai giá trị đầu vào để thấy mức phân kỳ giữa hai phương pháp.

| **Target Price DCF:** Target Price_DCF = 0.60 x Price_FCFF + 0.40 x Price_FCFE |
|--------------------------------------------------------------------------------|

| **Gap giữa FCFF và FCFE:** Valuation Gap = (Price_FCFF / Price_FCFE) - 1 |
|--------------------------------------------------------------------------|

| **Mức gap**     | **Đánh giá**   | **Hành động**                                         |
|-----------------|----------------|-------------------------------------------------------|
| \< 10%          | Nhất quán      | Có thể dùng weighted DCF bình thường                  |
| 10% - 25%       | Cần giải thích | Kiểm tra Net Debt, Net Borrowing, CAPEX, NWC          |
| \> 25%          | Rủi ro mô hình | Không kết luận target price nếu chưa audit dòng tiền  |
| FCFE âm kéo dài | Không phù hợp  | Ưu tiên FCFF và dùng FCFE như cảnh báo rủi ro cổ đông |

## 5.1. Bảng sensitivity target price kết hợp

| **Price_FCFF \\ Price_FCFE** | **80** | **90** | **100** | **110** | **120** |
|------------------------------|--------|--------|---------|---------|---------|
| 90                           | 86     | 90     | 94      | 98      | 102     |
| 100                          | 92     | 96     | 100     | 104     | 108     |
| 110                          | 98     | 102    | 106     | 110     | 114     |
| 120                          | 104    | 108    | 112     | 116     | 120     |
| 130                          | 110    | 114    | 118     | 122     | 126     |

*Ví dụ trong bảng: nếu Price_FCFF = 110 và Price_FCFE = 100 thì Target Price_DCF = 0.6 x 110 + 0.4 x 100 = 106. Đơn vị có thể là nghìn VND/cổ phiếu hoặc VND/cổ phiếu tùy mô hình.*

# 6. SENSITIVITY CHO ĐỊNH GIÁ TƯƠNG ĐỐI

Định giá tương đối cần sensitivity vì target multiple và dự phóng EPS/EBITDA thường là hai biến chính quyết định giá mục tiêu. Không nên dùng một P/E hoặc EV/EBITDA duy nhất mà không có peer group và range.

## 6.1. Peer group: cách chọn và xử lý

| **Bước** | **Nội dung**                       | **Quy tắc thực hành**                                                     |
|----------|------------------------------------|---------------------------------------------------------------------------|
| 1        | Chọn ngành chính                   | Cùng ngành dược, y tế, sản xuất thuốc hoặc phân phối dược nếu thiếu mẫu   |
| 2        | Chọn mô hình kinh doanh tương đồng | OTC/ETC, sản xuất/ phân phối, generic/brand, thị trường nội địa/xuất khẩu |
| 3        | Kiểm tra quy mô                    | Doanh thu, vốn hóa, thanh khoản, ROE, margin                              |
| 4        | Loại outlier                       | Loại P/E âm, P/E quá cao do EPS thấp bất thường, EV/EBITDA âm             |
| 5        | Dùng median thay vì average        | Median ít bị kéo lệch bởi outlier                                         |
| 6        | Điều chỉnh premium/discount        | Dựa trên tăng trưởng, ROE, margin, thanh khoản, chất lượng quản trị       |

| **Peer median P/E:** Peer Median P/E = MEDIAN(P/E_peer_1, P/E_peer_2, ..., P/E_peer_n) |
|----------------------------------------------------------------------------------------|

| **Adjusted Target P/E:** Target P/E = Peer Median P/E x (1 + Premium/Discount) |
|--------------------------------------------------------------------------------|

| **Premium/Discount gợi ý:** Premium/Discount = f(Growth Premium, ROE Premium, Margin Premium, Liquidity Discount, Governance Discount) |
|----------------------------------------------------------------------------------------------------------------------------------------|

## 6.2. Trailing P/E và Forward P/E

| **EPS TTM:** EPS_TTM = Net Income last 4 quarters / Weighted Average Diluted Shares |
|-------------------------------------------------------------------------------------|

| **Trailing P/E:** Trailing P/E = Current Market Price / EPS_TTM |
|-----------------------------------------------------------------|

| **Forward EPS:** EPS_FY1 = Forecast Net Income_FY1 / Forecast Diluted Shares_FY1 |
|----------------------------------------------------------------------------------|

| **Forward P/E:** Forward P/E = Current Market Price / EPS_FY1 |
|---------------------------------------------------------------|

| **Target Price theo Forward P/E:** Target Price_PE = EPS_FY1 x Target Forward P/E |
|-----------------------------------------------------------------------------------|

| **Khuyến nghị:** Dùng trailing P/E để xem cổ phiếu đang giao dịch ở mức nào so với lợi nhuận gần nhất. Dùng forward P/E để ra target price vì định giá phản ánh kỳ vọng tương lai. |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## 6.3. Sensitivity EPS x Target P/E

| **EPS_FY1 \\ Target P/E** | **12x** | **14x** | **16x** | **18x** | **20x** |
|---------------------------|---------|---------|---------|---------|---------|
| 5,000                     | 60,000  | 70,000  | 80,000  | 90,000  | 100,000 |
| 6,000                     | 72,000  | 84,000  | 96,000  | 108,000 | 120,000 |
| 7,000                     | 84,000  | 98,000  | 112,000 | 126,000 | 140,000 |
| 8,000                     | 96,000  | 112,000 | 128,000 | 144,000 | 160,000 |

| **Ô giá trị P/E sensitivity:** Target Price_ij = EPS_FY1_i x Target P/E_j |
|---------------------------------------------------------------------------|

## 6.4. EV/EBITDA sensitivity

| **Enterprise Value:** EV = Market Capitalization + Total Interest-bearing Debt + Preferred Equity + Minority Interest - Cash & Short-term Investments |
|-------------------------------------------------------------------------------------------------------------------------------------------------------|

| **Target EV:** Target EV = EBITDA_FY1 x Target EV/EBITDA |
|----------------------------------------------------------|

| **Equity Value từ EV/EBITDA:** Equity Value = Target EV - Net Debt + Non-operating Assets - Minority Interest |
|---------------------------------------------------------------------------------------------------------------|

| **Target Price EV/EBITDA:** Target Price_EVEBITDA = Equity Value / Diluted Shares Outstanding |
|-----------------------------------------------------------------------------------------------|

| **EBITDA_FY1 \\ EV/EBITDA** | **8x**   | **9x**   | **10x**  | **11x**  | **12x**  |
|-----------------------------|----------|----------|----------|----------|----------|
| 900                         | EV/Price | EV/Price | EV/Price | EV/Price | EV/Price |
| 1,000                       | EV/Price | EV/Price | EV/Price | EV/Price | EV/Price |
| 1,100                       | EV/Price | EV/Price | EV/Price | EV/Price | EV/Price |
| 1,200                       | EV/Price | EV/Price | EV/Price | EV/Price | EV/Price |

## 6.5. P/B và P/S sensitivity

| **BVPS:** BVPS = Equity attributable to common shareholders / Shares Outstanding |
|----------------------------------------------------------------------------------|

| **Target Price P/B:** Target Price_PB = BVPS_FY1 x Target P/B |
|---------------------------------------------------------------|

| **Sales per Share:** SPS = Revenue_FY1 / Shares Outstanding |
|-------------------------------------------------------------|

| **Target Price P/S:** Target Price_PS = SPS_FY1 x Target P/S |
|--------------------------------------------------------------|

| **Cách dùng:** P/B phù hợp hơn với ngân hàng, bảo hiểm hoặc doanh nghiệp tài sản lớn. P/S phù hợp khi lợi nhuận tạm thời thấp hoặc âm. Với cổ phiếu dược có lợi nhuận ổn định, P/E và FCFF/FCFE thường có trọng số cao hơn. |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# 7. CÁCH ĐỌC VÀ ĐÁNH GIÁ KẾT QUẢ SENSITIVITY

## 7.1. Upside, downside và margin of safety

| **Upside/Downside:** Upside = Target Price / Current Market Price - 1 |
|-----------------------------------------------------------------------|

| **Margin of Safety:** Margin of Safety = (Intrinsic Value - Current Market Price) / Intrinsic Value |
|-----------------------------------------------------------------------------------------------------|

| **Expected Return gồm cổ tức:** Expected Return = (Target Price - Current Price + Expected Dividend) / Current Price |
|----------------------------------------------------------------------------------------------------------------------|

| **Kết quả**       | **Diễn giải**              | **Hành động**                                                  |
|-------------------|----------------------------|----------------------------------------------------------------|
| Upside \> 20%     | Có dư địa tăng giá đáng kể | Kiểm tra lại giả định nhạy nhất trước khi kết luận             |
| Upside 5%-20%     | Dư địa vừa phải            | So sánh với rủi ro và chi phí cơ hội                           |
| Upside -5% đến 5% | Gần fair value             | Không nên khuyến nghị mạnh                                     |
| Downside \> 10%   | Rủi ro định giá            | Xem xét giảm khuyến nghị hoặc yêu cầu margin of safety cao hơn |

## 7.2. Đo mức độ nhạy của biến đầu vào

| **Absolute Sensitivity:** Impact = Output_new - Output_base |
|-------------------------------------------------------------|

| **Percentage Sensitivity:** Impact % = Output_new / Output_base - 1 |
|---------------------------------------------------------------------|

| **Elasticity:** Elasticity = (% Change in Output) / (% Change in Input) |
|-------------------------------------------------------------------------|

| **Mức elasticity** | **Đánh giá**             | **Ý nghĩa**                                   |
|--------------------|--------------------------|-----------------------------------------------|
| \< 0.5x            | Ít nhạy                  | Biến không phải driver chính                  |
| 0.5x - 1.5x        | Nhạy vừa                 | Cần theo dõi nhưng không phải rủi ro lớn nhất |
| \> 1.5x            | Rất nhạy                 | Cần giải thích rõ và có nguồn cho giả định    |
| Âm mạnh            | Tác động ngược chiều lớn | Ví dụ WACC tăng làm valuation giảm mạnh       |

## 7.3. Cách kết luận sau sensitivity

- Không chỉ ghi “giá mục tiêu là X”; phải ghi vùng giá hợp lý, ví dụ 95,000 - 120,000 VND/cp.

- Nêu biến có tác động lớn nhất: WACC, Re, terminal growth, EBIT margin, EPS forecast hoặc target P/E.

- Nếu Base case chỉ hợp lý trong một vùng giả định rất hẹp, confidence phải giảm.

- Nếu Bear case vẫn cao hơn giá thị trường, margin of safety mạnh hơn.

- Nếu Bull case mới có upside còn Base gần fair value, không nên kết luận cổ phiếu hấp dẫn.

# 8. TEMPLATE EXCEL CHO SENSITIVITY

Các công thức dưới đây có thể đưa trực tiếp vào Excel. Tên ô chỉ mang tính minh họa và nên thay bằng named ranges trong model thực tế.

| **Mục tiêu**               | **Công thức Excel mẫu**                                                                                   |
|----------------------------|-----------------------------------------------------------------------------------------------------------|
| FCFF từ CFO                | =CFO + Interest_Expense\*(1-Tax_Rate) + CAPEX_CFS                                                         |
| FCFE từ CFO                | =CFO + CAPEX_CFS + Net_Borrowing                                                                          |
| PV dòng tiền               | =FCF_t/(1+Discount_Rate)^t                                                                                |
| Terminal value             | =IF(Discount_Rate\<=Terminal_Growth,"INVALID",FCF_n\*(1+Terminal_Growth)/(Discount_Rate-Terminal_Growth)) |
| Target DCF 60/40           | =0.6\*Price_FCFF + 0.4\*Price_FCFE                                                                        |
| Upside                     | =Target_Price/Current_Price-1                                                                             |
| Forward P/E target         | =EPS_FY1\*Target_PE                                                                                       |
| EV/EBITDA target price     | =(EBITDA_FY1\*Target_EV_EBITDA-Net_Debt+NonOperatingAssets-MinorityInterest)/Shares                       |
| Terminal weight            | =PV_Terminal_Value/Enterprise_Value                                                                       |
| Valuation gap FCFF vs FCFE | =Price_FCFF/Price_FCFE-1                                                                                  |

# 9. CHECKLIST KIỂM TOÁN CHO AI AGENT

| **Checkpoint**      | **Câu hỏi kiểm tra**                                   | **Nếu lỗi thì xử lý**          |
|---------------------|--------------------------------------------------------|--------------------------------|
| Phương pháp         | Có tách rõ FCFF dùng WACC và FCFE dùng Re không?       | Dừng xuất target price         |
| CAPEX sign          | CAPEX CFS âm có bị trừ thêm lần nữa không?             | Chuẩn hóa CAPEX trước khi tính |
| Terminal condition  | WACC \> g và Re \> g chưa?                             | Báo INVALID                    |
| Terminal weight     | PV terminal value có vượt 70% EV không?                | Gắn cảnh báo độ nhạy cao       |
| Peer group          | Có peer thực tế và loại outlier chưa?                  | Không dùng target multiple     |
| Trailing vs forward | P/E đang dùng EPS TTM hay EPS forecast?                | Ghi nhãn lại rõ ràng           |
| Multiple bridge     | EV/EBITDA có bridge EV về equity value không?          | Bổ sung net debt và shares     |
| Scenario            | Bear/Base/Bull có nhất quán với narrative không?       | Không dùng scenario rời rạc    |
| Market price        | Giá thị trường và số cổ phiếu có cùng thời điểm không? | Cập nhật snapshot              |
| Warnings            | warnings có rỗng dù còn giả định default không?        | Bắt buộc tạo warning           |

# 10. QUY TẮC CẢNH BÁO ĐỎ

| **Dấu hiệu**                                | **Mức độ**  | **Thông điệp cảnh báo nên xuất hiện**                 |
|---------------------------------------------|-------------|-------------------------------------------------------|
| WACC \<= g hoặc Re \<= g                    | Critical    | Mô hình terminal value không hợp lệ                   |
| CAPEX âm bị trừ trong công thức CFO - CAPEX | Critical    | Sai quy ước dấu CAPEX, valuation có thể bị thổi phồng |
| PV terminal value \> 70% EV                 | High        | Kết quả phụ thuộc mạnh vào giả định dài hạn           |
| FCFF và FCFE lệch trên 25%                  | High        | Cần audit Net Borrowing, Net Debt, CAPEX và NWC       |
| Target P/E không có peer group              | High        | Relative valuation chưa đủ cơ sở                      |
| EPS âm nhưng vẫn tính P/E                   | Medium/High | P/E không có ý nghĩa, dùng P/S hoặc EV/Sales thay thế |
| EV/EBITDA âm                                | Medium/High | Không dùng multiple này cho valuation chính           |
| Base case nằm ngoài toàn bộ peer range      | Medium      | Cần giải thích premium/discount đặc biệt              |

# 11. MẪU DIỄN GIẢI KẾT QUẢ

Khi viết báo cáo, không nên chỉ đưa bảng sensitivity. Cần viết phần diễn giải ngắn để người đọc hiểu biến nào là trọng yếu và kết luận có đáng tin cậy không.

| **Tình huống**                   | **Mẫu diễn giải**                                                                                                                                                                                   |
|----------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| DCF nhạy với WACC                | Kết quả định giá thay đổi mạnh khi WACC tăng/giảm 1 điểm %. Điều này cho thấy phần lớn giá trị đến từ terminal value, do đó giả định WACC cần được kiểm chứng bằng dữ liệu thị trường và peer beta. |
| FCFF và FCFE lệch lớn            | Chênh lệch giữa FCFF và FCFE phản ánh tác động của net borrowing và cấu trúc vốn. Cần kiểm tra lại lịch vay/trả nợ, net debt và dòng tiền cho cổ đông trước khi dùng target price cuối cùng.        |
| P/E sensitivity                  | Giá mục tiêu theo P/E phụ thuộc đồng thời vào EPS forecast và target multiple. Nếu EPS FY1 không chắc chắn, nên trình bày vùng giá thay vì một con số điểm.                                         |
| Peer multiple cao hơn thị trường | Việc áp dụng premium so với peer cần được giải thích bằng ROE, tăng trưởng lợi nhuận, biên lợi nhuận, vị thế ngành hoặc chất lượng quản trị.                                                        |

# 12. KẾT LUẬN THỰC HÀNH

Sensitivity analysis là bước bắt buộc để biến mô hình định giá từ một phép tính điểm thành một vùng giá có kiểm soát rủi ro. Với mô hình 60% FCFF + 40% FCFE, người phân tích cần kiểm tra riêng FCFF, riêng FCFE, sau đó kiểm tra mức phân kỳ giữa hai phương pháp trước khi đưa ra target price DCF cuối cùng.

| **Nguyên tắc cuối cùng:** Một target price đáng tin cậy không phải là con số cao nhất hoặc đẹp nhất, mà là con số vẫn hợp lý sau khi bị thử sức bởi các giả định bất lợi. |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# PHỤ LỤC: BẢNG TÓM TẮT CÔNG THỨC

| **Nhóm**         | **Công thức**                                                                   |
|------------------|---------------------------------------------------------------------------------|
| FCFF             | FCFF = EBIT x (1 - Tax) + D&A - CAPEX - Delta NWC                               |
| FCFF từ CFO      | FCFF = CFO + Interest x (1 - Tax) - CAPEX_positive                              |
| FCFE             | FCFE = NI + D&A - CAPEX - Delta NWC + Net Borrowing                             |
| FCFE từ CFO      | FCFE = CFO - CAPEX_positive + Net Borrowing                                     |
| FCFF Value       | EV = Sum\[FCFF/(1+WACC)^t\] + TV/(1+WACC)^n                                     |
| FCFE Value       | Equity Value = Sum\[FCFE/(1+Re)^t\] + TV/(1+Re)^n                               |
| Terminal FCFF    | TV = FCFF_n x (1+g)/(WACC-g)                                                    |
| Terminal FCFE    | TV = FCFE_n x (1+g)/(Re-g)                                                      |
| Combined DCF     | Target Price = 0.6 x Price_FCFF + 0.4 x Price_FCFE                              |
| Trailing P/E     | Current Price / EPS_TTM                                                         |
| Forward P/E      | Current Price / EPS_FY1                                                         |
| Target P/E Price | EPS_FY1 x Target Forward P/E                                                    |
| EV/EBITDA Price  | (EBITDA x Multiple - Net Debt + NonOperatingAssets - MinorityInterest) / Shares |
| Upside           | Target Price / Current Price - 1                                                |
| Elasticity       | (% Change in Output) / (% Change in Input)                                      |
