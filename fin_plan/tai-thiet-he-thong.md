# PLAN.md — Agent-First, Artifact-Governed Equity Research System

## 0. Mục Tiêu Tái Kiến Trúc

Tái kiến trúc hệ thống thành một **multi-agent equity research team** có khả năng tạo ra **full equity research report chất lượng cao**, tương đương bản nháp của một đội chuyên viên phân tích tài chính thâm niên tại công ty chứng khoán lớn.

Mục tiêu không phải là tạo thêm nhiều agent hoặc workflow phức tạp. Mục tiêu là tạo một production path duy nhất, dễ hiểu, dễ kiểm soát, nhưng đủ mạnh để sinh ra báo cáo có:

* luận điểm đầu tư rõ ràng;
* phân tích doanh nghiệp và ngành có chiều sâu;
* phân tích tài chính dựa trên số liệu thật;
* dự phóng theo driver, không dự phóng chung chung;
* định giá có lineage, assumption, sensitivity và target price bridge;
* bảng, biểu đồ, phụ lục tương tự báo cáo chuyên nghiệp;
* citation/evidence rõ ràng;
* critic review theo chuẩn senior analyst;
* human approval tại các điểm có judgment quan trọng.

Phiên bản đầu tiên chỉ hỗ trợ:

```text
run_type = full_report
```

Không triển khai `flash_memo`, `catalyst_refresh`, dynamic graph phức tạp, open-web crawling tự do, multi-run dependency hoặc partial recompute nâng cao trong bản tái kiến trúc đầu tiên.

---

## 1. Nguyên Tắc Thiết Kế Cốt Lõi

### 1.1. Agent-first, artifact-governed

Hệ thống là một **research team gồm các agent chuyên môn**, không phải một deterministic pipeline có vài bước gọi LLM.

Agent được quyền:

* lập luận chuyên môn;
* chọn approved tools;
* đặt câu hỏi follow-up có cấu trúc;
* phát hiện thiếu evidence;
* đề xuất assumption;
* xây thesis;
* phản biện report.

Nhưng mọi output quan trọng phải được lưu thành artifact có schema, version, checksum và trace.

### 1.2. Code làm việc code giỏi, agent làm việc agent giỏi

Code deterministic chịu trách nhiệm:

* ingestion;
* parsing;
* normalization;
* canonical fact promotion;
* retrieval;
* ratio calculation;
* forecast calculation;
* valuation;
* sensitivity;
* citation validation;
* numeric validation;
* rendering.

Agent chịu trách nhiệm:

* xác định cần phân tích gì;
* chọn tool nào cần dùng;
* diễn giải kết quả;
* nối số liệu với business drivers;
* xây thesis;
* phát hiện contradiction;
* đánh giá chất lượng lập luận.

### 1.3. Không để LLM tự tạo số

LLM không được tự tính nhẩm, tự tạo financial facts, tự thay đổi valuation artifact hoặc tự ghi số mới vào báo cáo.

Mọi số liệu trong báo cáo phải đến từ:

* `facts_snapshot.json`;
* `financial_analysis.json`;
* `forecast_model.json`;
* `valuation.json`;
* `market_snapshot.json`;
* `evidence_pack.json`.

### 1.4. Không overengineering

Bản đầu tiên giữ workflow cố định:

```text
Plan
-> Evidence
-> Financial Analysis
-> Forecast
-> Valuation
-> Assumption Approval
-> Readiness Review
-> Thesis & Report
-> Gates
-> Critic
-> One Revision
-> Final Approval
-> Render
```

Không dynamic graph rewriting.
Không vòng lặp vô hạn.
Không agent handoff hình thức.
Không legacy compatibility runtime.
Không fallback prose giả lập báo cáo.

---

## 2. Kiến Trúc Mục Tiêu

Hệ thống gồm **6 agents**:

```text
1. Research Manager Agent
2. Data & Evidence Agent
3. Financial Analysis Agent
4. Forecast & Valuation Agent
5. Thesis & Report Agent
6. Senior Critic Agent
```

Các agents sử dụng deterministic tools thông qua `ToolRegistry`.

Orchestrator chỉ quản lý:

* run lifecycle;
* stage order;
* artifact dependencies;
* timeout;
* retry;
* cost;
* approval checkpoints;
* revision limit;
* rendering decision.

Orchestrator không thay thế judgment chuyên môn của agents.

---

## 3. Production Workflow

