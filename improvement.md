



## Context

Kết luận trực tiếp: **DHG_fast_report đã tiến bộ về cấu trúc cơ bản, nhưng chưa đạt chuẩn FPTS-grade**. Vấn đề không chỉ nằm ở giao diện PDF, mà sâu hơn là **mức độ phân tích vẫn còn generic**, thiếu phân rã theo động lực kinh doanh đặc thù của từng doanh nghiệp dược, và mô hình tài chính còn các lỗi khiến luận điểm đầu tư chưa đủ tin cậy để mở rộng cho toàn bộ universe.

Báo cáo FPTS về DBD không chỉ đẹp hơn ở trình bày; nó hơn ở **logic phân tích ngành dược**: đi từ kênh ETC/OTC, nhóm sản phẩm chủ lực, thị phần, chuẩn GMP, tiến độ nhà máy, giá API, kết quả 9 tháng, dự phóng từng dòng doanh thu, rồi mới đến định giá FCFF/FCFE. Báo cáo DHG hiện mới có “khung báo cáo nghiên cứu cổ phiếu”, nhưng chưa có độ sâu tương đương một báo cáo sell-side thực thụ.

---

## Problem Statement

Nếu dùng DHG làm mẫu để sửa hệ thống chung cho 52 mã dược còn lại, lỗi lớn nhất hiện nay là: **template báo cáo đang cố bắt chước hình thức research report, nhưng data model và analytical model chưa đủ granular để sinh ra insight đặc thù theo từng công ty**.

Báo cáo DHG đã có trang đầu, khuyến nghị, giá mục tiêu, bảng tài chính, mô hình định giá, ma trận độ nhạy, rủi ro và phụ lục. Tuy nhiên, FPTS tạo cảm giác chuyên nghiệp hơn vì mỗi trang trả lời một câu hỏi phân tích cụ thể: công ty kiếm tiền từ đâu, sản phẩm nào dẫn dắt tăng trưởng, kênh ETC/OTC biến động thế nào, biên lợi nhuận bị ảnh hưởng bởi API nào, dây chuyền EU-GMP làm thay đổi giá bán và nhóm thầu ra sao, và tác động cuối cùng lên định giá là bao nhiêu. Báo cáo FPTS nêu rõ DBD có kênh ETC chiếm vai trò chủ đạo, phân rã thuốc ung thư, kháng sinh, dung dịch thẩm phân, đồng thời lượng hóa doanh thu, tăng trưởng và thị phần theo từng nhóm sản phẩm. fileciteturn2file1

Trong khi đó, báo cáo DHG chủ yếu nói DHG có ETC, OTC, API, GMP-EU, capex, WACC, FCFF. Các khái niệm đúng về mặt ngành nhưng vẫn còn giống “narrative ngành dược dùng chung”. Nó chưa trả lời đủ sâu: DHG mạnh ở sản phẩm nào, sản phẩm nào đang chậm lại, Taisho/đối tác chiến lược ảnh hưởng gì, kênh OTC/ETC chiếm bao nhiêu, nhóm thuốc chủ lực nào quyết định biên gộp, tender nào thực sự material, danh mục thuốc và năng lực nhà máy có tạo lợi thế giá hay chỉ giữ ổn định.

---

## Technical Deep-Dive

### 1. Đánh giá tổng thể theo chuẩn FPTS-grade

