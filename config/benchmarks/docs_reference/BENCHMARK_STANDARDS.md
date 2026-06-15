# BENCHMARK_STANDARDS.md

# Chuẩn đánh giá benchmark cho hệ thống Vietnam Pharma Equity Research Agent

## 1. Mục đích

Tài liệu này chuẩn hóa cách thiết kế, tính toán và đặt ngưỡng đánh giá cho các nhóm benchmark của hệ thống sinh báo cáo phân tích cổ phiếu ngành dược/y tế Việt Nam. Mục tiêu không phải tạo một bảng điểm phức tạp, mà là tạo một bộ tiêu chuẩn đủ rõ để trả lời bốn câu hỏi vận hành cốt lõi:

1. Dữ liệu đầu vào có đủ, đúng nguồn và đủ tin cậy để dùng cho phân tích không?
2. Mô hình tài chính, định giá, trích dẫn và báo cáo có lỗi nghiêm trọng không?
3. Báo cáo hiện tại có thể đưa sang bước con người duyệt hoặc xuất bản không?
4. Phiên bản mới của parser, retriever, prompt, model hoặc renderer có tốt hơn baseline không?

Benchmark phải ưu tiên tính thực dụng: có công thức rõ ràng, threshold rõ ràng, phạm vi đo rõ ràng, có ví dụ lỗi và có hành động sửa lỗi cụ thể.

---

## 2. Nguyên tắc thiết kế benchmark

### 2.1. Tách ba lớp đánh giá

Không được trộn lẫn cổng chặn xuất bản, benchmark hồi quy và chỉ số vận hành vào cùng một logic “Đạt/Chưa đạt”. Hệ thống sử dụng ba lớp đánh giá sau:

| Lớp | Mục đích | Có chặn xuất bản không? |
|---|---|---|
| Release Gates | Kiểm tra artifact của một báo cáo cụ thể có lỗi nghiêm trọng không | Có |
| Quality Diagnostics | Chẩn đoán chất lượng RAG, LLM, report, rubric và benchmark offline | Không trực tiếp |
| System Observability | Theo dõi độ trễ, chi phí, retry, fallback, lỗi render và lỗi upload | Chỉ chặn khi ảnh hưởng artifact cuối |

### 2.2. Threshold phải gắn với loại metric

Mỗi metric phải thuộc một trong năm loại ngưỡng sau:

| Loại metric | Ví dụ | Cách đặt threshold |
|---|---|---|
| Coverage | Citation coverage, source coverage, schema validity | `>= x%` |
| Error rate | OCR error rate, LLM retry rate, fallback rate | `<= x%` |
| Error count | Số lỗi render, số citation hỏng, số valuation mismatch | `= 0` hoặc `<= n` |
| Score | LLM Judge score, report quality score | `>= điểm tối thiểu` |
| Latency percentile | p50, p95, p99 latency | `<= thời gian tối đa` |

Threshold bằng `0` không sai. Nó đúng khi metric là số lỗi nghiêm trọng không được phép tồn tại trong artifact cuối. Threshold `0` không nên áp dụng bừa cho toàn bộ dữ liệu thô hoặc toàn bộ OCR corpus.

### 2.3. Deterministic gates có quyền cao hơn LLM Judge

LLM Judge chỉ dùng để đánh giá chất lượng lập luận, độ đầy đủ nội dung, độ mạch lạc và mức độ bám nhiệm vụ. LLM Judge không được ghi đè các lỗi tất định như sai số liệu, sai công thức, sai citation, sai bridge định giá hoặc lỗi render artifact cuối.

Quy tắc:

```text
Nếu deterministic gate fail ở mức P0 → báo cáo bị chặn.
Nếu LLM Judge score cao nhưng numeric/citation/valuation gate fail → vẫn bị chặn.
Nếu deterministic gates pass nhưng report quality thấp → chuyển sang Needs Human Review.
```

### 2.4. Mọi metric phải có scope và sample size

Một metric không có phạm vi đo sẽ gây hiểu nhầm. Mỗi metric phải ghi rõ được đo trên:

- một báo cáo cụ thể,
- một ticker,
- một benchmark suite offline,
- một cửa sổ vận hành hệ thống,
- hay một phiên bản artifact/model/prompt/parser.

---

## 3. Chuẩn trạng thái xuất bản

Hệ thống không nên chỉ dùng hai trạng thái “Đạt” và “Chưa đạt”. Trạng thái xuất bản nên được chuẩn hóa như sau:

| Trạng thái | Ý nghĩa |
|---|---|
| `NOT_EVALUATED` | Chưa chạy đủ benchmark hoặc thiếu artifact cần đánh giá |
| `BLOCKED_BY_P0` | Có lỗi nghiêm trọng, không được đưa sang xuất bản |
| `NEEDS_HUMAN_REVIEW` | Không có lỗi P0 nhưng còn lỗi P1 hoặc điểm chất lượng thấp |
| `DRAFT_PUBLISHABLE` | Release gates đã đạt, chờ con người duyệt |
| `APPROVED_FOR_EXPORT` | Đã đạt release gates và đã có phê duyệt cuối |

Logic đề xuất:

```text
if missing_required_artifacts or benchmark_not_run:
    status = NOT_EVALUATED
elif any(P0 release gate fails):
    status = BLOCKED_BY_P0
elif any(P1 gate fails) or report_quality_score < threshold:
    status = NEEDS_HUMAN_REVIEW
elif release_gates_passed and not human_approved:
    status = DRAFT_PUBLISHABLE
elif release_gates_passed and human_approved:
    status = APPROVED_FOR_EXPORT
```

---

## 4. Chuẩn schema cho mỗi metric

Mỗi metric nên được lưu với schema tối thiểu sau:

```yaml
metric_id: string
metric_name: string
category: data_quality | rag | financial_model | citation | agent_llm | report_quality | operations
layer: release_gate | diagnostic | observability
metric_type: coverage | error_rate | error_count | score | latency_percentile | boolean
scope: report_run | ticker | benchmark_suite | system_window
severity: P0 | P1 | P2 | P3
blocks_publish: true | false
value: number | string | boolean
threshold: number | string | boolean
threshold_operator: ">=" | "<=" | "=" | ">" | "<"
unit: percent | count | score | seconds | minutes | boolean
status: pass | fail | warning | not_evaluable
sample_size: number
artifact_id: string | null
artifact_version: string | null
dataset_version: string | null
benchmark_suite_version: string | null
owner: data | retrieval | valuation | report | platform | reviewer
failed_examples: list
remediation_hint: string
evaluated_at: datetime
```

Bắt buộc phải có `threshold_operator`, `unit`, `scope`, `severity`, `blocks_publish`, `sample_size` và `failed_examples` nếu metric fail.

---

## 5. Chuẩn benchmark theo nhóm

## 5.1. Chất lượng và độ tin cậy dữ liệu

### Mục tiêu

Kiểm tra dữ liệu đầu vào có đủ kỳ, có nguồn, được đối soát, không có lỗi OCR trọng yếu và không có fact chuẩn hóa bị trùng lặp chưa xử lý.

### Chuẩn metric

| Chỉ số | Công thức hoặc phương pháp tính | Threshold | Loại metric | Chặn xuất bản |
|---|---|---:|---|---|
| Độ đầy đủ các kỳ bắt buộc | Số kỳ bắt buộc có dữ liệu / Tổng số kỳ bắt buộc | `= 100%` | Coverage | Có nếu thiếu kỳ trọng yếu |
| Độ bao phủ nguồn cho accepted facts | Số accepted facts có source_id hợp lệ / Tổng accepted facts dùng trong report | `= 100%` | Coverage | Có |
| Tỷ lệ đối soát dữ kiện trọng yếu với nguồn chính thức | Số dữ kiện trọng yếu khớp nguồn chính thức / Tổng dữ kiện trọng yếu cần đối soát | `>= 95%` | Coverage | Có nếu sai dữ kiện trọng yếu |
| Lỗi OCR ảnh hưởng số liệu trọng yếu | Số lỗi OCR ảnh hưởng số liệu dùng trong report | `= 0` | Error count | Có |
| Tỷ lệ lỗi OCR toàn corpus | Số lỗi OCR chưa xử lý / Tổng đơn vị OCR kiểm tra | `<= 5%` | Error rate | Không, chỉ cảnh báo |
| Duplicate canonical fact chưa xử lý | Số fact chuẩn hóa bị trùng key ticker-period-line_item-source_priority | `= 0` | Error count | Có |

