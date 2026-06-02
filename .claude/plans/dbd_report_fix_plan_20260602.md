# Kế hoạch debug và chuẩn hóa báo cáo Equity Research
**Phiên bản: 1.0 — 2026-06-02**
**Phạm vi: Áp dụng cho mọi ticker trong universe Vietnam Pharma**
**Tài liệu tham chiếu gốc:**
- `danh_gia_tien_do_chat_luong_gen_bao_cao_hien_tai.md` — checklist lỗi kiểm toán
- `BCTC_DP3_converted.md` — dữ liệu mẫu minh họa (ticker DP3/DBD)

> **Cách dùng tài liệu này:** Mỗi phần đều gồm (1) mô tả lỗi tổng quát, (2) công thức/quy tắc chuẩn, (3) ví dụ minh họa từ case DBD/DP3. Khi debug cho một ticker cụ thể, thay số liệu thực vào các công thức.

---

## 0. Bức tranh tổng quan — Các nhóm lỗi cần kiểm soát

Mọi báo cáo equity research khi được sinh ra cần kiểm tra theo 4 tầng:

| Tầng | Nhóm lỗi | Mức độ tối thiểu phải sạch |
|---|---|---|
| T1 | Dữ liệu đầu vào sai (metadata, số CP, sàn) | Phải sạch trước khi tính bất cứ thứ gì |
| T2 | Công thức tài chính sai (CAPEX, FCF, DCF bridge) | Phải sạch trước khi xuất target price |
| T3 | Cấu trúc định giá thiếu (TV, FCFE, blend, sensitivity) | Phải sạch trước khi publish |
| T4 | Trình bày và QA (citation, chart, narrative, units) | Phải sạch trước khi gửi khách |

Một báo cáo có thể bị block ở bất kỳ tầng nào. Không được nhảy cóc.

---

## 1. Tầng T1 — Kiểm tra dữ liệu đầu vào

### 1.1 Quy tắc tổng quát

**Mọi giá trị đầu vào phải có nguồn cụ thể** trước khi được dùng trong tính toán. Không chấp nhận "lấy từ API" hay "theo hệ thống" mà không nêu rõ tên nguồn, ngày lấy, và phiên bản.

| Trường | Nguồn bắt buộc | Kiểm tra |
|---|---|---|
| Số CP lưu hành | VSD hoặc CBTT HoSE/HNX tại ngày định giá | Phải khớp với Vốn điều lệ ÷ mệnh giá 10,000 VND **hoặc** có giải thích chênh lệch |
| Sàn niêm yết | Website HoSE/HNX hoặc CBTT chính thức | HoSE: HSX, HNX: HNX, UpCoM: UpCoM |
| Giá cổ phiếu | Giá đóng cửa ngày định giá — ghi rõ ngày | Không dùng giá tùy tiện hoặc không có ngày |
| Vốn hóa thị trường | = Giá đóng cửa × Số CP lưu hành | Phải tự tính, không lấy số tổng hợp từ nguồn thứ cấp |
| Tổng tài sản / Vốn CSH | BCTC kiểm toán gần nhất (Q4 hoặc năm) | Phân biệt rõ BCTC hợp nhất vs. riêng lẻ |

**Lỗi thường gặp ở T1:**

- Dùng số CP từ BCTC cũ chưa cập nhật phát hành thêm (bonus share, rights issue, ESOP).
  > *Ví dụ DBD: BCTC ghi Vốn ĐL = 215 tỷ → 21.5 triệu CP, nhưng thực tế tại ngày định giá là ~94 triệu CP do phát hành thêm sau đó. Tất cả EPS, BVPS, target price/share tính từ 21.5M đều sai.*

- Lấy vốn hóa từ nguồn tổng hợp (cafef, vndirect) mà không kiểm tra ngày snapshot.

- Dùng BCTC riêng lẻ để tính ROE nhưng lại dùng số CP hợp nhất để tính EPS.

**Cách kiểm tra nhanh:**
```
Market_Cap_check = Price_ref × Shares_outstanding
nếu abs(Market_Cap_check - Market_Cap_reported) / Market_Cap_check > 2%:
    → FAIL: shares hoặc price không khớp, phải điều tra
```

---

## 2. Tầng T2 — Kiểm tra công thức tài chính

### 2.1 CAPEX — Lỗi dấu và lỗi nguồn tính

**Quy tắc:**

