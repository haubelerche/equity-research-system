# Đánh giá tiến độ chất lượng gen báo cáo hiện tại

## 1. Các lỗi dữ liệu định lượng ban đầu

1. **Sai sàn niêm yết:** DBD niêm yết trên sàn HSX, không phải HNX.
2. **Sai vốn hóa:** vốn hóa hiện tại khoảng **4.745 tỷ VND**, trong khi báo cáo xuất ra là **5.481 tỷ VND**.
3. **Sai tổng tài sản:** tài sản hiện tại khoảng **2.519 tỷ VND**, trong khi báo cáo xuất ra là **2.687 tỷ VND**.
4. **Sai vốn chủ sở hữu:** vốn chủ sở hữu khoảng **1.734 tỷ VND**, trong khi báo cáo xuất ra là **1.816 tỷ VND**.
5. **Sai số lượng cổ phiếu:** mô hình định giá đang dùng **109 triệu cổ phiếu**, trong khi thực tế là hơn **94 triệu cổ phiếu**.
6. **Sai định dạng CAPEX:** CAPEX xuất ra dưới dạng phần trăm, trong khi đáng ra phải để dạng số tuyệt đối và cần kiểm tra khả năng tính sai.
7. **Mâu thuẫn logic định giá:** doanh thu và lợi nhuận sau thuế tăng trưởng đều, nhưng mô hình lại đưa ra khuyến nghị bán.

---

# Các lỗi còn tồn đọng trong file DBD Report

## Đánh giá file `DRIVER_FIX_DRAFT_20260601_DBD_report.html`

### Kết luận tổng quát

File HTML đã cải thiện về phần narrative driver-based, có đề cập tới cổ tức, CAPEX/revenue, nợ ròng, GMP-EU, dự án SVI và WACC. Tuy nhiên, mô hình định lượng vẫn chưa đủ chuẩn để dùng làm valuation chính thức.

Các lỗi trọng yếu còn nằm ở:

- CAPEX/FCF reconciliation.
- Cổ tức chưa đi vào equity roll-forward.
- Thiếu cash sweep và debt schedule.
- Chưa có FCFE đúng nghĩa.
- Sensitivity analysis còn mỏng.
- Thiếu peer group.
- Thiếu valuation bridge.

---

## 2. Phạm vi kiểm tra

Tài liệu này tổng hợp các lỗi còn tồn đọng sau khi đọc file HTML DBD report. Trọng tâm kiểm tra gồm:

- CAPEX.
- Dòng tiền tự do.
- Cổ tức.
- Nợ ròng.
- FCFE.
- DCF 60% FCFF / 40% FCFE.
- Sensitivity analysis.
- Định giá tương đối.
- Valuation bridge.
- Rủi ro.
- Các lỗi trình bày/QA.

Nguồn tham chiếu nội bộ:

- File DBD report HTML.
- Cẩm nang định giá 60% FCFF / 40% FCFE.
- Hướng dẫn sensitivity analysis đã xây trước đó.

| Nhóm lỗi | Mức độ | Trạng thái cần xử lý |
|---|---:|---|
| CAPEX và FCF reconciliation | Critical | Sửa ngay trước khi xuất target price |
| Cổ tức và equity roll-forward | Critical | Bắt buộc nối vào cash/equity forecast |
| Debt schedule và cash sweep | Critical | Bắt buộc tạo module riêng |
| Thiếu FCFE đúng nghĩa và Blend 60/40 | High | Thêm bảng FCFE, Re, TV FCFE và Price_FCFE |
| Sensitivity còn thiếu | High | Bổ sung WACC/g, Re/g, CAPEX/NWC, dividend/debt/issuance |
| Peer group và định giá tương đối | High | Bổ sung peer median, outlier filter, forward multiple |
| Valuation bridge | High | Bổ sung bridge từ dòng tiền đến target price |
| Narrative và số liệu không khớp | Medium | Chuẩn hóa số liệu doanh thu, kế hoạch và assumptions |
| Rủi ro đầu tư còn sơ sài | Medium | Liên kết rủi ro với driver định lượng |
| Lỗi trình bày và QA | Medium | Sửa class khuyến nghị, đơn vị, nguồn, banner draft |