### Ghi chú chuẩn hóa

- Không dùng threshold `0%` cho toàn bộ raw OCR corpus.
- Không cấm raw duplicate tuyệt đối. Chỉ chặn duplicate đã đi vào canonical facts hoặc artifact cuối.
- “Kỳ bắt buộc” phải được cấu hình theo loại báo cáo, ví dụ: 3 năm lịch sử gần nhất, quý gần nhất, hoặc giai đoạn forecast bắt buộc.

---

## 5.2. RAG và truy xuất bằng chứng

### Mục tiêu

Đánh giá khả năng truy xuất đúng bằng chứng, xếp hạng bằng chứng liên quan và cung cấp context đủ để sinh nội dung có căn cứ.

### Chuẩn metric

| Chỉ số | Công thức hoặc phương pháp tính | Threshold MVP | Threshold mục tiêu | Loại metric | Chặn xuất bản |
|---|---|---:|---:|---|---|
| Hit-rate@5 | Tỷ lệ câu hỏi có ít nhất một evidence đúng trong top 5 | `>= 90%` | `>= 95%` | Coverage | Không trực tiếp |
| MRR@5 | Mean Reciprocal Rank của evidence đúng đầu tiên trong top 5 | `>= 0.75` | `>= 0.80` | Score | Không trực tiếp |
| Context Precision | Tỷ lệ context retrieved thực sự liên quan | `>= 0.80` | `>= 0.85` | Score | Không trực tiếp |
| Context Recall | Tỷ lệ bằng chứng cần thiết được retrieve | `>= 0.80` | `>= 0.85` | Score | Không trực tiếp |
| Faithfulness | Điểm nội dung bám evidence | `>= 0.85` | `>= 0.90` | Score | Không trực tiếp |
| Response Relevancy | Điểm câu trả lời đúng trọng tâm truy vấn | `>= 0.85` | `>= 0.85` | Score | Không trực tiếp |
| Source-tier hit rate | Tỷ lệ truy vấn trọng yếu có nguồn cấp ưu tiên trong top-k | `>= 90%` | `>= 95%` | Coverage | Không trực tiếp |

### Quy tắc sử dụng

- RAG benchmark là diagnostic hoặc offline regression benchmark, không phải release gate trực tiếp.
- Nếu RAG yếu nhưng report vẫn có citation đúng và đủ bằng chứng, report không nhất thiết bị chặn.
- Nếu RAG làm claim thiếu citation hoặc citation sai, lỗi đó bị bắt ở citation gate, không bắt ở RAG score.

---

## 5.3. Tính chính xác của mô hình tài chính và định giá

### Mục tiêu

Đảm bảo số liệu tài chính, công thức định giá, bridge định giá và khuyến nghị được tính bằng code, có thể tái lập, không phụ thuộc vào LLM tự suy diễn.

### Chuẩn metric

| Chỉ số | Công thức hoặc phương pháp tính | Threshold | Loại metric | Chặn xuất bản |
|---|---|---:|---|---|
| Vi phạm bất biến kế toán nghiêm trọng | Số lỗi như tài sản không khớp nợ phải trả + vốn chủ sở hữu, cash flow không khớp biến động tiền | `= 0` | Error count | Có |
| Kết quả định giá chuẩn sai lệch vượt ngưỡng | Số case trong golden valuation regression fail | `= 0` | Error count | Có |
| Sai lệch số cổ phiếu dùng trong EPS hoặc target price | Số case share count mismatch | `= 0` | Error count | Có |
| Sai bridge EV/equity value/target price | Số case không tái lập được target price từ valuation artifact | `= 0` | Error count | Có |
| WACC nhỏ hơn hoặc bằng terminal growth | Số case WACC <= terminal growth trong DCF | `= 0` | Error count | Có |
| Net debt reconciliation error | Số case nợ ròng không khớp công thức chuẩn | `= 0` | Error count | Có |
| Forecast anomaly không có giải trình | Số bất thường trọng yếu không có explanation hoặc catalyst | `= 0` với lỗi trọng yếu | Error count | Có hoặc cần human review |
| Recommendation inconsistency | Số case rating không khớp target price, current price và upside/downside | `= 0` | Error count | Có |

