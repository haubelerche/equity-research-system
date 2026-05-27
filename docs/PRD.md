# PRD — Vietnam Pharma Multi-Agent Equity Research

*Tài liệu yêu cầu sản phẩm cho backend và workflow nghiên cứu cổ phiếu dược/y tế niêm yết Việt Nam.*

---

## 1. Tóm tắt sản phẩm

Sản phẩm là một nền tảng `multi-agent equity research` cho ngành dược/y tế Việt Nam, có khả năng:

- ingest và chuẩn hóa dữ liệu từ nguồn Việt Nam,
- tạo `canonical facts` cho phân tích,
- chạy `code-first valuation`,
- tạo `grounded draft report` có citation,
- yêu cầu `HITL approval` trước khi phát hành,
- hỗ trợ `flash memo` và `catalyst refresh`.

Sản phẩm không cạnh tranh trực tiếp ở lớp terminal dữ liệu toàn cầu; lợi thế nằm ở `Vietnam-local data`, `artifact-first reasoning`, `workflow có kiểm soát`, và `reporting có nguồn`.

---

## 2. Người dùng mục tiêu

### 2.1 Personas chính

- `Sell-side analyst`: cần giảm thời gian lấy số, giữ consistency, và sinh bản nháp nhanh.
- `Portfolio manager / buy-side`: cần tóm tắt ngắn, catalyst alert, và nhanh chóng thấy tác động đến valuation.
- `Research lead / reviewer`: cần công cụ kiểm tra luận điểm, citation, assumptions, và audit trail.

### 2.2 Personas vận hành

- `Data ops`: quản lý connector, parser, data quality, freshness, và lỗi nguồn.
- `Compliance / reviewer`: phê duyệt nội dung trước publish, kiểm tra disclaimer và nguồn.
- `Admin`: quản trị người dùng, quota, policy, và cấu hình model.

---

## 3. Mục tiêu sản phẩm

### 3.1 Mục tiêu kinh doanh

- Rút ngắn thời gian tạo `full report draft` từ `15-30 giờ` xuống dưới `60 phút` ở điều kiện backend ổn định.
- Cung cấp `flash memo` trong vòng `5 phút` cho các trigger đã chuẩn hóa.
- Chuẩn hóa research workflow cho `23` mã trong danh mục mục tiêu.

### 3.2 Mục tiêu chất lượng

- `100%` claim định lượng trong bản đã duyệt phải có citation hợp lệ.
- Chất lượng reviewer cho `accuracy / logicality / storytelling` đạt tối thiểu `8 / 8 / 7.5` ở giai đoạn pilot.
- `EPS forecast accuracy > 90%` theo định nghĩa trong mục đo lường.

### 3.3 Mục tiêu vận hành

- Hỗ trợ `resume`, `retry`, `partial recompute`, và `audit log`.
- Có `usage tracking` và `cost governance` cho từng research run.
- Có `data quality gates` trước khi dữ liệu trở thành fact có thể dùng cho valuation.

---

## 4. Phạm vi sản phẩm

### 4.1 Trong phạm vi giai đoạn 1

- `23` mã dược/y tế niêm yết Việt Nam.
- `Full report`, `flash memo`, `catalyst refresh`.
- `DCF`, `P/E`, `EV/EBITDA`, sensitivity analysis.
- Dữ liệu từ BCTC, niêm yết, đấu thầu, BHYT, regulatory notices, company news.
- Peer comparison theo taxonomy nội bộ.
- Báo cáo tiếng Việt có citation, approval workflow, và audit trail.

### 4.2 Ngoài phạm vi giai đoạn 1

- Auto-trading, auto-order routing, hoặc recommendation publish tự động.
- Bao phủ cổ phiếu ngoài danh mục dược/y tế mục tiêu.
- Global biotech/pharma làm lõi dữ liệu.
- Lấy Bloomberg API làm dependency bắt buộc.

---

## 5. Kết quả người dùng mong đợi

### 5.1 Full report

Người dùng gửi yêu cầu nghiên cứu và nhận lại:

- trạng thái run theo từng bước,
- assumptions draft,
- valuation artifact,
- report draft có citation map,
- báo cáo xuất bản sau khi được duyệt.

### 5.2 Flash memo