Phải dùng đúng một trong hai quy ước, nhất quán cho toàn bộ lịch sử và forecast:

| Quy ước | Công thức | Khi nào dùng |
|---|---|---|
| **CAPEX_positive** (số dương = tiền chi ra) | `FCF = CFO - CAPEX_positive` | Khi tự tính từ thay đổi tài sản |
| **CAPEX_CFS_signed** (số âm = tiền ra, như trong CFS) | `FCF = CFO + CAPEX_CFS_signed` | Khi lấy trực tiếp từ dòng tiền đầu tư |

**Không bao giờ** dùng `CFO - CAPEX_CFS_signed` khi CAPEX_CFS_signed < 0 (sẽ cộng thêm thay vì trừ).

**Cách tính CAPEX_positive từ bảng cân đối kế toán (phương pháp ưu tiên khi CFS thiếu dòng riêng):**
```
CAPEX_positive = ΔGross_TangiblePPE + ΔIntangible_Gross + ΔWIP + Gross_Disposed
               = (Gross_PPE_t - Gross_PPE_t-1)
               + (Intangible_Gross_t - Intangible_Gross_t-1)
               + (WIP_t - WIP_t-1)
               + Gross_value_of_disposed_assets

Nếu kết quả âm (thanh lý > đầu tư mới): CAPEX_positive = 0, ghi note "net asset disposal year"
```

**Kiểm tra chéo:**
```
CAPEX_positive ≈ abs(CFS_investing_line_CAPEX)
nếu chênh > 10%: kiểm tra thanh lý tài sản, điều chỉnh WIP, hoặc sai dòng
```

> *Ví dụ DBD/DP3: BCTC 2025 cho thấy:*
> - *Gross tangible PPE tăng từ 236.3 tỷ lên 238.2 tỷ → ΔGross = +1.9 tỷ*
> - *WIP tăng từ 0.12 tỷ lên 3.86 tỷ → Δ = +3.7 tỷ*
> - *CAPEX_positive 2025 ≈ 5.7 tỷ (thay vì -5.9 tỷ âm mà model đang dùng)*
> - *Model hiện dùng thay đổi khấu hao lũy kế thay vì gross PP&E → cho ra CAPEX âm → FCF bị thổi phồng*

**Kiểm tra bảng CAPEX sau khi fix:**

| Cột | Giá trị hợp lệ | Cờ đỏ |
|---|---|---|
| CAPEX_positive | ≥ 0 cho mọi năm | Bất kỳ giá trị âm nào |
| CAPEX/Revenue | 0%–30% cho pharma VN | >30%: cần giải thích; <0%: lỗi |
| CAPEX vs Depreciation | CAPEX ≈ D&A ± 50% ở trạng thái ổn định | CAPEX << D&A kéo dài → tài sản đang bị mòn không được tái đầu tư |

---

### 2.2 FCF — Quy ước nhất quán giữa lịch sử và forecast

**Quy tắc:** Cùng một quy ước phải được áp dụng cho tất cả các năm — không trộn công thức giữa năm thực tế (actual) và năm dự phóng (forecast).

**Kiểm tra chéo bắt buộc:**
```
FCF_check = CFO_t - CAPEX_positive_t
nếu abs(FCF_reported_t - FCF_check_t) / abs(FCF_check_t) > 5% cho bất kỳ năm nào:
    → FAIL: FCF không reconcile với CFO và CAPEX
```

> *Ví dụ DBD: báo cáo cũ dùng `CFO + CAPEX` cho 2024A và 2025A (CAPEX âm trong CFS), nhưng `CFO - CAPEX` cho 2026F trở đi. Đây là mixed convention → toàn bộ FCFF lịch sử không thể so sánh được với forecast.*

---

### 2.3 FCFF — Công thức chuẩn và kiểm tra

**Công thức chuẩn:**
```
FCFF = EBIT × (1 - Tax_Rate) + D&A - CAPEX_positive - ΔNWC

ΔNWC = Operating_NWC_t - Operating_NWC_t-1
Operating_NWC = AR + Inventory + Other_Operating_CA - AP - Other_Operating_CL
(Không tính cash, ST investments, short-term loans trong NWC)

D&A = ΔAccumulated_Depreciation_t (từ gross → net PPE) + D&A_intangible
```

**Kiểm tra chéo:**
```
FCFF_from_CFO = CFO + Interest_Expense × (1 - Tax_Rate) - CAPEX_positive
nếu abs(FCFF_from_EBIT - FCFF_from_CFO) / abs(FCFF_from_EBIT) > 5%:
    → WARNING: hai phương pháp không reconcile, kiểm tra D&A và NWC
```