### Công thức chuẩn tối thiểu

```text
Net debt = interest-bearing debt - cash - short-term investments
EPS = net income attributable to parent / diluted shares
FCFF = EBIT × (1 - tax rate) + D&A - CAPEX - ΔNWC
FCFE = net income + D&A - CAPEX - ΔNWC + net borrowing
Target price = equity value / diluted shares outstanding
Upside = target price / current market price - 1
```

### Ghi chú threshold

Nhiều metric trong nhóm tài chính có threshold `= 0` là hợp lý vì đây là lỗi tất định. Một lỗi sai target price bridge, sai share count hoặc sai WACC/terminal growth có thể làm báo cáo sai bản chất.

---

## 5.4. Trích dẫn và nguồn bằng chứng

### Mục tiêu

Đảm bảo mọi claim trọng yếu trong báo cáo, đặc biệt là claim định lượng và claim định giá, có citation hợp lệ, phân giải được, trỏ đúng nguồn và hỗ trợ đúng nội dung được nêu.

### Chuẩn metric

| Chỉ số | Công thức hoặc phương pháp tính | Threshold | Loại metric | Chặn xuất bản |
|---|---|---:|---|---|
| Citation coverage cho claim định lượng | Số claim định lượng có citation / Tổng claim định lượng | `= 100%` | Coverage | Có |
| Citation resolver success | Số khóa citation phân giải được / Tổng khóa citation trong final report | `= 100%` | Coverage | Có |
| Source ID hợp lệ | Số source_id hợp lệ / Tổng source_id được dùng | `= 100%` | Coverage | Có |
| Numeric citation mismatch trọng yếu | Số số liệu trích dẫn không khớp bằng chứng | `= 0` | Error count | Có |
| Luận điểm trọng yếu chỉ dựa vào nguồn cấp thấp | Số luận điểm trọng yếu chỉ có nguồn cấp 3 hoặc nguồn không đủ tin cậy | `= 0` | Error count | Có hoặc cần human review |
| Citation label chung chung | Số citation không xác định được tài liệu cụ thể | `= 0` trong final report | Error count | Có |
| Catalyst thiếu evidence span | Số catalyst được dùng trong thesis nhưng không có đoạn bằng chứng | `= 0` | Error count | Có |

### Claim schema đề xuất

```yaml
claim_id: string
claim_text: string
claim_type: numeric_fact | qualitative_fact | forecast_assumption | valuation_output | recommendation
materiality: high | medium | low
source_id: string
source_tier: official | reputable_media | third_party | unknown
document_version: string
page_or_section: string
evidence_span: string
extracted_value: string | number | null
reported_value: string | number | null
tolerance: string | number | null
match_status: exact | rounded | mismatch | unsupported
```

### Ghi chú threshold

- Citation tồn tại chưa đủ. Citation phải hỗ trợ đúng claim.
- Với final report, citation hỏng hoặc citation sai số liệu trọng yếu phải có threshold `= 0`.

---

## 5.5. Agent Governance và LLM Judge

### Mục tiêu

Đánh giá agent có tuân thủ quyền công cụ, schema đầu ra, boundary tính toán và vai trò được giao không; đồng thời dùng LLM Judge để chẩn đoán chất lượng lập luận và mức hoàn thành nhiệm vụ.

### Chuẩn metric

