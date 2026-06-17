# Nguồn dữ liệu và ingestion

Cập nhật: 2026-06-17

## Context

Hệ thống thu thập dữ liệu tài chính, tài liệu công bố, catalyst/news và dữ liệu thị trường cho universe dược/y tế Việt Nam. Dữ liệu thô không được dùng trực tiếp trong valuation hoặc report; nó phải đi qua normalization, reconciliation, source-tier policy và snapshot readiness.

Trạng thái hiện hành đã mở rộng dữ liệu vận hành ra ngoài MVP5: universe cấu hình có 43 ticker, có thư mục tài liệu ĐHCĐ/DHCD 2026 trong `config/dataset/DHCD/`, có các artifact PDF LLM/AGM ingest trong `artifacts/official_sources/`, và benchmark suite đã sinh output theo nhiều ticker. Các artifact này là bằng chứng xử lý dữ liệu, nhưng chỉ dữ liệu đã được promote thành canonical fact hoặc driver có provenance mới được dùng downstream.

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
| Local official PDF gap-fill | `scripts/ingest_pdf_llm.py` | Đọc PDF đã staging trong `data/official_documents/<ticker>/<year>/source_document.pdf`, trích fact còn thiếu và evidence định tính |
| AGM/DHCD packets | `scripts/ingest_agm.py` | Đọc tài liệu ĐHCĐ trong `config/dataset/DHCD/`, trích nghị quyết và driver kế hoạch tương lai |
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

### 4. PDF LLM gap-fill và AGM/DHCD driver

| Luồng | Lệnh | Policy |
|---|---|---|
| PDF LLM gap-fill | `python scripts/ingest_pdf_llm.py --ticker DHG --from-year 2021 --to-year 2025` | Additive-only; chỉ ghi metric còn thiếu trong production facts, không ghi đè structured source đã có. |
| AGM/DHCD ingest | `python scripts/ingest_agm.py --ticker DHG` | Forward-only; ghi nghị quyết và driver kế hoạch vào `research.agm_resolutions`, không sửa historical facts. |

Hai luồng này nên chạy trước `scripts/run_research.py` khi muốn forecast/valuation dùng dữ liệu chính thức và driver ĐHCĐ mới nhất. `make run-once` bọc đúng thứ tự này cho một ticker.

Trong code hiện tại, AGM/DHCD ingest ghi dữ liệu theo hướng forward-only vào lớp nghiên cứu, phục vụ driver kế hoạch như vay nợ, đầu tư, cổ tức hoặc chỉ tiêu kinh doanh tương lai. Luồng này không sửa lại dữ liệu lịch sử và không thay thế nguồn báo cáo tài chính.

### 5. Source tier

| Tier | Ý nghĩa vận hành |
|---|---|
| Tier 1 | Tài liệu chính thức hoặc nguồn có thẩm quyền cao |
| Tier 2 | Aggregator/API có cấu trúc, hữu ích để đối chiếu |
| Tier 3 | Nguồn yếu hơn, chỉ dùng hỗ trợ bối cảnh nếu không material |

Material fact chỉ dựa vào Tier 3 phải bị block ở source provenance hoặc citation gate. Report không được xuất final nếu claim trọng yếu thiếu source trace.

### 6. Snapshot reuse

Stage `INGEST_AND_VALIDATE` gọi `latest_ready_snapshot`. Nếu snapshot hiện có còn fresh và policy không `force_ingest`, pipeline bỏ qua auto ingest/build index nặng và chỉ load lại facts cần thiết. Thiết kế này giảm latency và cost, nhưng vẫn giữ downstream gate dựa trên snapshot id explicit.

## Strategic Recommendations

| Rủi ro | Kiểm soát |
|---|---|
| PDF scan gây sai OCR | Bắt buộc validation, reconciliation và promotion gate |
| API field đổi tên | Dùng metric dictionary và tests connector/normalizer |
| Source cũ bị dùng lại | Dùng snapshot freshness và artifact manifest theo run |
| Claim material chỉ có nguồn yếu | Block bằng source tier/citation gates |
| Mở rộng ticker ngoài MVP | Cập nhật universe, source mapping và golden facts tối thiểu |