---

### 2.4 FCFE — Công thức chuẩn và phân biệt với FCFF

**Công thức chuẩn:**
```
FCFE = Net_Income + D&A - CAPEX_positive - ΔNWC + Net_Borrowing

Net_Borrowing = New_Debt_Issued - Principal_Debt_Repaid
             = (Debt_end - Debt_begin)  [tính từ bảng cân đối]
             hoặc lấy từ CFS financing lines
```

**Quy tắc phân biệt FCFF vs FCFE:**

| | FCFF | FCFE |
|---|---|---|
| Chiết khấu bằng | **WACC** | **Re (cost of equity)** |
| Kết quả | Enterprise Value | Equity Value trực tiếp |
| Trừ Net Debt | Có (EV → Equity Value) | **Không** (đã bao gồm trong dòng tiền) |
| Điều kiện hợp lệ | WACC > g | Re > g |

**Lỗi cực kỳ phổ biến:**
- Discount FCFE bằng WACC → overvalue nếu công ty có nợ
- Discount FCFF bằng Re → undervalue nếu công ty có nợ
- Tính Equity Value FCFE rồi lại trừ net debt thêm một lần nữa → double counting

---

### 2.5 Terminal Value — Bước hay bị bỏ quên nhất

**Công thức:**
```
TV_FCFF = FCFF_terminal × (1 + g) / (WACC - g)
TV_FCFE = FCFE_terminal × (1 + g) / (Re - g)

PV(TV_FCFF) = TV_FCFF / (1 + WACC)^N
PV(TV_FCFE) = TV_FCFE / (1 + Re)^N
```

**EV và Equity Value bridges:**
```
EV_FCFF = Σ [FCFF_t / (1+WACC)^t] + PV(TV_FCFF)   ← PHẢI bao gồm PV(TV)
Equity_Value_FCFF = EV_FCFF - Net_Debt + Non_operating_Assets - Minority_Interest
Price_FCFF = Equity_Value_FCFF / Diluted_Shares

Equity_Value_FCFE = Σ [FCFE_t / (1+Re)^t] + PV(TV_FCFE)  ← KHÔNG trừ Net Debt thêm
Price_FCFE = Equity_Value_FCFE / Diluted_Shares
```

**Kiểm tra TV weight:**
```
TV_Weight = PV(TV) / EV

nếu TV_Weight > 0.85: → CRITICAL WARNING — định giá quá phụ thuộc terminal assumption
nếu TV_Weight > 0.70: → HIGH WARNING — cần mở rộng sensitivity cho g và discount rate
```

> *Ví dụ DBD: model tính TV_FCFF = 17,692 tỷ nhưng trong hàng PV(CF), ô terminal lại chứa tổng 5 năm PV = 978 tỷ (công thức cell reference sai). EV bị tính thiếu TV → EV = 978 tỷ thay vì ~15,235 tỷ. Sai ~15.6 lần. Đây là lỗi spreadsheet điển hình: cell reference dùng SUM range thay vì ô TV.*

---

### 2.6 Net Debt — Công thức đúng

**Công thức:**
```
Net_Debt = Interest_Bearing_Debt - Cash_and_Equivalents - ST_Investments

Interest_Bearing_Debt = Vay ngắn hạn + Nợ thuê tài chính NH + Trái phiếu NH
                      + Vay dài hạn đến hạn + Vay dài hạn + Trái phiếu DH
(Không tính: phải trả nhà cung cấp, phải trả lương, thuế phải nộp → operational liabilities)

Cash_and_Equivalents = Tiền mặt + Các khoản tương đương tiền (maturity ≤ 3 tháng)
ST_Investments = Đầu tư tài chính ngắn hạn (tiền gửi có kỳ hạn, trái phiếu chính phủ ngắn hạn)
```

**Net Debt âm = Net Cash position.** Khi đó:
```
Equity_Value_FCFF = EV_FCFF - Net_Debt = EV_FCFF + abs(Net_Cash)
```
Đây là điểm cộng cho cổ đông — phải phản ánh đúng vào target price, không phải bỏ qua.

