# Kế hoạch tái kiến trúc format báo cáo theo chuẩn FPTS

## 1. Context

Mục tiêu là đưa báo cáo HTML/PDF của hệ thống tiến gần chất lượng biên tập của báo cáo tham chiếu FPTS DBD, nhưng vẫn giữ kiến trúc ticker-agnostic và dữ liệu được sinh từ artifacts có kiểm định.

Báo cáo tham chiếu không chỉ khác về màu sắc hoặc font. Đây là một hệ thống editorial layout hoàn chỉnh, trong đó nội dung, biểu đồ, bảng và phân trang được tổ chức theo luận điểm phân tích thay vì theo ranh giới module backend.

## 2. Problem Statement

### 2.1. Khoảng cách kiến trúc

| Dimension | Báo cáo tham chiếu FPTS | Báo cáo hiện tại | Tác động |
|---|---|---|---|
| Pagination | Continuous editorial flow; section có thể kéo dài nhiều trang | Ép chính xác 8 section và chèn page break sau mỗi section | Nhiều trang trắng hoặc chỉ dùng 15-35% diện tích |
| Trang đầu | Dashboard hai cột, rating nổi bật, chart giá, thông tin giao dịch, thesis | Recommendation banner tách thành một trang gần như trắng; snapshot sang trang sau | Mất trang quan trọng nhất và tạo cảm giác bản nháp |
| Nội dung thân bài | Luận điểm, số liệu và chart được đặt cạnh nhau | Narrative, chart và bảng nằm ở các trang/section tách biệt | Người đọc khó theo dõi cơ chế tác động |
| Bảng | Bảng có hierarchy, subtotal, màu tăng/giảm, mật độ cao | Một renderer chung cho mọi bảng, ít hierarchy | Bảng đúng số nhưng không truyền đạt insight |
| Biểu đồ | Chart nhỏ, nhiều loại, gắn trực tiếp với từng luận điểm | Chỉ C1/C2/C4 được wire vào view model; chart thường full-width | Thiếu bằng chứng trực quan và lãng phí diện tích |
| Financial appendix | Một trang hai cột gồm KQKD, CĐKT và ratios | Các bảng rộng 9 năm trải trên nhiều trang | Khó đọc, khó đối chiếu, nhiều khoảng trắng |
| Header/footer | Logo, ticker, page number và brand lặp lại ổn định | Header có ticker/date nhưng footer không cố định theo từng trang | Thiếu cảm giác báo cáo xuất bản chuyên nghiệp |
| Ngôn ngữ | Thuần Việt, nhãn section nhất quán | Nhiều tiêu đề tiếng Anh | Trải nghiệm đọc thiếu nhất quán |

### 2.2. Root causes trong code

1. `backend/reporting/templates/report.html.j2` chèn `.page-break` giữa mọi section.
2. `backend/reporting/client_section_builder.py` ánh xạ một section logic thành một page vật lý.
3. `.client-report-page`, `.model-table-block`, `table` và chart đều dùng `page-break-inside: avoid`, khiến các khối lớn bị đẩy nguyên sang trang sau.
4. `backend/reporting/client_report_view_model.py::_charts()` chỉ đăng ký C1, C2 và C4 dù chart engine có C1-C8.
5. `_render_table()` là renderer duy nhất cho mọi loại bảng, không hỗ trợ row hierarchy, subtotal, variance colors hoặc compact financial statements.
6. `layout_audit.py` mới kiểm tra overflow theo heuristic, chưa đo mức sử dụng diện tích, trang trắng, orphan heading hoặc vị trí chart.
7. PDF renderer chưa tạo page number/header/footer bằng print CSS; template đang mô phỏng header bằng HTML block trong từng section.

## 3. Technical Deep-Dive

### 3.1. Đặc điểm kiến trúc của mẫu FPTS

#### Trang mở đầu