---

## 3. Lỗi CAPEX và dòng tiền tự do vẫn còn nghiêm trọng

Lỗi nổi bật nhất trong file là phần CAPEX. Trong bảng các khoản mục cân đối kế toán và dòng tiền, dòng CAPEX bị hiển thị dưới dạng phần trăm rất lớn, ví dụ:

- 14874.5%
- 40857.3%
- 16550.0%
- 17590.0%
- 18690.0%

Đây gần như chắc chắn là lỗi định dạng đơn vị. Nếu các giá trị này thực chất là **148.7 tỷ**, **408.6 tỷ**, **165.5 tỷ**, **175.9 tỷ** và **186.9 tỷ**, thì bảng đang format sai thành phần trăm và nhân lên 100 lần. Lỗi này có thể khiến người đọc hiểu sai quy mô đầu tư vốn và làm hỏng toàn bộ phần kiểm toán dòng tiền.

Nghiêm trọng hơn, dòng tiền tự do không khớp nhất quán với CFO và CAPEX. Với 2024A và 2025A, FCF trong bảng có vẻ gần với `CFO + CAPEX`, trong khi từ 2026F trở đi lại gần với `CFO - CAPEX`. Nếu đúng, mô hình đang dùng hai quy ước khác nhau giữa lịch sử và dự phóng. Đây là lỗi rất lớn vì DCF phụ thuộc trực tiếp vào dòng tiền tự do.

Chuẩn bắt buộc là phải tách rõ:

- `CAPEX_positive`
- `CAPEX_CFS_signed`

Nếu CAPEX là số dương đại diện cho tiền chi ra, công thức phải là:

```text
FCF = CFO - CAPEX_positive
```

Nếu CAPEX lấy từ báo cáo lưu chuyển tiền tệ và là số âm, công thức phải là:

```text
FCF = CFO + CAPEX_CFS_signed
```

Không được trộn hai kiểu trong cùng một bảng.

| Năm | CFO | CAPEX ngầm hiểu | FCF trong bảng | Vấn đề |
|---|---:|---:|---:|---|
| 2024A | 265 | ~148.7 | 413 | Có vẻ cộng CAPEX vào CFO |
| 2025A | 615 | ~408.6 | 1,024 | Có vẻ cộng CAPEX vào CFO |
| 2026F | 473 | ~165.5 | 311 | Có vẻ trừ CAPEX khỏi CFO |

---

## 4. Cổ tức đã được thêm nhưng chưa xử lý đúng trong equity roll-forward

File đã có dòng cổ tức/cp **2,000 VND** và cổ tức khoảng **218 tỷ đồng mỗi năm**. Đây là cải tiến so với các bản trước, nhưng cổ tức chưa được trừ nhất quán khỏi vốn chủ sở hữu dự phóng.

Năm 2025 có vẻ hợp lý vì vốn chủ cuối kỳ xấp xỉ vốn chủ đầu kỳ cộng lợi nhuận ròng trừ cổ tức. Tuy nhiên, từ 2026F trở đi, vốn chủ sở hữu gần như bằng vốn chủ đầu kỳ cộng toàn bộ lợi nhuận ròng, tức là cổ tức không bị trừ khỏi retained earnings/equity. Điều này làm equity, BVPS, P/B và ROE forecast bị sai.

Cổ tức không phải khoản trừ trực tiếp khỏi FCFE valuation, nhưng phải đi qua cash flow và equity roll-forward. Nếu không, mô hình sẽ vừa trả cổ tức cho cổ đông, vừa vẫn giữ lại toàn bộ lợi nhuận trong vốn chủ sở hữu, tạo ra sai lệch kép.

| Năm | Vốn CSH đầu năm | LNST | Cổ tức | Vốn CSH đúng nên gần | Vốn CSH trong bảng | Sai lệch |
|---|---:|---:|---:|---:|---:|---:|
| 2026F | 1,736 | 420 | 218 | 1,938 | 2,156 | ~218 |
| 2027F | 2,156 | 447 | 218 | 2,385 | 2,603 | ~218 |

---