> *Ví dụ DBD 2025A:*
> - *Vay ngắn hạn = 34.3 tỷ*
> - *Tiền mặt = 4.5 tỷ*
> - *ST Investments (gửi tiết kiệm) = 471.0 tỷ*
> - *Net Debt = 34.3 - 4.5 - 471.0 = **-441.2 tỷ** (net cash lớn)*
> - *Model cũ dùng total liabilities = 133.3 tỷ thay vì net debt = -441.2 tỷ → equity value thấp hơn thực tế ~575 tỷ*

**Lưu ý đặc biệt với doanh nghiệp dược VN:** Nhiều công ty giữ tiền gửi tiết kiệm (term deposits) rất lớn → ST Investments chiếm phần lớn tài sản. Phải bao gồm trong net cash.

---

### 2.7 Equity Roll-Forward — Cổ tức phải được trừ

**Công thức:**
```
Equity_end_t = Equity_begin_t + NI_t - Dividends_Paid_t + Equity_Issuance_t - Buybacks_t ± OCI_t
```

**Kiểm tra:**
```
Equity_check_t = Equity_t-1 + NI_t - Dividends_t
nếu abs(Equity_reported_t - Equity_check_t) > threshold (ví dụ 5 tỷ):
    → kiểm tra: có equity issuance, buyback, hoặc OCI không?
    → nếu không có lý do: FAIL equity roll-forward
```

**Hậu quả nếu không trừ cổ tức:**
- Equity bị overstated → BVPS cao hơn thực tế → P/B thấp giả tạo → ROE thấp giả tạo
- Sai lệch lũy kế theo năm (mỗi năm cộng thêm một lần bằng dividend)

> *Ví dụ DBD: cổ tức trả ~62–68 tỷ/năm (2021–2025). Nếu không trừ trong forecast 5 năm, equity 2030F bị overstated khoảng 300–350 tỷ.*

---

### 2.8 Cash Sweep và Debt Schedule

**Module cash sweep bắt buộc:**
```
Cash_end_t = Cash_begin_t
           + CFO_t
           - CAPEX_positive_t
           - Dividends_Paid_t
           + New_Debt_Issued_t
           - Principal_Repaid_t
           + Equity_Issuance_t
           ± Change_in_ST_Investments_t  ← tiền gửi tiết kiệm thay đổi
           ± Other_t

Debt_end_t = Debt_begin_t + New_Debt_Issued_t - Principal_Repaid_t

Net_Debt_end_t = Debt_end_t - Cash_end_t - ST_Investments_end_t
```

**Kiểm tra DebtFlowMismatch:**
```
ΔNet_Debt_t = Net_Debt_end_t - Net_Debt_end_t-1
Expected_ΔNet_Debt = Net_Borrowing_t - ΔCash_t - ΔST_Investments_t

nếu abs(ΔNet_Debt_t - Expected_ΔNet_Debt_t) > threshold:
    → WARNING: net debt movement không reconcile với cash flows
    → cần kiểm tra equity issuance, asset sales, hoặc các dòng tiền khác
```

**Khi narrative có sự kiện phát hành cổ phiếu (equity issuance):**
- Phải mô phỏng số CP mới phát hành
- Phải tính EPS pha loãng sau phát hành
- Không được để narrative nói "phát hành 1,100 tỷ" mà model không phản ánh

---

## 3. Tầng T3 — Kiểm tra cấu trúc định giá

### 3.1 Blended DCF 60% FCFF / 40% FCFE

**Yêu cầu tối thiểu:**

| Module | Bắt buộc |
|---|---|
| FCFF forecast (N năm) | Có |
| TV_FCFF = FCFF_N × (1+g) / (WACC-g) | Có |
| PV(FCFF) + PV(TV_FCFF) = EV_FCFF | Có |
| Equity_Value_FCFF = EV_FCFF - Net_Debt | Có |
| Price_FCFF = Equity_Value_FCFF / Diluted_Shares | Có |
| FCFE forecast (N năm) | Có |
| TV_FCFE = FCFE_N × (1+g) / (Re-g) | Có |
| Equity_Value_FCFE = PV(FCFE) + PV(TV_FCFE) | Có — **không trừ Net Debt** |
| Price_FCFE = Equity_Value_FCFE / Diluted_Shares | Có |
| Target_Price = 0.60 × Price_FCFF + 0.40 × Price_FCFE | Có |

**Cảnh báo FCFF/FCFE divergence:**
```
nếu abs(Price_FCFF / Price_FCFE - 1) > 25%:
    → HIGH WARNING: hai phương pháp cho kết quả khác nhau >25%
    → kiểm tra: net borrowing, net debt, CAPEX, NWC
    → phải giải thích trong báo cáo tại sao diverge
```