- Header ba tầng: brand, loại báo cáo/ngày, tên doanh nghiệp.
- Grid hai cột khoảng 42/58.
- Cột trái chứa analyst, chart giá, market statistics và company profile.
- Cột phải chứa giá hiện tại, giá mục tiêu, recommendation, thesis, triển vọng và yếu tố theo dõi.
- Toàn bộ trang có mật độ cao nhưng vẫn rõ hierarchy.

#### Trang phân tích hoạt động

- Mỗi trang xoay quanh một luận điểm cụ thể, không phải một module chung chung.
- Heading cấp cao ngắn; subheading thường là một kết luận có định hướng.
- Chart hoặc bảng nằm ngay sau/đối diện đoạn giải thích.
- Màu xanh lá/đỏ chỉ dùng để mã hóa tác động tích cực/tiêu cực.
- Footnote nguồn đặt sát artifact, không dồn toàn bộ về cuối báo cáo.

#### Trang triển vọng

- Dùng grid hai cột lặp lại: chart bên trái, narrative bên phải.
- Có thể đặt hai luận điểm hoàn chỉnh trên cùng một trang.
- Chart có kích thước nhỏ vừa đủ để đọc và luôn có caption nguồn.

#### Trang định giá

- Ngắn gọn, tập trung vào kết quả, assumptions và bridge.
- Dùng nhiều bảng nhỏ thay vì một bảng valuation model 20 dòng x 9 năm.
- Giá mục tiêu và phương pháp định giá được nhấn mạnh bằng typography và màu.

#### Trang financial summary

- Dùng layout hai cột độc lập.
- KQKD, CĐKT, ratios và working-capital indicators được đặt trên cùng một trang.
- Chỉ hiển thị 1 năm lịch sử và 3 năm dự phóng để giữ khả năng đọc.

### 3.2. Nguyên tắc thiết kế mới

1. Section logic không đồng nghĩa với page vật lý.
2. Nội dung phải chảy liên tục; chỉ hard page-break tại các mốc editorial quan trọng.
3. Chart/table phải colocate với narrative giải thích chúng.
4. Main report ưu tiên insight; bảng chi tiết 9 năm chuyển xuống appendix.
5. Mỗi trang phải đạt mức sử dụng diện tích tối thiểu, trừ disclaimer cuối báo cáo.
6. Mọi component phải có variant rõ ràng thay vì một renderer dùng cho tất cả.

## 4. Strategic Recommendations

## Phase 0 - Baseline và visual acceptance harness

### Scope

- Tạo tập ảnh baseline cho các trang đại diện của PDF tham chiếu và PDF hiện tại.
- Xây dựng script render PDF thành PNG và đo:
  - tỷ lệ vùng trắng;
  - số trang gần trắng;
  - bounding box nội dung;
  - số chart/table trên mỗi trang;
  - orphan heading và bảng bị tách.
- Lưu golden snapshots cho DBD và DHG.

### Files

- Tạo `scripts/audit_report_layout.py`.
- Mở rộng `backend/reporting/layout_audit.py`.
- Tạo `tests/reporting/test_visual_layout_contract.py`.

### Acceptance

- Không còn trang chỉ chứa recommendation banner hoặc header.
- Không có trang thân bài sử dụng dưới 55% chiều cao khả dụng.
- Có artifact layout audit JSON cho từng lần render.

## Phase 1 - Tái cấu trúc pagination engine

### Scope

- Bỏ quy tắc một section bằng một page.
- Thay `.page-break` giữa mọi section bằng break policy:
  - `break-before: page` cho major chapter;
  - `break-inside: avoid` chỉ cho chart/table nhỏ;
  - cho phép bảng dài và narrative tự chảy qua trang.
- Loại `page-break-inside: avoid` khỏi `.client-report-page`.
- Tách logical sections khỏi physical page composition.

### Files

- `backend/reporting/templates/report.html.j2`
- `backend/reporting/templates/report.css`
- `backend/reporting/client_section_builder.py`
- `backend/reporting/html_renderer.py`
- `tests/unit/test_html_renderer.py`
- `tests/unit/test_client_report_contract.py`

