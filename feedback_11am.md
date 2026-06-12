**Bối Cảnh**

Tôi đã rà soát toàn bộ 9 trang của [DHG_report.pdf](C:/Users/Admin/Desktop/multi-agent-equity-research/DHG_report.pdf), đối chiếu với 17 trang của [báo cáo FPTS DBD](<C:/Users/Admin/Desktop/multi-agent-equity-research/Bao_cao_cap_nhat_dinh_gia_CTCP_Duoc_Trang_thiet_bi_y_te_Binh_Dinh_HSX_DBD_0400ba27 (1).pdf>), đồng thời truy nguyên các vấn đề về code.

Kết luận thẳng: báo cáo DHG hiện vẫn giống **đầu ra tự động của mô hình tài chính** hơn là **báo cáo nghiên cứu cổ phiếu đã được chuyên viên biên tập**. Khoảng cách với FPTS chủ yếu đến từ dữ liệu nghiên cứu, logic lập luận và kiểm soát biên tập; không chỉ từ CSS hoặc số trang.

**Đánh Giá Tổng Quan**

| Tiêu chí | DHG hiện tại | FPTS tham chiếu |
|---|---|---|
| Độ sâu nghiên cứu doanh nghiệp | Chủ yếu dùng chỉ tiêu tài chính tổng hợp và nhận định ngành chung | Phân tích từng kênh, sản phẩm, nhà máy, thị phần, hợp đồng thầu và lộ trình |
| Storytelling | Lặp lại các biến ETC, API, biên gộp, FCFF | Mỗi chương trả lời một câu hỏi đầu tư cụ thể |
| Dữ liệu minh chứng | Nhiều trường thiếu, biểu đồ trống, nguồn chung chung | Mỗi luận điểm có số liệu, biểu đồ và nguồn đặt cạnh nhau |
| Ngôn ngữ | Trộn tiếng Việt và thuật ngữ tiếng Anh không kiểm soát | Thuần Việt; chỉ giữ thuật ngữ tài chính/ngành cần thiết |
| Mật độ trình bày | Trung bình khoảng 82% diện tích trắng | Khoảng 69%; không có trang gần trắng |
| Khả năng kiểm chứng định giá | Giá mục tiêu chưa reconcile rõ với bảng độ nhạy | Kết quả FCFF/FCFE, trọng số và giả định nối liền nhau |

## Problem Statement

### 1. Sai Sót Nghiêm Trọng Về Độ Tin Cậy Dữ Liệu

Một số biểu đồ không chỉ thiếu dữ liệu mà đang có logic thay thế sai bản chất:

- Khi thiếu doanh thu, code có thể dùng lịch sử FCF làm đại diện doanh thu.
- Biên EBITDA có thể được ước lượng bằng `biên ròng + 3 điểm phần trăm`.
- Doanh thu dự phóng của biểu đồ có thể được lấy từ `projected_fcf`.
- Lợi nhuận dự phóng được tính bằng biên ròng nhân với giá trị đang được gọi là doanh thu dự phóng.

Các logic này nằm tại [generate_charts.py](C:/Users/Admin/Desktop/multi-agent-equity-research/scripts/generate_charts.py:141), [generate_charts.py](C:/Users/Admin/Desktop/multi-agent-equity-research/scripts/generate_charts.py:154) và [generate_charts.py](C:/Users/Admin/Desktop/multi-agent-equity-research/scripts/generate_charts.py:178).

Đây là lỗi nghiêm trọng nhất: biểu đồ có thể trông hợp lệ về hình thức nhưng không đại diện đúng chỉ tiêu được ghi trên biểu đồ.

### 2. Giá Mục Tiêu Chưa Reconcile Với Phân Tích Độ Nhạy

Báo cáo công bố:

- Giá mục tiêu: `101.546 VND/cp`.
- WACC cơ sở: `13,8%`.
- Tăng trưởng dài hạn cơ sở: `3,0%`.

Tuy nhiên, ô tương ứng trong ma trận độ nhạy chỉ cho giá trị `91.271 VND/cp`. Báo cáo không giải thích phần chênh lệch khoảng `11,3%` đến từ FCFE, trọng số blend hay phương pháp định giá khác.