---

### 3.2 Sensitivity Analysis — Yêu cầu tối thiểu

**3 bảng bắt buộc:**

**Bảng 1: FCFF DCF — WACC × Terminal Growth Rate**
```
Cột: WACC ∈ {base-150bp, base-75bp, base, base+75bp, base+150bp}
Hàng: g ∈ {1%, 2%, base_g, base_g+1%, base_g+2%}
Ô: Price_FCFF tính lại với WACC và g đó

Điều kiện hợp lệ: WACC > g (nếu không: ghi "INVALID")
```

**Bảng 2: FCFE DCF — Re × Terminal Growth Rate**
```
Cột: Re ∈ {base-150bp, base-75bp, base, base+75bp, base+150bp}
Hàng: g ∈ {1%, 2%, base_g, base_g+1%, base_g+2%}
Ô: Price_FCFE tính lại

Điều kiện hợp lệ: Re > g
```

**Bảng 3: Relative Valuation — EPS_FY1 × Forward P/E**
```
Cột: P/E ∈ {peer_median-5x, peer_median-3x, peer_median, peer_median+3x, peer_median+5x}
Hàng: EPS_FY1 scenario ∈ {Bear, Mild Bear, Base, Mild Bull, Bull}
Ô: Target Price = EPS × P/E
```

**Break-even analysis (khuyến khích):**
```
Break_even_WACC: WACC tại đó Price_FCFF = Current_Market_Price
Break_even_PE:   P/E tại đó Target_Price_PE = Current_Market_Price
```

**Lỗi thường gặp trong sensitivity:**
- Dùng absolute cell reference ($A$1) thay vì mixed/relative → tất cả ô cho cùng kết quả
- Không bao gồm TV trong EV khi tính lại → sensitivity không phản ánh thay đổi thực
- Grid quá hẹp (chỉ ±25bp) → không capture được rủi ro thực

> *Ví dụ DBD: bảng sensitivity hiện tại trả về 40,489.73 cho MỌI tổ hợp WACC và g. Đây chính xác là lỗi absolute reference.*

---

### 3.3 Peer Group và Định giá tương đối

**Yêu cầu tối thiểu:**

- Ít nhất 3 công ty cùng ngành, cùng sàn hoặc cùng khu vực
- Mỗi peer phải có: P/E trailing, P/E forward, EV/EBITDA, P/B, ROE, net margin
- Dùng **median** (không phải mean) khi sample nhỏ hoặc có outlier
- Áp outlier filter: loại peer có EPS ≤ 0, EBITDA ≤ 0, hoặc P/E > 50x do one-off

**EV/EBITDA bridge:**
```
Target_EV = EBITDA_FY1 × Target_EV/EBITDA_Multiple
Equity_Value_EVEBITDA = Target_EV - Net_Debt + Non_operating_Assets - Minority_Interest
Price_EVEBITDA = Equity_Value_EVEBITDA / Diluted_Shares
```

**Premium/discount rationale:** Phải giải thích tại sao ticker được định giá cao hơn hoặc thấp hơn peer median, dựa trên ít nhất một trong: ROE tương đối, tăng trưởng tương đối, margin, thanh khoản, governance.

---

### 3.4 Valuation Bridge — Bắt buộc hiển thị

Người đọc phải có thể tái lập target price từ bảng này mà không cần mở mô hình:

```
╔══════════════════════════════════════════════════════╗
║  FCFF Bridge                                         ║
║  Σ PV(FCFF forecast):              [X] tỷ VND        ║
║  + PV(Terminal Value FCFF):        [Y] tỷ VND        ║
║  = Enterprise Value:               [X+Y] tỷ VND      ║
║  - Net Debt (năm forecast đầu):    [Z] tỷ VND        ║
║    (âm = cộng net cash vào EV)                       ║
║  - Minority Interest:              [MI] tỷ VND       ║
║  + Non-operating Assets:           [NOA] tỷ VND      ║
║  = Equity Value (FCFF):            [EV_eq] tỷ VND    ║
║  ÷ Diluted Shares:                 [N] triệu CP      ║
║  = Price_FCFF:                     [P1] VND/CP       ║
║                                                      ║
║  FCFE Bridge                                         ║
║  Σ PV(FCFE forecast):              [A] tỷ VND        ║
║  + PV(Terminal Value FCFE):        [B] tỷ VND        ║
║  = Equity Value (FCFE):            [A+B] tỷ VND      ║
║  ÷ Diluted Shares:                 [N] triệu CP      ║
║  = Price_FCFE:                     [P2] VND/CP       ║
║                                                      ║
║  Blended Target Price:                               ║
║  = 60% × [P1] + 40% × [P2] = [TP] VND/CP            ║
║  Upside vs. Current Price: [TP/P0 - 1]%              ║
╚══════════════════════════════════════════════════════╝
```