## 5. Nợ ròng chưa được giải thích bằng cash sweep và debt schedule

File có dòng thay đổi nợ ròng và nợ ròng cuối năm, nhưng chưa có debt schedule để giải thích nợ vay đầu kỳ, vay mới, trả nợ gốc và nợ vay cuối kỳ. Đồng thời, thay đổi nợ ròng chưa được nối với cash sweep đầy đủ.

Ví dụ 2026F: nếu FCF khoảng **311 tỷ** và cổ tức khoảng **218 tỷ**, tiền dư sau cổ tức chỉ khoảng **93 tỷ**. Tuy nhiên, nợ ròng lại cải thiện từ **-160** lên **-295**, tương đương tăng net cash khoảng **135 tỷ**. Chênh lệch này cần được giải thích bằng phát hành cổ phiếu, bán tài sản, thay đổi đầu tư tài chính ngắn hạn hoặc các dòng tiền khác. Hiện file chưa làm rõ.

Phần narrative có nhắc phương án huy động vốn riêng lẻ hơn **1.100 tỷ đồng** cho hai nhà máy. Tuy nhiên, mô hình chưa mô phỏng phát hành cổ phiếu, tăng tiền mặt, tăng số cổ phiếu hoặc pha loãng EPS. Đây là mâu thuẫn lớn giữa narrative và financial model.

| Khoản mục bắt buộc trong cash/debt module | Công thức hoặc kiểm tra |
|---|---|
| Cash sweep | `Ending Cash = Beginning Cash + CFO - CAPEX - Dividends + New Borrowing - Debt Repayment + Equity Issuance +/- Other Cash Items` |
| Debt schedule | `Ending Debt = Beginning Debt + New Borrowing - Debt Repayment` |
| Net debt | `Net Debt = Interest-bearing Debt - Cash - Short-term Investments` |
| DebtFlowMismatch check | Nếu thay đổi nợ ròng không khớp với FCF, cổ tức, phát hành và dòng tiền khác, phải báo lỗi |
| Equity issuance/dilution scenario | Nếu narrative có huy động vốn riêng lẻ, phải có kịch bản số cổ phiếu mới và EPS pha loãng |

---

## 6. FCFE chưa thực sự được triển khai

File hiện chủ yếu nói về FCFF, P/E, P/B, EV/EBITDA và EV/FCF. Tuy nhiên, chưa có bảng FCFE độc lập. Không thấy các dòng:

```text
FCFE = Net Income + D&A - CAPEX - Delta NWC + Net Borrowing
```

hoặc:

```text
FCFE = CFO - CAPEX + Net Borrowing
```

Cũng chưa có Re, Terminal Value FCFE, Equity Value FCFE, Price_FCFE và Blend 60% FCFF / 40% FCFE.

Điều này khiến file chưa đi theo framework định giá mới mà agent cần dùng. Nếu chỉ có FCFF và các multiple quan sát, mô hình chưa đủ để kiểm tra dòng tiền còn lại cho cổ đông, đặc biệt trong bối cảnh có cổ tức tiền mặt, nợ vay tăng và khả năng phát hành cổ phiếu riêng lẻ.

| Module cần thêm | Nội dung bắt buộc |
|---|---|
| FCFE forecast | NI, D&A, CAPEX_positive, Delta NWC, Net Borrowing, FCFE |
| Discount rate | Re / Cost of Equity, không dùng WACC cho FCFE |
| Terminal value | `TV_FCFE = FCFE_N x (1 + g) / (Re - g)` |
| Equity value | `Equity Value_FCFE = PV(FCFE) + PV(TV_FCFE)` |
| Price_FCFE | `Equity Value_FCFE / Diluted Shares` |
| Blend DCF | `Target Price = 60% Price_FCFF + 40% Price_FCFE` |

---

## 7. Lợi nhuận 2026F tăng quá mạnh nhưng chưa được giải thích đầy đủ

Bảng tài chính cho thấy doanh thu 2026F chỉ tăng khoảng **6.3%** nhưng lợi nhuận ròng và EPS lại tăng khoảng **44.0%**. Đây là biến động rất lớn. Mô hình cần giải thích rõ driver nào tạo ra mức tăng này.