```text
PREFLIGHT

RESEARCH_MANAGER_PLAN

DATA_AND_EVIDENCE

FINANCIAL_ANALYSIS
OPTIONAL_DATA_FOLLOWUP_FOR_FINANCIAL

DRIVER_BASED_FORECAST

VALUATION_PROPOSAL
WAITING_ASSUMPTION_APPROVAL
VALUATION_EXECUTION
OPTIONAL_DATA_FOLLOWUP_FOR_VALUATION

LOCK_RESEARCH_ARTIFACTS

RESEARCH_MANAGER_READINESS

THESIS_AND_REPORT

REPORT_ASSEMBLY

DETERMINISTIC_CONTENT_GATES

SENIOR_CRITIC_REVIEW

OPTIONAL_SINGLE_REPORT_REVISION

FINAL_EXPORT_GATE

WAITING_FINAL_APPROVAL

RENDER_AND_PUBLISH
```

### 3.1. Follow-up rule

Financial Analysis Agent, Forecast & Valuation Agent, hoặc Thesis & Report Agent được tạo tối đa **một structured evidence request**.

Nếu sau một follow-up vẫn thiếu dữ liệu:

* nếu non-critical: đánh dấu `insufficient_evidence` và tiếp tục;
* nếu critical cho valuation, thesis hoặc recommendation: chuyển `HITL_REQUIRED`.

### 3.2. Revision rule

Senior Critic Agent được yêu cầu tối đa **một report revision**.

Nếu sau một revision vẫn còn critical finding:

```text
status = HITL_REQUIRED
```

Không tạo loop sửa vô hạn.

---

## 4. Agent Contracts

## 4.1. Research Manager Agent

### Nhiệm vụ

Research Manager Agent đóng vai trò lead analyst. Agent này không viết report và không tính toán. Agent có hai lần được gọi:

1. Lập research plan đầu run.
2. Readiness review trước khi viết report.

### Input

```yaml
user_request:
ticker:
run_type:
available_data_inventory:
reference_report_template:
```

### Output: `research_plan.json`

```yaml
schema_version:
run_id:
ticker:
producer: research_manager_agent

research_questions:
  - question_id:
    question:
    priority: high | medium | low
    required_artifacts:
    required_evidence_types:

required_sections:
  - cover_summary
  - company_overview
  - business_model
  - recent_financial_performance
  - channel_and_product_analysis
  - industry_and_catalyst_analysis
  - driver_based_forecast
  - valuation_and_recommendation
  - risks_and_monitoring_factors
  - forecast_financial_summary
  - appendix

specialist_instructions:
  data_and_evidence:
  financial_analysis:
  forecast_and_valuation:
  thesis_and_report:

completion_criteria:
  minimum_evidence_coverage:
  required_tables:
  required_charts:
  required_valuation_outputs:
  required_critic_scores:

known_constraints:
```

### Output: `readiness_review.json`

```yaml
schema_version:
run_id:
ticker:
producer: research_manager_agent

decision: ready_for_report | human_review_required

answered_questions:
unresolved_questions:
critical_missing_items:
artifact_refs:

report_instructions:
  key_thesis_to_test:
  required_emphasis:
  required_caveats:
  prohibited_claims:
```

### Không được làm

* Không tính số liệu.
* Không viết report.
* Không sửa specialist artifacts.
* Không bypass gates.
* Không publish.
* Không tạo graph mới giữa run.

---

## 4.2. Data & Evidence Agent

### Nhiệm vụ

Data & Evidence Agent chịu trách nhiệm thu thập, chọn lọc và chuẩn hóa evidence cần thiết cho report.

Agent được quyền chọn approved tools và nguồn whitelist cố định.

### Whitelist nguồn

Bản đầu chỉ dùng fixed whitelist:

```text
1. Company official disclosures:
   - BCTC
   - BCTN
   - investor bulletin
   - nghị quyết
   - tài liệu ĐHĐCĐ
   - công bố thông tin doanh nghiệp

2. Exchange / disclosure sources:
   - HOSE
   - HNX
   - UPCOM
   - SSC

3. Pharma / regulatory / healthcare sources:
   - Cục Quản lý Dược
   - Bộ Y tế
   - BHYT
   - đấu thầu thuốc
   - văn bản regulatory liên quan

4. Market data sources already integrated.

5. Approved broker / industry reports if available.

6. User-uploaded documents approved for the run.
```

Không open web tự do trong v1.

### Output: `evidence_pack.json`

