# Hướng dẫn định giá cổ phiếu theo phương pháp P/E Forward

## 1. Bản chất của phương pháp P/E Forward

Phương pháp **P/E Forward** là phương pháp định giá cổ phiếu dựa trên **lợi nhuận kỳ vọng trong tương lai** thay vì lợi nhuận đã xảy ra trong quá khứ.

Công thức tổng quát:

```text
Giá mục tiêu = EPS Forward × Target P/E
```

Trong đó:

- **EPS Forward**: thu nhập trên mỗi cổ phiếu dự phóng cho năm tới hoặc một năm mục tiêu trong tương lai.
- **Target P/E**: hệ số P/E hợp lý mà nhà phân tích lựa chọn dựa trên doanh nghiệp so sánh, trung bình ngành, triển vọng tăng trưởng, rủi ro và chất lượng lợi nhuận.

Phương pháp này thường được dùng trong equity research vì đơn giản, dễ so sánh và phản ánh kỳ vọng của thị trường đối với lợi nhuận tương lai.

---

## 2. Phân biệt Trailing P/E và Forward P/E

| Chỉ tiêu | Công thức | Ý nghĩa |
|---|---|---|
| Trailing P/E | Giá thị trường / EPS 12 tháng gần nhất | Dựa trên lợi nhuận quá khứ |
| Forward P/E | Giá thị trường / EPS dự phóng | Dựa trên lợi nhuận tương lai |
| Target P/E | P/E hợp lý do analyst lựa chọn | Dùng để tính giá mục tiêu |

Trong định giá cổ phiếu, **Forward P/E thường quan trọng hơn Trailing P/E**, vì giá cổ phiếu phản ánh kỳ vọng tương lai chứ không chỉ phản ánh kết quả đã công bố.

---

## 3. Quy trình định giá theo P/E Forward

Quy trình gồm 6 bước chính:

```text
Bước 1: Dự phóng lợi nhuận sau thuế
Bước 2: Tính EPS Forward
Bước 3: Chọn nhóm doanh nghiệp so sánh
Bước 4: Tính P/E của nhóm so sánh
Bước 5: Xác định Target P/E hợp lý
Bước 6: Tính giá mục tiêu
```

---

## 4. Bước 1: Dự phóng lợi nhuận sau thuế

Trước tiên cần dự phóng **lợi nhuận sau thuế thuộc cổ đông công ty mẹ** cho năm định giá.

Ví dụ:

| Năm | LNST dự phóng |
|---|---:|
| 2026F | 120 tỷ đồng |

Nếu doanh nghiệp có cổ đông không kiểm soát, cần dùng:

```text
LNST thuộc cổ đông công ty mẹ = LNST sau thuế - LNST của cổ đông không kiểm soát
```

Không nên dùng lợi nhuận trước thuế hoặc lợi nhuận gộp để tính EPS.

---

## 5. Bước 2: Tính EPS Forward

Công thức:

```text
EPS Forward = LNST thuộc cổ đông công ty mẹ / Số cổ phiếu lưu hành bình quân
```

Ví dụ:

| Chỉ tiêu | Giá trị |
|---|---:|
| LNST dự phóng | 120 tỷ đồng |
| Số cổ phiếu lưu hành | 20 triệu cổ phiếu |

```text
EPS Forward = 120 tỷ / 20 triệu = 6,000 đồng/cp
```

Lưu ý: nên dùng **số cổ phiếu lưu hành bình quân pha loãng** nếu doanh nghiệp có cổ phiếu thưởng, ESOP, trái phiếu chuyển đổi hoặc quyền mua cổ phiếu.

---

## 6. Bước 3: Chọn nhóm doanh nghiệp so sánh

Target P/E không nên chọn tùy ý. Cần dựa trên một nhóm doanh nghiệp so sánh phù hợp.

Các tiêu chí chọn peer group:

| Tiêu chí | Ý nghĩa |
|---|---|
| Cùng ngành | Mô hình kinh doanh tương đồng |
| Cùng quy mô tương đối | Tránh so doanh nghiệp nhỏ với doanh nghiệp đầu ngành quá lớn |
| Tỷ suất lợi nhuận tương đồng | Biên lợi nhuận khác nhau sẽ xứng đáng P/E khác nhau |
| Tăng trưởng tương đồng | Công ty tăng trưởng cao thường có P/E cao hơn |
| Cấu trúc tài chính tương đồng | Doanh nghiệp nợ cao thường rủi ro hơn |
| Thanh khoản cổ phiếu | Cổ phiếu thanh khoản thấp thường bị chiết khấu P/E |

Không nên chọn peer chỉ vì cùng sàn niêm yết. Quan trọng hơn là **cùng mô hình kinh doanh và cùng động lực lợi nhuận**.

---