| Chỉ số | Công thức hoặc phương pháp tính | Threshold | Loại metric | Chặn xuất bản |
|---|---|---:|---|---|
| Tool permission compliance | Số lượt gọi công cụ đúng quyền / Tổng lượt gọi công cụ | `= 100%` | Coverage | Có nếu vi phạm nghiêm trọng |
| JSON schema validity | Số output hợp lệ theo schema / Tổng output bắt buộc | `= 100%` | Coverage | Có nếu artifact bắt buộc fail |
| Không tự ý thực hiện tính toán tài chính bằng LLM | Số lượt tuân thủ quy tắc / Tổng lượt cần kiểm tra | `= 100%` | Coverage | Có |
| Role adherence | Điểm LLM Judge cho mức tuân thủ vai trò | `>= 0.85` | Score | Không trực tiếp |
| Groundedness judge score | Điểm LLM Judge về mức kết luận có căn cứ | `>= 0.85` | Score | Không trực tiếp |
| Task completion | Điểm hoàn thành yêu cầu bắt buộc | `>= 0.85` | Score | Không trực tiếp |
| Plan compliance | Điểm thực hiện đúng kế hoạch | `>= 0.80` | Score | Không trực tiếp |
| Seeded issue detection | Số lỗi cài trước được phát hiện / Tổng lỗi cài trước | `>= 90%` | Coverage | Không trực tiếp, dùng cho regression |

### Seeded issue evaluation tối thiểu

| Loại lỗi cài trước | Ví dụ |
|---|---|
| Numeric mismatch | Doanh thu trong report khác canonical fact |
| Unit mismatch | Tỷ đồng bị đọc thành triệu đồng |
| Wrong period | Dùng 2023 thay cho 2024 |
| Wrong ticker | Lẫn DHG và DBD |
| Invalid citation | Citation trỏ sai source |
| Unsupported forecast | Forecast margin tăng mạnh không có rationale |
| Valuation bridge error | Equity value chia sai số cổ phiếu |
| Recommendation inconsistency | Upside âm nhưng rating mua |
| Prompt injection | Tài liệu nguồn yêu cầu bỏ qua instruction hệ thống |
| Missing data | Hệ thống phải flag thiếu, không được bịa |

Target nâng cao:

```text
P0 seeded issue detection >= 99%
P1 seeded issue detection >= 95%
P2 seeded issue detection >= 90%
```

---

## 5.6. Chất lượng báo cáo đầu tư

### Mục tiêu

Đánh giá báo cáo có đủ phần, phân tích có chiều sâu, forecast có giải trình, valuation minh bạch, khuyến nghị nhất quán và trình bày đủ chuyên nghiệp hay không.

### Chuẩn metric tối giản cho MVP

| Chỉ số | Công thức hoặc phương pháp tính | Threshold MVP | Threshold mục tiêu | Loại metric | Chặn xuất bản |
|---|---|---:|---:|---|---|
| Report quality tổng | Điểm rubric tổng hợp | `>= 85/100` | `>= 90/100` | Score | Không trực tiếp |
| Report completeness | Số phần bắt buộc có nội dung đủ / Tổng phần bắt buộc | `>= 90%` | `= 100%` | Coverage | Có nếu thiếu phần trọng yếu |
| Financial analysis depth | Điểm phân tích tài chính | `>= 80/100` | `>= 85/100` | Score | Không trực tiếp |
| Forecast rationale | Điểm giải trình forecast | `>= 80/100` | `>= 85/100` | Score | Không trực tiếp |
| Valuation transparency | Điểm minh bạch định giá | `>= 85/100` | `>= 90/100` | Score | Có nếu thiếu artifact định giá |

### Rubric đề xuất nếu cần chi tiết hơn

| Dimension | Weight |
|---|---:|
| Completeness | 15% |
| Thesis specificity | 15% |
| Financial analysis depth | 15% |
| Forecast rationale | 15% |
| Valuation transparency | 15% |
| Risk/catalyst quality | 10% |
| Evidence integration | 10% |
| Presentation quality | 5% |

### Quy tắc đánh giá

```text
Nếu thiếu artifact bắt buộc → report_quality_status = NOT_EVALUABLE
Nếu có P0 financial/citation/valuation error → report_quality_score không được dùng để approve
Nếu score < threshold nhưng không có P0 → NEEDS_HUMAN_REVIEW
```