| Hạng mục | DHG hiện tại | FPTS DBD | Đánh giá |
|---|---:|---:|---|
| Nhận diện báo cáo | Có khung, có màu chủ đạo | Rất rõ, có logo, người phân tích, người phê duyệt | DHG thiếu tính institutional |
| Trang đầu | Có khuyến nghị, giá mục tiêu, chart, trading info | Executive page rất cô đọng, giàu số liệu, có thesis rõ | DHG dài chữ, ít phân cấp |
| Luận điểm đầu tư | Có 3 câu hỏi chính | Có thesis cụ thể: EU-GMP, ETC, API, nhóm thuốc | DHG còn generic |
| Cập nhật kinh doanh | Chủ yếu doanh thu, biên, ETC/OTC chung | Phân rã 9M, 3Q, channel, product, tender, market share | DHG thiếu granularity |
| Biểu đồ | Có nhưng nhỏ, khó đọc | Nhiều biểu đồ, gắn trực tiếp với luận điểm | DHG cần rebuild chart system |
| Dự phóng | Có driver table | Dự phóng theo dòng sản phẩm/kênh tới 2033 | DHG thiếu driver-level forecast |
| Định giá | Có DCF và sensitivity | Có FCFF/FCFE 50:50, WACC bridge, valuation summary | DHG chưa đủ auditability |
| Bảng tài chính | Có phụ lục 2022A-2030F | Có BCKQKD, CĐKT, chỉ số thanh khoản, vòng quay | DHG còn thiếu forward balance sheet nhất quán |
| Citation | Có danh sách nguồn | Nguồn gắn theo từng bảng/biểu đồ | DHG citation còn “gom cụm” |
| Tính mở rộng | Có skeleton chung | Template gắn với ngành và từng mã | DHG cần data contract mới |

Điểm tổng hợp: **DHG hiện khoảng 5/10 so với FPTS-grade**. Nếu chỉ xét “có đủ mục” thì đạt mức 6/10. Nếu xét “độ sâu phân tích + tính đúng mô hình + trình bày chuyên nghiệp” thì chỉ khoảng 4,5-5/10.

---

### 2. Format trình bày: các lỗi cần sửa ngay

Trang 1 của DHG đã tốt hơn nhiều so với bản sơ khai: có sidebar, bảng thông tin, khuyến nghị, giá mục tiêu và phần luận điểm. Tuy nhiên, cách bố trí vẫn chưa đạt chuẩn FPTS. FPTS dùng trang đầu như một “investment dashboard”: bên trái là analyst, chart, trading info, company overview; bên phải là recommendation, thesis, triển vọng doanh thu, lợi nhuận, yếu tố theo dõi. Mỗi đoạn đều có số cụ thể, headline rõ và chữ đậm để dẫn mắt. DHG thì phần thân bên phải quá dài, text block dày, nhiều câu dài liên tục, khiến người đọc không nắm được ba ý chính trong 30 giây đầu. DHG cũng thiếu thông tin người phân tích, người phê duyệt, ngày giá tham chiếu, nguồn dữ liệu rõ như một báo cáo tổ chức.

Lỗi format nghiêm trọng nhất là **trang 2 bị orphan/widow layout**: chỉ còn vài dòng tiếp nối sidebar và một đoạn ngắn, phần còn lại gần như trắng. Đây là lỗi trình bày không thể chấp nhận ở báo cáo chuyên nghiệp. Nó cho thấy engine chia trang chưa có rule kiểm soát “minimum page fill”, “keep section together”, “avoid orphan continuation”, và “balance first-page two-column flow”. Một báo cáo khi mở rộng lên 52 mã sẽ thường xuyên gặp lỗi này nếu không sửa ở tầng renderer.

Biểu đồ trong DHG còn yếu. Trang 3 có hai biểu đồ nhỏ, font trong biểu đồ quá nhỏ, trục và legend khó đọc khi in A4. Trang 5 biểu đồ dự phóng bị thu nhỏ quá mức, nhãn trục và nguồn gần như không đọc được; phần bảng phía dưới còn có dấu hiệu cắt nội dung ở dòng “Tăng trưởng dài hạn”, làm mất thông tin diễn giải cuối dòng. Đây là lỗi layout và chart contract, không phải lỗi nội dung đơn lẻ. Trong khi đó, FPTS sử dụng biểu đồ như một phần của lập luận: biểu đồ thị phần, biểu đồ doanh thu theo sản phẩm, biểu đồ lợi nhuận gộp, biểu đồ recommendation history đều có tiêu đề, nguồn và vị trí phù hợp với đoạn giải thích. fileciteturn2file1