## 7. Bước 4: Tính P/E của nhóm so sánh

Công thức P/E:

```text
P/E = Giá thị trường / EPS
```

Có thể tính:

```text
Trailing P/E = Giá hiện tại / EPS quá khứ
Forward P/E = Giá hiện tại / EPS dự phóng
```

Ví dụ bảng peer:

| Doanh nghiệp | Giá cổ phiếu | EPS Forward | Forward P/E |
|---|---:|---:|---:|
| Công ty A | 60,000 | 5,000 | 12.0x |
| Công ty B | 45,000 | 4,000 | 11.3x |
| Công ty C | 80,000 | 6,000 | 13.3x |

Nên dùng **median P/E** thay vì average P/E nếu nhóm có outlier.

Ví dụ:

```text
Peer median P/E = 12.0x
```

---

## 8. Bước 5: Xác định Target P/E hợp lý

Sau khi có P/E của nhóm so sánh, cần điều chỉnh để phản ánh đặc điểm riêng của doanh nghiệp được định giá.

Công thức tham khảo:

```text
Target P/E = Peer median P/E × (1 ± Premium/Discount)
```

### Khi nào doanh nghiệp xứng đáng P/E cao hơn peer?

Doanh nghiệp có thể được áp dụng premium nếu:

- tăng trưởng lợi nhuận cao hơn ngành;
- ROE cao hơn;
- biên lợi nhuận ổn định hơn;
- bảng cân đối tài chính lành mạnh;
- quản trị doanh nghiệp tốt;
- thanh khoản cổ phiếu tốt;
- vị thế cạnh tranh mạnh.

### Khi nào doanh nghiệp nên bị chiết khấu P/E?

Doanh nghiệp nên bị discount nếu:

- quy mô nhỏ hơn peer;
- thanh khoản cổ phiếu thấp;
- lợi nhuận biến động mạnh;
- phụ thuộc vào thu nhập bất thường;
- nợ vay cao;
- rủi ro ngành cao;
- chất lượng công bố thông tin thấp.

Ví dụ:

| Chỉ tiêu | Giá trị |
|---|---:|
| Peer median P/E | 12.0x |
| Discount do quy mô nhỏ và thanh khoản thấp | 15% |
| Target P/E | 10.2x |

```text
Target P/E = 12.0 × (1 - 15%) = 10.2x
```

---

## 9. Bước 6: Tính giá mục tiêu

Công thức:

```text
Giá mục tiêu = EPS Forward × Target P/E
```

Ví dụ:

| Chỉ tiêu | Giá trị |
|---|---:|
| EPS Forward | 6,000 đồng/cp |
| Target P/E | 10.2x |

```text
Giá mục tiêu = 6,000 × 10.2 = 61,200 đồng/cp
```

---

## 10. Định giá bằng EPS năm nào?

Có 3 cách thường dùng.

### Cách 1: One-year forward P/E

Dùng EPS năm kế tiếp.

```text
Target Price = EPS năm tới × Target P/E
```

Phù hợp khi lợi nhuận năm tới phản ánh trạng thái kinh doanh bình thường.

### Cách 2: Two-year forward P/E rồi chiết khấu về hiện tại

Dùng EPS năm sau nữa nếu năm tới bị nhiễu bởi yếu tố bất thường.

```text
Target Price hiện tại = EPS năm thứ 2 × Target P/E / (1 + Cost of Equity)
```

Ví dụ:

| Chỉ tiêu | Giá trị |
|---|---:|
| EPS 2027F | 7,000 |
| Target P/E | 9.0x |
| Cost of Equity | 15% |

```text
Target Price = 7,000 × 9 / 1.15 = 54,783 đồng/cp
```

### Cách 3: Normalized P/E

Dùng EPS bình thường hóa, loại bỏ các yếu tố bất thường như:

- lãi/lỗ tài chính bất thường;
- lãi thanh lý tài sản;
- chi phí một lần;
- hoàn nhập dự phòng;
- thu nhập không lặp lại.

Công thức:

```text
Normalized EPS = Normalized Net Income / Shares Outstanding
```

Phù hợp với doanh nghiệp có lợi nhuận biến động mạnh hoặc có khoản thu nhập tài chính lớn.

---

## 11. Phương pháp Core P/E + Net Cash

Một số doanh nghiệp có lượng tiền mặt hoặc đầu tư tài chính lớn. Khi đó, nếu dùng EPS báo cáo, lợi nhuận tài chính có thể làm P/E bị nhiễu.

Có thể dùng cách:

```text
Giá trị cổ phiếu = Core EPS × Target Core P/E + Net Cash per Share
```

Trong đó:

```text
Core EPS = Core Net Income / Shares Outstanding
```

```text
Net Cash per Share = Net Cash / Shares Outstanding
```

