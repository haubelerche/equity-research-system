# Tình hình hiện tại của hệ thống Vietnam Pharma Equity Research Agent

**Ngày tổng hợp:** 2026-06-13  
**Phạm vi:** đánh giá trạng thái hiện tại của pipeline tạo báo cáo DHG, cơ chế kiểm định, chất lượng định giá, chiều sâu phân tích và khả năng mở rộng sang universe 53 mã y dược/y tế.  
**Kết luận điều hành:** hệ thống **chưa đạt chuẩn FPTS**, **chưa đủ điều kiện công bố báo cáo định giá**, và **chưa sẵn sàng mở rộng sang universe 53 mã**.

---

## 1. Kết luận tổng quan

Hệ thống hiện mới đạt mức **khung kỹ thuật tạo báo cáo** và một số cổng kiểm định riêng lẻ, nhưng chưa đạt chuẩn của một hệ thống nghiên cứu cổ phiếu có thể tin cậy ở cấp chuyên viên phân tích. PDF đầu ra hiện tại chỉ đạt rõ ràng **1/14 tiêu chí nghiệm thu**: có bảng độ nhạy. Các tiêu chí còn lại liên quan đến mô hình tài chính, kiểm soát định giá, dẫn chứng theo từng luận điểm, độ sâu phân tích doanh nghiệp, tính nhất quán khuyến nghị và kiểm soát xuất bản đều chưa đạt.

Điểm nghiêm trọng nhất không phải là một phép tính riêng lẻ bị sai, mà là **đường xuất báo cáo nhanh đang vượt qua toàn bộ cơ chế kiểm định**. Pipeline đầy đủ đã biết báo cáo chưa đạt và chặn tại bước rà soát, nhưng một đường render khác vẫn có thể tạo PDF trông như báo cáo hoàn chỉnh. Đây là lỗi quản trị quy trình nghiêm trọng vì làm mất ý nghĩa của toàn bộ hệ thống cổng kiểm định.

Trạng thái phù hợp hiện tại của báo cáo DHG là:

> **Bản nháp nội bộ để kiểm thử hệ thống, không phải báo cáo định giá có thể công bố hoặc dùng làm kết luận đầu tư.**

---

## 2. Trạng thái thực tế của lần chạy gần nhất

| Hạng mục | Trạng thái hiện tại | Nhận định |
|---|---:|---|
| Pipeline đầy đủ | Bị chặn tại bước `REVIEW` | Đúng về nguyên tắc vì chất lượng chưa đạt |
| Kết quả xuất PDF | Vẫn có PDF từ đường fast-render | Sai nghiêm trọng về quản trị xuất bản |
| Trạng thái báo cáo | Vừa hiển thị “ĐANG XEM XÉT”, vừa có khuyến nghị và giá mục tiêu | Không nhất quán |
| Định giá chính | Giá mục tiêu trong PDF: 106.752 VND/cp | Không đủ tin cậy vì nhiều giả định bị chặn hoặc thiếu nguồn |
| Valuation log gần nhất | Có chênh lệch với PDF; PDF có thể dùng artifact cũ hoặc artifact từ run không đạt | Rủi ro stale artifact và snapshot mismatch |
| Khả năng mở rộng 53 mã | Chưa sẵn sàng | Template và evidence hiện chưa đủ theo archetype |

Run đầy đủ gần nhất ghi nhận **NO PDF GENERATED**, nhưng PDF vẫn được tạo bởi đường render nhanh. Điều này chứng minh hệ thống hiện chưa fail-closed: một báo cáo không đạt vẫn có thể được render thành hình thức giống báo cáo hoàn chỉnh.

---

## 3. Các lỗi P0 vẫn tồn tại