### Acceptance

- Không còn blank-page regression.
- DBD/DHG dùng 12-18 trang tùy dữ liệu, không bị khóa ở 8 section hoặc 12 trang.
- Heading không đứng một mình ở cuối trang.

## Phase 2 - Trang mở đầu theo kiến trúc broker report

### Scope

- Gộp recommendation banner vào trang snapshot.
- Xây dựng header ba tầng và grid hai cột.
- Sidebar gồm analyst/team, price chart, trading statistics, ownership/company profile.
- Main column gồm recommendation hero, thesis bullets, business outlook và watchlist.
- Không tạo trang recommendation độc lập.

### Components mới

- `report-brand-header`
- `recommendation-hero`
- `snapshot-sidebar`
- `market-stat-grid`
- `thesis-checklist`
- `watchlist-box`

### Acceptance

- Trang 1 sử dụng trên 80% diện tích khả dụng.
- Giá hiện tại, giá mục tiêu, upside và rating nhìn thấy trong 3 giây đầu.
- C1 nằm trong sidebar; thiếu C1 thì dùng market-stat block, không dùng placeholder rỗng.

## Phase 3 - Editorial section composition

### Scope

- Thay các page generic như `Company Overview`, `Financial Performance` bằng chapter tiếng Việt có luận điểm.
- Hỗ trợ block composition:
  - text + chart 50/50;
  - chart + text 45/55;
  - two charts;
  - full-width evidence table;
  - callout conclusion.
- Đặt chart ngay cạnh narrative liên quan.
- Wire C3, C5, C6, C7 và C8 vào view model và section builder.

### Files

- `backend/reporting/client_section_builder.py`
- `backend/reporting/client_report_view_model.py`
- `scripts/generate_charts.py`
- `backend/reporting/chart_generator.py`

### Acceptance

- Mỗi chapter hoạt động/triển vọng có ít nhất một evidence artifact nếu dữ liệu tồn tại.
- Không có chart được tạo nhưng không được sử dụng.
- Không có chart full-width nếu nội dung chỉ cần half-width.

## Phase 4 - Hệ thống bảng chuyên biệt

### Scope

- Thay `_render_table()` duy nhất bằng renderer theo loại:
  - `variance-table`: actual vs prior period, màu tăng/giảm;
  - `forecast-summary-table`: 1A + 3F;
  - `valuation-summary-table`;
  - `valuation-bridge-table`;
  - `financial-statement-compact`;
  - `sensitivity-matrix`;
  - `risk-monitor-table`.
- Hỗ trợ subtotal, indent line items, highlighted output rows và negative-number parentheses.
- Main report chỉ giữ bảng cô đọng; bảng 9 năm chuyển appendix.

### Acceptance

- Bảng main report không vượt 6 cột dữ liệu, trừ sensitivity.
- Trang financial summary chứa tối thiểu ba khối tài chính trên một trang A4.
- Positive/negative variance dùng màu có kiểm soát và vẫn đọc được khi in grayscale.

## Phase 5 - Typography, brand system và chart styling

### Scope

- Chuẩn hóa ngôn ngữ tiêu đề sang tiếng Việt.
- Thiết lập design tokens cho màu, font size, spacing, border và table density.
- Dùng Noto Sans đầy đủ Regular/Medium/SemiBold/Bold.
- Chỉnh chart theo phong cách broker:
  - kích thước 6-8pt;
  - legend ngắn;
  - nhãn số trực tiếp;
  - không title tiếng Anh trong chart;
  - caption nguồn tiếng Việt;
  - palette navy/green/red nhất quán.

### Files

- `backend/reporting/templates/report.css`
- `backend/reporting/chart_generator.py`
- `scripts/setup_fonts.py`
- `assets/fonts/`

### Acceptance