FPTS giải quyết vấn đề này bằng bảng kết quả FCFE/FCFF, trọng số từng phương pháp và giá mục tiêu làm tròn trên cùng một trang.

### 3. Báo Cáo Tự Mâu Thuẫn Về Trạng Thái Công Bố

Trang đầu hiển thị `NẮM GIỮ`, giá mục tiêu và upside như một báo cáo chính thức. Nhưng trang cuối lại ghi báo cáo đang được rà soát và khuyến nghị chưa được công bố chính thức.

Điều này làm người đọc không biết tài liệu là:

- Báo cáo gửi khách hàng;
- Bản nháp chuyên viên;
- Hay gói kiểm toán nội bộ.

Publish gate hiện đã bị tách khỏi lớp hiển thị quá mức, khiến `client_final` vẫn có thể xuất bản dù thiếu dữ liệu bắt buộc.

## Technical Deep-Dive

### 4. Thiếu Dữ Liệu Nhưng Không Giải Thích Đủ Nguyên Nhân

| Dữ liệu thiếu | Biểu hiện trong DHG | Nguyên nhân pipeline |
|---|---|---|
| Biến động giá YTD, 1T, 3T, 12T | Toàn bộ `N/A` | Không có lịch sử giá run-scoped; database và provider không khả dụng |
| Biểu đồ giá so với VNINDEX | Không xuất hiện | Không có `MarketDataArtifact` đủ dữ liệu |
| Cơ cấu cổ đông | Không có | View model vẫn hardcode `N/A` |
| So sánh doanh nghiệp cùng ngành | Trang tiêu đề nói có, nhưng không có peer | `peer_table=None` |
| Sự kiện hỗ trợ/catalyst cụ thể | Chỉ có nhận định chung | `catalyst_table=None` |
| EPS và P/E trailing | Không có trên trang đầu | Chưa được wire vào trading statistics |
| Lịch sử khuyến nghị | Không có | Chưa có artifact hoặc section tương ứng |
| Phân tích sản phẩm/kênh bán hàng | Không có số liệu | Chưa ingest dữ liệu phân khúc, thầu, thị phần |
| Cổ tức | Hiển thị dấu `—` | Không có dữ liệu nhưng cũng không có chú thích lý do |

Các placeholder và cấu trúc thiếu nằm tại [client_report_view_model.py](C:/Users/Admin/Desktop/multi-agent-equity-research/backend/reporting/client_report_view_model.py:1629) và [client_report_view_model.py](C:/Users/Admin/Desktop/multi-agent-equity-research/backend/reporting/client_report_view_model.py:1655).

Chính sách “luôn xuất với `N/A`” đang xung đột với mục tiêu tạo báo cáo chuyên nghiệp. Chính sách này phù hợp cho bản nháp, nhưng các trường bắt buộc như lịch sử giá, nguồn tài chính, peer và reconciliation định giá phải chặn bản khách hàng.

### 5. Phân Tích Đang Là Boilerplate Ngành, Không Phải Nghiên Cứu DHG

Nhiều kết luận được viết như sự thật về DHG nhưng không có bằng chứng DHG đi kèm:

- ETC là động lực tăng trưởng chính.
- OTC tăng trưởng thấp hơn và chỉ giúp giảm biến động.
- Chi phí phục vụ đấu thầu ETC không co giãn theo doanh thu.
- Chu kỳ phải thu bệnh viện thường kéo dài 60–90 ngày.
- Nâng chuẩn GMP-EU sẽ mở rộng khách hàng xuất khẩu.
- Chuyển từ generic sang branded generic sẽ cải thiện biên lợi nhuận.
- Trúng thêm thầu ETC là yếu tố hỗ trợ lớn nhất và gần nhất.

Những câu này được hardcode trong [narrative_builder.py](C:/Users/Admin/Desktop/multi-agent-equity-research/backend/reporting/narrative_builder.py:118), [narrative_builder.py](C:/Users/Admin/Desktop/multi-agent-equity-research/backend/reporting/narrative_builder.py:225) và [narrative_builder.py](C:/Users/Admin/Desktop/multi-agent-equity-research/backend/reporting/narrative_builder.py:227).

FPTS viết cùng chủ đề nhưng luôn chỉ rõ:

- Tỷ trọng doanh thu từng kênh.
- Giá trị trúng thầu và tăng trưởng so với cùng kỳ.
- Dòng thuốc tạo tăng trưởng.
- Thị phần và nhà cung cấp API.
- Thời điểm nhà máy dự kiến đạt chuẩn.
- Mức đóng góp doanh thu dự kiến.

Báo cáo DHG hiện kể “cơ chế có thể xảy ra”; FPTS chứng minh “điều gì đang xảy ra với doanh nghiệp”.

### 6. Storytelling Chưa Tạo Insight

Báo cáo DHG lặp lại nhiều lần cùng một chuỗi:

`ETC → doanh thu → API/tỷ giá → biên gộp → FCFF`.

Các câu về doanh thu `5.267 tỷ`, tăng trưởng `7,8%`, biên gộp `47,6%`, chuyển đổi tiền mặt `1,42 lần` và ETC/API xuất hiện trên nhiều trang nhưng không bổ sung bằng chứng mới.

Những điểm còn thiếu:

- Không có câu hỏi đầu tư trung tâm: “Vì sao nên sở hữu DHG tại thời điểm này?”
- Không có sự kiện thay đổi quan điểm so với báo cáo trước.
- Không có phân rã tăng trưởng theo giá, sản lượng, sản phẩm hoặc kênh.
- Không lượng hóa tác động: nếu biên gộp giảm 1 điểm phần trăm thì lợi nhuận và giá mục tiêu giảm bao nhiêu.
- Không phân biệt rõ dữ kiện, giả định, nhận định và rủi ro.
- Không có quan điểm trái chiều hoặc điều kiện khiến khuyến nghị sai.

FPTS tổ chức nội dung theo chuỗi:

`Dữ kiện mới → nguyên nhân → tác động lên phân khúc → tác động tài chính → thay đổi dự phóng → tác động định giá`.

### 7. Ngôn Ngữ Chưa Nhất Quán Và Mang Giọng Mô Hình

Các cụm từ làm giảm tính chuyên nghiệp:

- `Driver vận hành trọng yếu`
- `driver-based`
- `catalyst có tác động lớn nhất`
- `cạnh tranh generic gia tăng`
- `branded generic`
- `upside/downside`
- `terminal value`
- `driver có tác động lớn nhất tới giá trị`

Không cần loại bỏ toàn bộ thuật ngữ chuyên ngành. `ETC`, `OTC`, `API`, `FCFF`, `FCFE`, `WACC`, `P/E` có thể giữ lại nhưng phải định nghĩa khi xuất hiện lần đầu.

Các từ nên chuẩn hóa:

| Hiện tại | Nên sử dụng |
|---|---|
| Driver | Động lực hoặc biến số chính |
| Catalyst | Yếu tố hỗ trợ hoặc sự kiện có thể thúc đẩy giá |
| Upside/downside | Tiềm năng tăng/giảm giá |
| Generic | Thuốc generic; định nghĩa tại lần đầu |
| Branded generic | Thuốc generic có thương hiệu |
| Terminal value | Giá trị cuối kỳ |
| Driver-based forecast | Dự phóng dựa trên các biến số hoạt động |

Ngoài ra, các câu như “ma trận độ nhạy là bắt buộc chứ không phải tùy chọn” hoặc “không đơn thuần là liệt kê định tính” đang nói về quy trình làm báo cáo thay vì phân tích doanh nghiệp.

### 8. Cấu Trúc Trình Bày Chưa Đạt Chuẩn Broker

- DHG có 9 trang nhưng trung bình khoảng `82%` diện tích trắng; FPTS khoảng `69%`.
- Trang 2, 5, 7, 8 và 9 sử dụng diện tích kém.
- Nhiều biểu đồ nhỏ, gần trống hoặc không có nhãn số hữu ích.
- Trang 3–4 dùng bảng 10 năm với chữ rất nhỏ; khó đọc và không truyền tải insight.
- Không có đánh số biểu đồ/bảng thống nhất.
- Nguồn không đặt sát từng luận điểm quan trọng.
- Không có liên kết chéo giữa luận điểm, biểu đồ và phụ lục.
- Không có phụ lục nghiên cứu doanh nghiệp, lịch sử khuyến nghị và bảng giả định thay đổi.
- Thông tin chuyên viên, người phê duyệt và đơn vị phát hành còn mang tính placeholder.
- Tiêu đề chương vẫn là nhãn chung như “Dự phóng tài chính”, thay vì kết luận định hướng như FPTS.