Nguyên nhân có vẻ đến từ dòng doanh thu tài chính/khác đang âm trong 2024-2025 rồi được normalize về gần 0 từ 2026F. Nếu đây là khoản bất thường, báo cáo phải ghi rõ đây là khoản one-off và mô hình đã loại bỏ từ năm dự phóng. Nếu không phải one-off, forecast lợi nhuận đang quá lạc quan.

Tên gọi “Doanh thu tài chính/khác” cũng chưa phù hợp nếu dòng này là số âm. Nên đổi thành “Lãi/lỗ tài chính và thu nhập/chi phí khác” để tránh hiểu nhầm.

| Chỉ tiêu | 2025A | 2026F | Tăng trưởng | Cần giải thích |
|---|---:|---:|---:|---|
| Doanh thu thuần | 1,865 | 1,982 | +6.3% | Tăng trưởng vận hành bình thường |
| Lợi nhuận ròng | 292 | 420 | +44.0% | Có thể do normalize khoản âm tài chính/khác |
| EPS điều chỉnh | 2,674 | 3,850 | +44.0% | Cần kiểm tra pha loãng nếu có phát hành riêng lẻ |

---

## 8. Doanh thu và kế hoạch 2026 chưa khớp giữa narrative và bảng

Phần narrative viết doanh thu 2025 khoảng **1.947 tỷ đồng**, nhưng bảng tài chính lại dùng **1.865 tỷ đồng**. Chênh lệch khoảng **82 tỷ đồng** cần được giải thích hoặc sửa lại.

Sidebar ghi kế hoạch doanh thu 2026 là **2.090 tỷ đồng**, nhưng bảng forecast 2026F là **1.982 tỷ đồng**. Nếu analyst cố tình chiết khấu kế hoạch doanh nghiệp, cần ghi rõ base case thấp hơn kế hoạch khoảng **5.2%** để phản ánh rủi ro thực thi. Nếu không, đây là lỗi không nhất quán giữa narrative và model.

| Khoản mục | Narrative / sidebar | Bảng forecast | Vấn đề |
|---|---:|---:|---|
| Doanh thu 2025 | 1,947 tỷ | 1,865 tỷ | Lệch khoảng 82 tỷ |
| Kế hoạch doanh thu 2026 | 2,090 tỷ | 1,982 tỷ | Base case thấp hơn kế hoạch khoảng 5.2%, cần giải thích |

---

## 9. Sensitivity analysis còn quá mỏng

File có bảng độ nhạy theo driver dạng Bear/Base/Bull với target price, revenue growth, gross margin và WACC. Bảng này hữu ích nhưng chưa đủ là sensitivity analysis chuẩn.

Bảng hiện tại không cho biết từng biến tác động bao nhiêu, không có WACC x terminal growth matrix, không có Re x g cho FCFE, không có CAPEX/NWC sensitivity, không có net borrowing/cổ tức sensitivity, không có terminal value weight và không có break-even analysis. Như vậy, người đọc chưa biết target price **30,074 VND** nhạy nhất với biến nào.

| Sensitivity cần bổ sung | Mục tiêu kiểm tra |
|---|---|
| WACC x g | Kiểm tra độ nhạy DCF và terminal value |
| Re x g | Kiểm tra FCFE nếu bổ sung module FCFE |
| Gross margin x revenue growth | Kiểm tra thesis vận hành |
| CAPEX/Sales x NWC/Sales | Kiểm tra dòng tiền và chu kỳ đầu tư |
| Dividend payout x equity issuance | Kiểm tra cash, equity và pha loãng |
| Net borrowing x interest rate | Kiểm tra FCFE và rủi ro nợ |
| EPS FY1 x Target P/E | Kiểm tra định giá tương đối bằng forward P/E |
| EBITDA FY1 x EV/EBITDA | Kiểm tra EV/EBITDA bridge |
| Break-even WACC/P/E | Tìm ngưỡng để target price bằng giá thị trường |

---

## 10. Định giá tương đối vẫn chưa đạt chuẩn