| Nhóm lỗi | Biểu hiện trong PDF hoặc log | Kết quả đánh giá | Mức độ |
|---|---|---:|---|
| LNST/EPS tăng bất thường | LNST +53,9%, EPS +59,1%, trong khi doanh thu chỉ +4,0% | Fail | P0 |
| EBIT margin jump | Biên EBIT tăng từ 20,3% lên 27,2% dù biên gộp giảm nhẹ | Fail | P0 |
| Bảng cân đối dự phóng không đầy đủ | Nợ, nợ ròng, tổng nợ phải trả vẫn để trống ở các năm dự phóng | Fail | P0 |
| Cổ tức không nhất quán | Có cổ tức dự phóng dương nhưng suất sinh lợi cổ tức bằng 0 | Fail | P0 |
| Toàn vẹn tên phương pháp FCFE | FCFE bị chặn nhưng nguồn và nhãn vẫn ghi FCFF/FCFE | Fail | P0 |
| Khuyến nghị không nhất quán trạng thái | Báo cáo hiển thị “NẮM GIỮ” và target price trong khi vẫn “ĐANG XEM XÉT” | Fail | P0 |
| Dẫn chứng theo từng luận điểm | Chỉ có một nguồn mô hình nội bộ chung chung, không có citation theo từng claim | Fail | P0 |
| Đường xuất bản | Fast-render có thể xuất PDF từ run bị chặn hoặc artifact chưa được duyệt | Fail | P0 |

---

## 4. Phân tích nguyên nhân kỹ thuật

### 4.1. Fast report đang bypass toàn bộ cổng kiểm định

`scripts/generate_fast_report.py` tự xác định đây là đường tạo báo cáo nhanh và không chạy pipeline đầy đủ hoặc các blocking review gates. Cơ chế hiện tại có các vấn đề sau:

- Mặc định render bằng `client_final`.
- Chọn run mới nhất chỉ cần có `final_report_model`.
- Không kiểm tra run đã được duyệt hay chưa.
- Không kiểm tra run bị `blocked` hay `failed`.
- Không kiểm tra điểm FPTS evaluator.
- Không kiểm tra tính nhất quán giữa artifact valuation, report model và snapshot dữ liệu.
- Có thể render artifact cũ hoặc artifact sinh ra từ run đã thất bại.

Đây là lỗi quản trị nghiêm trọng nhất. Hệ thống đầy đủ có thể phát hiện lỗi và chặn báo cáo, nhưng đường fast-render vẫn có thể tạo PDF trông như báo cáo hoàn chỉnh. Khi đó, mọi cổng kiểm định phía trước trở nên vô nghĩa.

### 4.2. Vòng đời artifact đặt tên sai

Hệ thống hiện có thể sinh `final_report_model` trước khi báo cáo vượt qua review. Đây là lỗi thiết kế vòng đời artifact. Một artifact chưa vượt qua toàn bộ cổng kiểm định không nên mang tên “final”.

Cách đặt tên đúng nên là:

```text
report_candidate_model
→ review_passed_report_model
→ publishable_final_report_model
```

Chỉ artifact ở trạng thái `publishable_final_report_model` mới được phép đưa vào renderer xuất PDF chính thức.

### 4.3. Gate đang phát hiện cảnh báo nhưng chưa chặn đủ mạnh

Log định giá cho thấy nhiều vấn đề đã được phát hiện: FCFE bị chặn, thiếu dữ liệu peer, thiếu lịch nợ vay đáng tin cậy, thiếu dữ liệu vốn lưu động, chính sách thuế chưa được phê duyệt, khuyến nghị cuối chưa được duyệt. Tuy nhiên hệ thống vẫn cho một số valuation gate đi qua và báo cáo vẫn có target price.

Điều này cho thấy cổng kiểm định hiện đang hoạt động theo kiểu “ghi cảnh báo” thay vì “chặn đầu ra có rủi ro cao”. Với báo cáo tài chính, các lỗi về định giá, nợ, cổ tức, FCFE và khuyến nghị phải là lỗi chặn, không phải warning thông thường.

---

## 5. Vấn đề mô hình tài chính và định giá

### 5.1. Lợi nhuận 2026F tăng bất thường

Báo cáo dự phóng doanh thu tăng 4,0% nhưng lợi nhuận sau thuế tăng 53,9% và EPS tăng 59,1%. Nguyên nhân chính là chi phí bán hàng và quản lý giảm mạnh từ khoảng 27,3% doanh thu năm 2025 xuống giả định 20,0% doanh thu năm 2026F.

Đây là giả định rất mạnh. Nếu đây là khoản chi phí bất thường, báo cáo phải chứng minh:

- khoản chi phí nào là bất thường;
- giá trị cụ thể bao nhiêu;
- có nguồn nào xác nhận;
- vì sao khoản đó không lặp lại trong năm dự phóng;
- ảnh hưởng sau thuế tới EPS và FCFF là bao nhiêu.

Nếu không có các chứng minh trên, mô hình đang tạo ra **margin reset không có bằng chứng**, làm phóng đại lợi nhuận, EPS và giá trị định giá.

### 5.2. Biên EBIT tăng không tương thích với logic vận hành

Biên lợi nhuận gộp gần như đi ngang hoặc giảm nhẹ, nhưng biên EBIT lại tăng từ 20,3% lên 27,2%. Điều này chỉ hợp lý nếu doanh nghiệp có đòn bẩy chi phí vận hành rất lớn hoặc loại bỏ được chi phí bất thường. Hiện báo cáo chưa cung cấp bằng chứng cho cả hai điều kiện này.

Đây là điểm không đạt chuẩn phân tích chuyên nghiệp vì biến động biên lợi nhuận vận hành là một trong những driver quan trọng nhất của định giá.

### 5.3. Bảng cân đối dự phóng chưa hoàn chỉnh

Các dòng quan trọng như nợ vay, nợ ròng, tổng nợ phải trả và một phần lịch vốn lưu động chưa được dự phóng đầy đủ. Một mô hình định giá theo FCFF hoặc FCFE không thể xem là hoàn chỉnh nếu không có ít nhất:

- tiền và tương đương tiền;
- đầu tư tài chính ngắn hạn;
- nợ vay ngắn hạn;
- nợ vay dài hạn;
- phải thu;
- hàng tồn kho;
- phải trả;
- tổng nợ phải trả;
- vốn chủ sở hữu;
- tài sản hoạt động và tài sản tài chính.

### 5.4. Mô hình vốn lưu động chưa đạt yêu cầu

Hệ thống không có dữ liệu lịch sử đầy đủ cho phải thu, tồn kho và phải trả. Vì vậy, các cấu phần vốn lưu động bị đưa về 0 hoặc được ước lượng bằng tỷ lệ đơn giản trên thay đổi doanh thu.

Đối với doanh nghiệp dược, đây là thiếu sót trọng yếu vì dòng tiền chịu ảnh hưởng mạnh từ:

- chu kỳ thanh toán bệnh viện;
- kênh ETC và đấu thầu thuốc;
- mức tồn kho nguyên liệu và thành phẩm;
- biến động tỷ giá và giá nguyên liệu nhập khẩu;
- chính sách tín dụng thương mại với nhà thuốc hoặc nhà phân phối.

### 5.5. FCFE bị chặn nhưng báo cáo vẫn trình bày như có mô hình FCFF/FCFE

FCFE không đủ điều kiện tính do thiếu lịch nợ vay và net borrowing đáng tin cậy. Tuy nhiên báo cáo và nguồn vẫn sử dụng nhãn FCFF/FCFE. Nếu định giá blend 60/40 không thể thực hiện vì FCFE bị chặn, hệ thống không được phép gọi kết quả cuối là blended target price.

Trạng thái đúng phải là:

```text
FCFF reference value only — FCFE blocked — target price not publishable.
```

### 5.6. Bridge định giá EV → equity value chưa minh bạch

Báo cáo cần trình bày rõ đường đi từ giá trị doanh nghiệp đến giá trị vốn chủ sở hữu:

```text
PV of explicit FCFF
+ PV of terminal value
= Enterprise value
+ Cash and short-term investments
- Interest-bearing debt
- Minority interest or other claims
= Equity value
/ Diluted shares outstanding
= Target price per share
```

Nếu không có bảng bridge này, người đọc không thể kiểm tra liệu giá mục tiêu đến từ giá trị doanh nghiệp hay giá trị vốn chủ sở hữu.

### 5.7. WACC chưa có phân rã

Báo cáo sử dụng WACC 13,8% nhưng chưa có bảng phân rã tối thiểu:

- lãi suất phi rủi ro;
- phần bù rủi ro thị trường;
- beta;
- phần bù quy mô hoặc thanh khoản nếu có;
- chi phí vốn chủ sở hữu;
- chi phí nợ trước thuế;
- thuế suất;
- cơ cấu vốn mục tiêu;
- WACC cuối cùng.

