# Nguồn dữ liệu và ingestion

Cập nhật: 2026-06-13

## Context

Hệ thống thu thập dữ liệu tài chính, tài liệu công bố, catalyst/news và dữ liệu thị trường cho universe dược/y tế Việt Nam. Dữ liệu thô không được dùng trực tiếp trong valuation hoặc report; nó phải đi qua normalization, reconciliation, source-tier policy và snapshot readiness.

## Problem Statement

Nguồn dữ liệu Việt Nam thường không đồng nhất về định dạng, encoding, tên chỉ tiêu, đơn vị, kỳ báo cáo và chất lượng PDF. Nếu ingestion chỉ crawl dữ liệu và để report writer tự diễn giải, rủi ro sai số tài chính sẽ rất cao. Pipeline cần phân biệt rõ official source, aggregator/API, OCR candidate và canonical fact.

## Technical Deep-Dive

### 1. Nhóm nguồn

| Nhóm | Module | Mục đích |
|---|---|---|
| Financial statements API | `scripts/connectors/vnstock_finance_connector.py` | Lấy báo cáo tài chính, ratios, raw API payload |
| Market price | `scripts/connectors/vnstock_price_connector.py`, `backend/reporting/market_data_artifact.py` | Giá hiện tại/lịch sử, market snapshot, chart input |
| Company metadata | `scripts/connectors/vnstock_company_connector.py` | Hồ sơ công ty, thông tin bổ trợ |
| Official documents | `backend/documents/connectors/` | Company IR, HOSE, HNX, SSC disclosures |
| Catalyst feeds | `scripts/connectors/catalyst_*.py`, `backend/catalysts/` | DAV, BHYT, HOSE, tender events |
| News/evidence | `backend/news/` | Thu thập và kiểm tra narrative evidence |
| Golden/manual data | `config/dataset/golden/`, `config/dataset/mvp/` | Bootstrap, fixtures, regression tests |

### 2. Official document flow

| Bước | Ý nghĩa |
|---|---|
| Discovery | Tìm tài liệu từ connector chính thức hoặc source catalog |
| Ranking | Chọn tài liệu phù hợp theo ticker, năm, loại nguồn và độ tin cậy |
| Fetch/store | Lưu binary vào `sources` bucket theo key chuẩn |
| Extract | Dùng text layer nếu có; dùng OCR nếu scan |
| Candidate facts | Tạo fact ứng viên từ bảng/text/OCR |
| Validation | Kiểm tra đơn vị, kỳ, metric mapping, format |
| Reconciliation | Đối chiếu nguồn khác hoặc canonical records |
| Promotion | Chỉ fact đạt policy mới được dùng downstream |

### 3. OCR policy

OCR là cơ chế hỗ trợ discovery, không phải nguồn sự thật tài chính. Candidate facts từ OCR phải qua validation và reconciliation. Gate `OCR_EXPORT_GATE` có thể cho draft đi tiếp nhưng phải block final nếu còn quantitative OCR fact bị blocked.

### 4. Source tier

| Tier | Ý nghĩa vận hành |
|---|---|
| Tier 1 | Tài liệu chính thức hoặc nguồn có thẩm quyền cao |
| Tier 2 | Aggregator/API có cấu trúc, hữu ích để đối chiếu |
| Tier 3 | Nguồn yếu hơn, chỉ dùng hỗ trợ bối cảnh nếu không material |

Material fact chỉ dựa vào Tier 3 phải bị block ở source provenance hoặc citation gate. Report không được xuất final nếu claim trọng yếu thiếu source trace.

### 5. Snapshot reuse

Stage `INGEST_AND_VALIDATE` gọi `latest_ready_snapshot`. Nếu snapshot hiện có còn fresh và policy không `force_ingest`, pipeline bỏ qua auto ingest/build index nặng và chỉ load lại facts cần thiết. Thiết kế này giảm latency và cost, nhưng vẫn giữ downstream gate dựa trên snapshot id explicit.

## Strategic Recommendations

| Rủi ro | Kiểm soát |
|---|---|
| PDF scan gây sai OCR | Bắt buộc validation, reconciliation và promotion gate |
| API field đổi tên | Dùng metric dictionary và tests connector/normalizer |
| Source cũ bị dùng lại | Dùng snapshot freshness và artifact manifest theo run |
| Claim material chỉ có nguồn yếu | Block bằng source tier/citation gates |
| Mở rộng ticker ngoài MVP | Cập nhật universe, source mapping và golden facts tối thiểu |