Quy chuẩn đề xuất cho hệ thống: body text 9,5-10,5 pt; bảng chính tối thiểu 8,5-9 pt; bảng phụ lục có thể 7,5-8 pt nhưng không được vỡ dòng làm mất nghĩa; chart title tối thiểu 8,5 pt; axis label tối thiểu 7,5 pt; data label tối thiểu 7 pt; không đặt hai biểu đồ nhỏ hơn 45% chiều rộng trang nếu có nhiều nhãn. Với báo cáo DHG hiện tại, biểu đồ nên hoặc tăng lên full-width, hoặc chỉ giữ một chart chính/trang, còn biểu đồ nhỏ đưa xuống phụ lục.

---

### 3. Vấn đề lớn nhất: luận điểm chưa đủ sâu và chưa đủ “DHG-specific”

Báo cáo DHG hiện có các cụm từ đúng ngành: ETC, OTC, API, tỷ giá, GMP-EU, capex, vốn lưu động. Nhưng phần lớn vẫn là mô tả khái quát. Một báo cáo FPTS-grade không chỉ nói “ETC quan trọng”, mà phải chỉ rõ: ETC chiếm bao nhiêu doanh thu, dòng sản phẩm nào ở ETC tăng trưởng, trúng thầu nhóm nào, thị phần thay đổi ra sao, tác động lên ASP/biên gộp thế nào, và khi đưa vào forecast thì doanh thu/biên/capex thay đổi bao nhiêu.

FPTS làm rất tốt điều này trong DBD: họ phân rã doanh nghiệp theo thuốc ung thư, kháng sinh, dung dịch thẩm phân; nêu ETC và OTC; giải thích vì sao WHO-GMP giới hạn nhóm thầu; sau đó nối EU-GMP với khả năng bước lên nhóm thầu 1, 2 và mức giá bán cao hơn. Đây là “causal chain” đúng chuẩn analyst: **operating fact → competitive position → financial driver → valuation impact**. fileciteturn2file1

DHG cần chuyển từ “narrative ngành” sang “company-specific thesis”. Ví dụ với DHG, hệ thống phải có ít nhất các nhóm dữ liệu và phân tích sau:

| Cụm phân tích bắt buộc | Cần sinh ra trong báo cáo |
|---|---|
| Danh mục sản phẩm | Nhóm thuốc chủ lực, đóng góp doanh thu, biên gộp tương đối |
| Kênh phân phối | ETC/OTC, nhà thuốc hiện đại, bệnh viện, khu vực bán hàng |
| Lợi thế cạnh tranh | Thương hiệu, nhà máy, chuẩn GMP, đối tác chiến lược, mạng lưới bán hàng |
| Áp lực ngành | Giá API, tỷ giá, đấu thầu tập trung, generic competition |
| Catalyst | Cổ tức, thay đổi nhân sự, nhà máy, sản phẩm mới, kết quả thầu, chính sách BHYT |
| Mô hình tài chính | Driver nào tác động doanh thu, driver nào tác động biên, driver nào tác động vốn lưu động |
| Định giá | Driver nào làm thay đổi FCFF, WACC, terminal growth, net cash, dividend yield |

Hiện báo cáo DHG có nhắc đến các yếu tố này nhưng chưa có số liệu phân rã đủ sâu. Đây là lý do đọc lên vẫn có cảm giác “AI viết hợp lý”, nhưng chưa phải “senior analyst hiểu doanh nghiệp”.

---

### 4. Mô hình tài chính còn lỗi nghiêm trọng

Đây là phần cần ưu tiên hơn cả format. Báo cáo DHG đang có một bất thường lớn: doanh thu 2026F chỉ tăng 4,0%, nhưng lợi nhuận ròng tăng 53,9% và EPS tăng 59,1%. Đồng thời, biên EBIT tăng từ 20,3% lên 27,2%, biên lợi nhuận ròng tăng từ 16,2% lên 23,9%. Những con số này xuất hiện trong bảng tài chính và mô hình định giá của DHG. fileciteturn2file0