Người dùng nhận:

- memo ngắn theo catalyst hoặc biến động đáng kể,
- tác động sơ bộ lên luận điểm hoặc định giá,
- nguồn và mức confidence.

### 5.3 Catalyst monitoring

Người dùng theo dõi mã và nhận:

- catalyst mới,
- mức độ nghiêm trọng,
- có cần recompute thesis hay valuation hay không.

---

## 6. Năng lực hệ thống bắt buộc

### CAP-1 Ingestion and connectors

- Hệ thống phải kết nối được với nguồn BCTC, công bố niêm yết, đấu thầu thuốc, BHYT, regulatory notices, và company news.
- Mỗi lần ingest phải sinh `source metadata`, `ingestion run`, và checksum hoặc version tương đương.

### CAP-2 Data quality and reconciliation

- Dữ liệu ingest phải qua validation trước khi ghi vào canonical store.
- Các rule tối thiểu gồm:
  - schema validation,
  - missing-field checks,
  - financial sanity rules,
  - reconciliation giữa subtotal và total nếu có,
  - duplicate detection,
  - source confidence scoring.

### CAP-3 Canonical financial model

- Hệ thống phải chuẩn hóa line item vào taxonomy nội bộ.
- Facts phải được lưu dưới schema ổn định, có `source_uri`, `effective_date`, `ingested_at`, `parser_version`, và `confidence`.

### CAP-4 Research orchestration

- Workflow phải là stateful run có `idempotency`, `checkpoint`, `retry`, `resume`, `manual escalation`.
- Hỗ trợ các run type: `full_report`, `flash_memo`, `catalyst_refresh`.

### CAP-5 Valuation engine

- Valuation chạy bằng code với input/output schema rõ ràng.
- LLM không được phép tạo hoặc sửa financial facts sau bước fact validation.
- Kết quả valuation phải lưu thành artifact riêng để downstream chỉ đọc, không tự diễn giải lại số.

### CAP-6 Grounded report generation

- Report draft phải được sinh từ artifact đã khóa nguồn.
- Mỗi claim định lượng phải có citation tới document chunk hoặc fact record hợp lệ.
- Nếu không tìm được grounding phù hợp, claim đó không được xuất bản tự động.

### CAP-7 HITL, review, and audit

- Có ít nhất hai approval gates:
  - assumptions and key drivers,
  - final recommendation and publish.
- Hệ thống phải lưu lại `who approved what`, `when`, và `against which artifact version`.

### CAP-8 Observability and admin

- Có dashboard hoặc API để xem trạng thái run, lỗi connector, lỗi parser, latency, và approval backlog.
- Có log và metric cho từng stage của workflow.

### CAP-9 Usage tracking and cost control

- Mỗi run phải ghi nhận token usage, model cost, retry count, và stop reason.
- Phải có budget policy để chọn downgrade model, skip low-value steps, hoặc escalation sang manual review khi chi phí vượt ngưỡng.

### CAP-10 Offline evaluation

- Hệ thống phải hỗ trợ đánh giá chất lượng trước production cho:
  - extraction quality,
  - citation grounding,
  - thesis quality,
  - report stability.
- Có regression baseline để so sánh giữa model/prompt/parser version.

---

## 7. User stories trọng tâm

### US-1 Analyst tạo full report

Là một `analyst`, tôi muốn gửi yêu cầu cho một mã với các kịch bản cơ sở để hệ thống tạo bản nháp báo cáo có citation, nhằm giảm thời gian dựng nền và giữ được cấu trúc phân tích ổn định.

### US-2 Reviewer duyệt khuyến nghị

Là một `reviewer`, tôi muốn xem assumptions, valuation artifact, citation map, và thay đổi so với bản gần nhất, nhằm quyết định approve, reject, hoặc yêu cầu chạy lại từng phần.

### US-3 PM nhận flash memo

Là một `portfolio manager`, tôi muốn nhận flash memo sau một catalyst mới, nhằm biết nhanh liệu luận điểm đầu tư có thay đổi đủ lớn để cần đọc lại full report hay không.

### US-4 Data ops xử lý lỗi nguồn