Với doanh nghiệp gần như không có nợ vay, WACC gần như là chi phí vốn chủ sở hữu. Vì vậy giả định này càng cần được chứng minh, không thể chỉ xuất hiện như một con số cố định.

### 5.8. Định giá tương đối chưa có peer đáng tin cậy

Hệ thống chưa có peer dataset nhưng vẫn sinh P/E forward anchor và Core P/E. Đây là cách làm không đạt chuẩn. Nếu không có nhóm so sánh được chọn theo mô hình kinh doanh, biên lợi nhuận, quy mô, thanh khoản và cơ cấu kênh bán hàng, các bội số định giá chỉ là giả định mặc định, không phải định giá tương đối.

### 5.9. Cổ tức và tổng tỷ suất lợi nhuận không nhất quán

Báo cáo có cổ tức dự phóng dương nhưng dividend yield bằng 0. Đồng thời tổng tỷ suất lợi nhuận lớn hơn upside giá. Nếu tổng return có cộng cổ tức, dividend yield phải được tính và công bố. Nếu không cộng cổ tức, tổng return phải bằng price upside.

---

## 6. Vấn đề chiều sâu phân tích và insight

### 6.1. Narrative hiện tại chủ yếu là nội dung ngành dược dùng chung

Các luận điểm về ETC, OTC, API, generic, tỷ giá và GMP-EU hiện có tính chất hợp lý ở mức ngành, nhưng chưa chứng minh được đây là insight đặc thù của DHG. Các đoạn này có thể áp dụng gần như nguyên văn cho nhiều doanh nghiệp dược khác, nên chưa đạt chuẩn company-specific analysis.

Các nội dung đang thiếu bằng chứng riêng cho DHG gồm:

- tỷ trọng doanh thu ETC/OTC thực tế;
- sản phẩm chủ lực;
- tender value hoặc tender win rate;
- thị phần theo nhóm sản phẩm;
- công suất và tiến độ nhà máy;
- chứng nhận GMP cụ thể;
- đăng ký thuốc hoặc hồ sơ lưu hành;
- tin tức mới có tác động tới giả định doanh thu, biên lợi nhuận, capex hoặc vốn lưu động.

### 6.2. News subsystem chưa được nối vào workflow phân tích

`backend/news` đã có các thành phần discovery, collector, extraction và storage, nhưng ToolRegistry production chưa có công cụ news/catalyst để các agent phân tích sử dụng. Vì vậy FinancialAnalysisAgent và ThesisReportAgent không nhận được event evidence mới.

Hiện news mới dừng ở mức trích xuất factual claim. Để tạo insight tài chính, news phải đi qua chuỗi phân tích:

```text
Sự kiện
→ mức độ trọng yếu
→ driver bị ảnh hưởng
→ khoản mục tài chính bị ảnh hưởng
→ thay đổi giả định dự phóng
→ thay đổi định giá
→ tác động tới luận điểm đầu tư
→ điều kiện bác bỏ luận điểm
```

Nếu thiếu chuỗi này, news chỉ là dữ liệu nền, chưa phải công cụ tạo insight.

### 6.3. Company research pack chưa thực sự có dữ liệu nghiên cứu

`company_research_pack` hiện chủ yếu làm schema normalization. Nó chưa tự ingest hoặc tạo evidence mới. Ngoài ra, module này mặc định yêu cầu các trường như API, GMP, channel và product cho mọi ticker. Thiết kế này không phù hợp với toàn bộ universe 53 mã vì không phải doanh nghiệp nào cũng là nhà sản xuất dược có rủi ro API/GMP/ETC.

Universe hiện gồm:

| Nhóm | Số mã |
|---|---:|
| Pharma | 44 |
| Healthcare services | 3 |
| Medical equipment | 3 |
| Medical distribution | 3 |

Một template ngành dược duy nhất không thể bao phủ đúng toàn bộ universe này.

---

## 7. Vấn đề evaluator và acceptance criteria

### 7.1. Lỗi contract trong FPTS evaluator

Production `ReportClaim` dùng schema:

```text
claim_type: fact | inference | opinion
quantitative: bool
```

Nhưng citation gate lại tìm:

```text
claim_type == "quantitative"
```