```yaml
schema_version:
run_id:
ticker:
producer: data_and_evidence_agent

canonical_fact_refs:
  - fact_id:
    metric:
    period:
    value:
    unit:
    source_ref:
    confidence:

document_evidence:
  - evidence_id:
    source_type:
    source_title:
    source_date:
    source_ref:
    excerpt_summary:
    relevant_sections:
    reliability_tier:

business_evidence:
  company_profile:
  business_segments:
  distribution_channels:
  product_groups:
  major_cost_drivers:
  shareholder_structure:

pharma_catalyst_evidence:
  eu_gmp_projects:
  tender_group_exposure:
  product_group_market_share:
  api_cost_trend:
  etc_otc_channel_trend:
  bhyt_policy_impact:
  regulatory_approval_timeline:
  capacity_expansion:
  competitive_position:

source_coverage:
  required_item:
  status: covered | partial | missing
  evidence_refs:

conflicts:
  - conflict_id:
    topic:
    source_a:
    source_b:
    conflict_description:
    suggested_handling:

unanswered_requests:
limitations:
```

### Không được làm

* Không tự tạo financial facts ngoài deterministic fact tools.
* Không dùng nguồn ngoài whitelist.
* Không tự viết thesis hoặc recommendation.

---

## 4.3. Financial Analysis Agent

### Nhiệm vụ

Financial Analysis Agent phân tích historical performance và financial health.

Agent chọn và gọi approved tools để tính:

* growth;
* margins;
* DuPont;
* ROE/ROA;
* working capital days;
* leverage;
* liquidity;
* interest coverage;
* cash conversion;
* anomaly detection.

### Output: `financial_analysis.json`

```yaml
schema_version:
run_id:
ticker:
producer: financial_analysis_agent

historical_periods:
latest_period:

income_statement_analysis:
  revenue_growth:
  gross_profit:
  gross_margin:
  selling_expense:
  admin_expense:
  operating_profit:
  net_profit:
  eps:

balance_sheet_analysis:
  cash:
  receivables:
  inventory:
  fixed_assets:
  construction_in_progress:
  short_term_debt:
  long_term_debt:
  equity:

cash_flow_analysis:
  operating_cash_flow:
  capex:
  free_cash_flow:
  dividends:
  net_borrowing:

ratio_diagnostics:
  profitability:
  efficiency:
  liquidity:
  leverage:
  coverage:
  working_capital_cycle:

business_interpretation:
  key_positive_drivers:
  key_negative_drivers:
  anomalies:
  one_off_items:
  sustainability_assessment:

segment_channel_analysis:
  etc_channel:
  otc_channel:
  product_groups:
    oncology:
    antibiotics:
    dialysis_solution:
    others:

financial_risks:
evidence_refs:
evidence_request:
```

### Yêu cầu chất lượng

Financial Analysis Agent không được chỉ liệt kê số. Mỗi nhận định phải có:

```text
number -> business reason -> implication for forecast or valuation
```

Ví dụ format bắt buộc:

```text
Doanh thu ETC tăng vì nhóm thuốc chủ lực duy trì nhu cầu và giá trị trúng thầu tăng.
Điều này hỗ trợ giả định tăng trưởng doanh thu ETC trong forecast.
```

---

## 4.4. Forecast & Valuation Agent

Trong v1, Forecast Agent và Valuation Agent được gộp thành một agent để tránh overengineering, vì forecast và valuation phụ thuộc chặt chẽ vào cùng một set assumptions.

### Nhiệm vụ

Agent này tạo forecast model và valuation proposal, sau đó gọi deterministic forecast/valuation engines.

Agent không tự tính valuation bằng text.

### 4.4.1. Driver-Based Forecast Contract

Forecast bắt buộc dựa trên drivers, không được dùng CAGR tổng chung nếu không có decomposition.

### Output: `forecast_model.json`

```yaml
schema_version:
run_id:
ticker:
producer: forecast_valuation_agent

forecast_horizon:
  start_year:
  end_year:
  explicit_years:

revenue_forecast:
  by_channel:
    etc:
      historical:
      forecast:
      drivers:
        - tender_value
        - hospital_demand
        - bhyt_coverage
        - eu_gmp_eligibility
        - product_mix
    otc:
      historical:
      forecast:
      drivers:
        - pharmacy_chain_expansion
        - traditional_pharmacy_demand
        - product_competitiveness
    others:

  by_product_group:
    oncology:
      historical:
      forecast:
      drivers:
        - market_share
        - tender_group_upgrade
        - eu_gmp_timeline
        - new_product_registration
        - cancer_incidence_trend
    antibiotics:
      historical:
      forecast:
      drivers:
        - hospital_demand
        - tender_group_upgrade
        - competition
        - antimicrobial_policy
    dialysis_solution:
      historical:
      forecast:
      drivers:
        - patient_demand
        - market_share
        - supply_advantage
    others:

gross_margin_forecast:
  assumptions:
    api_cost_trend:
    product_mix:
    eu_gmp_pricing_uplift:
    tender_group_pricing:
  forecast:

opex_forecast:
  selling_expense:
  admin_expense:
  assumptions:

working_capital_forecast:
  receivable_days:
  inventory_days:
  payable_days:

capex_and_depreciation:
  capex_projects:
  construction_in_progress:
  depreciation:

debt_cash_interest:
  cash:
  short_term_debt:
  long_term_debt:
  interest_expense:
  net_borrowing:

share_count:
  current:
  forecast:
  dilution_or_bonus_issue_assumptions:

forecast_quality_checks:
  historical_continuity_check:
  driver_support_check:
  margin_sanity_check:
  balance_sheet_balance_check:
  cash_flow_consistency_check:

evidence_refs:
limitations:
```

