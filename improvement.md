## Benchmark Remediation Phases

### Context

`BENCHMARK_STANDARDS.md` previously described professional frameworks and an
explainable metric contract, but the executable evaluator mainly emitted
heuristics, nullable scores, and static UI labels. The remediation is split
into independently verifiable phases.

| Phase | Scope | Implementation status | Acceptance evidence |
|---|---|---|---|
| Phase 1 | Metric truthfulness, threshold registry, cross-ticker isolation | Implemented | `config/eval/metric_registry.yaml`; missing values become `not_evaluable`; DHG golden queries cannot score DBD |
| Phase 2 | Click-through metric explanation UI | Implemented | Clicking a metric opens framework/version, formula, arguments, sample results, threshold rationale, failed examples, and remediation |
| Phase 3 | Pandera DataFrame validation | Implemented | Data quality evaluation executes Pandera and stores schema failure cases |
| Phase 4 | Ragas and DeepEval adapters | Implemented, dataset-gated | Adapters execute only with ticker-scoped datasets and credentials; otherwise they emit `not_executed` without fabricated scores |
| Phase 5 | Regression verification and rollout | In progress | Backend/frontend tests, production build, regenerated evaluation packet, and deployment configuration review |

### Remaining Data Work

- Build versioned `config/eval/ragas/<TICKER>.json` datasets from production
  retriever outputs and expert reference contexts.
- Build calibrated `config/eval/deepeval/<TICKER>.json` cases with human labels.
- Persist run-scoped claim ledgers, retrieval traces, report-quality artifacts,
  latency windows, and cost ledgers so currently missing metrics can execute.
- Treat semantic framework scores as diagnostics until calibration is complete;
  deterministic finance, citation, and publication gates retain authority.

---

## Context

Đúng. Nếu mục tiêu của chị là hệ thống **tính FCFE, FCFF, P/E, EV/EBITDA và blend đầy đủ**, thì không thể chỉ vá governance hoặc renderer. Phải quay về tầng dữ liệu và đặt lại nguyên tắc:

> **Valuation engine không được tự “cố tính” khi thiếu dữ liệu. Data layer phải biết chính xác method nào cần field nào, field đó lấy từ đâu, có đủ chưa, đơn vị là gì, và có lineage không.**

Nói ngắn gọn: chị cần xây **data completeness layer** trước valuation.

---

## Problem Statement

Hiện tại hệ thống đang thiếu một tầng rất quan trọng:

```text
Data source
→ Raw extraction
→ Canonical facts
→ Data completeness check
→ Valuation input snapshot
→ Valuation calculation
→ Publishability policy
→ Report
```

Có vẻ hệ thống hiện đang đi kiểu:

```text
Data source
→ Một số facts lấy được
→ Valuation cố chạy
→ Artifact thiếu trace/bridge/sensitivity
→ Governance block
```

Do đó FCFE/blend lỗi là hợp lý. Không phải vì “FCFE khó” theo nghĩa công thức phức tạp, mà vì hệ thống chưa buộc dữ liệu đầu vào phải đầy đủ trước khi cho method chạy.

---

## Technical Deep-Dive

### 1. Phải định nghĩa “đầy đủ” theo từng phương pháp định giá

Không có khái niệm “lấy đầy đủ số liệu” chung chung. Phải có **data requirement contract** cho từng method.

#### FCFF DCF cần tối thiểu

| Nhóm               | Trường bắt buộc                                      |
| ------------------ | ---------------------------------------------------- |
| Kết quả kinh doanh | Doanh thu, EBIT hoặc lợi nhuận trước thuế và lãi vay |
| Thuế               | Thuế suất hiệu dụng hoặc chi phí thuế                |
| Dòng tiền          | Khấu hao, CAPEX, thay đổi vốn lưu động               |
| Bảng cân đối       | Tiền, nợ vay ngắn hạn, nợ vay dài hạn                |
| Cổ phiếu           | Số cổ phiếu lưu hành                                 |
| Giả định           | WACC, tăng trưởng dài hạn, forecast horizon          |
| Market data        | Giá thị trường, ngày định giá                        |

#### FCFE DCF cần tối thiểu