Hệ quả là quantitative claims trong production có thể không được kiểm tra đúng, trong khi test có thể pass vì fixture dùng schema khác production. Đây là lỗi contract nghiêm trọng vì làm suy yếu toàn bộ cơ chế kiểm soát claim định lượng.

### 7.2. Professional presentation gate quá hẹp

`professional_presentation` hiện chủ yếu phụ thuộc vào recommendation consistency. Nó chưa kiểm tra các yếu tố cốt lõi của báo cáo phân tích chuyên nghiệp:

- độ sâu insight;
- tính mới của luận điểm;
- mức độ đặc thù công ty;
- materiality của catalyst;
- chất lượng biểu đồ;
- số bảng và hình có đánh số, tiêu đề, nguồn;
- khả năng bác bỏ giả định;
- tính nhất quán giữa mô hình và narrative.

### 7.3. Report completeness gate kiểm tra hình thức nhiều hơn nội dung

Report completeness hiện chủ yếu kiểm tra sự tồn tại của section, table và chart. Điều này không đủ. Một báo cáo có đủ tiêu đề nhưng nội dung là placeholder hoặc narrative dùng chung vẫn có thể vượt qua gate. Cần kiểm tra chất lượng nội dung thực tế, không chỉ kiểm tra cấu trúc.

---

## 8. Kiểm toán acceptance criteria

| Tiêu chí | Trạng thái | Ghi chú |
|---|---:|---|
| Company-specific analysis | Fail | Narrative còn dùng chung cho ngành dược |
| Quarterly/latest-period update | Fail | Chưa có cập nhật kỳ mới nhất hoặc sự kiện mới có materiality |
| Driver-based forecast thực sự | Fail | Doanh thu tăng flat 4%, chưa có forecast theo kênh/sản phẩm |
| Complete/scoped financial model | Fail | Bảng cân đối và vốn lưu động chưa đầy đủ |
| FCFF/FCFE valuation bridge | Fail | FCFE bị block, bridge EV → equity chưa minh bạch |
| WACC decomposition | Fail | Chỉ có WACC cuối, không có build-up |
| Sensitivity table | Pass | Có bảng WACC × terminal growth |
| Peer comparison hoặc giải thích thiếu | Fail | Chưa có peer dataset đáng tin cậy |
| Claim-level citations | Fail | Chỉ có nguồn mô hình nội bộ chung chung |
| Không có unexplained profit/EPS jump | Fail | LNST/EPS 2026F tăng bất thường |
| Balance sheet không incomplete | Fail | Nợ, nợ ròng, tổng nợ phải trả dự phóng còn trống |
| Recommendation/status consistency | Fail | Vừa “NẮM GIỮ”, vừa “ĐANG XEM XÉT” |
| Charts/tables numbered và sourced | Fail | Chưa đạt chuẩn trình bày báo cáo chuyên nghiệp |
| FPTS evaluator score ≥85 | Chưa chứng minh | Run đầy đủ bị chặn tại REVIEW |

**Kết quả:** chỉ đạt rõ ràng **1/14 tiêu chí**. PDF hiện có 7 trang, thấp hơn yêu cầu báo cáo đầy đủ khoảng 12–16 trang.

---

## 9. Rủi ro nếu mở rộng ngay sang 53 mã

Mở rộng ở trạng thái hiện tại sẽ khuếch đại lỗi, không giải quyết lỗi. Các rủi ro chính gồm:

1. **Sai insight theo archetype:** doanh nghiệp thiết bị y tế, phân phối và dịch vụ y tế sẽ bị áp narrative API/GMP/ETC không phù hợp.
2. **Sai định giá hàng loạt:** mô hình chưa xử lý đầy đủ vốn lưu động, nợ, cổ tức, peer và WACC.
3. **Mất kiểm soát xuất bản:** fast-render có thể tạo PDF từ run bị chặn.
4. **Evaluator cho cảm giác an toàn giả:** citation gate có lỗi contract nên có thể bỏ sót claim định lượng.
5. **Artifact stale hoặc mismatch:** PDF có thể dùng report model và valuation artifact không cùng snapshot.
6. **Chi phí debug tăng tuyến tính hoặc siêu tuyến tính:** càng nhiều mã, càng khó xác định lỗi thuộc dữ liệu, archetype, mô hình hay renderer.