### Forecast minimum requirements

Report không được qua readiness nếu thiếu:

* revenue forecast theo kênh;
* revenue forecast theo nhóm sản phẩm chính;
* gross margin forecast;
* opex forecast;
* working capital forecast;
* capex/depreciation assumptions;
* debt/cash assumptions;
* EPS forecast;
* forecast financial statement summary.

### 4.4.2. Valuation Method Contract

Default valuation v1:

```text
FCFF + FCFE, weight 50:50.
```

Có thể cho analyst thay đổi weight trong HITL, nhưng hệ thống mặc định dùng 50:50 để giữ nhất quán.

### Output: `valuation_proposal.json`

```yaml
schema_version:
run_id:
ticker:
producer: forecast_valuation_agent

selected_methods:
  - FCFF
  - FCFE

method_weights:
  FCFF: 50
  FCFE: 50

key_assumptions:
  forecast_horizon:
  terminal_growth:
  risk_free_rate:
  equity_risk_premium:
  beta:
  cost_of_equity:
  cost_of_debt:
  tax_rate:
  wacc:
  share_count:
  cash_and_short_term_investments:
  short_term_debt:
  long_term_debt:

assumption_rationale:
  - assumption:
    value:
    rationale:
    evidence_refs:
    sensitivity_importance:

scenario_design:
  base_case:
  bull_case:
  bear_case:

approval_required_items:
  - wacc
  - terminal_growth
  - revenue_growth
  - gross_margin
  - capex
  - working_capital
  - net_borrowing
  - method_weights
```

### Output after approval: `valuation.json`

```yaml
schema_version:
run_id:
ticker:
producer: valuation_engine

approved_assumption_refs:

fcff:
  projected_fcff:
  pv_of_fcff:
  terminal_value:
  pv_of_terminal_value:
  enterprise_value:
  cash_and_short_term_investments:
  debt:
  equity_value:
  shares_outstanding:
  value_per_share:

fcfe:
  projected_fcfe:
  pv_of_fcfe:
  terminal_value:
  pv_of_terminal_value:
  equity_value:
  shares_outstanding:
  value_per_share:

weighted_target_price:
  raw:
  rounded:
  upside_downside_vs_current_price:

sensitivity:
  wacc_vs_terminal_growth:
  revenue_growth_vs_margin:
  scenario_values:

sanity_checks:
  pe_implied:
  ev_ebitda_implied:
  historical_multiple_comparison:
  peer_multiple_comparison:
  target_price_reconciliation:
  balance_sheet_bridge_check:

limitations:
```

### Valuation gates

Fail nếu:

* target price không reconcile với FCFF/FCFE;
* share count thiếu;
* cash/debt treatment thiếu;
* FCFE net borrowing không có assumption;
* WACC thiếu components;
* terminal growth vượt policy;
* valuation output không tái lập được từ artifacts;
* upside/downside không khớp current price;
* valuation conclusion mâu thuẫn với recommendation.

---

## 4.5. Thesis & Report Agent

### Nhiệm vụ

Thesis & Report Agent tạo report draft theo professional equity research template.

Agent không được viết report tự do. Agent phải bám `Target Report Contract`.

### Input

```yaml
research_plan:
readiness_review:
evidence_pack:
financial_analysis:
forecast_model:
valuation:
market_snapshot:
reference_template_contract:
```

### Output: `report_draft.json`

```yaml
schema_version:
run_id:
ticker:
producer: thesis_report_agent

sections:
  cover_investment_summary:
  trading_snapshot:
  company_overview:
  business_model:
  recent_financial_performance:
  channel_and_product_analysis:
  industry_and_catalyst_analysis:
  driver_based_forecast:
  valuation_and_recommendation:
  risks_and_monitoring_factors:
  forecast_financial_summary:
  appendix:

claims:
  - claim_id:
    section:
    text:
    claim_type: fact | inference | opinion
    quantitative: true | false
    supporting_refs:
    source_artifact_refs:
    confidence:
    uncertainty:
    reviewer_note:

required_tables:
required_charts:
limitations:
```

### Report writing rule

Mỗi section phân tích chính phải có:

```text
1. Key message
2. Supporting numbers
3. Business explanation
4. Implication for forecast / valuation / thesis
5. Risk or caveat if relevant
```

Không được viết kiểu liệt kê số liệu.
Không được viết section dưới dạng summary chung chung.
Không được đưa nhận định định lượng nếu không có source hoặc artifact.

---

## 4.6. Senior Critic Agent

### Nhiệm vụ

Senior Critic Agent đóng vai trò research director/reviewer tại công ty chứng khoán.

Critic không chỉ kiểm lỗi citation. Critic phải đánh giá chất lượng report theo chuẩn senior analyst.

### Output: `critic_review.json`

```yaml
schema_version:
run_id:
ticker:
producer: senior_critic_agent

decision: pass | revision_required | human_review_required

scorecard:
  thesis_strength:
    score:
    explanation:
  driver_logic:
    score:
    explanation:
  forecast_consistency:
    score:
    explanation:
  valuation_coherence:
    score:
    explanation:
  evidence_depth:
    score:
    explanation:
  sector_specificity:
    score:
    explanation:
  risk_balance:
    score:
    explanation:
  table_chart_completeness:
    score:
    explanation:
  narrative_quality:
    score:
    explanation:
  numeric_integrity:
    score:
    explanation:
  citation_integrity:
    score:
    explanation:

findings:
  - finding_id:
    severity: low | medium | high | critical
    target_section:
    target_agent:
    claim_id:
    issue_type:
      - unsupported_claim
      - weak_thesis
      - missing_driver
      - forecast_not_driver_based
      - valuation_incoherent
      - numeric_mismatch
      - citation_mismatch
      - missing_risk
      - overconfident_recommendation
      - poor_storytelling
      - missing_table_or_chart
    explanation:
    evidence_refs:
    required_action:

revision_instructions:
```

### Minimum pass thresholds

```yaml
minimum_scores:
  thesis_strength: 8
  driver_logic: 8
  forecast_consistency: 8
  valuation_coherence: 8
  evidence_depth: 7.5
  sector_specificity: 8
  risk_balance: 7.5
  table_chart_completeness: 8
  narrative_quality: 8
  numeric_integrity: 9.5
  citation_integrity: 9.5
```

Nếu `numeric_integrity` hoặc `citation_integrity` dưới ngưỡng, report không được publish.

---

## 5. Target Report Contract

Final report phải bám cấu trúc tối thiểu sau.

## 5.1. Cover Investment Summary

Bắt buộc có:

* ticker;
* company name;
* sector;
* current price;
* target price;
* upside/downside;
* recommendation;
* market cap;
* shares outstanding;
* EPS trailing;
* P/E trailing;
* 52-week high/low;
* average trading volume;
* foreign ownership;
* main business;
* main cost driver;
* main risk;
* investment thesis headline;
* 3-5 bullet key outlook points;
* key monitoring factors.

## 5.2. Company Overview

Bắt buộc có:

* business description;
* revenue structure;
* distribution channels;
* product group breakdown;
* cost structure;
* competitive position;
* data disclosure quality;
* major shareholders if available.

## 5.3. Business Model and Segment Analysis

Bắt buộc phân tích:

* ETC channel;
* OTC channel;
* product groups;
* key customer groups;
* pricing mechanism;
* tender exposure;
* regulation dependency;
* capacity and plant standards.

## 5.4. Recent Financial Performance

Bắt buộc có:

* latest quarter;
* latest 9M or full-year period;
* revenue;
* gross profit;
* gross margin;
* SG&A;
* operating profit;
* financial income/expense;
* interest expense;
* PBT;
* NPAT;
* margin analysis;
* plan completion;
* YoY comparison;
* explanation of positive/negative drivers.

## 5.5. Channel and Product-Line Analysis

Bắt buộc có nếu dữ liệu đủ:

* ETC revenue trend;
* OTC revenue trend;
* oncology revenue;
* antibiotics revenue;
* dialysis solution revenue;
* market share where available;
* tender value;
* key drivers by product group.

## 5.6. Industry and Catalyst Analysis

Bắt buộc có:

* sector growth context;
* regulatory context;
* BHYT or healthcare policy impact;
* tender group impact;
* API cost trend;
* EU-GMP or manufacturing standard catalyst;
* capacity expansion;
* competitive risks;
* catalyst timeline.

## 5.7. Driver-Based Forecast

Bắt buộc có:

* forecast period;
* revenue by channel;
* revenue by product group;
* gross margin forecast;
* SG&A forecast;
* EBIT/NPAT/EPS forecast;
* working capital assumptions;
* capex/depreciation assumptions;
* debt/cash assumptions;
* explanation of each major driver.

## 5.8. Valuation and Recommendation

Bắt buộc có:

* selected methods;
* method weights;
* FCFF result;
* FCFE result;
* weighted target price;
* current price;
* upside/downside;
* recommendation;
* WACC;
* COE;
* COD;
* beta;
* risk-free rate;
* equity risk premium;
* terminal growth;
* forecast horizon;
* sensitivity table;
* sanity check against multiples;
* key valuation risks.

## 5.9. Risks and Monitoring Factors

Bắt buộc có:

* input cost risk;
* regulatory approval risk;
* tender risk;
* competition risk;
* execution/capex risk;
* margin risk;
* demand risk;
* liquidity/market risk if relevant;
* what to monitor next.

## 5.10. Forecast Financial Statement Summary

Bắt buộc có bảng:

* income statement forecast;
* balance sheet forecast;
* profitability ratios;
* liquidity/leverage ratios;
* working capital days;
* EPS forecast.

## 5.11. Appendix

Bắt buộc có nếu evidence đủ:

* project timeline;
* tender/product evidence;
* key product price comparison;
* market share table;
* valuation assumptions;
* source/evidence table;
* disclaimer.

---

## 6. Required Table and Chart Contract

Report không được publish nếu thiếu các bảng/biểu đồ tối thiểu sau, trừ khi evidence thật sự không có và được đánh dấu `insufficient_evidence`.

### 6.1. Required tables

```text
1. Trading snapshot table
2. Company overview table
3. Recent financial results table
4. Business plan completion table
5. Forecast assumptions table
6. Valuation summary table
7. DCF assumptions table
8. FCFF/FCFE bridge table
9. Forecast financial statement summary table
10. Risk and monitoring factors table
```

### 6.2. Required charts

```text
1. Stock price vs benchmark chart
2. Revenue by channel chart
3. Product group revenue or market share chart
4. Gross margin / net margin trend chart
5. Forecast revenue chart
6. Forecast gross profit or margin chart
7. Valuation sensitivity chart/table
8. Recommendation history chart if historical recommendations exist
```

### 6.3. Chart generation rule

Charts are generated deterministically from artifacts.
LLM may suggest chart interpretation but may not fabricate chart data.

---

## 7. Artifact Contract

```text
runs/{run_id}/
  manifest.json

  research_plan.json
  market_snapshot.json
  facts_snapshot.json
  evidence_pack.json

  financial_analysis.json
  forecast_model.json
  valuation_proposal.json
  approved_assumptions.json
  valuation.json

  readiness_review.json

  report_draft.json
  report_draft.md
  claim_ledger.json

  quality_gate.json
  critic_review.json
  revised_report_draft.json

  chart_specs.json
  table_specs.json

  final_report_model.json
  trace.jsonl

  report.html
  report.pdf
```

Mỗi artifact bắt buộc có:

```yaml
schema_version:
run_id:
ticker:
producer:
input_refs:
version:
checksum:
created_at:
updated_at:
```

---

## 8. Tool Registry Contract

Mỗi tool trong `ToolRegistry` phải khai báo:

```yaml
tool_name:
description:
allowed_agent_roles:
input_schema:
output_schema:
side_effect_permission:
timeout_seconds:
retry_policy:
artifact_producer: true | false
required_source_refs:
cost_policy:
```

### Tool groups

```text
1. Source / ingestion tools
2. Parser / OCR tools
3. Retrieval tools
4. Source validation tools
5. Canonical fact tools
6. Financial calculation tools
7. Forecast tools
8. Valuation tools
9. Sensitivity tools
10. Citation validation tools
11. Numeric validation tools
12. Chart/table generation tools
13. Report rendering tools
```

Agents call tools.
Tools return artifacts.
Gates validate artifacts.

---

## 9. Deterministic Gates

## 9.1. Data Quality Gate

Fail nếu:

* thiếu source cho key financial facts;
* mismatch ticker;
* mismatch period;
* unit không rõ;
* duplicate/conflicting facts không được xử lý;
* stale data không được flag.

## 9.2. Forecast Quality Gate

Fail nếu:

* revenue forecast không có driver decomposition;
* gross margin forecast không có cost/product mix rationale;
* balance sheet không balance;
* working capital forecast thiếu assumptions;
* capex/depreciation thiếu assumptions;
* forecast growth nhảy bất thường không có explanation.

## 9.3. Valuation Gate

Fail nếu:

* valuation không reproduce được;
* FCFF/FCFE bridge thiếu;
* WACC components thiếu;
* target price không reconcile;
* sensitivity thiếu;
* upside/downside sai;
* recommendation không khớp valuation.

## 9.4. Citation Gate

Fail nếu:

* quantitative claim không có source;
* citation không support claim;
* source ngoài whitelist;
* claim dùng evidence stale mà không flag;
* citation trỏ nhầm ticker/period.