---

## 4. Tầng T4 — Kiểm tra trình bày và QA

### 4.1 Cấu trúc báo cáo bắt buộc

| # | Section | Nội dung tối thiểu | Từ tối thiểu |
|---|---|---|---|
| 1 | Tóm tắt đầu tư | Recommendation box, target price, upside, key thesis (3 điểm), key risk (2 điểm) | 200 |
| 2 | Tổng quan doanh nghiệp | Lịch sử, ngành nghề, cơ cấu sản phẩm/dịch vụ, vị thế thị trường | 300 |
| 3 | Bối cảnh ngành và thị trường | Quy mô thị trường, tăng trưởng ngành, regulatory, competitive dynamics | 300 |
| 4 | Phân tích tài chính | 5 năm lịch sử, key ratios, trends, nhận định từng chỉ tiêu, chart analysis | 350 |
| 5 | Định giá | DCF bridge, sensitivity, peer comparison, target price reconciliation | 350 |
| 6 | Luận điểm đầu tư | Bull/Base/Bear drivers cụ thể, catalysts với timeline | 300 |
| 7 | Rủi ro | Bảng rủi ro có impact × probability, link với driver định lượng | 250 |
| 8 | Kết luận | Restate recommendation có điều kiện, horizon | 150 |
| 9 | Phụ lục | Assumptions table, valuation tables, citation map, eval summary | — |

### 4.2 Biểu đồ — Yêu cầu tối thiểu

**6 biểu đồ bắt buộc cho báo cáo full:**

| # | Biểu đồ | Loại | Dữ liệu | Section |
|---|---|---|---|---|
| C1 | Doanh thu & Gross Margin N năm | Bar + Line combo | Revenue bar, Gross margin % line | 4 |
| C2 | Cơ cấu chi phí (năm gần nhất) | Stacked bar hoặc Waterfall | COGS, Selling, Admin, EBIT | 4 |
| C3 | Tỷ suất sinh lợi N năm | Multi-line | ROE, ROA, Net margin | 4 |
| C4 | FCFF và LNST N năm | Bar grouped hoặc Bar + Line | FCFF (bar), NI (line) | 4 |
| C5 | Sensitivity heatmap | Color-coded table | WACC × g → Price_FCFF | 5 |
| C6 | Peer Comparison | Horizontal bar hoặc Scatter | P/E vs ROE hoặc P/E vs Growth | 5 |

**Quy tắc kỹ thuật:**
- Mỗi biểu đồ phải có đoạn phân tích liền sau (~100–150 chữ): xu hướng, điểm nổi bật, ý nghĩa đầu tư
- Trục Y phải ghi đơn vị: "tỷ VND", "%", "VND/CP"
- Tooltip khi hover hiển thị giá trị chính xác và đơn vị
- Màu sắc nhất quán trong toàn bộ báo cáo

### 4.3 Citation — Quy tắc bắt buộc

**Mẫu citation chuẩn:**

```
[CT-IS-YYYY]   BCTC kiểm toán năm YYYY, [Tên công ty], Báo cáo KQHĐKD.
               Kiểm toán bởi [Tên công ty kiểm toán].
[CT-BS-YYYY]   BCTC kiểm toán năm YYYY, [Tên công ty], Bảng CĐKT.
[CT-CF-YYYY]   BCTC kiểm toán năm YYYY, [Tên công ty], Báo cáo LCTT.
[CT-AR-YYYY]   Báo cáo thường niên YYYY, [Tên công ty].
[CT-AGM-YYYY]  Nghị quyết ĐHĐCĐ thường niên YYYY, [Tên công ty], ngày DD/MM/YYYY.
[CT-EX-DATE]   Công bố thông tin HoSE/HNX ngày DD/MM/YYYY — [Tiêu đề CBTT].
[CT-MKT-DATE]  Dữ liệu thị trường HoSE/HNX, ngày DD/MM/YYYY. Giá đóng cửa.
[CT-PEER-XX]   BCTC kiểm toán [Tên peer XX], năm tài chính YYYY.
[CT-MACRO-SRC] [Tên nguồn macro/ngành], [Tên báo cáo], [Năm xuất bản].
```

