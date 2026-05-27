# AI Agent Định Giá Cổ Phiếu Doanh Nghiệp Ngành Y Dược Việt Nam

> **Vietnam Pharma Equity Research Agent** — hệ thống **Multi-Agent AI 5 tác tử** hỗ trợ phân tích và định giá cổ phiếu doanh nghiệp ngành y dược tại Việt Nam.  
> Dự án lấy cảm hứng từ FinRobot nhưng được tái thiết kế cho **thị trường chứng khoán Việt Nam**, **dữ liệu tiếng Việt**, **cổ phiếu y dược Việt Nam** và **pipeline định giá có kiểm chứng nguồn**.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Design Principles](#3-design-principles)
4. [Reference Sources](#4-reference-sources)
5. [Business Scope](#5-business-scope)
6. [Target Outputs](#6-target-outputs)
7. [5-Agent Architecture](#7-5-agent-architecture)
8. [End-to-End Workflow](#8-end-to-end-workflow)
9. [Data Contract](#9-data-contract)
10. [Valuation Methodology](#10-valuation-methodology)
11. [Evaluation Framework](#11-evaluation-framework)
12. [Technology Stack](#12-technology-stack)
13. [Project Structure](#13-project-structure)
14. [API Design](#14-api-design)
15. [6-Week Delivery Roadmap](#15-6-week-delivery-roadmap)
16. [Developer Workflow with Claude Code, Cursor, and Codex](#16-developer-workflow-with-claude-code-cursor-and-codex)
17. [Quality Gates and Done Criteria](#17-quality-gates-and-done-criteria)
18. [Limitations](#18-limitations)
19. [Disclaimer](#19-disclaimer)

---

## 1. Executive Summary

Dự án xây dựng một hệ thống AI Agent hỗ trợ quy trình **equity research và định giá cổ phiếu ngành y dược Việt Nam**. Hệ thống không phải là chatbot tài chính tự do, không phải công cụ khuyến nghị mua/bán tự động, và không để LLM tự tạo số liệu định giá.

Mục tiêu cốt lõi là tạo ra một **financial-document intelligence engine** có khả năng:

1. Thu thập, chuẩn hóa và kiểm tra dữ liệu tài chính của doanh nghiệp y dược Việt Nam.
2. Phân tích báo cáo tài chính, dữ liệu giá, báo cáo thường niên, công bố thông tin và tin tức doanh nghiệp.
3. Tính toán chỉ tiêu tài chính, peer comparison, DCF, multiples và sensitivity analysis bằng **Python deterministic code**.
4. Sinh báo cáo phân tích bằng tiếng Việt với **claim-level citation**, **source manifest**, **valuation assumptions**, **audit trail** và **evaluation result**.
5. Cho phép human analyst kiểm tra giả định, đánh giá chất lượng và duyệt báo cáo cuối.

Dự án được thiết kế theo hướng:

```text
FinRobot-inspired, not FinRobot-copied.
Pipeline-first multi-agent, not autonomous-agent chaos.
Deterministic financial calculation first, LLM narrative second.
Evaluation-first report generation, not AI writing without verification.
```

---

## 2. Problem Statement

Các báo cáo phân tích cổ phiếu truyền thống thường tốn nhiều thời gian do analyst phải thu thập dữ liệu, đọc báo cáo tài chính, chuẩn hóa số liệu, tính toán chỉ tiêu, so sánh peer, xây mô hình định giá và viết báo cáo. Với nhóm cổ phiếu y dược Việt Nam, khó khăn tăng thêm do dữ liệu phân tán, chất lượng công bố không đồng nhất, thuật ngữ tiếng Việt không chuẩn hóa và nguồn tin định tính khó kiểm chứng.

Bài toán của dự án:

> Xây dựng hệ thống AI Agent có khả năng sinh bản nháp báo cáo phân tích và định giá cổ phiếu ngành y dược Việt Nam, trong đó mọi số liệu định lượng được tính bằng các hàm công thức tài chính, mọi nhận định quan trọng có nguồn, mọi giả định định giá được lưu vết, và báo cáo cuối được đánh giá bằng bộ kiểm thử chống hallucination.

### Success Criteria

| Tiêu chí | Mục tiêu MVP |
|---|---:|
| Universe cổ phiếu | 53 mã y dược Việt Nam được khai báo bằng config |
| Golden dataset | 3 mã được kiểm toán thủ công dữ liệu 3–5 năm |
| Số lượng agent | 5 logical agents |
| Công thức định giá | Có nguồn học thuật/nghề nghiệp rõ ràng |
| Tính toán tài chính | 100% bằng Python deterministic code |
| Citation coverage | 100% claim định lượng có `source_id` |
| Numeric consistency | >= 99% số trong report khớp structured state |
| Report language | Tiếng Việt |
| Report artifacts | Markdown/HTML, claim ledger, source manifest, valuation result, eval result |
| Human review | Bắt buộc ở assumptions và final report |

---

## 3. Design Principles

### 3.1. Code-first quantitative analysis

LLM không được tính toán kết quả tài chính cuối cùng. Các thành phần sau bắt buộc chạy bằng code:

- Financial ratios.
- Growth metrics.
- Margin analysis.
- Peer comparison.
- DCF.
- Relative valuation.
- Sensitivity analysis.
- Numeric consistency checking.

LLM chỉ được dùng cho:

- Tóm tắt tài liệu.
- Trích xuất có schema.
- Diễn giải kết quả đã tính.
- Sinh narrative tiếng Việt có grounding.
- Phát hiện mâu thuẫn giữa các nguồn.
- Audit report theo rubric.

### 3.2. Every number must be traceable

Mọi số liệu trong báo cáo phải truy vết được về:

```text
source_id
source_type
source_name
period
statement_type
line_item
unit
currency
retrieval_timestamp
transformation_method
```

Nếu không truy vết được, số liệu không được xuất hiện trong report final.

### 3.3. Five agents only

Dự án sử dụng đúng **5 logical agents** để giảm độ phức tạp, phù hợp nguồn lực 1 người và thời gian 6 tuần:

1. `orchestrator_agent`
2. `data_foundation_agent`
3. `core_analyst_agent`
4. `valuation_reasoning_agent`
5. `synthesis_auditor_agent`

Các evaluator, quality gates, deterministic calculators, retrievers và renderers **không được tính là agent**. Chúng là tools/services được agent gọi.

### 3.4. Dynamic by configuration, not uncontrolled autonomy

Hệ thống phải mở rộng bằng config, không để agent tự do quyết định quá nhiều:

- Thêm ticker mới bằng `data/universe/pharma_vn_53.yaml`.
- Thay peer group bằng YAML.
- Bật/tắt phương pháp định giá bằng config.
- Thay model bằng `configs/model_config.yaml`.
- Thay ngưỡng evaluation bằng `configs/evaluation_thresholds.yaml`.

### 3.5. Evaluation is a first-class subsystem

Evaluation không phải phần phụ sau khi viết report. Hệ thống phải sinh kèm:

```text
valuation_result.json
claim_ledger.json
source_manifest.json
eval_result.json
report.md hoặc report.html
run_log.json
```

---

## 4. Reference Sources

Dự án chỉ sử dụng phương pháp tài chính, kiến trúc agent và quy trình dữ liệu có nguồn tham chiếu rõ ràng.

| Nhóm nguồn | Vai trò trong dự án | Nguồn tham chiếu |
|---|---|---|
| Kiến trúc AI Agent tài chính | Tham khảo mô hình agent, financial chain-of-thought, LLMOps/DataOps và financial foundation models | FinRobot paper: https://arxiv.org/html/2405.14767v2 |
| Equity research automation | Tham khảo pipeline sinh equity research report, phân tích tài chính, valuation, peer comparison | FinRobot GitHub: https://github.com/AI4Finance-Foundation/FinRobot |
| Financial NLP/DataOps | Tham khảo cách tổ chức dữ liệu news, filings, earnings calls, financial NLP | FinNLP GitHub: https://github.com/AI4Finance-Foundation/FinNLP |
| Stock-specific news modeling | Tham khảo hướng khai thác tin tức gắn với từng mã cổ phiếu | Astock GitHub: https://github.com/JinanZou/Astock |
| Text-price benchmark | Tham khảo cấu trúc dữ liệu kết hợp văn bản và giá lịch sử | StockNet dataset: https://github.com/yumoxu/stocknet-dataset |
| Free Cash Flow Valuation | Cơ sở cho FCFF, FCFE, WACC, terminal value, sensitivity analysis | CFA Institute Free Cash Flow Valuation: https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/free-cash-flow-valuation |
| Market-Based Valuation | Cơ sở cho P/E, P/B, EV/EBITDA, EV/Sales, peer comparison | CFA Institute Market-Based Valuation: https://www.cfainstitute.org/insights/professional-learning/refresher-readings/2026/market-based-valuation-price-enterprise-value-multiples |
| Công bố thông tin Việt Nam | Cơ sở sử dụng báo cáo tài chính, báo cáo thường niên, báo cáo quản trị và công bố thông tin | Thông tư 96/2020/TT-BTC: https://vanban.chinhphu.vn/default.aspx?docid=201902&pageid=27160 |
| OpenAI API | LLM provider mặc định cho hệ thống | OpenAI API docs: https://platform.openai.com/docs |

---

## 5. Business Scope

### 5.1. Universe cổ phiếu

Dự án tập trung vào khoảng **53 mã cổ phiếu ngành y dược Việt Nam**. Danh sách chính thức được cấu hình trong:

```text
data/universe/pharma_vn_53.yaml
```

Ví dụ:

```yaml
universe_name: vietnam_pharma_53
market: vietnam
language: vi
currency: VND

sector_scope:
  - duoc_pham
  - y_te
  - thiet_bi_y_te
  - benh_vien
  - phan_phoi_duoc

tickers:
  - ticker: DHG
    exchange: HOSE
    company_name: "Công ty Cổ phần Dược Hậu Giang"
    subsector: "duoc_pham"
    peer_group: ["TRA", "IMP", "DBD"]
    enabled_valuation_methods: ["dcf", "pe", "pb"]

  - ticker: DBD
    exchange: HOSE
    company_name: "Công ty Cổ phần Dược - Trang thiết bị Y tế Bình Định"
    subsector: "duoc_pham_thiet_bi_y_te"
    peer_group: ["DHG", "IMP", "TRA"]
    enabled_valuation_methods: ["dcf", "pe", "pb", "ev_ebitda"]
```

### 5.2. MVP golden dataset

Không triển khai sâu cả 53 mã ngay từ đầu. MVP tập trung vào **3 mã golden dataset** để kiểm chứng end-to-end:

```text
DHG
TRA
IMP hoặc DBD
```

Mỗi mã golden nên có:

```text
company_profile.yaml
financial_statements_3y.csv hoặc financial_statements_5y.csv
market_prices.csv
peer_group.yaml
audited_ratios.csv
valuation_assumptions.yaml
source_manifest.yaml
expected_report_quality_rubric.md
```

### 5.3. Data types

| Loại dữ liệu | Ví dụ | Vai trò |
|---|---|---|
| Dữ liệu giá | OHLCV, vốn hóa, thanh khoản | Market context, multiples, biểu đồ |
| Báo cáo tài chính | Income statement, balance sheet, cash flow | FCFF/FCFE, margin, ROE, ROA, leverage |
| Báo cáo thường niên | Chiến lược, ngành nghề, rủi ro, ban lãnh đạo | Qualitative analysis, risk narrative |
| Công bố thông tin | Nghị quyết, giải trình biến động, cổ tức, phát hành | Event extraction, assumption validation |
| Tin tức | Tin doanh nghiệp, chính sách ngành, đấu thầu thuốc | Catalyst và rủi ro |
| Peer data | Doanh nghiệp cùng ngành | Relative valuation và benchmarking |

### 5.4. Out of Scope for MVP

Các thành phần sau **không triển khai trong MVP 6 tuần** trừ khi có thời gian dư:

| Thành phần | Lý do loại khỏi MVP |
|---|---|
| SEC XBRL | Không phù hợp trực tiếp với thị trường Việt Nam |
| ClinicalTrials.gov | Không có coverage trực tiếp cho phần lớn doanh nghiệp dược niêm yết Việt Nam |
| OpenFDA | Không phải nguồn chính cho định giá cổ phiếu dược Việt Nam |
| LayoutLMv3/Nougat | Tốn thời gian triển khai, không cần cho MVP nếu có CSV/API/golden data |
| Vanna.ai Text-to-SQL | Không cần thiết khi schema nhỏ và query có thể viết deterministic |
| Celery/Redis | Chỉ cần khi batch workload lớn; MVP có thể chạy sync/background đơn giản |
| MinIO/S3 | Chưa cần nếu lưu local artifacts |
| Fully autonomous agent planning | Rủi ro cao, khó kiểm thử, không cần cho đồ án 6 tuần |

---

## 6. Target Outputs

Mỗi lần chạy phân tích phải tạo một **Report Package** gồm:

```text
artifacts/
├── reports/
│   └── {run_id}_{ticker}_report.md
├── reports_html/
│   └── {run_id}_{ticker}_report.html
├── valuation_results/
│   └── {run_id}_{ticker}_valuation_result.json
├── claim_ledgers/
│   └── {run_id}_{ticker}_claim_ledger.json
├── source_manifests/
│   └── {run_id}_{ticker}_source_manifest.json
├── eval_results/
│   └── {run_id}_{ticker}_eval_result.json
└── run_logs/
    └── {run_id}_{ticker}_run_log.json
```

### 6.1. Report sections

Báo cáo tiếng Việt phải có cấu trúc cố định:

1. Tóm tắt đầu tư.
2. Hồ sơ doanh nghiệp.
3. Tổng quan ngành y dược và vị thế doanh nghiệp.
4. Phân tích tài chính lịch sử.
5. Phân tích dòng tiền và chất lượng lợi nhuận.
6. Định giá DCF.
7. Định giá tương đối theo peer multiples.
8. Sensitivity analysis.
9. Catalyst tăng trưởng.
10. Rủi ro ngành, rủi ro doanh nghiệp và rủi ro dữ liệu.
11. Kịch bản bear/base/bull.
12. Kết luận định giá với khoảng giá hợp lý.
13. Phụ lục nguồn dữ liệu, giả định và công thức.

### 6.2. Report constraints

Báo cáo không được:

- Đưa lệnh mua/bán tự động.
- Tự tạo số liệu không có trong structured state.
- Tự tạo nguồn hoặc citation giả.
- Khẳng định vị thế ngành, năng lực ban lãnh đạo, lợi thế pháp lý hoặc pipeline sản phẩm nếu không có evidence.
- Cá nhân hóa khuyến nghị đầu tư cho người dùng.

---

## 7. 5-Agent Architecture

### 7.1. Architecture Overview

```text
┌──────────────────────────────────────────────────────────┐
│                    Orchestrator Agent                    │
│     Validate request · Build plan · Route · HITL          │
└────────────────────────────┬─────────────────────────────┘
                             │
                             v
┌──────────────────────────────────────────────────────────┐
│                  Data Foundation Agent                   │
│   Ingest · Normalize · Source manifest · Data quality     │
└────────────────────────────┬─────────────────────────────┘
                             │
                             v
┌──────────────────────────────────────────────────────────┐
│                    Core Analyst Agent                    │
│    Financial ratios · Peer comparison · Business analysis │
└────────────────────────────┬─────────────────────────────┘
                             │
                             v
┌──────────────────────────────────────────────────────────┐
│              Valuation & Reasoning Agent                 │
│   DCF · Multiples · Sensitivity · Believer/Skeptic pass   │
└────────────────────────────┬─────────────────────────────┘
                             │
                             v
┌──────────────────────────────────────────────────────────┐
│                Synthesis & Auditor Agent                 │
│   Vietnamese report · Claim ledger · Citation · Audit     │
└──────────────────────────────────────────────────────────┘
```

### 7.2. Agent responsibilities

| Agent | Trách nhiệm | Output chính | Không được làm |
|---|---|---|---|
| `orchestrator_agent` | Validate ticker, tạo research plan, route workflow, quản lý HITL và run state | `ResearchPlan` | Không tự phân tích tài chính, không tự kết luận đầu tư |
| `data_foundation_agent` | Lấy dữ liệu, chuẩn hóa, kiểm tra missing/stale/conflict, tạo source manifest | `DataSnapshot` | Không tự sửa số liệu thiếu nguồn, không tự forecast |
| `core_analyst_agent` | Gọi analytics engine, phân tích tài chính, peer comparison, business/risk context | `FundamentalAnalysis` | Không tính target price cuối, không tạo công thức mới |
| `valuation_reasoning_agent` | Gọi DCF/multiples/sensitivity engine, chạy internal believer-skeptic reasoning | `ValuationResult` | Không để LLM tính DCF, không dùng assumption thiếu kiểm chứng |
| `synthesis_auditor_agent` | Viết báo cáo tiếng Việt, tạo claim ledger, kiểm citation, audit numeric consistency | `FinalReportPackage` | Không thay đổi kết quả tính toán, không tạo nguồn giả |

### 7.3. Internal modes are not additional agents

Để giữ đúng 5 agent, một số năng lực được triển khai như **internal mode** hoặc **tool**, không tách thành agent mới:

| Năng lực | Cách triển khai |
|---|---|
| Risk analysis | Một phần của `core_analyst_agent` và report sections |
| Regulation analysis | Tool/retriever được Core Analyst hoặc Synthesis gọi |
| Believer/Skeptic debate | Hai pass nội bộ trong `valuation_reasoning_agent` |
| Citation checker | Deterministic evaluator/tool trong `evaluation/` |
| Numeric consistency checker | Deterministic evaluator/tool trong `evaluation/` |
| Report quality judge | Rubric evaluator, không phải core agent |

---

## 8. End-to-End Workflow

### 8.1. Business workflow

```text
1. User chọn ticker, kỳ phân tích, loại báo cáo.
2. Orchestrator kiểm tra ticker thuộc universe và tạo ResearchPlan.
3. Data Foundation lấy dữ liệu từ Vnstock/API/CSV/documents/news.
4. Data Foundation chuẩn hóa dữ liệu và tạo DataSnapshot.
5. Data Quality Gate kiểm tra completeness, stale data, conflict và source manifest.
6. Core Analyst tính ratios, growth, margins, leverage, liquidity, cash flow và peer metrics.
7. Calculation Gate kiểm tra công thức và consistency.
8. Valuation & Reasoning tính DCF, multiples, sensitivity và scenario.
9. HITL Assumption Gate cho người dùng/analyst duyệt assumption quan trọng.
10. Synthesis & Auditor viết báo cáo tiếng Việt từ structured outputs.
11. Final Audit Gate kiểm citation, numeric consistency, hallucination risk và report quality.
12. Hệ thống xuất report package.
```

### 8.2. LangGraph state flow

```text
START
  |
  v
orchestrator_agent
  |
  v
data_foundation_agent
  |
  v
data_quality_gate
  |--- fail ---> human_review_or_stop
  |
  v
core_analyst_agent
  |
  v
calculation_consistency_gate
  |--- fail ---> human_review_or_stop
  |
  v
valuation_reasoning_agent
  |
  v
assumption_review_gate
  |--- needs_review ---> human_approval
  |
  v
synthesis_auditor_agent
  |
  v
final_evaluation_gate
  |--- fail ---> revision_required
  |
  v
END
```

### 8.3. Core state object

```python
class EquityResearchState(BaseModel):
    run_id: str
    ticker: str
    research_plan: ResearchPlan | None = None
    data_snapshot: DataSnapshot | None = None
    fundamental_analysis: FundamentalAnalysis | None = None
    valuation_result: ValuationResult | None = None
    final_report_package: FinalReportPackage | None = None
    source_manifest: list[SourceRecord] = []
    claim_ledger: list[ReportClaim] = []
    eval_result: EvaluationResult | None = None
    warnings: list[str] = []
    errors: list[str] = []
    status: Literal[
        "initialized",
        "data_ready",
        "analysis_ready",
        "valuation_ready",
        "needs_human_review",
        "report_ready",
        "failed"
    ] = "initialized"
```

---

## 9. Data Contract

### 9.1. SourceRecord

```python
class SourceRecord(BaseModel):
    source_id: str
    source_type: Literal[
        "market_data",
        "financial_statement",
        "annual_report",
        "disclosure",
        "news",
        "manual_golden_dataset"
    ]
    source_name: str
    source_url: str | None
    document_path: str | None
    retrieval_timestamp: datetime
    period: str | None
    reliability: Literal["high", "medium", "low"]
```

### 9.2. DataSnapshot

```python
class DataSnapshot(BaseModel):
    ticker: str
    as_of_date: date
    company_profile: CompanyProfile
    financial_statements: list[FinancialStatement]
    market_data: MarketData
    peer_data: list[PeerSnapshot]
    news_events: list[NewsEvent]
    source_manifest: list[SourceRecord]
    data_quality: DataQualityReport
```

### 9.3. DataQualityReport

```python
class DataQualityReport(BaseModel):
    completeness_score: float
    missing_fields: list[str]
    stale_sources: list[str]
    conflicting_values: list[str]
    warnings: list[str]
    pass_gate: bool
```

### 9.4. GroundedClaim

```python
class GroundedClaim(BaseModel):
    claim_id: str
    claim: str
    claim_type: Literal["quantitative", "qualitative", "inference"]
    supporting_metrics: list[str]
    source_ids: list[str]
    confidence: float
```

### 9.5. Claim ledger

Mỗi report final phải sinh `claim_ledger.json`.

```json
{
  "claim_id": "CLAIM_001",
  "section": "financial_analysis",
  "claim_text": "Doanh thu của DHG tăng trưởng ổn định trong giai đoạn phân tích.",
  "claim_type": "quantitative",
  "numbers_used": ["revenue_2021", "revenue_2022", "revenue_2023", "revenue_cagr_3y"],
  "source_ids": ["SRC_FINANCIALS_DHG_2023", "SRC_GOLDEN_DHG"],
  "confidence": 0.92,
  "verdict": "pass"
}
```

---

## 10. Valuation Methodology

Dự án áp dụng nguyên tắc:

> Không tự tạo công thức định giá. Không dùng LLM để tính intrinsic value. Không kết luận định giá nếu assumption không được ghi rõ.

### 10.1. FCFF-based DCF

```text
Firm Value = Σ FCFF_t / (1 + WACC)^t + Terminal Value / (1 + WACC)^n
Equity Value = Firm Value - Market Value of Debt + Cash and Equivalents
Equity Value per Share = Equity Value / Shares Outstanding
```

Các công thức FCFF được phép dùng:

```text
FCFF = NI + NCC + Int(1 - Tax rate) - FCInv - WCInv
FCFF = CFO + Int(1 - Tax rate) - FCInv
FCFF = EBIT(1 - Tax rate) + Dep - FCInv - WCInv
```

### 10.2. FCFE-based DCF

```text
Equity Value = Σ FCFE_t / (1 + r)^t + Terminal Value / (1 + r)^n
FCFE = NI + NCC - FCInv - WCInv + Net Borrowing
FCFE = CFO - FCInv + Net Borrowing
```

### 10.3. Terminal value

```text
Terminal Value = FCFF_{n+1} / (WACC - g)
```

Control rules:

```text
g < WACC
terminal_growth_rate phải hợp lý với ngành và nền kinh tế dài hạn
WACC, g, margin, growth assumptions phải xuất hiện trong valuation_result.json
```

### 10.4. Relative valuation

| Multiple | Điều kiện dùng | Ghi chú |
|---|---|---|
| P/E | EPS dương, lợi nhuận không quá bất thường | Ưu tiên cho doanh nghiệp có lợi nhuận ổn định |
| P/B | Book value đáng tin, vốn chủ sở hữu dương | Hữu ích với doanh nghiệp tài sản hữu hình lớn |
| EV/EBITDA | Có dữ liệu EV và EBITDA đáng tin | Dùng bổ trợ nếu cấu trúc nợ khác biệt |
| EV/Sales | Biên lợi nhuận biến động hoặc EBITDA âm | Chỉ dùng làm tham khảo, không làm kết luận chính |

### 10.5. Sensitivity analysis

Bắt buộc có sensitivity theo tối thiểu:

```text
WACC
terminal_growth_rate
revenue_growth
operating_margin
```

### 10.6. Scenario analysis

Hệ thống phải tạo 3 kịch bản:

| Scenario | Ý nghĩa |
|---|---|
| Bear | Giả định thận trọng, tăng trưởng thấp, margin suy giảm hoặc WACC cao hơn |
| Base | Giả định trung tâm, dựa trên dữ liệu lịch sử và industry context |
| Bull | Giả định tích cực nhưng phải có catalyst/evidence hỗ trợ |

---

## 11. Evaluation Framework

Evaluation là phần trọng tâm của đồ án. Hệ thống phải chứng minh report đáng tin bằng cả deterministic tests và rubric-based evaluation.

### 11.1. Evaluation layers

| Lớp evaluation | Mục tiêu | Cách đo | Threshold MVP |
|---|---|---|---:|
| Data Extraction Eval | Kiểm tra số liệu lấy đúng | So với golden dataset/manual audited data | >= 98% field accuracy |
| Data Quality Eval | Kiểm tra thiếu dữ liệu, stale source, conflict | `DataQualityReport` | completeness >= 0.85 |
| Calculation Eval | Kiểm tra công thức tài chính và valuation | Unit tests với expected values | 100% pass |
| Source Grounding Eval | Kiểm tra claim có nguồn | Claim ledger kiểm `source_ids` | 100% quantitative claims |
| Numeric Consistency Eval | Kiểm số trong report khớp structured state | Regex/table parser + tolerance | >= 99% |
| Hallucination Risk Eval | Phát hiện claim ngoài evidence | Rule-based + optional LLM judge | risk <= threshold |
| Reasoning Quality Eval | Kiểm thesis, logic, risk balance | Rubric LLM judge + human review | >= 4/5 |
| End-to-End Eval | Kiểm report package chạy hoàn chỉnh | E2E test trên golden dataset | 3/3 golden tickers pass |

### 11.2. Numeric tolerance

| Loại số | Tolerance |
|---|---:|
| Doanh thu, lợi nhuận, tài sản | 0.1% hoặc rounding tolerance |
| Ratio phần trăm | ±0.1 điểm phần trăm |
| P/E, P/B | ±0.05x |
| Target price | ±1% do rounding |
| CAGR | ±0.1 điểm phần trăm |

### 11.3. Report quality rubric

| Tiêu chí | Mô tả | Weight |
|---|---|---:|
| Factual accuracy | Số liệu khớp nguồn và structured state | 25% |
| Citation completeness | Claim định lượng có nguồn | 20% |
| Valuation discipline | Assumption rõ, không tùy tiện | 20% |
| Investment reasoning | Thesis có logic nhân-quả | 15% |
| Risk balance | Có phản biện, không một chiều | 10% |
| Vietnamese financial writing | Văn phong analyst, không marketing | 10% |

Score interpretation:

```text
>= 4.5/5: Excellent
4.0–4.5: Strong student project
3.5–4.0: Acceptable but needs revision
< 3.5: Fail quality gate
```

### 11.4. Final confidence score

```python
final_confidence = (
    0.35 * data_quality_score
    + 0.25 * numeric_consistency_score
    + 0.20 * citation_coverage
    + 0.10 * valuation_assumption_quality
    + 0.10 * report_quality_score
)
```

Gate:

```text
final_confidence >= 0.85: pass
0.70 <= final_confidence < 0.85: needs_human_review
final_confidence < 0.70: fail
```

### 11.5. Hallucination policy

Các claim sau bị cấm nếu không có evidence:

| Claim bị kiểm soát | Ví dụ |
|---|---|
| Market leadership | “Doanh nghiệp dẫn đầu ngành...” |
| Management quality | “Ban lãnh đạo có năng lực vượt trội...” |
| Regulatory advantage | “Doanh nghiệp hưởng lợi rõ rệt từ chính sách...” |
| Product pipeline | “Pipeline sản phẩm mạnh...” |
| Foreign investor interest | “Khối ngoại quan tâm mạnh...” |
| Valuation certainty | “Cổ phiếu chắc chắn đang rẻ...” |

Khi thiếu dữ liệu, report phải viết:

```text
Dữ liệu hiện tại chưa đủ để kết luận chắc chắn về ...
```

---

## 12. Technology Stack

### 12.1. MVP stack

| Layer | Công nghệ | Vai trò |
|---|---|---|
| Backend API | FastAPI | REST API cho analysis/report |
| Workflow | LangGraph | Stateful 5-agent workflow |
| Schema | Pydantic v2 | Data contract, structured output |
| LLM provider | OpenAI API | Report synthesis, extraction, audit |
| Primary model | gpt-4o | Reasoning, report writing, complex qualitative analysis |
| Fast model | gpt-4o-mini | Routing, classification, simple extraction, JSON validation |
| Data processing | pandas, numpy | Financial calculations |
| Valuation | Custom deterministic Python modules | DCF, multiples, sensitivity |
| Config | YAML + Pydantic Settings | Universe, models, thresholds |
| Reporting | Jinja2 Markdown/HTML | Report rendering |
| Testing | pytest | Unit/integration/evaluation tests |
| Storage MVP | Local files + optional SQLite | Artifacts, run logs, golden dataset |
| Frontend MVP | Empty or minimal placeholder | Deferred until backend is stable |

### 12.2. Optional post-MVP stack

| Component | Khi nào thêm |
|---|---|
| PostgreSQL | Khi cần persistent multi-run database |
| pgvector | Khi RAG tài liệu lớn và cần semantic search bền vững |
| Redis/Celery | Khi batch 53 mã hoặc long-running jobs cần queue |
| MinIO/S3 | Khi lưu nhiều PDF, annual reports, artifacts |
| Streamlit dashboard | Khi cần HITL UI nhanh |
| Next.js frontend | Khi muốn production-like web app |
| WeasyPrint/python-docx | Khi cần export PDF/Word đẹp |
| LangSmith/Langfuse | Khi cần tracing chi tiết LLM/agent runs |

### 12.3. Model config

```yaml
llm:
  provider: openai
  primary_reasoning_model: gpt-4o
  fast_model: gpt-4o-mini
  structured_outputs: true
  max_retries: 2

temperature:
  extraction: 0.0
  financial_analysis: 0.1
  valuation_reasoning: 0.1
  report_generation: 0.2
  audit: 0.0
```

Model phải được cấu hình qua file config, không hardcode trong code.

---

## 13. Project Structure

```text
vietnam-pharma-equity-agent/
├── README.md
├── CHANGELOG.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── CLAUDE.md
├── DONE_CRITERIA.md
│
├── specs/
│   ├── PRD.md
│   ├── PROBLEM_BRIEF.md
│   ├── BACKEND_PLAN.md
│   ├── DATA_CONTRACT.md
│   ├── AGENT_SPECS.md
│   ├── VALUATION_METHODOLOGY.md
│   ├── EVALUATION_PLAN.md
│   ├── REPORT_TEMPLATE.md
│   └── SEQUENCE.md
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   │
│   │   ├── api/
│   │   │   ├── routes_research.py
│   │   │   ├── routes_reports.py
│   │   │   └── routes_health.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   ├── errors.py
│   │   │   └── constants.py
│   │   │
│   │   ├── domain/
│   │   │   ├── universe.py
│   │   │   ├── financials.py
│   │   │   ├── valuation.py
│   │   │   ├── claims.py
│   │   │   └── reports.py
│   │   │
│   │   ├── agents/
│   │   │   ├── orchestrator.py
│   │   │   ├── data_foundation.py
│   │   │   ├── core_analyst.py
│   │   │   ├── valuation_reasoning.py
│   │   │   └── synthesis_auditor.py
│   │   │
│   │   ├── workflows/
│   │   │   ├── graph.py
│   │   │   ├── state.py
│   │   │   ├── edges.py
│   │   │   └── gates.py
│   │   │
│   │   ├── connectors/
│   │   │   ├── vnstock_client.py
│   │   │   ├── market_data_client.py
│   │   │   ├── financial_statement_client.py
│   │   │   ├── disclosure_client.py
│   │   │   ├── news_client.py
│   │   │   └── llm_client.py
│   │   │
│   │   ├── dataops/
│   │   │   ├── ingestion.py
│   │   │   ├── normalization.py
│   │   │   ├── quality_checks.py
│   │   │   ├── source_manifest.py
│   │   │   └── cache.py
│   │   │
│   │   ├── analytics/
│   │   │   ├── ratios.py
│   │   │   ├── peer_analysis.py
│   │   │   ├── forecasting.py
│   │   │   ├── dcf.py
│   │   │   ├── multiples.py
│   │   │   └── sensitivity.py
│   │   │
│   │   ├── evaluation/
│   │   │   ├── data_eval.py
│   │   │   ├── calculation_eval.py
│   │   │   ├── citation_eval.py
│   │   │   ├── numeric_consistency_eval.py
│   │   │   ├── hallucination_eval.py
│   │   │   ├── report_quality_eval.py
│   │   │   └── eval_runner.py
│   │   │
│   │   ├── reporting/
│   │   │   ├── templates/
│   │   │   │   └── equity_report_vi.md.jinja2
│   │   │   ├── renderer.py
│   │   │   └── exporter.py
│   │   │
│   │   └── schemas/
│   │       ├── requests.py
│   │       ├── responses.py
│   │       ├── financials.py
│   │       ├── valuation.py
│   │       ├── agent_outputs.py
│   │       └── evaluation.py
│   │
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── golden/
│   │   └── e2e/
│   │
│   └── scripts/
│       ├── ingest_universe.py
│       ├── backfill_golden_dataset.py
│       ├── generate_report.py
│       └── run_eval.py
│
├── data/
│   ├── universe/
│   │   └── pharma_vn_53.yaml
│   ├── golden/
│   │   ├── DHG/
│   │   ├── TRA/
│   │   └── IMP/
│   ├── raw/
│   ├── curated/
│   └── cache/
│
├── artifacts/
│   ├── reports/
│   ├── reports_html/
│   ├── valuation_results/
│   ├── claim_ledgers/
│   ├── source_manifests/
│   ├── eval_results/
│   └── run_logs/
│
├── frontend/
│   └── README.md
│
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_dcf_prototype.ipynb
│   └── 03_report_eval.ipynb
│
├── research/
│   ├── finrobot_architecture_notes.md
│   ├── vietnam_pharma_domain_notes.md
│   └── third_party/
│       └── README.md
│
└── .claude/
    ├── EXECUTION_STATE.md
    ├── rules/
    │   ├── architecture.md
    │   ├── backend.md
    │   ├── finance_domain.md
    │   ├── agent_contracts.md
    │   ├── valuation.md
    │   ├── evaluation.md
    │   ├── testing.md
    │   └── documentation.md
    └── plan/
        ├── 00_MASTER_CONTEXT.md
        ├── 01_DATA_CONTRACT.md
        ├── 02_GOLDEN_DATASET.md
        ├── 03_ANALYTICS_ENGINE.md
        ├── 04_VALUATION_ENGINE.md
        ├── 05_LANGGRAPH_5_AGENTS.md
        ├── 06_SYNTHESIS_AUDITOR.md
        ├── 07_EVALUATION_HARNESS.md
        └── 08_API_AND_REPORTING.md
```

### 13.1. Repository hygiene

Không đặt nguyên source code của FinRobot hoặc vnstock trong production path. Nếu cần tham khảo, đặt vào:

```text
research/third_party/
```

Production backend chỉ import qua adapter chính thức:

```text
backend/app/connectors/vnstock_client.py
```

---

## 14. API Design

| Endpoint | Method | Vai trò |
|---|---|---|
| `/api/health` | GET | Health check |
| `/api/tickers` | GET | Lấy danh sách mã cổ phiếu trong universe |
| `/api/research/start` | POST | Tạo analysis run |
| `/api/research/{run_id}/status` | GET | Kiểm tra trạng thái run |
| `/api/research/{run_id}/approve-assumptions` | POST | HITL duyệt assumption định giá |
| `/api/reports/{run_id}` | GET | Lấy report package |
| `/api/reports/{run_id}/markdown` | GET | Lấy Markdown report |
| `/api/reports/{run_id}/html` | GET | Lấy HTML report |
| `/api/evaluation/{run_id}` | GET | Lấy kết quả evaluation |
| `/api/sources/{run_id}` | GET | Lấy source manifest |

### Example request

```json
{
  "ticker": "DHG",
  "report_type": "full_equity_research",
  "language": "vi",
  "fiscal_years": [2021, 2022, 2023, 2024],
  "valuation_methods": ["dcf", "pe", "pb"],
  "require_human_review": true
}
```

### Example response

```json
{
  "run_id": "RUN_DHG_20260504_001",
  "ticker": "DHG",
  "status": "initialized",
  "message": "Research run created successfully."
}
```

---

## 15. 6-Week Delivery Roadmap

### Week 1 — Contract-first foundation

Deliverables:

- `DATA_CONTRACT.md`
- `AGENT_SPECS.md`
- `EVALUATION_PLAN.md`
- `VALUATION_METHODOLOGY.md`
- `pharma_vn_53.yaml`
- Backend skeleton: FastAPI, Pydantic, config, logging.
- Golden dataset folder structure.

Done criteria:

```text
pytest runs successfully
schema validation passes
no LLM call in financial calculation modules
5-agent contract is documented
```

### Week 2 — Data Foundation + Golden Dataset

Deliverables:

- `vnstock_client.py` or market data adapter.
- CSV/YAML ingestion.
- `normalization.py`.
- `source_manifest.py`.
- `quality_checks.py`.
- Golden data for 3 tickers.

Done criteria:

```text
DataSnapshot can be generated for 3 golden tickers
data_quality.completeness_score >= 0.85
source_manifest is non-empty
normalization unit tests pass
```

### Week 3 — Core Analytics Engine

Deliverables:

- `ratios.py`.
- `peer_analysis.py`.
- `forecasting.py`.
- `calculation_eval.py`.
- `core_analyst_agent.py`.

Done criteria:

```text
100% financial calculation unit tests pass
metrics_table is complete
no metric is generated by LLM
peer comparison works for golden tickers
```

### Week 4 — Valuation Engine + Reasoning

Deliverables:

- `dcf.py`.
- `multiples.py`.
- `sensitivity.py`.
- `valuation_reasoning.py`.
- `VALUATION_METHODOLOGY.md`.

Done criteria:

```text
valuation result is reproducible
target price traces back to assumptions
bear/base/bull scenarios are meaningfully different
DCF and multiples unit tests pass
```

### Week 5 — Synthesis + Auditor + Report

Deliverables:

- `equity_report_vi.md.jinja2`.
- `synthesis_auditor.py`.
- `citation_eval.py`.
- `numeric_consistency_eval.py`.
- `hallucination_eval.py`.
- `claim_ledger.json` generation.

Done criteria:

```text
100% quantitative claims have source_id
numeric_consistency_score >= 0.99
hallucination_risk_score <= configured threshold
Markdown report generated for 3 golden tickers
```

### Week 6 — End-to-End Hardening + Demo

Deliverables:

- End-to-end reports for 3 golden tickers.
- `eval_results/*.json`.
- API endpoints for research/report/evaluation.
- Demo script.
- Final README and documentation.

Done criteria:

```text
one command can generate a complete report package
3/3 golden tickers pass final evaluation gate
all critical tests pass
academic disclaimer included in every report
```

---

## 16. Developer Workflow with Claude Code, Cursor, and Codex

Dự án được triển khai bởi 1 người với 3 coding agents. Mỗi tool phải có vai trò rõ để tránh trùng việc và context rot.

| Tool | Vai trò chính | Không nên dùng cho |
|---|---|---|
| Claude Code | Implement module lớn theo plan, wiring LangGraph, refactor có kiểm soát | Tự quyết định architecture khi specs chưa khóa |
| Cursor | Review interactive, sửa bug nhỏ, kiểm tra flow, inspect diff | Giao refactor lớn nhiều file không có acceptance criteria |
| Codex | Viết unit tests, fixtures, deterministic utility, evaluation scripts | Viết agent prompt phức tạp hoặc sửa architecture tổng thể |

### Required task format for coding agents

```text
Task:
Scope:
Files allowed:
Files forbidden:
Expected outputs:
Tests to run:
Acceptance criteria:
Do not:
```

Example:

```text
Task: Implement financial ratio engine.

Scope:
- Implement backend/app/analytics/ratios.py
- Implement backend/tests/unit/test_ratios.py

Files allowed:
- backend/app/analytics/ratios.py
- backend/tests/unit/test_ratios.py
- backend/app/schemas/financials.py only if schema is missing

Files forbidden:
- backend/app/agents/*
- backend/app/workflows/*
- specs/*

Expected outputs:
- calculate_profitability_ratios()
- calculate_growth_metrics()
- calculate_leverage_metrics()
- calculate_liquidity_metrics()

Tests to run:
- pytest backend/tests/unit/test_ratios.py -q

Acceptance criteria:
- 100% tests pass
- No LLM calls
- No network calls
- Handles zero denominator safely

Do not:
- Do not add new dependencies
- Do not modify architecture
- Do not create agent logic
```

---

## 17. Quality Gates and Done Criteria

### 17.1. Data quality gate

Fail if:

```text
revenue missing
net_income missing
equity missing
total_assets missing
market_price missing
fiscal_years < 3
source_manifest empty
data_quality.completeness_score < 0.85
```

### 17.2. Calculation gate

Fail if:

```text
unit tests fail
division-by-zero is not handled
negative/invalid financial values are not flagged
valuation output cannot be reproduced
```

### 17.3. Assumption gate

Fail or require human review if:

```text
WACC <= terminal_growth_rate
terminal_growth_rate unrealistic
forecast growth materially exceeds historical growth without evidence
peer group has fewer than 3 valid companies
DCF target price deviates too much from relative valuation without explanation
```

### 17.4. Citation gate

Fail if:

```text
quantitative claim has no source_id
source_id not found in source_manifest
citation refers to a non-existent document
claim ledger missing
```

### 17.5. Numeric consistency gate

Fail if:

```text
number in report is not found in DataSnapshot, FundamentalAnalysis, or ValuationResult
rounded number exceeds tolerance
valuation conclusion uses target price not present in ValuationResult
```

### 17.6. Final report gate

Fail if:

```text
final_confidence < 0.70
report lacks disclaimer
report contains buy/sell command
report contains unsupported market leadership claim
report contains unsupported management quality claim
```

---

## 18. Limitations

1. Kết quả định giá phụ thuộc mạnh vào dữ liệu đầu vào và giả định dự phóng.
2. Dự án không cam kết độ chính xác đầu tư thực tế.
3. Dự án không thực hiện giao dịch tự động.
4. Dự án không thay thế tư vấn tài chính cá nhân hoặc báo cáo phân tích của tổ chức được cấp phép.
5. LLM có thể sai khi tóm tắt hoặc diễn giải; vì vậy các claim quan trọng phải có citation và các phép tính phải chạy bằng code deterministic.
6. Một số nguồn dữ liệu thương mại như FiinPro, Vietstock, SSI hoặc FiinGroup API chỉ được sử dụng nếu có quyền truy cập hợp lệ.
7. MVP ưu tiên 3 mã golden dataset có kiểm chứng, sau đó mới mở rộng lên toàn bộ 53 mã.
8. Báo cáo sinh ra là bản nháp nghiên cứu học thuật, cần human analyst duyệt trước khi sử dụng ngoài phạm vi học tập.

---

## 19. Disclaimer

Dự án này phục vụ mục đích học thuật và nghiên cứu. Kết quả phân tích không phải khuyến nghị đầu tư, không phải tư vấn tài chính cá nhân, không phải lời mời mua/bán chứng khoán và không đảm bảo lợi nhuận. Người dùng cần tự kiểm chứng dữ liệu, giả định, phương pháp định giá và rủi ro trước khi sử dụng bất kỳ kết quả nào trong thực tế.