## 9.5. Report Completeness Gate

Fail nếu thiếu section bắt buộc:

* investment summary;
* company overview;
* recent financial performance;
* driver-based forecast;
* valuation;
* risks;
* forecast financial summary.

## 9.6. Senior Analyst Quality Gate

Fail nếu:

* thesis chung chung;
* không có causal reasoning;
* chỉ liệt kê số liệu;
* không nối forecast với valuation;
* risk analysis một chiều;
* thiếu industry/catalyst logic;
* narrative không đạt chuẩn chuyên nghiệp.

---

## 10. Evaluation Harness

## 10.1. Golden Report Benchmark

Tạo benchmark từ các báo cáo chuyên nghiệp đã upload/được phê duyệt.

Mỗi generated report được so với benchmark theo:

```yaml
section_completeness:
table_completeness:
chart_completeness:
driver_based_forecast_presence:
valuation_reconciliation:
claim_grounding:
numeric_consistency:
insight_density:
sector_specificity:
senior_analyst_readability:
risk_balance:
```

## 10.2. Report Quality Score

Mỗi report có score:

```yaml
report_quality_score:
  structure: 0-10
  financial_depth: 0-10
  forecast_depth: 0-10
  valuation_quality: 0-10
  evidence_quality: 0-10
  narrative_quality: 0-10
  chart_table_quality: 0-10
  critic_pass: true | false
```

Minimum publish threshold:

```yaml
minimum_publish_score:
  structure: 8
  financial_depth: 8
  forecast_depth: 8
  valuation_quality: 8
  evidence_quality: 8
  narrative_quality: 8
  chart_table_quality: 8
```

## 10.3. Regression Dataset

Create golden datasets for MVP tickers:

```text
DHG
IMP
DMC
TRA
DBD
```

For each ticker:

* 3-5 years financial facts;
* latest quarterly facts;
* market data snapshot;
* official disclosures;
* industry/catalyst documents;
* expected valuation sanity range;
* expected report section checklist.

---

## 11. Reporting Assembly

`ReportAssembler` is deterministic.

Input:

```text
report_draft.json
claim_ledger.json
financial_analysis.json
forecast_model.json
valuation.json
chart_specs.json
table_specs.json
market_snapshot.json
```

Output:

```text
final_report_model.json
report.html
report.pdf
```

ReportAssembler may format and arrange content.
ReportAssembler may not invent prose or numbers.
If a required section is missing, it fails.

---

## 12. Codebase Rebuild and Cleanup

### 12.1. Orchestration

* Replace old runner with lifecycle-focused orchestrator.
* Remove compiled-but-unused LangGraph.
* Remove Supervisor compatibility facade.
* CLI, API and batch must use the same production path.
* API must not connect to DB at import time.
* Remove agent handoff artifacts and handoff gates.

### 12.2. Agent Runtime

Remove old prompts/configs:

```text
supervisor
data_retrieval
financial_analyst
valuation
report_writer_critic
news_editor
```

Create new configs:

```text
research_manager
data_evidence
financial_analysis
forecast_valuation
thesis_report
senior_critic
```

Use typed artifacts, not generic `AgentResult`.

Agent context must include actual artifact content needed for reasoning, not only file paths.

### 12.3. Deterministic Services

Keep and expose as tools:

* connectors;
* OCR/parser;
* normalization;
* canonical fact promotion;
* retrieval;
* citation validation;
* evidence indexing;
* ratio calculator;
* forecast engine;
* valuation engine;
* sensitivity engine;
* chart generator;
* renderer;
* gates.

### 12.4. Reporting

* Remove monolithic production `generate_report.py`.
* Remove glob/latest artifact discovery.
* Remove compatibility facades.
* Remove deterministic prose fallback.
* Final report must use persisted Thesis & Report Agent artifact.

### 12.5. News and Evidence

* No separate News Editor Agent in v1.
* News/catalyst is part of Data & Evidence Agent toolset.
* Keep whitelist enforcement in code and DB.
* Catalyst evidence must be structured into `pharma_catalyst_evidence`.

### 12.6. Evaluation and Observability

* Langfuse root trace per run.
* Child spans for agents, tools, gates, approvals, render.
* Remove fake/static OfflineEvaluator.
* Create real benchmark and report quality scoring.

### 12.7. Destructive Cutover

* Create backup before reset.
* Dry-run reset by default.
* Require explicit confirmation token.
* Squash migrations into fresh baseline.
* Remove obsolete schemas, tests, docs and compatibility code.
* UTF-8 is mandatory for all active files.

---

## 13. Test Plan

## 13.1. Agent Contract Tests