Nếu một analyst dự phóng lợi nhuận tăng mạnh hơn doanh thu như vậy, báo cáo phải có bridge rõ ràng: giá vốn giảm bao nhiêu, SG&A giảm vì nguyên nhân gì, chi phí tài chính/lợi nhuận khác được normalize thế nào, thuế suất thay đổi vì ưu đãi nào, có one-off nào trong năm gốc không. Hiện DHG chưa làm được. Tệ hơn, bảng mô hình cho thấy chi phí bán hàng và quản lý giảm từ -1.438 tỷ năm 2025A xuống -1.096 tỷ năm 2026F trong khi doanh thu tăng. Đây là nguồn chính làm EBIT margin nhảy vọt, nhưng báo cáo không giải thích bằng bằng chứng vận hành.

Một lỗi khác là forward balance sheet và debt forecast chưa đầy đủ. Bảng phụ lục có tổng nợ phải trả, nợ vay, nợ ròng lịch sử, nhưng các năm dự phóng để trống nhiều dòng. Nếu định giá FCFF có equity bridge, hệ thống cần forecast hoặc ít nhất khóa giả định cho tiền mặt, nợ vay, vốn lưu động và capex. Không thể có DCF đáng tin nếu phần balance sheet forward bị bỏ trống trong khi vẫn xuất giá mục tiêu.

Ngoài ra, suất sinh lợi cổ tức trong phụ lục hiển thị bằng 0, trong khi báo cáo có dòng cổ tức dương và tổng tỷ suất lợi nhuận trên trang đầu là +18,7%, cao hơn tiềm năng tăng giá +13,9%. Đây là inconsistency giữa dividend model, total return model và summary page. Hệ thống cần chặn xuất báo cáo nếu dividend yield = 0 nhưng dividend cash payout > 0 và total return lại bao gồm phần cổ tức.

---

### 5. Định giá: có khung nhưng chưa đủ chuẩn sell-side

DHG có WACC 13,8%, terminal growth 3,0%, ma trận độ nhạy, giá mục tiêu 106.752 VND/cp và vùng giá trị 89.059-137.751 VND/cp. Đây là tiến bộ tốt về mặt cấu trúc. Nhưng phần định giá vẫn chưa đủ chuẩn vì thiếu các lớp sau:

Thứ nhất, không có **WACC bridge**. FPTS trình bày WACC, chi phí nợ, chi phí vốn chủ sở hữu, lãi suất phi rủi ro, phần bù rủi ro, beta đòn bẩy, tăng trưởng dài hạn và thay đổi so với kỳ trước. DHG chỉ đưa WACC 13,8% như một giả định đã có, không giải thích nguồn và công thức. Với 52 mã, hệ thống phải có WACC engine chuẩn: risk-free rate, equity risk premium, beta, target capital structure, cost of debt, tax shield, size/liquidity premium nếu có.

Thứ hai, DHG chỉ thể hiện FCFF DCF, trong khi FPTS dùng FCFF và FCFE với trọng số 50:50 cho DBD, rồi trình bày bảng tổng hợp giá trị từng phương pháp. fileciteturn2file1 Không nhất thiết mọi mã phải dùng 50:50, nhưng hệ thống phải có policy: khi nào dùng FCFF, khi nào dùng FCFE, khi nào dùng P/E, EV/EBITDA, dividend discount, hoặc sum-of-the-parts. Với doanh nghiệp dược có net cash và cổ tức cao như DHG, chỉ dùng FCFF mà không xử lý dividend yield nhất quán sẽ làm recommendation thiếu chắc.

Thứ ba, sensitivity table hiện có nhưng chưa được diễn giải thành investment implication. Ma trận WACC × g chỉ là bảng số; FPTS-grade cần viết: ở WACC cơ sở/g cơ sở giá trị là bao nhiêu; downside case tương ứng giả định nào; upside case cần catalyst nào; nếu API tăng hoặc ETC kém thì margin/WACC/g thay đổi ra sao. Sensitivity không nên là decoration, mà phải là risk communication.

---

### 6. Citation và nguồn: có danh sách nhưng chưa đủ auditability