| Nhóm                 | Trường bắt buộc                         |
| -------------------- | --------------------------------------- |
| Dòng tiền kinh doanh | CFO                                     |
| Đầu tư               | CAPEX                                   |
| Tài trợ              | Tiền thu từ đi vay, tiền trả nợ gốc vay |
| Cổ phiếu             | Số cổ phiếu lưu hành                    |
| Giả định             | Cost of equity, tăng trưởng dài hạn     |
| Market data          | Giá thị trường, ngày định giá           |

FCFE đang lỗi nhiều khả năng vì thiếu phần **tiền thu từ đi vay** và **tiền trả nợ gốc vay** trong lưu chuyển tiền tệ. Nếu chỉ ingest bảng cân đối và kết quả kinh doanh thì không đủ để tính FCFE.

#### P/E cần tối thiểu

| Nhóm      | Trường bắt buộc                                        |
| --------- | ------------------------------------------------------ |
| EPS       | EPS trailing hoặc forward EPS                          |
| Lợi nhuận | LNST sau lợi ích cổ đông thiểu số nếu dùng EPS tự tính |
| Cổ phiếu  | Số cổ phiếu bình quân/lưu hành                         |
| Peer      | Nhóm so sánh đúng taxonomy                             |
| Multiple  | P/E peer median, mean, hoặc selected multiple          |

#### EV/EBITDA cần tối thiểu

| Nhóm     | Trường bắt buộc                           |
| -------- | ----------------------------------------- |
| EBITDA   | EBIT + khấu hao                           |
| Net debt | Nợ vay ngắn hạn + nợ vay dài hạn - tiền   |
| Peer     | Nhóm so sánh đúng                         |
| Multiple | EV/EBITDA peer                            |
| Shares   | Số cổ phiếu lưu hành để quy đổi về giá/cp |

#### Blend cần tối thiểu

Blend không phải method độc lập. Nó chỉ được chạy nếu các method con đã đạt chuẩn.

```text
Blend chỉ được tính từ methods có status = publishable.
Không dùng method blocked.
Không dùng method low-confidence.
Không dùng P/E nếu policy chỉ cho P/E làm cross-check.
Không dùng method không có sensitivity.
```

---

## Strategic Recommendations

### P0 — Xây Data Requirement Registry

Tạo một registry mô tả từng valuation method cần field nào.

Ví dụ:

```python
VALUATION_DATA_REQUIREMENTS = {
    "fcff_dcf": {
        "required_facts": [
            "revenue",
            "ebit",
            "tax_expense",
            "depreciation_amortization",
            "capex",
            "change_in_working_capital",
            "cash_and_equivalents",
            "short_term_debt",
            "long_term_debt",
            "shares_outstanding",
            "market_price",
        ],
        "required_assumptions": [
            "wacc",
            "terminal_growth",
            "forecast_years",
        ],
    },
    "fcfe_dcf": {
        "required_facts": [
            "cfo",
            "capex",
            "debt_issuance",
            "debt_repayment",
            "shares_outstanding",
            "market_price",
        ],
        "required_assumptions": [
            "cost_of_equity",
            "terminal_growth",
            "forecast_years",
        ],
    },
    "pe": {
        "required_facts": [
            "eps",
            "shares_outstanding",
            "market_price",
        ],
        "required_market_data": [
            "peer_pe_median",
            "peer_group",
        ],
    },
    "ev_ebitda": {
        "required_facts": [
            "ebit",
            "depreciation_amortization",
            "cash_and_equivalents",
            "short_term_debt",
            "long_term_debt",
            "shares_outstanding",
            "market_price",
        ],
        "required_market_data": [
            "peer_ev_ebitda_median",
            "peer_group",
        ],
    },
}
```

Mục tiêu: trước khi chạy valuation, hệ thống phải biết **thiếu field nào** thay vì để method tự chết ở giữa.

---

### P1 — Tạo Data Availability Matrix cho từng ticker

Mỗi ticker phải có bảng kiểm tra dữ liệu như sau:

| Ticker | Method    | Required fields | Available | Missing                           | Status                  |
| ------ | --------- | --------------: | --------: | --------------------------------- | ----------------------- |
| DHG    | FCFF      |              12 |        11 | `change_in_working_capital`       | blocked                 |
| DHG    | FCFE      |               6 |         4 | `debt_issuance`, `debt_repayment` | blocked                 |
| DHG    | P/E       |               5 |         5 | none                              | cross_check             |
| DHG    | EV/EBITDA |               8 |         8 | none                              | publishable/cross_check |