**Mapping claim → citation — bắt buộc:**

| Loại claim | Citation bắt buộc |
|---|---|
| Doanh thu / Lợi nhuận / Tổng tài sản năm X | [CT-IS-X] hoặc [CT-BS-X] |
| Vốn hóa thị trường | [CT-MKT-DATE] × [CT-EX-DATE] (số CP) |
| EPS, BVPS, số CP lưu hành | [CT-BS-YYYY] + [CT-EX-DATE] |
| Kế hoạch doanh nghiệp, mục tiêu năm tới | [CT-AGM-YYYY] hoặc [CT-AR-YYYY] |
| WACC assumption: Rf | Lãi suất TPCP từ [nguồn cụ thể, ngày] |
| WACC assumption: Beta | [Tên data provider], ngày tính |
| Peer multiple | [CT-PEER-XX] cho từng peer |
| Số liệu ngành | [CT-MACRO-SRC] |
| Ước tính analyst | Ghi rõ "Ước tính analyst, dựa trên [assumption]" |

**Không được viết:** "Nguồn: API", "Nguồn: Hệ thống", "Nguồn: Dữ liệu thị trường" mà không có tên nguồn cụ thể và ngày.

### 4.4 Metadata và QA header

**Phải có trong mọi báo cáo:**

```html
<!-- Header metadata bắt buộc -->
Ticker:          [TICKER]
Sàn niêm yết:   [HoSE / HNX / UpCoM]
Ngày định giá:  DD/MM/YYYY
Giá tham chiếu: X,XXX VND (đóng cửa ngày DD/MM/YYYY, nguồn: HoSE)
Số CP lưu hành: XX,XXX,XXX CP (nguồn: [CBTT ngày DD/MM/YYYY])
Vốn hóa:        X,XXX tỷ VND
Khuyến nghị:    [MUA / TRUNG LẬP / BÁN]  ← CSS class phải match
Target price:   X,XXX VND/CP (12 tháng)
Upside:         +/-X.X%

Trạng thái:     [DRAFT — Chưa được analyst phê duyệt] ← bắt buộc cho đến khi approve
```

**CSS class khuyến nghị phải đồng bộ với nội dung:**
```css
.recommendation-buy    { background: #e6f4ea; border-left: 4px solid #34a853; }
.recommendation-hold   { background: #fef7e0; border-left: 4px solid #fbbc04; }
.recommendation-sell   { background: #fce8e6; border-left: 4px solid #ea4335; }
/* Không dùng .recommendation-review cho báo cáo có nội dung MUA/BÁN/TRUNG LẬP */
```

### 4.5 Nhất quán narrative vs. bảng số

**Kiểm tra bắt buộc:**

| Loại kiểm tra | Quy tắc |
|---|---|
| Số trong narrative vs. bảng | Sai lệch ≤ 1 tỷ sau rounding (ví dụ: "438 tỷ" vs. bảng "437.9 tỷ" → OK) |
| Kế hoạch doanh nghiệp vs. forecast | Nếu forecast khác kế hoạch: phải giải thích (ví dụ "base case chiết khấu 5% so với kế hoạch do rủi ro thực thi") |
| Upside/downside vs. recommendation | Upside > 15%: không nên là BÁN; Downside > 10%: không nên là MUA |
| Đơn vị | Nhất quán trong toàn bộ báo cáo: chọn "tỷ VND" hoặc "triệu VND", không trộn lẫn |

---

## 5. Quy trình debug chuẩn hóa khi nhận báo cáo mới

```
Bước 1: Load BCTC gốc (IS, BS, CF) — xác nhận ticker, sàn, năm báo cáo
Bước 2: T1 check — số CP, giá, sàn, vốn hóa
Bước 3: Tính lại CAPEX từ gross PP&E → so sánh với model
Bước 4: Tính lại FCFF, FCFE từ công thức chuẩn → so sánh với model
Bước 5: Kiểm tra TV có được đưa vào EV không → xem cell PV(TV)
Bước 6: Kiểm tra Net Debt = interest-bearing debt - cash - ST investments
Bước 7: Kiểm tra equity roll-forward (cổ tức có được trừ không)
Bước 8: Kiểm tra cash sweep reconcile
Bước 9: Kiểm tra sensitivity grid có thực sự thay đổi theo biến không
Bước 10: Kiểm tra T4 — citation, chart, narrative consistency, CSS class
```