- Không có heading tiếng Anh trong PDF client-facing.
- Font tiếng Việt đúng trên Chrome và fallback PDF renderer.
- Chart đọc được ở kích thước half-page.

## Phase 6 - Header/footer, appendix và disclaimer

### Scope

- Dùng print CSS running header/footer hoặc renderer-supported page header/footer.
- Header: brand, ticker.
- Footer: nguồn/website nội bộ, ngày, page number.
- Tạo appendix riêng:
  - detailed financial model;
  - assumptions;
  - citation/source list;
  - disclaimer.
- Disclaimer cuối báo cáo có layout ba cột/thông tin liên hệ khi metadata tồn tại.

### Acceptance

- Mỗi trang sau trang 1 có ticker và page number.
- Appendix không làm gián đoạn mạch luận điểm chính.
- Disclaimer không chứa dữ liệu giả hoặc analyst identity giả.

## Phase 7 - Visual QA và multi-ticker regression

### Scope

- Render DBD, DHG, IMP, DMC và TRA bằng cùng template.
- Kiểm tra pixel/screenshot và layout metrics.
- Thêm gate cho:
  - blank-page ratio;
  - content utilization;
  - chart/table overflow;
  - missing page number;
  - untranslated heading;
  - unused chart artifacts.

### Acceptance

| Metric | Target |
|---|---:|
| Trang gần trắng trong thân báo cáo | 0 |
| Trang có content utilization dưới 55% | <= 1, không tính disclaimer |
| Chart artifacts được sử dụng | >= 80% |
| Bảng main report quá 7 cột dữ liệu | 0 |
| Heading tiếng Anh client-facing | 0 |
| Overflow/tofu/mojibake | 0 |
| Multi-ticker visual regression pass | 5/5 |

## 5. Execution Order

| Priority | Phase | Rationale |
|---:|---|---|
| P0 | Phase 0-1 | Pagination hiện là nguyên nhân trực tiếp tạo trang trắng và phá mật độ |
| P0 | Phase 2 | Trang đầu quyết định cảm nhận chất lượng toàn báo cáo |
| P1 | Phase 3-4 | Colocation và bảng chuyên biệt tạo ra giá trị đọc thực tế |
| P1 | Phase 5 | Typography/chart styling chỉ hiệu quả sau khi grid ổn định |
| P2 | Phase 6-7 | Hoàn thiện publication system và chống regression |

## 6. Files Most Likely To Change

| File | Expected change |
|---|---|
| `backend/reporting/client_section_builder.py` | Tái cấu trúc composition và component rendering |
| `backend/reporting/client_report_view_model.py` | Bổ sung page-ready blocks, chart registry và compact tables |
| `backend/reporting/templates/report.html.j2` | Bỏ page-per-section, thêm running document shell |
| `backend/reporting/templates/report.css` | Grid, break policy, table variants, typography tokens |
| `backend/reporting/chart_generator.py` | Chart style và compact rendering |
| `backend/reporting/html_renderer.py` | Metadata/header/footer và document composition |
| `backend/reporting/pdf_renderer.py` | Page numbering và consistent Chrome print path |
| `backend/reporting/layout_audit.py` | Visual/layout metrics thực tế |

## 7. Definition of Done

Format rebuild được coi là hoàn thành khi báo cáo không chỉ có cùng màu sắc, mà đạt được các đặc điểm kiến trúc của mẫu:

1. Trang đầu là dashboard đầy đủ, không có trang recommendation riêng.
2. Nội dung chảy liên tục và không còn trang trắng do forced page break.
3. Luận điểm, biểu đồ và bảng bằng chứng được đặt cùng ngữ cảnh.
4. Financial summary cô đọng trên một trang; bảng chi tiết nằm appendix.
5. Định giá được trình bày bằng các bảng kết quả/assumption/bridge rõ ràng.
6. Header/footer/page number ổn định trên toàn PDF.
7. Visual layout gate chạy tự động và pass trên tối thiểu năm ticker.