File có các chỉ số P/E, P/B, EV/EBITDA, EV/FCF, P/S, EV/Doanh thu và PEG, nhưng đây mới là bảng multiple quan sát theo thị giá hiện tại, chưa phải định giá tương đối đầy đủ.

Thiếu peer group, median peer multiple, outlier filter, target forward P/E, target EV/EBITDA, premium/discount rationale và target price theo multiple. Không thấy nhóm peer như DHG, TRA, DBD, IMP, DMC, OPC hoặc peer khu vực. Vì vậy, P/E và EV/EBITDA hiện chỉ giúp người đọc biết cổ phiếu đang giao dịch ở mức nào, chưa dùng được làm cross-check định giá chính thức.

| Thành phần còn thiếu | Cách sửa |
|---|---|
| Peer group | Lập bảng peer nội địa và/hoặc khu vực, ghi rõ ngành, quy mô, thanh khoản |
| Outlier filter | Loại EPS âm, EBITDA âm, P/E quá cao do lợi nhuận thấp, sự kiện one-off |
| Forward P/E | Dùng EPS FY1/FY2 và target forward P/E từ peer median |
| EV/EBITDA bridge | `Target EV = EBITDA x multiple`; `Equity Value = EV - Net Debt + Non-operating Assets - Minority Interest` |
| Premium/discount rationale | Điều chỉnh theo ROE, growth, margin, liquidity, governance và rủi ro dự án |

---

## 11. Chưa có valuation bridge rõ ràng từ dòng tiền đến target price

Target price **30,074 VND/cp** được đưa ra nhưng file chưa trình bày bridge đầy đủ từ dòng tiền đến giá mục tiêu. Không có bảng rõ ràng cho FCFF forecast, terminal value, PV FCFF, PV terminal value, enterprise value, net debt, equity value, shares outstanding và target price.

Nếu không có valuation bridge, người đọc không thể tái lập target price. Đây là lỗi lớn về tính kiểm toán của mô hình.

| Nếu dùng FCFF | Nếu dùng FCFE |
|---|---|
| FCFF forecast từng năm | FCFE forecast từng năm |
| `TV_FCFF = FCFF_N x (1+g)/(WACC-g)` | `TV_FCFE = FCFE_N x (1+g)/(Re-g)` |
| `EV = PV(FCFF) + PV(TV_FCFF)` | `Equity Value = PV(FCFE) + PV(TV_FCFE)` |
| `Equity Value = EV - Net Debt + Non-operating Assets` | Không trừ net debt lần nữa |
| `Price_FCFF = Equity Value / Diluted Shares` | `Price_FCFE = Equity Value / Diluted Shares` |

---

## 12. Rủi ro đầu tư và QA còn thiếu

Phần rủi ro đầu tư hiện còn quá ngắn so với chính narrative. File chỉ nêu áp lực giá thầu thuốc, biến động nguyên liệu/tỷ giá và cạnh tranh generic. Trong khi đó narrative đã nhắc đến GMP-EU, SVI, CAPEX hơn **548 tỷ**, phương án huy động vốn riêng lẻ hơn **1.100 tỷ**, hàng tồn kho tăng, nợ vay tăng và cash conversion/leverage.

Những rủi ro này phải được đưa vào bảng rủi ro chính vì chúng tác động trực tiếp đến CAPEX, nợ vay, pha loãng EPS, FCFE, WACC và ROIC.

Một số lỗi trình bày/QA cũng cần sửa:

- CSS class `recommendation-card review` nhưng nội dung là **BÁN**.
- Sàn ghi HNX: DBD cần kiểm tra lại.
- Bảng diễn biến giá cổ phiếu toàn dấu gạch ngang.
- Đơn vị vốn hóa và số cổ phiếu chưa rõ.
- Nguồn tham khảo chỉ liệt kê chung.
- Thiếu citation theo từng claim.
- Thiếu draft/internal banner.
- Thiếu assumption approval status.