Đây là thứ chị cần nhìn thấy trước valuation. Nếu không có matrix này, mỗi lần lỗi sẽ rất khó biết là thiếu data, sai mapping, hay sai công thức.

---

### P2 — Bắt buộc lưu lineage cho từng số

Mỗi canonical fact phải có tối thiểu:

```text
ticker
company_name
fiscal_year
fiscal_period
statement_type
canonical_field
raw_label
raw_value
normalized_value
raw_unit
normalized_unit
currency
source_uri
source_title
source_type
published_date
ingested_at
parser_version
confidence
checksum
```

Nếu một field không có `source_uri`, không có `unit`, hoặc không có `fiscal_period`, thì không được dùng cho valuation chính thức.

---

### P3 — Ưu tiên nguồn dữ liệu theo tầng

Không nên crawl lung tung rồi merge mù. Phải có source priority rõ.

| Tầng   | Nguồn                                                                                                | Dùng cho                                                                   |
| ------ | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Tier 1 | Báo cáo tài chính kiểm toán, báo cáo thường niên, công bố chính thức HOSE/HNX/UPCOM, website công ty | Financial facts chính                                                      |
| Tier 2 | Dữ liệu tài chính từ provider/API như vnstock hoặc nguồn market data                                 | Price, shares, historical market data, cross-check                         |
| Tier 3 | Tin tức, đấu thầu, BHYT, Cục Quản lý Dược, regulatory notices                                        | Catalyst, thesis, risk                                                     |
| Tier 4 | Media hoặc third-party                                                                               | Chỉ dùng làm tham khảo, không làm nguồn số liệu chính nếu thiếu kiểm chứng |

Quan trọng: **financial facts không nên lấy từ RAG text nếu đã có structured source**. RAG dùng để chứng minh narrative và citation, không nên là nguồn chính cho số định lượng.

---

### P4 — Sửa ingestion theo hướng “statement-complete”

Đối với mỗi ticker và mỗi năm, hệ thống phải ingest đủ 3 báo cáo:

| Báo cáo              | Vì sao bắt buộc                                                |
| -------------------- | -------------------------------------------------------------- |
| Kết quả kinh doanh   | Doanh thu, EBIT, lợi nhuận, EPS                                |
| Bảng cân đối kế toán | Tiền, nợ vay, vốn chủ, tài sản                                 |
| Lưu chuyển tiền tệ   | CFO, CAPEX, vay/trả nợ, cổ tức                                 |
| Thuyết minh BCTC     | Chi tiết nợ vay, tài sản cố định, cổ phiếu, chính sách kế toán |

Nếu thiếu lưu chuyển tiền tệ hoặc thuyết minh, FCFE gần như không đủ chuẩn.

---

### P5 — Không fallback im lặng

Các fallback nguy hiểm phải bị cấm:

| Fallback cũ                                              | Vì sao sai                       |
| -------------------------------------------------------- | -------------------------------- |
| `net_borrowing = 0` khi thiếu dữ liệu                    | Làm FCFE sai nhưng trông hợp lệ  |
| Dùng total liabilities thay cho debt                     | Sai bản chất tài chính           |
| Dùng latest valuation artifact của ticker khác/run khác  | Gây nhiễm nghiêm trọng           |
| Dùng P/E làm target chính khi policy chỉ cho cross-check | Làm recommendation thiếu nền     |
| Dùng blend khi sensitivity rỗng                          | Không chứng minh được độ ổn định |
| Dùng field không có source_uri                           | Không audit được                 |

Đúng phải là:

```text
missing required input
→ method_status = blocked
→ missing_fields = [...]
→ data_gap_report generated
→ valuation không publishable
```

---

## Kiến trúc sửa thành công

### Luồng đúng

```text
1. Ingest official documents
2. Extract raw tables
3. Normalize raw line items
4. Map to canonical facts
5. Validate unit, period, subtotal, source confidence
6. Build valuation input snapshot
7. Run data completeness check per method
8. Run only eligible valuation methods
9. Generate sensitivity grid
10. Build publishability policy
11. Render report with diagnostics
```

### Artifact bắt buộc trước valuation

Trước khi valuation chạy, phải sinh một file kiểu:

```json
{
  "ticker": "DHG",
  "valuation_date": "2026-06-14",
  "data_completeness": {
    "fcff_dcf": {
      "status": "ready",
      "missing_fields": []
    },
    "fcfe_dcf": {
      "status": "blocked",
      "missing_fields": ["debt_issuance", "debt_repayment"]
    },
    "pe": {
      "status": "ready",
      "missing_fields": []
    },
    "ev_ebitda": {
      "status": "ready",
      "missing_fields": []
    }
  },
  "facts": {
    "cfo": {
      "value": 123456,
      "unit": "million_vnd",
      "source_uri": "...",
      "confidence": "high"
    }
  }
}
```

---

## Việc cần yêu cầu coding agent làm ngay

Gửi trực tiếp đoạn này:

```text
We need to fix the system so it can collect and validate all required data before valuation. Do not focus only on governance or renderer.

Implement a valuation data completeness layer.

1. Add a ValuationDataRequirementRegistry for each method:
   - FCFF DCF
   - FCFE DCF
   - P/E
   - EV/EBITDA
   - Blend

2. For each method, define required facts, required assumptions, required market data, required source metadata, and required units.

3. Build a DataAvailabilityMatrix per ticker/run before valuation:
   - available fields
   - missing fields
   - source_uri/fact_id
   - unit
   - fiscal_period
   - confidence
   - parser_version
   - method readiness status

4. FCFE must require CFO, CAPEX, debt_issuance, debt_repayment, shares_outstanding, and market_price. If debt_issuance or debt_repayment is missing, FCFE must be blocked with an explicit data gap. Do not set net_borrowing to zero.

5. Ingestion must become statement-complete:
   - income statement
   - balance sheet
   - cash flow statement
   - notes to financial statements where required
   - market data
   - peer multiples

6. Add canonical mapping for Vietnamese financial statement line items:
   - lưu chuyển tiền thuần từ hoạt động kinh doanh → CFO
   - tiền chi để mua sắm/xây dựng TSCĐ và tài sản dài hạn khác → CAPEX
   - tiền thu từ đi vay → debt_issuance
   - tiền trả nợ gốc vay → debt_repayment
   - vay và nợ thuê tài chính ngắn hạn → short_term_debt
   - vay và nợ thuê tài chính dài hạn → long_term_debt
   - tiền và tương đương tiền → cash_and_equivalents
   - số cổ phiếu lưu hành/bình quân → shares_outstanding

7. Add unit normalization:
   - VND
   - thousand VND
   - million VND
   - billion VND
   - shares
   - thousand shares
   - million shares

8. Add hard validation:
   - no fact without source_uri
   - no fact without unit
   - no fact without fiscal_period
   - no valuation if required facts are missing
   - no blend using blocked or low-confidence methods
   - no publishable valuation without sensitivity grid and EV-to-equity bridge

9. Produce a data_gap_report for DHG and DBD:
   - exact missing fields
   - expected source
   - whether missing due to ingestion, parser, canonical mapping, or source absence
   - recommended fix

10. Add regression tests using real DHG/DBD valuation artifacts and one synthetic complete artifact. The synthetic complete artifact must pass; DHG/DBD may remain blocked only if required real data is still missing.
```

---

## Kết luận

Chị không nên yêu cầu hệ thống “cứ tính cho ra đủ số”. Yêu cầu đúng phải là:

> **Hệ thống phải tự động lấy, chuẩn hóa, kiểm định và báo cáo đầy đủ trạng thái dữ liệu trước khi định giá. Method nào đủ dữ liệu thì chạy; method nào thiếu thì chỉ ra thiếu trường nào, thiếu từ nguồn nào, do parser hay do source không có.**

Trạng thái thành công không phải là mọi ticker luôn có FCFE/blend. Trạng thái thành công là:

```text
Nếu dữ liệu tồn tại trong nguồn chính thức:
→ hệ thống lấy được, map được, normalize được, trace được, và tính được.

Nếu dữ liệu không tồn tại hoặc nguồn không công bố:
→ hệ thống báo thiếu chính xác, không tự bịa, không fallback sai.
```

Muốn tính toán đầy đủ, việc cần làm ngay là **data completeness layer + statement-complete ingestion + canonical fact lineage**, rồi mới sửa valuation/blend phía sau.