Cần lưu ý: nếu dùng **Core EPS + Net Cash**, thì phải loại bỏ thu nhập tài chính khỏi lợi nhuận. Không được vừa dùng reported EPS vừa cộng thêm net cash, vì như vậy sẽ bị double count.

---

## 12. Bảng Excel mẫu

### Bảng 1: EPS Forward

| Item | Formula / Value |
|---|---:|
| Net income forecast | Input |
| Minority interest | Input |
| Net income to parent | `=Net income - Minority interest` |
| Shares outstanding | Input |
| EPS Forward | `=Net income to parent / Shares outstanding` |

### Bảng 2: Peer P/E

| Company | Price | EPS Forward | P/E |
|---|---:|---:|---:|
| Peer A | Input | Input | `=Price/EPS` |
| Peer B | Input | Input | `=Price/EPS` |
| Peer C | Input | Input | `=Price/EPS` |
| Median P/E |  |  | `=MEDIAN(P/E range)` |

### Bảng 3: Target Price

| Item | Formula / Value |
|---|---:|
| Peer median P/E | Input |
| Premium / Discount | Input |
| Target P/E | `=Peer median P/E*(1+Premium/Discount)` |
| EPS Forward | Input |
| Target Price | `=EPS Forward*Target P/E` |

---

## 13. Sensitivity Table cho P/E Forward

Nên tạo bảng nhạy cảm giữa EPS và Target P/E.

| EPS / P/E | 8.0x | 9.0x | 10.0x | 11.0x | 12.0x |
|---:|---:|---:|---:|---:|---:|
| 4,000 | 32,000 | 36,000 | 40,000 | 44,000 | 48,000 |
| 5,000 | 40,000 | 45,000 | 50,000 | 55,000 | 60,000 |
| 6,000 | 48,000 | 54,000 | 60,000 | 66,000 | 72,000 |
| 7,000 | 56,000 | 63,000 | 70,000 | 77,000 | 84,000 |

Công thức từng ô:

```text
Target Price = EPS × Target P/E
```

Bảng này giúp kiểm tra xem giá mục tiêu thay đổi như thế nào khi EPS hoặc P/E thay đổi.

---

## 14. Cách kết hợp P/E với các phương pháp khác

P/E Forward thường được dùng để kiểm tra chéo với DCF.

Ví dụ:

| Phương pháp | Giá mục tiêu | Trọng số |
|---|---:|---:|
| FCFF | 55,000 | 40% |
| FCFE | 52,000 | 30% |
| P/E Forward | 58,000 | 30% |

```text
Target Price cuối cùng = 55,000×40% + 52,000×30% + 58,000×30%
```

```text
Target Price cuối cùng = 55,000 đồng/cp
```

Không nên chỉ dựa vào một phương pháp duy nhất, vì P/E phụ thuộc nhiều vào tâm lý thị trường và peer group.

---

## 15. Các lỗi thường gặp khi định giá P/E Forward

### Lỗi 1: Dùng EPS sai

Không nên dùng EPS quá khứ nếu đang nói về P/E Forward.

### Lỗi 2: Chọn peer không phù hợp

Doanh nghiệp khác ngành, khác mô hình kinh doanh hoặc khác quy mô có thể làm Target P/E bị sai.

### Lỗi 3: Dùng average P/E khi có outlier

Nên dùng median P/E để tránh doanh nghiệp có P/E quá cao hoặc quá thấp làm méo kết quả.

### Lỗi 4: Không điều chỉnh yếu tố bất thường

Nếu lợi nhuận có khoản một lần, cần điều chỉnh về normalized earnings.

### Lỗi 5: Double count net cash

Không được vừa dùng EPS đã bao gồm thu nhập tài chính, vừa cộng thêm tiền mặt ròng vào giá trị cổ phiếu.

### Lỗi 6: Chọn P/E theo giá mục tiêu mong muốn

Không nên chọn Target P/E chỉ để ra mức giá mong muốn. Target P/E phải có cơ sở từ peer group, chất lượng doanh nghiệp và triển vọng tăng trưởng.

---

## 16. Kết luận

Phương pháp P/E Forward phù hợp khi doanh nghiệp có lợi nhuận tương đối ổn định và có nhóm so sánh rõ ràng.

Công thức quan trọng nhất:

```text
Target Price = EPS Forward × Target P/E
```

Quy trình đúng là:

```text
Dự phóng LNST
→ Tính EPS Forward
→ Chọn peer group
→ Tính median P/E
→ Điều chỉnh premium/discount
→ Tính target price
→ Kiểm tra bằng sensitivity table
```

Trong một báo cáo định giá hoàn chỉnh, P/E Forward nên được dùng cùng với các phương pháp khác như FCFF, FCFE hoặc EV/EBITDA để tăng độ tin cậy của giá mục tiêu.
