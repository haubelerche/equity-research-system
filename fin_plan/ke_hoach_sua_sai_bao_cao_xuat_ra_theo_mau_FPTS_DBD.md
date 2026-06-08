# CORE PLAN — Sửa lỗi nền tảng sinh báo cáo equity research

## 1. Mục tiêu sửa core

Mục tiêu không phải hard-code theo một mã cổ phiếu cụ thể. Mục tiêu là sửa pipeline sinh báo cáo để mọi ticker đều xuất ra được báo cáo equity research đúng chuẩn:

* Có cấu trúc report chuyên nghiệp.
* Có số liệu đầy đủ, đúng kỳ, đúng đơn vị.
* Có phân tích thực chất, không chỉ liệt kê dữ liệu.
* Có valuation reproducible bằng code.
* Có citation rõ ràng nhưng không làm rối người đọc.
* Không lộ thuật ngữ backend, warning kỹ thuật, tier, database, gate, artifact.
* Không để LLM tự bịa hoặc tự tính số tài chính quan trọng.

DBD/FPTS chỉ dùng làm ví dụ benchmark để hiểu chuẩn đầu ra, không được hard-code ticker, số liệu, ngành hàng, luận điểm hoặc layout riêng cho DBD.

---

## 2. Các lỗi core cần sửa

### 2.1. Lỗi cấu trúc báo cáo

Hiện report đang sinh theo kiểu ghép section rời rạc, thiếu logic của một equity research report. Cần chuẩn hóa lại skeleton chung:

1. Investment snapshot
2. Luận điểm đầu tư chính
3. Tổng quan doanh nghiệp
4. Cập nhật kết quả kinh doanh
5. Phân tích theo mảng/kênh/driver
6. Triển vọng và dự phóng
7. Định giá và khuyến nghị
8. Rủi ro/yếu tố theo dõi
9. Bảng tài chính lịch sử và dự phóng
10. Phụ lục/citation appendix nếu cần

Không để các phần bị gộp lẫn như: tổng quan doanh nghiệp lẫn với định giá, triển vọng lẫn với rủi ro, cập nhật KQKD lẫn với mô tả ngành.

---

### 2.2. Lỗi sinh nội dung quá nông

Report hiện có xu hướng viết chung chung, thiếu insight và thiếu phân tích theo driver. Cần sửa Report Writer để mỗi section phải dựa trên artifact phân tích đã có, không viết bằng prompt trống.

Mỗi phần phân tích phải trả lời tối thiểu:

* Chỉ tiêu nào đang thay đổi?
* Thay đổi bao nhiêu?
* Nguyên nhân đến từ đâu?
* Tác động tới doanh thu, biên lợi nhuận, dòng tiền hoặc định giá là gì?
* Điều gì cần theo dõi tiếp?
* Có nguồn hoặc dữ liệu nào chứng minh không?

Không cho sinh đoạn văn kiểu “doanh nghiệp có triển vọng tích cực” nếu không có số liệu, catalyst hoặc driver hỗ trợ.

---

### 2.3. Lỗi tính toán tài chính và valuation

Đây là lỗi nghiêm trọng nhất. Cần khóa nguyên tắc:

* LLM không được tự tính số liệu tài chính.
* Toàn bộ ratios, margins, growth, FCFF, FCFE, WACC, equity value, target price phải tính bằng code.
* Report chỉ được đọc valuation artifact đã khóa.
* Nếu valuation artifact fail kiểm định thì không được export report.

Cần đặc biệt sửa FCFE:

```text
FCFE = Net Income 
     + D&A 
     - CAPEX 
     - ΔNWC 
     + Net Borrowing
```

`Net Borrowing` không được đoán bằng LLM. Phải lấy từ mô hình dự phóng bảng cân đối hoặc lịch vay nợ:

```text
Net Borrowing = Debt Ending - Debt Beginning
```

Trong đó Debt phải bao gồm đúng vay ngắn hạn + vay dài hạn có tính chất nợ vay, không lấy toàn bộ nợ phải trả.

Nếu hệ thống không dự phóng được debt schedule thì phải fallback:

* FCFE không được dùng làm valuation chính; hoặc
* dùng FCFF làm primary valuation;
* hoặc yêu cầu analyst nhập debt assumptions;
* tuyệt đối không được tự gán net borrowing tùy tiện.

---

### 2.4. Lỗi thiếu reconciliation giữa 3 báo cáo tài chính

Pipeline hiện cần bắt buộc có kiểm tra liên kết giữa:

* Báo cáo kết quả kinh doanh
* Bảng cân đối kế toán
* Lưu chuyển tiền tệ
* Dự phóng valuation

Các check tối thiểu:

```text
Revenue growth khớp doanh thu từng năm
Gross profit = Revenue - COGS
Gross margin = Gross profit / Revenue
EBIT margin = EBIT / Revenue
Net margin = Net income / Revenue
Total assets = Total liabilities + Equity
Ending cash khớp cash flow nếu có đủ dữ liệu
Debt ending khớp debt schedule
Shares outstanding khớp EPS và target price
Equity value / shares = target price
```

Nếu fail bất kỳ check trọng yếu nào thì phải block export hoặc chuyển sang Needs Review.

---

### 2.5. Lỗi forecast không driver-based

Dự phóng hiện không được chỉ kéo CAGR hoặc tăng trưởng tuyến tính. Cần sửa forecast engine theo hướng driver-based.

Tùy từng ticker và dữ liệu có sẵn, forecast phải ưu tiên:

* Doanh thu theo mảng/kênh/sản phẩm nếu có.
* Biên lợi nhuận gộp theo mix sản phẩm hoặc giá vốn.
* SG&A theo tỷ lệ doanh thu hoặc theo lịch sử.
* CAPEX theo kế hoạch đầu tư hoặc tỷ lệ tài sản/doanh thu.
* Working capital theo số ngày phải thu, tồn kho, phải trả.
* Debt theo nhu cầu funding, CAPEX và chính sách tài chính.

Nếu không có dữ liệu chi tiết, hệ thống được phép dùng top-down forecast nhưng phải ghi rõ assumption và confidence thấp hơn.

---

### 2.6. Lỗi citation gây rối người đọc

Citation cần phục vụ kiểm chứng, không được làm report giống log kỹ thuật.

Cần sửa theo nguyên tắc:

* Trong thân report chỉ hiển thị citation sạch, ngắn, dễ đọc.
* Không hiện `citation_json`, `source_id`, `chunk_id`, `tier`, `database`, `gate`, `artifact`.
* Citation map chi tiết đưa vào appendix hoặc file audit riêng.
* Mỗi claim định lượng phải trỏ về fact record hoặc source hợp lệ.
* Không có nguồn thì không sinh claim chắc chắn.

---

### 2.7. Lỗi warning/backend leakage

Báo cáo cuối không được chứa các nội dung kiểu:

* Warning kỹ thuật
* Backend tier
* Database status
* Missing artifact
* Model confidence thô
* Gate failed/internal logs
* “Generated by AI”
* Debug note
* JSON dump
* Placeholder rỗng

Các thông tin này chỉ được nằm trong evaluation report nội bộ, không xuất hiện trong PDF/HTML gửi người đọc.

---

### 2.8. Lỗi bảng và biểu đồ

Bảng và biểu đồ phải là artifact có kiểm định, không phải ảnh/trang trí.

Cần sửa:

* Bảng phải đủ số liệu, đúng đơn vị, đúng format tiếng Việt.
* Biểu đồ phải lấy từ cùng data source với bảng.
* Không để biểu đồ lệch số với narrative.
* Không để bảng vỡ layout, mất cột, sai font tiếng Việt.
* Bảng tài chính dự phóng phải có ít nhất 3 khối: KQKD, CĐKT, chỉ số tài chính.
* Các bảng valuation phải có assumptions, output và reconcile rõ ràng.

---

### 2.9. Lỗi thiếu report quality gate

Trước khi export, bắt buộc chạy quality gate:

1. Structure gate: đủ section bắt buộc.
2. Numeric gate: số liệu khớp structured data.
3. Valuation gate: target price reproduce được.
4. Citation gate: claim định lượng có citation.
5. Narrative gate: không có đoạn chung chung thiếu căn cứ.
6. Layout gate: PDF/HTML không vỡ bảng, không lỗi font.
7. Leakage gate: không có thuật ngữ backend/debug/warning.

Chỉ export khi pass. Nếu fail thì xuất evaluation report cho developer, không xuất báo cáo final cho end-user.

---

## 3. Việc Claude cần làm

### Step 1 — Tách report template khỏi ticker

Tạo template report chung, không phụ thuộc DBD/DHG/IMP hay bất kỳ ticker nào. Template chỉ định nghĩa section, required inputs, required tables, required charts và quality rules.

### Step 2 — Chuẩn hóa financial artifact

Tạo schema thống nhất cho:

* Historical financials
* Forecast financials
* Segment/channel drivers
* DCF assumptions
* FCFF output
* FCFE output
* Multiples output
* Sensitivity output
* Citation map

Report Writer chỉ được đọc các artifact này.

### Step 3 — Sửa valuation engine

Tính lại FCFF/FCFE bằng code. Đặc biệt sửa `net borrowing` trong FCFE bằng debt schedule hoặc balance sheet forecast. Không có debt forecast thì không được tự đoán.

### Step 4 — Thêm validation/reconciliation

Tạo validator cho toàn bộ report trước export. Mọi số trong narrative, bảng và biểu đồ phải trace được về artifact.

### Step 5 — Sửa citation renderer

Tách citation nội bộ và citation hiển thị. Thân report chỉ hiển thị citation sạch. Audit map để riêng.

### Step 6 — Sửa PDF/HTML renderer

Loại bỏ mọi warning/debug/backend term. Chuẩn hóa font tiếng Việt, bảng, biểu đồ, spacing, header/footer và format số.

### Step 7 — Thêm regression test đa ticker

Không test bằng một ticker duy nhất. Tạo test cho ít nhất 5 mã MVP để đảm bảo fix là core, không hard-code theo DBD.

---

## 4. Acceptance criteria

Một bản sửa được coi là đạt khi:

* Cùng một pipeline chạy được nhiều ticker mà không hard-code logic riêng.
* Report có đủ cấu trúc equity research chuẩn.
* FCFF và FCFE reproduce được từ valuation artifact.
* Net borrowing trong FCFE lấy từ debt forecast hoặc bị flag thiếu assumption.
* Target price tính lại được từ equity value và shares outstanding.
* Không có warning/backend/debug text trong PDF/HTML final.
* Citation sạch, không gây rối người đọc.
* Bảng và biểu đồ không lệch số với narrative.
* Quality gate chặn được report sai số, thiếu citation hoặc valuation không khớp.
* Regression test pass trên nhiều ticker, không chỉ ticker mẫu.