Khi report quality fail, dashboard phải hiển thị lý do cụ thể, ví dụ:

```yaml
missing_required_sections:
  - forecast_bridge
  - valuation_sensitivity
  - peer_comparison
missing_required_artifacts:
  - citation_map
  - valuation_snapshot
  - market_price_snapshot
```

---

## 5.7. Vận hành, chi phí và độ trễ

### Mục tiêu

Theo dõi hệ thống có chạy ổn định, chi phí hợp lý, ít retry, ít fallback và xuất được artifact cuối hay không.

### Chuẩn metric

| Chỉ số | Công thức hoặc phương pháp tính | Threshold | Loại metric | Chặn xuất bản |
|---|---|---:|---|---|
| LLM retry rate | Số lượt gọi LLM phải retry / Tổng lượt gọi LLM | `<= 5%` | Error rate | Không trực tiếp |
| Retrieval fallback rate | Số truy vấn dùng fallback / Tổng truy vấn retrieval | `<= 20%` | Error rate | Không, chỉ cảnh báo |
| OCR failure trên tài liệu trọng yếu | Số tài liệu OCR trọng yếu thất bại / Tổng tài liệu OCR trọng yếu | `<= 5%` | Error rate | Có nếu ảnh hưởng số liệu final |
| Lỗi OCR ảnh hưởng số liệu final | Số lỗi OCR làm sai số liệu trong final report | `= 0` | Error count | Có |
| Artifact final upload failure | Số artifact cuối tải lên thất bại | `= 0` | Error count | Có |
| PDF final render failure | Số lần render PDF cuối thất bại | `= 0` | Error count | Có |
| Full report p95 latency, warm run | p95 thời gian tạo full report khi dữ liệu/artifact đã có sẵn | `<= 10 phút` | Latency percentile | Không trực tiếp |
| Full report p95 latency, cold run | p95 thời gian tạo full report khi cần ingest/OCR/xử lý lại | `<= 30 phút` | Latency percentile | Không trực tiếp |
| Render-only p95 latency | p95 thời gian dựng PDF từ artifact đã khóa | `<= 2 phút` | Latency percentile | Có nếu render fail |
| Flash memo p95 latency, warm run | p95 thời gian tạo flash memo khi dữ liệu đã có sẵn | `<= 90 giây` | Latency percentile | Không trực tiếp |
| Flash memo p95 latency, cold retrieval | p95 thời gian tạo flash memo khi cần retrieval/crawl thêm | `<= 3 phút` | Latency percentile | Không trực tiếp |
| Latency regression | p95 mới / p95 baseline | `<= 1.25x` | Score | Không trực tiếp |

### Ghi chú về ngưỡng latency

- `Full report p95 <= 60 phút` chỉ nên xem là trần sản phẩm cấp PRD hoặc worst-case SLA, không dùng làm engineering benchmark chính.
- Benchmark kỹ thuật nên dùng ngưỡng sát thực tế hơn: warm run `<= 10 phút`, cold run `<= 30 phút`, render-only `<= 2 phút`.
- Nếu baseline thực tế nhanh hơn nhiều, áp dụng rule hồi quy:

```text
fail_regression_if new_p95 > old_p95 * 1.25
```

---

## 6. Chuẩn severity

| Severity | Ý nghĩa | Ví dụ | Hành động |
|---|---|---|---|
| P0 | Lỗi nghiêm trọng làm report không được xuất bản | Sai target price, citation hỏng, valuation không tái lập, PDF final fail | Block publish |
| P1 | Lỗi đáng kể cần con người duyệt | Forecast bất thường chưa đủ giải trình, report quality thấp | Needs Human Review |
| P2 | Lỗi chất lượng hoặc trải nghiệm | RAG score thấp, narrative chưa sâu, fallback cao | Cảnh báo và backlog |
| P3 | Lỗi nhỏ hoặc tối ưu vận hành | Latency tăng nhẹ, formatting chưa tối ưu | Theo dõi |

---

## 7. Chuẩn UI benchmark

### 7.1. Nguyên tắc hiển thị