Quyết định kỹ thuật đúng là **đóng băng mở rộng universe** cho đến khi P0 governance và evaluator được sửa.

---

## 10. Khuyến nghị chiến lược

### 10.1. P0 — Khôi phục fail-closed governance

Mục tiêu của P0 là bảo đảm rằng báo cáo không đạt thì không thể xuất thành PDF hoàn chỉnh.

Yêu cầu sửa:

1. Cấm `generate_fast_report` render `client_final` nếu run chưa được phê duyệt.
2. Fast render bắt buộc kiểm tra:
   - run status;
   - package validation;
   - FPTS score;
   - artifact snapshot consistency;
   - trạng thái approval;
   - trạng thái export gates.
3. Không lưu tên `final_report_model` trước khi review pass.
4. Đổi artifact trước review thành `report_candidate_model`.
5. Chỉ tạo `publishable_final_report_model` sau toàn bộ export gates.
6. Sửa citation gate theo cờ `quantitative: true`, không dùng `claim_type == "quantitative"`.
7. Chặn model hiện tại khi xuất hiện các lỗi:
   - LNST/EPS jump không giải thích được;
   - nợ và nợ ròng dự phóng trống;
   - dividend yield mâu thuẫn với cổ tức;
   - FCFE bị block nhưng vẫn dùng nhãn FCFF/FCFE;
   - recommendation không nhất quán với trạng thái báo cáo.

### 10.2. P1 — Xây event-to-insight engine

News không nên chỉ được dùng để tóm tắt. Nó phải thay đổi hoặc thách thức giả định mô hình. Mỗi sự kiện nên tạo artifact dạng:

```yaml
analyst_insight:
  observation:
  evidence_refs:
  company_specificity:
  novelty:
  materiality:
  financial_transmission:
    affected_drivers:
    affected_line_items:
    direction:
    time_horizon:
    magnitude_range:
  scenario_delta:
  valuation_delta:
  thesis_implication:
  falsification_trigger:
  confidence:
```

Đầu ra này mới đủ điều kiện đưa vào forecast và report narrative.

### 10.3. P1 — Thiết kế theo company archetype

Không nên dùng một template “pharma” duy nhất cho toàn bộ 53 mã. Cần taxonomy tối thiểu:

| Archetype | Đặc điểm chính | Yêu cầu mô hình riêng |
|---|---|---|
| Branded/generic manufacturer | Sản xuất thuốc, có danh mục sản phẩm và biên gộp theo mix | Kênh bán, giá nguyên liệu, công suất, GMP, sản phẩm chủ lực |
| Tender-focused manufacturer | Phụ thuộc nhiều vào đấu thầu ETC | Tender value, win rate, giá trúng thầu, chu kỳ thanh toán |
| Traditional medicine | Thuốc đông dược hoặc sản phẩm đặc thù | Thương hiệu, kênh OTC, vùng nguyên liệu, biên sản phẩm |
| Distributor | Phân phối dược phẩm hoặc thiết bị | Vòng quay hàng tồn kho, working capital, gross spread, logistics |
| Medical equipment | Thiết bị y tế | Capex bệnh viện, nhập khẩu, tỷ giá, đấu thầu thiết bị |
| Healthcare services | Bệnh viện, phòng khám, dịch vụ y tế | Công suất giường/phòng khám, lượt bệnh nhân, ARPU, payer mix |

Mỗi archetype phải có:

- driver taxonomy riêng;
- required evidence riêng;
- peer-selection rules riêng;
- forecast model riêng;
- insight-depth gate riêng.

### 10.4. P1 — Xây peer engine có bằng chứng

Peer engine phải chọn nhóm so sánh theo:

- mô hình kinh doanh;
- margin profile;
- channel mix;
- quy mô doanh thu và vốn hóa;
- thanh khoản;
- chu kỳ vốn lưu động;
- mức độ phụ thuộc vào đấu thầu hoặc nhập khẩu;
- chất lượng lợi nhuận và dòng tiền.

Không được chọn peer chỉ vì cùng ngành cấp cao.

### 10.5. P1 — Forecast chỉ được gọi là driver-based khi thật sự có driver