* Registry contains exactly six agents.
* Each agent receives typed context.
* Each agent can call only approved tools.
* Research Manager is called only at plan and readiness.
* Structured evidence request triggers at most one follow-up.
* Critic triggers at most one report revision.
* Agents cannot publish, bypass gates, or write unapproved numeric facts.

## 13.2. Forecast and Valuation Tests

* Forecast model includes channel decomposition.
* Forecast model includes product group decomposition.
* Balance sheet balances.
* Cash flow reconciles.
* FCFF and FCFE reproduce from assumptions.
* Target price reconciles with share count.
* Sensitivity table exists.
* Recommendation matches upside/downside policy.

## 13.3. Report Quality Tests

* All required sections exist.
* All required tables exist.
* All required charts exist or are marked insufficient evidence.
* Each quantitative claim has citation.
* Claim ledger maps every claim to artifact refs.
* Narrative contains business interpretation, not only number listing.
* Risks are specific and balanced.
* Final report passes senior analyst quality rubric.

## 13.4. Workflow Tests

* CLI, API, and batch use same production path.
* Full report pauses at assumption approval.
* Full report pauses at final approval.
* HITL is triggered for critical missing evidence.
* HTML/PDF are created only after final approval.
* Old legacy graph and artifact contracts are not referenced.

## 13.5. Golden Benchmark Tests

For each MVP ticker:

* run full report;
* compare with benchmark checklist;
* compute report quality score;
* record numeric error rate;
* record citation coverage;
* record critic findings;
* store regression result.

---

## 14. Final Acceptance Criteria

The restructuring is accepted only when all conditions below pass.

### 14.1. Architecture

* One production path.
* Six agents only.
* No old supervisor facade.
* No unused LangGraph.
* No handoff gate.
* No legacy glob report loading.
* No fake evaluator.
* No deterministic prose fallback.

### 14.2. Agent Quality

System demonstrates actual agency:

* Research Manager creates useful research plan.
* Data & Evidence Agent selects relevant sources.
* Financial Analysis Agent explains drivers, not only numbers.
* Forecast & Valuation Agent builds driver-based model.
* Thesis & Report Agent writes professional research narrative.
* Senior Critic Agent catches weak thesis, weak forecast, unsupported claims and valuation issues.

### 14.3. Report Quality

Final report must include:

* investment summary;
* trading snapshot;
* company overview;
* business model;
* recent financial performance;
* channel/product analysis;
* industry/catalyst analysis;
* driver-based forecast;
* valuation and recommendation;
* risks and monitoring factors;
* forecast financial statement summary;
* appendix and evidence table.

### 14.4. Financial Quality

* All numbers trace to artifacts.
* Valuation is reproducible.
* FCFF/FCFE bridge is complete.
* Target price reconciles.
* Forecast is driver-based.
* Sensitivity exists.
* Financial statements are internally consistent.

### 14.5. Professional Quality

Report must read like a senior brokerage analyst draft:

* clear thesis;
* strong causal reasoning;
* specific business drivers;
* sector-specific insight;
* balanced risks;
* coherent valuation rationale;
* professional Vietnamese writing;
* dense but readable analysis;
* useful tables/charts;
* no generic filler.

---

## 15. Implementation Priority

### Phase 1 — Core Path

Build:

```text
full_report workflow
six agent configs
ToolRegistry
artifact contracts
basic gates
ReportAssembler
```

### Phase 2 — Research Harness

Build:

```text
target report contract
driver-based forecast model
valuation contract
chart/table specs
senior critic rubric
```

### Phase 3 — Evaluation

Build:

```text
golden benchmark
report quality score
MVP ticker regression set
Langfuse trace
cost ledger
```

### Phase 4 — Cleanup

Remove:

```text
legacy agents
legacy prompts
legacy report loader
old artifacts
unused LangGraph
fake evaluator
compatibility facades
```

---

## 16. Non-Goals for v1

Do not implement:

* catalyst refresh;
* flash memo;
* autonomous publish;
* open web crawling;
* dynamic graph rewriting;
* multi-run dependency;
* unlimited agent loops;
* portfolio-level research;
* intraday trading signal;
* autonomous stock picking;
* user-facing complex dashboard before report quality is solved.

---

## 17. Final Direction

The system must not be judged by whether it has many agents.
It must be judged by whether it can produce a high-quality, auditable, valuation-backed equity research report.

The final architecture is:

```text
A fixed, simple production workflow
+ real specialist agents
+ deterministic financial tools
+ driver-based forecast harness
+ professional report contract
+ senior analyst critic rubric
+ artifact lineage
+ human approval
```

This is the minimum architecture strong enough to produce reports comparable to a professional analyst team while remaining understandable, controllable and maintainable.