DHG có danh sách nguồn [1]-[10], nhưng citation còn ở dạng gom cụm. Ví dụ nhiều nhận định định tính về ETC, OTC, API, GMP, trúng thầu, capex được gắn nhiều nguồn cùng lúc, nhưng người đọc không biết câu nào được chứng minh bởi nguồn nào. Một báo cáo FPTS thường đặt nguồn ngay dưới từng bảng/biểu đồ: “DBD, FPTS tổng hợp”, “Cục Quản lý dược, FPTS ước tính và tổng hợp”, “FPTS ước tính”. Cách này giúp người đọc biết dữ liệu nào là công ty công bố, dữ liệu nào là cơ quan quản lý, dữ liệu nào là ước tính của analyst.

Với hệ thống chung, cần chuyển từ citation theo đoạn sang **claim-level provenance**. Mỗi claim định lượng phải trỏ tới một fact record hoặc chart/table source. PRD của dự án cũng đã xác định valuation phải chạy bằng code với schema rõ ràng, report draft phải sinh từ artifact đã khóa nguồn, và mỗi claim định lượng phải có citation hợp lệ. fileciteturn2file2

Đặc biệt, nguồn tin tức trong DHG hiện có nhiều sự kiện hành chính như thay CEO, thay đổi đăng ký kinh doanh, thông báo cổ tức. Nhưng báo cáo chưa phân loại được sự kiện nào thật sự ảnh hưởng valuation. Tin tức không nên chỉ “đủ số lượng 8 bài”; cần có materiality scoring: tác động doanh thu, tác động biên, tác động capex, tác động governance, tác động dividend, hoặc không material.

---

## Strategic Recommendations

### P0 — Sửa financial integrity trước khi sửa đẹp

Trước khi mở rộng thêm mã, hệ thống phải có hard gates cho mô hình tài chính:

| Gate | Điều kiện chặn xuất báo cáo |
|---|---|
| Profit growth sanity | LNST/EPS tăng vượt doanh thu trên 15-20 điểm % mà không có bridge |
| Margin jump gate | EBIT margin hoặc net margin tăng trên 300 bps mà không có explanation artifact |
| SG&A sanity | SG&A giảm tuyệt đối trong khi doanh thu tăng mà không có restructuring/one-off evidence |
| Balance sheet completeness | Forward debt, cash, working capital, equity, total assets bị trống |
| Dividend consistency | Dividend payout > 0 nhưng dividend yield = 0 |
| Recommendation consistency | Total return, upside, dividend yield và rating threshold không khớp |
| Valuation reproducibility | Không recompute được target price từ assumptions đã in trong báo cáo |

Nếu các gate này fail, báo cáo vẫn có thể render, nhưng phải ghi rõ ở trạng thái báo cáo: “Model requires review: margin bridge missing”, không được trình bày như báo cáo final.

---

### P1 — Thiết kế lại template theo FPTS logic, không chỉ FPTS style

Template chuẩn cho mỗi mã dược nên cố định như sau:

1. **Trang 1: Investment snapshot**  
   Khuyến nghị, giá hiện tại, giá mục tiêu, upside, total return, trading data, chart giá so với VNIndex, 3 luận điểm chính, 3 yếu tố theo dõi.

2. **Tổng quan doanh nghiệp**  
   Mô hình kinh doanh, sản phẩm chủ lực, kênh ETC/OTC, thị phần, chuẩn nhà máy, cổ đông chiến lược, lợi thế cạnh tranh.

3. **Cập nhật kết quả kinh doanh gần nhất**  
   Quý gần nhất và lũy kế 6M/9M/năm; phân rã doanh thu, gộp, SG&A, EBIT, LNST; giải thích YoY theo driver.

4. **Phân tích kênh và sản phẩm**  
   ETC, OTC, xuất khẩu nếu có; nhóm thuốc chủ lực; tender; thị phần; giá bán; sản lượng.

5. **Triển vọng và dự phóng**  
   Doanh thu theo kênh/sản phẩm; gross margin; SG&A; capex; working capital; tax; cash conversion.