Một forecast chỉ được gắn nhãn driver-based khi thỏa mãn tối thiểu:

```text
Revenue = Σ forecast theo kênh hoặc sản phẩm
Margin = mix + pricing + API/FX + tender effects
Opex = selling expense + admin expense + event-specific changes
Capex = identified projects or capacity plans
Working capital = AR + inventory + AP schedule
Debt = debt maturity or borrowing/repayment schedule
```

Dự phóng kiểu flat +4% mỗi năm phải bị chặn hoặc chỉ được ghi là simple trend forecast, không được gọi là driver-based forecast.

---

## 11. Thứ tự triển khai đúng

Thứ tự sửa nên đi theo dependency thực tế, không nên tối ưu report depth trước khi đóng đường bypass:

1. **Đóng đường bypass export.** Không cho PDF được tạo nếu run chưa approved hoặc bị blocked.
2. **Sửa contract và evaluator.** Đặc biệt là citation gate cho quantitative claims và các cổng chặn lỗi tài chính P0.
3. **Sửa lifecycle artifact.** Tách rõ candidate, reviewed và publishable artifacts.
4. **Xây event-to-insight pipeline.** News phải chuyển thành insight có materiality và financial transmission.
5. **Xây archetype-driven company research pack.** Không dùng một template dược cho toàn bộ 53 mã.
6. **Sửa forecast và valuation model.** Bổ sung working capital, debt schedule, dividend yield, WACC build-up, peer engine và valuation bridge.
7. **Nâng cấp report depth.** Chỉ sau khi dữ liệu, insight và model đủ tốt mới tối ưu cấu trúc báo cáo 12–16 trang.
8. **Mở rộng universe có kiểm soát.** Chỉ mở rộng sau khi DHG và một nhóm pilot đại diện qua được FPTS evaluator.

---

## 12. Definition of Done cho giai đoạn sửa lỗi

Hệ thống chỉ được xem là sẵn sàng quay lại mở rộng khi đạt các điều kiện sau:

| Nhóm | Điều kiện hoàn thành |
|---|---|
| Governance | Không có đường render nào xuất PDF nếu run bị blocked, failed hoặc chưa approved |
| Artifact lifecycle | Không có artifact tên “final” trước khi review và export gates pass |
| Citation | 100% claim định lượng dùng `quantitative: true` được kiểm tra và có citation hợp lệ |
| Financial model | Không còn unexplained EPS/LNST jump, không còn balance sheet projection trống ở dòng trọng yếu |
| Valuation | Có bridge EV → equity value → target price, có WACC decomposition, có trạng thái rõ cho FCFF/FCFE |
| Dividend | Total return, dividend yield và cổ tức dự phóng nhất quán |
| Peer | Nếu thiếu peer dataset, định giá tương đối bị chặn hoặc ghi rõ là chưa khả dụng |
| Insight | Mỗi luận điểm chính có evidence riêng cho công ty, không chỉ narrative ngành dùng chung |
| News | Catalyst mới tạo được analyst insight có materiality và financial transmission |
| Archetype | Mỗi mã được gán archetype và dùng driver/evidence/model phù hợp |
| FPTS evaluator | Điểm ≥85 được chứng minh trên run đầy đủ, không phải fast-render |
| Report length/depth | Báo cáo đầy đủ đạt cấu trúc 12–16 trang với bảng/hình được đánh số và có nguồn |

---

## 13. Kết luận cuối cùng

Tình hình hiện tại có thể tóm gọn như sau:

- Hệ thống **chưa đạt FPTS-grade**.
- Lỗi nghiêm trọng nhất là **fast-render bypass toàn bộ gate**.
- Lỗi mô hình nghiêm trọng nhất là **LNST/EPS tăng bất thường do margin reset chưa được chứng minh**.
- Lỗi nghiên cứu nghiêm trọng nhất là **insight chưa đặc thù công ty và thiếu evidence theo từng luận điểm**.
- Lỗi mở rộng nghiêm trọng nhất là **một template pharma đang bị dùng cho universe nhiều archetype khác nhau**.

Quyết định đúng hiện tại là:

Ưu tiên sửa governance, evaluator và mô hình định giá trước khi tối ưu hình thức báo cáo.**