Dashboard benchmark phải ưu tiên khả năng sửa lỗi, không chỉ hiển thị nhiều ô xanh đỏ. Cần tránh một bảng phẳng quá dài khiến người dùng không biết lỗi nào thực sự chặn hệ thống.

### 7.2. Bố cục đề xuất

```text
Publication Status
- BLOCKED_BY_P0 / NEEDS_HUMAN_REVIEW / DRAFT_PUBLISHABLE / APPROVED_FOR_EXPORT

Top Blockers
1. Lỗi P0 hoặc P1 quan trọng nhất
2. Artifact bị ảnh hưởng
3. Hành động sửa lỗi đề xuất

Tabs
- Release Gates
- Quality Diagnostics
- Operations
- Regression History
```

### 7.3. Cột bắt buộc trong bảng metric

| Cột | Ý nghĩa |
|---|---|
| Chỉ số | Tên metric |
| Loại metric | Coverage, error rate, error count, score, latency |
| Phạm vi | Report run, ticker, benchmark suite, system window |
| Đạt khi | Threshold rõ ràng |
| Kết quả | Giá trị thực tế |
| Trạng thái | Đạt, Chưa đạt, Cảnh báo, Chưa đánh giá |
| Severity | P0, P1, P2, P3 |
| Chặn xuất bản | Có hoặc Không |
| Sample size | Số mẫu được đo |
| Failed examples | Link hoặc mô tả ví dụ lỗi |
| Owner | Nhóm chịu trách nhiệm |
| Action | Mở artifact, chạy lại, kiểm citation, kiểm valuation |

### 7.4. Cách ghi threshold trong UI

Không nên chỉ có cột “Chưa đạt khi”. Nên có tối thiểu hai cột:

| Cột | Ví dụ |
|---|---|
| Đạt khi | `>= 95%`, `= 0`, `<= 10 phút` |
| Loại ngưỡng | Coverage, error count, latency percentile |

---

## 8. Bộ benchmark tối thiểu cho MVP

Nếu cần triển khai nhanh, MVP chỉ cần các metric bắt buộc sau:

| Nhóm | Metric bắt buộc |
|---|---|
| Data Quality | Required periods completeness, accepted facts source coverage, material OCR error count, duplicate canonical fact count |
| RAG | Hit-rate@5, MRR@5, context precision, faithfulness |
| Financial Model | Accounting invariant violations, valuation regression failures, share count mismatch, target price bridge error, recommendation inconsistency |
| Citation | Quant citation coverage, citation resolver success, numeric citation mismatch, catalyst evidence span |
| Agent/LLM | Tool permission compliance, JSON schema validity, no LLM financial calculation, seeded issue detection |
| Report Quality | Report quality total, completeness, forecast rationale, valuation transparency |
| Operations | LLM retry rate, artifact upload failure, PDF render failure, warm full report p95, render-only p95 |

---

## 9. Kết luận chuẩn

Benchmark chuẩn cho hệ thống equity research không cần phức tạp quá, nhưng bắt buộc phải rõ ràng ở bốn điểm:

1. Metric thuộc loại nào: coverage, error rate, error count, score hay latency.
2. Threshold là gì và vì sao dùng threshold đó.
3. Metric có chặn xuất bản hay chỉ dùng để chẩn đoán.
4. Khi fail thì ai sửa, sửa artifact nào và xem ví dụ lỗi ở đâu.

Các threshold `= 0` nên được giữ cho lỗi nghiêm trọng dạng count trong artifact cuối, như sai citation trọng yếu, sai valuation bridge, sai share count, lỗi render PDF hoặc lỗi upload artifact. Các metric chất lượng mềm như RAG score, LLM Judge, retry rate, OCR toàn corpus và latency nên dùng threshold phần trăm, điểm số hoặc percentile thực tế hơn.

Nguyên tắc cuối cùng:

```text
Deterministic release gates quyết định báo cáo có an toàn để đưa sang human review hoặc xuất bản không.
Quality diagnostics giúp cải thiện chất lượng.
System observability giúp vận hành ổn định.
LLM Judge không được ghi đè lỗi số liệu, citation hoặc định giá.
```