**Output của debug session:**

```yaml
status: PASS | WARN | FAIL | INVALID
ticker: [TICKER]
valuation_date: [DATE]
t1_data_input: PASS / FAIL (+ list lỗi)
t2_formula:    PASS / WARN / FAIL (+ list lỗi + công thức sai cụ thể)
t3_structure:  PASS / WARN / FAIL (+ module nào thiếu)
t4_presentation: PASS / WARN / FAIL (+ list QA items)
blocking_issues: [list critical issues]
target_price_publishable: yes / no
recommended_next_action: [cụ thể 1 bước]
```

---

## 6. Files cần tạo hoặc sửa (áp dụng khi implement fix)

| File | Action | Lý do |
|---|---|---|
| `backend/analytics/capex.py` | Tạo mới | Hàm tính CAPEX_positive từ gross PP&E |
| `backend/analytics/dcf.py` | Sửa | Đảm bảo PV(TV) được cộng vào EV; tách FCFF/FCFE bridge rõ ràng |
| `backend/analytics/sensitivity.py` | Sửa | Fix relative reference bug; thêm break-even analysis |
| `backend/analytics/peer_valuation.py` | Tạo mới | Peer group, outlier filter, median multiple |
| `backend/analytics/cash_sweep.py` | Tạo mới | Cash sweep, debt schedule, DebtFlowMismatch check |
| `backend/reporting/section_builder.py` | Sửa | Đảm bảo ≥250 chữ/section, chart analysis text |
| `backend/reporting/templates/report.html.j2` | Sửa | Valuation bridge box, CSS class sync, citation appendix, DRAFT banner |
| `backend/reporting/chart_generator.py` | Sửa | 6 biểu đồ với đơn vị và tooltip chuẩn |
| `backend/evaluation/numeric_consistency.py` | Sửa | Thêm checks: TV in EV, CAPEX positive, Net Debt formula, equity roll-forward |
| `backend/evaluation/citation_coverage.py` | Sửa | Reject citation type "API" hoặc "Hệ thống" |

---

## 7. Phụ lục — Công thức kiểm tra nhanh

| Nhóm | Công thức | Cờ đỏ nếu |
|---|---|---|
| CAPEX | `CAPEX_positive = ΔGross_PPE + ΔIntangible + ΔWIP` | Kết quả âm |
| FCF (positive CAPEX) | `FCF = CFO - CAPEX_positive` | Dùng CFO + CAPEX_positive |
| FCF (CFS signed) | `FCF = CFO + CAPEX_CFS_signed` | Dùng CFO - CAPEX_CFS_signed khi CAPEX_CFS_signed < 0 |
| FCFF | `EBIT(1-t) + D&A - CAPEX_positive - ΔNWC` | CAPEX âm; WACC ≤ g |
| FCFE | `NI + D&A - CAPEX_positive - ΔNWC + Net_Borrowing` | Re ≤ g; trừ Net Debt lần 2 |
| EV_FCFF | `Σ PV(FCFF) + PV(TV_FCFF)` | PV(TV) = 0 hoặc = Σ PV(FCFF) |
| Equity_FCFF | `EV_FCFF - Net_Debt` | Dùng Total_Liabilities thay vì Net_Debt |
| Equity_FCFE | `Σ PV(FCFE) + PV(TV_FCFE)` | Trừ Net_Debt thêm lần nữa |
| Net Debt | `Interest_Debt - Cash - ST_Investments` | Không trừ ST_Investments |
| Equity Roll | `Equity_t = Equity_{t-1} + NI_t - Div_t` | Thiếu Div_t trong forecast |
| Blend | `TP = 0.60 × Price_FCFF + 0.40 × Price_FCFE` | Blend EV thay vì Price |
| TV Weight | `PV(TV) / EV` | > 85% (critical), > 70% (high warn) |
| FCFF/FCFE Gap | `abs(Price_FCFF/Price_FCFE - 1)` | > 25% |

---

*Tài liệu này là hướng dẫn kỹ thuật tổng quát. Mọi giá trị cụ thể (WACC, số CP, tổng tài sản) phải được lấy từ dữ liệu thực của từng ticker tại thời điểm định giá.*