### 9. Kiến Trúc Code Vẫn Chưa Thực Sự Động Theo Bằng Chứng

Mặc dù kế hoạch yêu cầu chương động, section builder vẫn tạo cố định tám chương cho mọi doanh nghiệp tại [client_section_builder.py](C:/Users/Admin/Desktop/multi-agent-equity-research/backend/reporting/client_section_builder.py:701).

Các vấn đề kiến trúc khác:

- `sector="Dược phẩm"` và hoạt động chính đang hardcode.
- Risk table dùng ba rủi ro chung cho toàn ngành.
- Agent narrative chỉ được dùng khi có manifest phù hợp; lần render hiện tại chủ yếu dùng deterministic template.
- Không có content gate kiểm tra lặp ý, pha trộn ngôn ngữ, claim thiếu citation hoặc insight không được lượng hóa.
- Không có điều kiện ẩn chương khi chart/table không đủ dữ liệu.
- Dữ liệu nguồn và narrative chưa được tổ chức thành luận điểm doanh nghiệp cụ thể.

## Strategic Recommendations

### Mức P0: Phải Sửa Trước Khi Gọi Là Báo Cáo Khách Hàng

1. Cấm hoàn toàn việc dùng FCF làm doanh thu, cộng biên tùy ý hoặc zero-fill để tạo biểu đồ.
2. Bắt buộc reconcile giá mục tiêu với FCFF, FCFE, trọng số và ô giả định cơ sở.
3. Tách rõ `analyst_draft` và `client_final`; bản final phải bị chặn nếu thiếu lịch sử giá, nguồn tài chính, định giá hoặc citation bắt buộc.
4. Loại bỏ mọi luận điểm doanh nghiệp không có evidence artifact và nguồn cụ thể.
5. Xây dựng kiểm tra ngôn ngữ để chặn thuật ngữ Anh–Việt không thuộc whitelist.

### Mức P1: Xây Dựng Lại Storytelling

Mỗi chương phải được sinh từ một `EditorialEvidenceBlock`:

`Kết luận cụ thể → dữ kiện doanh nghiệp → nguyên nhân → tác động tài chính → tác động định giá → điều kiện cần theo dõi → nguồn`.

Tiêu đề phải là kết luận, ví dụ:

- Thay vì `Động lực tăng trưởng`: `Tăng trưởng ETC chưa đủ bù đắp đà chậm lại của OTC`.
- Thay vì `Động lực biên lợi nhuận`: `Biên gộp có thể chịu áp lực nếu giá API tăng nhanh hơn khả năng điều chỉnh giá bán`.
- Thay vì `Rủi ro và sự kiện trọng yếu`: `Khả năng duy trì biên gộp là biến số quyết định khuyến nghị NẮM GIỮ`.

### Mức P2: Hoàn Thiện Kiến Trúc Báo Cáo

- Trang đầu: biểu đồ giá thật, EPS/P/E trailing, cơ cấu cổ đông, thông tin doanh nghiệp và luận điểm ngắn.
- Thân bài: phân tích động theo phân khúc có dữ liệu, không ép mọi ticker vào cùng khung ETC/OTC.
- Trang định giá: kết quả FCFF/FCFE, trọng số, giả định thay đổi và reconciliation.
- Tóm tắt tài chính: chỉ giữ `1 năm thực tế + 3 năm dự phóng`.
- Phụ lục: dữ liệu chi tiết, lịch sử khuyến nghị, giả định và nguồn.

**Kết Luận**

Vấn đề cốt lõi không phải báo cáo “chưa giống FPTS về màu sắc”. Hệ thống hiện thiếu một lớp nghiên cứu doanh nghiệp có bằng chứng và một lớp biên tập chuyên nghiệp. Khi chưa sửa hai lớp này, việc tiếp tục điều chỉnh CSS hoặc tăng số trang chỉ làm báo cáo trông dài hơn, không làm báo cáo đáng tin hoặc lôi cuốn hơn.