Là một `data ops`, tôi muốn biết connector nào lỗi, record nào fail validation, và tài liệu nào gây parse mismatch, nhằm xử lý nhanh mà không ảnh hưởng toàn bộ pipeline.

---

## 8. Acceptance criteria

### 8.1 MVP 5 mã

Phạm vi: `DHG`, `IMP`, `DMC`, `TRA`, `DBD`.

- Có thể ingest tối thiểu `3-5 năm` dữ liệu BCTC cho mỗi mã.
- Có golden dataset cho facts và EPS actuals của 5 mã.
- `Full report p95 < 60 phút` trong môi trường mục tiêu.
- `Flash memo p95 < 5 phút`.
- `Citation coverage = 100%` cho claim định lượng trong bản đã duyệt.
- `>= 90%` observation trong tập vàng đạt sai số EPS trong ngưỡng đã định.
- Hệ thống hỗ trợ `retry/resume` nếu lỗi ở bước sau ingestion.
- Có approval workflow cho assumptions và final recommendation.
- Mỗi run có cost ledger và stop reason.

### 8.2 Scale-up 23 mã

- Có taxonomy và peer grouping ổn định cho toàn bộ 23 mã.
- Có catalyst ingestion tối thiểu theo lịch định sẵn và trigger thủ công.
- Hỗ trợ tải đồng thời nhiều run với queue isolation.
- Có incremental recompute khi document hoặc catalyst mới xuất hiện.
- Có monitoring và alert cho freshness, failure rate, và abnormal cost per run.

---

## 9. Định nghĩa chỉ số

### 9.1 EPS forecast accuracy > 90%

Đề xuất mặc định:

- Tập đánh giá gồm `N` quý gần nhất của các mã trong MVP.
- Sai số theo quý:

```text
abs(EPS_forecast - EPS_actual) / max(abs(EPS_actual), epsilon)
```

- Một quan sát được tính là thành công khi sai số `<= 15%`.
- KPI đạt khi `>= 90%` tổng số quan sát thành công.

### 9.2 Citation coverage

- Tỷ lệ claim định lượng trong report final có ít nhất một citation hợp lệ trỏ về source hoặc fact record đã được chấp nhận.

### 9.3 Cost per run

- Tổng chi phí LLM và compute của một run, được theo dõi theo từng stage để kiểm soát budget.

---

## 10. Yêu cầu phi chức năng

- `Reliability`: run phải có khả năng resume và partial recompute.
- `Security`: RBAC theo vai trò `analyst`, `reviewer`, `data_ops`, `admin`.
- `Compliance`: mọi publish phải có approval record.
- `Scalability`: queue và worker scale ngang cho ingestion, indexing, valuation, synthesis.
- `Observability`: trace, metrics, logs, lineage, và run history.
- `Data rights`: tuân thủ giấy phép và điều khoản nguồn.
- `Cost control`: budget policy, fallback model, và usage reporting.

---

## 11. Rủi ro và phụ thuộc

- Chất lượng `OCR/PDF parsing` của BCTC và tài liệu pháp lý.
- Tính ổn định và quyền truy cập của nguồn đấu thầu/BHYT/regulatory.
- Chất lượng taxonomy nội bộ và peer grouping.
- Rủi ro LLM diễn giải vượt ra ngoài artifact hoặc mất grounding.
- Chi phí model tăng nhanh nếu không khóa scope và cache hợp lý.

---

## 12. Lộ trình phát hành

1. `Foundation and data contracts`
2. `Fact ingestion and code-first valuation`
3. `RAG and citation pipeline`
4. `Orchestration and HITL`
5. `Production hardening`
6. `Agentic reasoning and thesis generation`

Mốc mục tiêu:

- `Q3/2026`: beta cho 5 mã MVP.
- `Q1/2027`: mở rộng 23 mã với catalyst monitoring ổn định.

---

## 13. Câu hỏi sản phẩm còn mở

- Định nghĩa chính thức của `500 users`: seat tổ chức hay MAU.
- Mức chi tiết catalyst đấu thầu trong MVP: toàn quốc, theo tỉnh, hay theo bệnh viện.
- Chính sách lưu trữ văn bản regulatory: cache nội bộ hay lưu metadata + link.
- Ngưỡng cost/run nào sẽ kích hoạt fallback hoặc chuyển sang manual review.
