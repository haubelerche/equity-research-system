# OCR pipeline

Cập nhật: 2026-06-13

## Context

OCR pipeline xử lý các tài liệu công bố dạng PDF scan, đặc biệt báo cáo tài chính tiếng Việt không có text layer ổn định. OCR chỉ là bước tạo dữ liệu ứng viên và evidence discovery; nó không được xem là nguồn sự thật tài chính cho valuation hoặc report final.

## Problem Statement

PDF scan có rủi ro nhận dạng sai ký tự, dấu tiếng Việt, dấu âm, dấu phân tách nghìn, hàng/cột bảng và đơn vị. Nếu OCR output được đưa trực tiếp vào canonical facts hoặc valuation, hệ thống có thể tạo sai lệch trọng yếu nhưng vẫn có vẻ hợp lệ. Vì vậy OCR phải đi qua validation, reconciliation và promotion trước khi fact được dùng downstream.

## Technical Deep-Dive

### 1. Dependency runtime

| Thành phần | Vai trò | Khai báo hiện tại |
|---|---|---|
| Tesseract OCR | Engine nhận dạng ký tự | Dockerfile cài `tesseract-ocr` |
| Vietnamese language data | Nhận dạng tiếng Việt | Dockerfile cài `tesseract-ocr-vie` |
| Poppler | Render PDF page sang image | Dockerfile cài `poppler-utils` |
| `pytesseract` | Python binding cho Tesseract | `requirements.txt` |
| `pdf2image` | Chuyển PDF sang image | `requirements.txt` |
| Pillow | Xử lý image | `requirements.txt` |
| `pdfplumber` | Trích text/table khi PDF có text layer | `requirements.txt` |

### 2. Luồng xử lý

| Bước | Module/script | Output |
|---|---|---|
| Discovery | `backend/documents/official_document_discovery.py`, `backend/documents/connectors/` | Candidate source documents |
| Fetch/store | Document fetch/store layer | PDF trong `sources` bucket |
| Text extraction | `backend/documents/pdf_extractor.py` | Text/table nếu PDF có text layer |
| OCR fallback | `pytesseract` + `pdf2image` | OCR text và page-level artifacts |
| Candidate fact extraction | `backend/documents/ocr_candidate_facts.py` | Candidate quantitative facts |
| Validation | `backend/documents/ocr_validation.py` | Validation status, warnings |
| Reconciliation | `backend/documents/ocr_reconciliation.py` | Conflict/resolution status |
| Promotion | `backend/documents/fact_promotion.py` | Promoted facts hoặc blocked candidates |

### 3. Gate policy

`OCR_EXPORT_GATE` cho phép draft mode đi tiếp để reviewer nhìn thấy dữ liệu còn unresolved, nhưng final mode phải fail nếu có candidate fact định lượng còn `promotion_status == "blocked"`. Các lý do block thường gặp gồm `validation_failed`, `reconciliation_not_run`, `conflicted` hoặc `promotion_blocked`.

### 4. Smoke test

```powershell
python scripts/check_ocr_runtime.py
```

Lệnh này kiểm tra Tesseract, Poppler và các Python package cần thiết. Nó nên chạy trước khi bật `--ocr` trong full pipeline hoặc trước khi build Docker image production cho môi trường có PDF scan.

### 5. Data governance

| Quy tắc | Lý do |
|---|---|
| OCR text không được dùng trực tiếp làm canonical fact | OCR có xác suất lỗi cao hơn structured API và official text layer |
| Candidate fact phải có source document id, page/region nếu có, metric id và period | Reviewer cần truy ngược về vị trí trong tài liệu |
| Mọi conflict phải được reconcile hoặc block | Không được để report chọn nguồn thuận tiện hơn |
| Unit và sign convention phải được kiểm tra | Sai đơn vị hoặc dấu âm làm lệch valuation |

## Strategic Recommendations

| Ưu tiên | Hành động |
|---|---|
| P0 | Không bypass OCR validation/reconciliation trong final export |
| P0 | Lưu OCR artifacts đủ metadata để reviewer kiểm tra lại page nguồn |
| P1 | Thêm golden OCR fixtures cho các mẫu BCTC scan phổ biến |
| P1 | Chuẩn hóa font/render environment trong Docker để OCR và PDF output ổn định |
| P2 | Nếu OCR trở thành bottleneck latency, cache page images và OCR text theo checksum tài liệu |