6. **Định giá và khuyến nghị**  
   FCFF/FCFE/multiples theo policy; WACC bridge; valuation bridge; sensitivity; upside/downside scenario.

7. **Rủi ro và catalyst**  
   Rủi ro theo cơ chế tài chính, không liệt kê chung chung.

8. **Phụ lục tài chính**  
   BCKQKD, CĐKT, LCTT, ratios, valuation assumptions, source map.

---

### P2 — Nâng cấp chart system

Mỗi biểu đồ phải có contract rõ:

| Loại biểu đồ | Quy chuẩn |
|---|---|
| Price chart | So sánh cổ phiếu với VNIndex, thời gian 1-5 năm, có mốc giá rõ |
| Revenue/margin chart | Bar doanh thu + line margin, không quá 2 trục nếu font nhỏ |
| Forecast chart | Tối đa 8-10 năm, highlight giai đoạn catalyst |
| Market share chart | Pie/donut chỉ dùng khi có ít nhóm; nếu nhiều nhóm dùng bar |
| Sensitivity table | Có ô base case highlight và diễn giải phía dưới |
| Source line | Đặt dưới chart bằng text thường, không nhúng quá nhỏ trong ảnh |

DHG hiện cần sửa ngay các biểu đồ trang 3 và trang 5: tăng kích thước, bỏ nguồn siêu nhỏ trong chart, tăng font trục, giảm số nhãn, đặt chú giải bên ngoài, và tránh dual-axis nếu không cần thiết.

---

### P3 — Bổ sung company-specific data pack cho toàn bộ universe

Muốn mở rộng 52 mã mà vẫn chất lượng, không thể để LLM tự suy luận từ vài bảng tài chính. Mỗi mã cần có **company profile artifact** ổn định:

```text
ticker
company_name
exchange
business_segments
product_groups
ETC_share
OTC_share
export_share
key_products
manufacturing_standards
plants_and_capacity
tender_groups
major_shareholders
strategic_partners
dividend_policy
capex_projects
regulatory_catalysts
API_exposure
FX_exposure
peer_group
```

Sau đó report writer chỉ được viết thesis từ artifact này, không viết theo prompt chung. Với DHG, nếu artifact chưa có product/channel/capacity/partner/tender data, hệ thống phải ghi “insufficient company-specific evidence”, không được viết generic.

---

### P4 — Chuyển narrative sang analyst reasoning chain

Mỗi nhận định nên theo cấu trúc:

```text
Số liệu quan sát được
→ Nguyên nhân vận hành
→ Tác động đến doanh thu/biên/vốn lưu động
→ Tác động đến valuation
→ Chỉ báo cần theo dõi
```

Ví dụ hiện tại DHG viết: “Biên gộp phụ thuộc API và tỷ giá.” Câu này đúng nhưng chưa đủ. Chuẩn tốt hơn là: “Nếu API nhập khẩu tăng x% và DHG không chuyển giá kịp ở kênh ETC do giá thầu cố định, gross margin có thể giảm y bps; với doanh thu 2026F z tỷ, tác động EBIT là n tỷ, tương đương m VND/cp trong DCF.” Đây mới là insight.

---

## Kết luận ưu tiên

Không nên tiếp tục “làm đẹp PDF” trước khi sửa model và data granularity. Thứ tự đúng là:

1. **Khóa financial sanity gates.**
2. **Bổ sung company-specific pharma data pack.**
3. **Thiết kế lại report schema theo FPTS analytical flow.**
4. **Sửa renderer: orphan page, chart font, table overflow, page density.**
5. **Nâng citation từ source list lên claim-level provenance.**
6. **Chạy regression trên DHG, DBD, IMP, TRA, DMC trước khi scale toàn universe.**

DHG có thể tiếp tục là mã pilot, nhưng tiêu chuẩn kiểm thử không nên là “PDF nhìn ổn hơn bản trước”. Tiêu chuẩn phải là: **một senior analyst có thể đọc báo cáo, kiểm lại số, hiểu driver, hiểu vì sao target price ra như vậy, và chỉ cần chỉnh judgment chứ không phải sửa lại mô hình từ đầu**.