| Lỗi QA | Tác động | Cách sửa |
|---|---|---|
| `recommendation-card review` nhưng nội dung BÁN | Sai trạng thái hiển thị | Đổi class theo rating hoặc thêm nhãn Draft/Review riêng |
| Sàn HNX: DBD cần kiểm tra | Sai metadata doanh nghiệp nếu source sai | Đối chiếu với source chính thức trước khi xuất |
| Bảng diễn biến giá toàn dấu `—` | Tạo cảm giác report chưa hoàn thiện | Bỏ bảng hoặc lấy dữ liệu giá thật |
| Đơn vị vốn hóa/số cổ phiếu chưa rõ | Dễ hiểu sai quy mô | Ghi rõ tỷ VND và triệu CP |
| Nguồn chung chung | Không kiểm toán được claim | Cần citation map theo từng claim định lượng/định tính |
| Không có banner draft rõ ràng | Dễ bị hiểu là báo cáo final | Thêm Draft / Needs Analyst Review |

---

## 13. Đánh giá cuối cùng và thứ tự ưu tiên sửa

File HTML này đã tốt hơn bản cũ về narrative và tư duy driver-based. Báo cáo đã đưa được gross margin, SG&A/revenue, CAPEX/revenue, WACC, cổ tức, nợ ròng, kế hoạch doanh nghiệp, GMP-EU và SVI vào phần phân tích.

Tuy nhiên, phần mô hình định lượng vẫn chưa đủ để dùng làm valuation chính thức.

Kết luận ngắn gọn: file đã sửa được phần “viết báo cáo theo driver”, nhưng chưa sửa xong phần “mô hình tài chính/định giá có thể kiểm toán”. Nếu chưa sửa các lỗi dưới đây, target price **30,074 VND/cp** chỉ nên xem là draft diagnostic output, không phải target price có thể publish.

| Ưu tiên | Việc cần làm | Lý do |
|---:|---|---|
| 1 | Sửa CAPEX row bị format sai và kiểm tra FCF reconciliation | CAPEX/FCF là nền tảng của DCF |
| 2 | Trừ cổ tức khỏi retained earnings/equity forecast | Tránh overstated equity, BVPS và sai ROE/PB |
| 3 | Tạo cash sweep và debt schedule thật | Giải thích nợ ròng, tiền mặt và net borrowing |
| 4 | Mô phỏng huy động vốn riêng lẻ và pha loãng số cổ phiếu | Narrative có sự kiện phát hành nhưng model chưa phản ánh |
| 5 | Thêm FCFE đúng nghĩa và Blend 60% FCFF / 40% FCFE | Đúng framework định giá đã thống nhất |
| 6 | Thêm valuation bridge đầy đủ | Cho phép tái lập target price |
| 7 | Mở rộng sensitivity | Xác định biến nhạy nhất và mức rủi ro mô hình |
| 8 | Bổ sung peer group và forward multiple | Định giá tương đối mới có cơ sở |
| 9 | Đồng bộ narrative, bảng số và rủi ro | Tránh mâu thuẫn nội bộ trong báo cáo |
| 10 | Thêm QA gate và assumption approval status | Chặn báo cáo draft bị hiểu nhầm là final |

---

## 14. Phụ lục công thức kiểm tra nhanh

| Nhóm | Công thức / rule |
|---|---|
| FCF từ CFO nếu CAPEX dương | `FCF = CFO - CAPEX_positive` |
| FCF từ CFO nếu CAPEX âm trong CFS | `FCF = CFO + CAPEX_CFS_signed` |
| FCFF từ EBIT | `FCFF = EBIT x (1 - Tax Rate) + D&A - CAPEX_positive - Delta NWC` |
| FCFE từ NI | `FCFE = Net Income + D&A - CAPEX_positive - Delta NWC + Net Borrowing` |
| Equity roll-forward | `Ending Equity = Beginning Equity + Net Income - Dividends Paid + Equity Issuance - Buyback +/- OCI` |
| Debt roll-forward | `Ending Debt = Beginning Debt + New Borrowing - Debt Repayment` |
| Net Debt | `Interest-bearing Debt - Cash - Short-term Investments` |
| FCFF Price | `(PV FCFF + PV TV - Net Debt + Non-operating Assets) / Diluted Shares` |
| FCFE Price | `(PV FCFE + PV TV FCFE) / Diluted Shares` |
| Blend DCF | `Target Price = 0.60 x Price_FCFF + 0.40 x Price_FCFE` |
