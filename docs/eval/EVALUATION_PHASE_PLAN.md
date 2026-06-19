# Kế hoạch đánh giá năng lực hệ thống Vietnam Pharma Equity Research Agent

## 1. Bối cảnh

Hệ thống Vietnam Pharma Equity Research Agent không nên được đánh giá bằng một điểm chất lượng tổng quát duy nhất. Đây là một hệ thống nghiên cứu cổ phiếu theo luồng nhiều lớp, gồm thu thập dữ liệu, chuẩn hóa dữ liệu, tạo fact chính quy, truy xuất bằng chứng, tính toán tài chính, sinh nội dung báo cáo, kiểm định citation, xuất bản artifact và phê duyệt con người. Mỗi lớp có dạng lỗi khác nhau, mức độ rủi ro khác nhau và cần framework đánh giá khác nhau.

Nguyên tắc nền tảng của giai đoạn đánh giá là: **LLM không được dùng để xác nhận tính đúng đắn của số liệu tài chính hoặc công thức định giá**. Các phần định lượng phải được kiểm bằng kiểm thử xác định, invariant tài chính, dữ liệu vàng, formula trace và gate fail-closed. LLM-as-judge chỉ được sử dụng cho các tiêu chí mềm như mức độ bám nguồn của narrative, tính đặc thù doanh nghiệp, role adherence của tác tử và chất lượng trình bày báo cáo.

Luồng đánh giá chuẩn của hệ thống phải đi theo thứ tự sau:

```text
Data reliability
-> Fact reconciliation
-> Retrieval and source provenance
-> Financial calculation invariants
-> Citation and claim grounding
-> Agent workflow and narrative evaluation
-> Report quality evaluation
-> Package validation
-> Human final approval
-> Client-final render authorization
-> Observability, cost and latency evaluation
```

Nếu một lớp deterministic critical fail thì không được để điểm LLM judge hoặc chất lượng văn bản ghi đè. Báo cáo chỉ được coi là publishable khi dữ liệu, valuation, citation, package validation, approval và publication readiness đều đạt.

---

## 2. Mục tiêu đánh giá

Giai đoạn evaluation cần trả lời bảy câu hỏi nghiệm thu chính:

| Câu hỏi nghiệm thu | Rủi ro nếu không đánh giá | Lớp đánh giá phù hợp |
|---|---|---|
| Dữ liệu đầu vào có đúng, đủ, mới và truy vết được không? | Fact sai hoặc stale được promote vào valuation | Data reliability evaluation |
| Retrieval có lấy đúng bằng chứng và đủ ngữ cảnh không? | Report có citation nhưng citation không support claim | RAG and evidence evaluation |
| Citation có thật sự truy về nguồn, fact, artifact hoặc formula trace không? | Citation hình thức, citation generic, Tier 3-only material source | Citation and source provenance evaluation |
| Mô hình tài chính có tính đúng, tái lập và nhất quán không? | Target price sai nhưng báo cáo vẫn có vẻ chuyên nghiệp | Financial calculation evaluation |
| Agent có dùng đúng tool, đúng vai trò và đúng artifact không? | Hallucination, tool misuse, vượt quyền tác tử, LLM tự tính số | Agent workflow evaluation |
| Báo cáo có đạt chuẩn phân tích, citation, presentation và export governance không? | PDF đẹp nhưng không đạt chuẩn report-quality hoặc bypass gate | Report quality evaluation |
| Hệ thống có ổn định về chi phí, độ trễ, trace và regression không? | Chạy được một lần nhưng không mở rộng được sang universe | Observability, cost and latency evaluation |

---

## 3. Nguyên tắc thiết kế evaluation

### 3.1. Deterministic-first

Các lỗi liên quan đến số liệu, công thức, citation, source tier, snapshot, package manifest và export authorization phải được kiểm bằng code. Không dùng LLM-as-judge để quyết định các lỗi này.

### 3.2. Artifact-level evaluation

Không đánh giá hệ thống bằng output cuối cùng duy nhất. Mỗi run phải sinh các artifact đánh giá riêng:

```text
data_quality.json
retrieval_eval.json
financial_eval.json
citation_eval.json
agent_eval.json
report_eval.json
publication_readiness.json
observability_eval.json
```

Các artifact này phải được gắn với `run_id`, `ticker`, `snapshot_id`, `artifact_version`, `source_checksum` và trạng thái gate tương ứng.

### 3.3. Fail-closed governance

Báo cáo final không được render nếu run đang ở trạng thái `blocked`, `failed`, `needs_human_review` hoặc chỉ mới `auto_exported`. Trạng thái `auto_exported` chỉ thể hiện bản nháp có thể xem nội bộ, không tương đương với client-final approval.

### 3.4. Claim-level accountability

Mọi claim định lượng, claim catalyst và claim ảnh hưởng đến khuyến nghị phải có `claim_id`, `claim_type`, `materiality`, `source_refs`, `fact_refs`, `artifact_refs` hoặc `formula_trace_refs`. Citation ở cấp tài liệu chung chung không đủ cho final.

### 3.5. Human-calibrated semantic evaluation

Các tiêu chí như insight depth, professional tone, storytelling, risk balance và company specificity cần có reviewer chấm mẫu trước. LLM judge chỉ được dùng sau khi đã được calibrate với human labels.

### 3.6. Benchmark versioning

Mỗi benchmark phải có version cố định để tránh leakage và cherry-picking:

```text
benchmark_version
source_snapshot_id
document_checksums
expected_fact_ids
expected_chunk_ids
expected_formula_trace_version
reviewer_rubric_version
```

---

## 4. Framework stack đề xuất

| Lớp evaluation | Framework/công cụ | Vai trò | Mức ưu tiên |
|---|---|---|---|
| Deterministic unit and invariant tests | `pytest` | Kiểm thử formula, gate, schema, renderer, regression | P0 |
| Structured payload validation | `Pydantic` | Validate artifact JSON, run state, stage output contract | P0 |
| Database integrity | PostgreSQL constraints | Enforce uniqueness, foreign key, source/fact/snapshot integrity | P0 |
| DataFrame schema validation | `Pandera` | Validate connector DataFrame trước normalization | P1 |
| Property-based testing | `hypothesis` | Sinh edge cases cho công thức tài chính | P1 |
| RAG semantic evaluation | `Ragas` | Context precision, context recall, faithfulness, response relevancy, noise sensitivity | P1 |
| Trace and dataset management | `Langfuse` | Lưu traces, datasets, experiment scores, manual annotation | P1 |
| Agent and narrative judge | `DeepEval` hoặc OpenAI Evals | Role adherence, tool correctness, custom G-Eval rubric, report narrative judge | P2 |
| Domain-specific gates | Custom validators | Source tier, official source, FCFF/FCFE bridge, recommendation policy, client-final authorization | P0 |

Quy tắc lựa chọn framework:

| Trường hợp | Không nên dùng | Nên dùng |
|---|---|---|
| Kiểm công thức định giá | LLM judge | `pytest`, formula trace, golden artifact |
| Kiểm đúng/sai số liệu trong report | LLM judge đơn thuần | Numeric consistency gate + citation map |
| Kiểm retrieval có lấy đúng context không | Chỉ đọc thủ công | RAG golden set + Ragas |
| Kiểm narrative có chuyên nghiệp không | Regex đơn giản | Human rubric + DeepEval/OpenAI Evals |
| Kiểm agent có gọi đúng tool không | LLM judge | Trace gate + permission metadata |
| Kiểm vận hành cost/latency | Log rời rạc | Langfuse + cost ledger + observability artifact |

---

## 5. Kế hoạch đánh giá theo từng đối tượng

## 5.1. Data reliability evaluation

### Mục tiêu

Đảm bảo dữ liệu đầu vào đúng, đủ, mới, có nguồn và không bị promote sai thành canonical fact. Đây là lớp evaluation đầu tiên vì toàn bộ valuation, citation và report đều phụ thuộc vào fact chính quy.

### Đối tượng cần đánh giá

| Đối tượng | Câu hỏi kiểm định | Failure mode cần chặn |
|---|---|---|
| Source registry | Nguồn có được allow-list và gán tier đúng không? | Dùng nguồn không chính thức cho claim trọng yếu |
| Raw observations | Payload có đủ ticker, period, statement, metric, unit không? | Mất dòng dữ liệu hoặc sai scope kỳ báo cáo |
| Financial facts | Metric canonical có mapping đúng với taxonomy không? | Mapping sai `net_income`, `debt`, `cash`, `capex` |
| OCR candidate facts | OCR có đủ confidence, validation và reconciliation không? | OCR scan sai được promote trực tiếp |
| Golden facts | Fact production có khớp fixture DHG/DBD không? | Regression sau refactor normalizer |
| Freshness | Snapshot có quá cũ so với reporting period không? | Báo cáo dùng artifact stale |
| Reconciliation | Vnstock/API/OCR/official doc có mâu thuẫn không? | Nguồn aggregator ghi đè official source |

### Framework sử dụng

| Framework | Vai trò |
|---|---|
| `pytest` | Regression và invariant tests |
| `Pydantic` | Contract cho records, run state và artifact schema |
| `Pandera` | DataFrame schema validation cho connector output |
| SQL constraints | Referential integrity, uniqueness, source/fact/snapshot integrity |
| Golden CSV/JSON fixtures | Expected facts cho ticker pilot |

### Benchmark cần xây

| Dataset | Mục đích |
|---|---|
| `config/dataset/golden/financials/DHG.csv` | Golden facts cho ticker pilot chính |
| `config/dataset/golden/financials/DBD.csv` | Cross-company regression |
| `config/dataset/golden/financials/IMP.csv` | Kiểm thử mở rộng trong pharma manufacturer |
| `config/dataset/golden/financials/DMC.csv` | Kiểm thử thêm dữ liệu công ty cùng ngành |
| `config/dataset/golden/financials/TRA.csv` | Kiểm thử ticker có đặc thù khác DHG |
| Official annual report PDFs | OCR và official reconciliation benchmark |
| Synthetic corrupt rows | Negative tests cho sai unit, thiếu source, duplicate, sai period |

### Metrics và thresholds

| Metric | Công thức | Threshold P0 |
|---|---|---:|
| Core metric coverage | Số core metrics có fact hợp lệ / tổng core metrics bắt buộc | >= 95% final |
| Period completeness | Số period đầy đủ statement / tổng period yêu cầu | 100% với DHG/DBD pilot |
| Source provenance coverage | Facts có source_id, source_tier, source_doc_id / total facts | 100% facts dùng trong valuation |
| Official reconciliation rate | Facts matched official hoặc manual_reviewed / material facts | >= 95% |
| OCR unresolved rate | OCR candidate blocked hoặc pending / OCR candidates material | 0% trong final |
| Freshness SLA | Days since latest accepted snapshot | Theo policy từng report |
| Duplicate fact rate | Duplicate canonical key / total facts | 0% |

### Required artifact: `data_quality.json`

```json
{
  "run_id": "string",
  "ticker": "DHG",
  "snapshot_id": "string",
  "core_metric_coverage": 0.0,
  "period_completeness": 0.0,
  "source_provenance_coverage": 0.0,
  "official_reconciliation_rate": 0.0,
  "ocr_unresolved_material_count": 0,
  "freshness_status": "fresh|stale|unknown",
  "duplicate_fact_count": 0,
  "critical_issues": [],
  "warnings": []
}
```

---

## 5.2. RAG and evidence evaluation

### Mục tiêu

Đảm bảo retriever lấy đúng bằng chứng, đủ ngữ cảnh, có metadata truy vết và generator chỉ viết dựa trên evidence đó. RAG trong hệ này không phải chatbot Q&A, mà là cơ chế tạo evidence packet cho report và citation.

### Đối tượng cần đánh giá

| Đối tượng | Metric cần đo | Failure mode |
|---|---|---|
| Chunking | Chunk coverage, metadata completeness, section/page availability | Chunk mất page/source nên citation không audit được |
| Embedding retrieval | Hit-rate@k, MRR, context precision, context recall | Không tìm đúng disclosure hoặc annual report |
| Full-text fallback | Hit-rate@k khi embedding unavailable | Fallback trả về nguồn sai tier |
| Citation map | Claim-to-context support | Citation có nhưng không support claim |
| Evidence packet | Completeness và reproducibility | Report không tái lập được evidence |
| Generated span | Faithfulness, response relevancy, unsupported claim rate | Agent hallucinate hoặc suy diễn quá nguồn |

### Framework sử dụng

| Framework | Vai trò |
|---|---|
| `Ragas` | Context precision, context recall, faithfulness, response relevancy, noise sensitivity |
| `pytest` | Golden retrieval regression |
| `Langfuse datasets` | Lưu query, expected contexts, runs và scores |
| PostgreSQL `pgvector` và full-text search | Retriever under test |
| Custom finance citation validator | Domain-specific support check |

### Golden query set

File đề xuất: `config/benchmarks/02_ragas_retrieval/golden_queries/default.yaml`

| Query class | Ví dụ | Expected evidence |
|---|---|---|
| Financial fact lookup | `DHG revenue 2024` | Annual report hoặc reconciled canonical fact |
| Valuation assumption support | `tax rate assumption DHG forecast` | Tax policy artifact hoặc official historical tax evidence |
| Catalyst lookup | `DHG GMP EU factory update` | Company disclosure, HOSE/HNX/IR document, reliable news |
| Risk lookup | `API cost exposure DHG` | Company-specific source hoặc explicit missing-evidence marker |
| Peer/multiple lookup | `Vietnam pharma peer P/E` | Peer dataset artifact hoặc blocked status nếu unavailable |

### Metrics và thresholds

| Metric | Tool | Threshold P0 | Threshold P1 |
|---|---|---:|---:|
| Hit-rate@5 | Custom pytest | >= 90% golden queries | >= 95% |
| MRR@5 | Custom pytest | >= 75% | >= 80% |
| Context precision | Ragas | >= 80% | >= 85% |
| Context recall | Ragas | >= 80% | >= 85% |
| Faithfulness | Ragas | >= 85% | >= 90% |
| Noise sensitivity | Ragas | Baseline only | Improve 20% |
| Unsupported claim rate | Custom validator | 0% final | 0% final |
| Tier-3-only material claim | Source gate | 0 | 0 |

### Required artifact: `retrieval_eval.json`

```json
{
  "ticker": "DHG",
  "run_id": "string",
  "retrieval_backend": "pgvector|full_text|hybrid",
  "query_set_version": "rag_golden_v1",
  "ragas_scores": {
    "context_precision": 0.0,
    "context_recall": 0.0,
    "faithfulness": 0.0,
    "response_relevancy": 0.0,
    "noise_sensitivity": 0.0
  },
  "golden_scores": {
    "hit_rate_at_5": 0.0,
    "mrr_at_5": 0.0
  },
  "unsupported_context_failures": [],
  "blocking_failures": []
}
```

---

## 5.3. Financial calculation evaluation

### Mục tiêu

Đảm bảo mọi tính toán tài chính được thực hiện bằng code, có formula trace, có thể tái lập và không bị LLM sửa số. Đây là lớp rủi ro product liability cao nhất vì lỗi valuation có thể làm sai toàn bộ kết luận báo cáo.

### Đối tượng cần đánh giá

| Module | Cần kiểm định | Critical failure |
|---|---|---|
| Ratios | Formula, unit, denominator, period scope | ROE/ROA/margin sai do nhầm VND bn với VND mn |
| Forecast | Driver support, margin sanity, BS balance, CF consistency | Lợi nhuận tăng bất thường không có bridge |
| Working capital | AR, inventory, AP days, delta NWC | Delta NWC bị đặt 0 hoặc sai dấu |
| Debt schedule | Short-term debt, long-term debt, net borrowing | FCFE tính khi không có debt schedule |
| Dividend schedule | DPS, payout, dividend yield, total return | Dividend yield bằng 0 trong khi DPS dương |
| FCFF | EBIT tax, D&A, CAPEX, NWC, TV, WACC, EV-to-equity | Target price thiếu bridge |
| FCFE | NI, D&A, CAPEX, NWC, net borrowing, Re | FCFE hợp lệ khi net borrowing missing |
| Blend valuation | Method weights, FCFF/FCFE availability | Gọi blended target khi FCFE blocked |
| Multiples | Peer selection, forward EPS, P/E, EV/EBITDA | Default peer multiple không có dataset |
| Sensitivity | FCFF WACC/g, FCFE Re/g, blend grid | Missing FCFE/blend grid hoặc base cell sai |

### Framework sử dụng

| Framework | Vai trò |
|---|---|
| `pytest` | Unit tests, regression tests, invariant tests |
| Golden artifacts | Expected valuation outputs cho DHG/DBD |
| `hypothesis` | Property-based tests cho edge cases |
| Formula trace JSON | Audit từng bước tính và version công thức |
| Custom deterministic gates | Block export khi công thức, bridge hoặc assumption fail |

### Critical invariants

| Invariant | Công thức hoặc rule | Severity |
|---|---|---|
| Net debt | `interest_bearing_debt - cash - short_term_investments` | Critical |
| EPS | `net_income * 1000 / diluted_shares_mn` nếu NI là VND bn | Critical |
| Balance sheet | `assets = equity + debt + other_liabilities` trong tolerance | Critical |
| FCFF | `EBIT * (1 - tax) + D&A - CAPEX - delta_NWC` | Critical |
| FCFE | `NI + D&A - CAPEX - delta_NWC + net_borrowing` | Critical |
| EV-to-equity | `EV + cash + ST investments - debt - minority_interest` | Critical |
| Target price | `equity_value / diluted_shares` với unit policy rõ | Critical |
| Gordon Growth | `discount_rate > terminal_growth` | Critical |
| Sensitivity | Matrix có ít nhất hai giá trị khác nhau | Critical |
| Sensitivity base cell | Base cell khớp target price trong tolerance | Critical |
| Recommendation | BUY/HOLD/SELL khớp upside policy | Critical nếu final |

### Acceptance thresholds

| Nhóm | Threshold |
|---|---:|
| Formula unit tests | 100% pass |
| Golden valuation drift | 0% ngoài tolerance đã khai báo |
| Critical invariant failures | 0 |
| Missing formula trace for final valuation | 0 |
| Missing WACC decomposition | 0 trong final |
| Missing EV-to-equity bridge | 0 trong final |
| FCFE blocked but report mentions FCFE target | 0 |
| Missing FCFE or blend sensitivity in final export path | 0 |

### Required artifact: `financial_eval.json`

```json
{
  "run_id": "string",
  "ticker": "DHG",
  "snapshot_id": "string",
  "formula_trace_version": "valuation_formula_v1",
  "critical_invariant_failures": [],
  "warnings": [],
  "valuation_reproducible": false,
  "wacc_decomposition_present": false,
  "ev_to_equity_bridge_present": false,
  "fcff_publishable": false,
  "fcfe_publishable": false,
  "sensitivity_status": {
    "fcff_matrix_present": false,
    "fcfe_matrix_present": false,
    "blend_grid_present": false,
    "base_cell_reconciled": false
  },
  "export_blocked": true
}
```

---

## 5.4. Citation and source provenance evaluation

### Mục tiêu

Đảm bảo mọi claim trọng yếu trong báo cáo có nguồn cụ thể, có lineage và citation support đúng nội dung claim. Citation evaluation không được dừng ở việc đếm số footnote.

### Đối tượng cần đánh giá

| Đối tượng | Câu hỏi kiểm định |
|---|---|
| Claim ledger | Tất cả material claims có `claim_id`, `claim_type`, `quantitative`, `materiality` không? |
| Citation map | Mỗi claim có citation key resolve được không? |
| Source tier | Citation có đúng Tier 1/Tier 2 cho material claim không? |
| Official source | Quantitative final claim có official document hoặc reconciled official fact không? |
| Numeric consistency | Giá trị trong report có khớp cited fact trong tolerance không? |
| Reconciliation status | Cited facts có `matched_official` hoặc `manual_reviewed` không? |
| Catalyst evidence | Event có source document, evidence span, event type và date không? |

### Framework sử dụng

| Framework | Vai trò |
|---|---|
| Custom deterministic gates | Source provenance policy, official source requirement |
| `pytest` | Regression cho source tier, citation map, final gate |
| Ragas faithfulness | Bổ sung semantic groundedness cho narrative span |
| LLM-as-judge | Optional support check cho qualitative material claims |

### Claim-level benchmark schema

```json
{
  "claim_id": "DHG_FY2024_REVENUE_GROWTH_001",
  "claim_text": "Doanh thu DHG năm 2024 tăng ...",
  "claim_type": "quantitative",
  "materiality": "high",
  "expected_fact_ids": ["fact_dhg_revenue_2024", "fact_dhg_revenue_2023"],
  "expected_source_tier": ["tier_1", "tier_2"],
  "expected_reconciliation_status": "matched_official",
  "numeric_tolerance": 0.001,
  "should_block_if_missing": true
}
```

### Final gate policy

| Gate | Blocking trong final | Ghi chú |
|---|---|---|
| Citation coverage | Có | Mọi quantitative/catalyst/material claim cần lineage |
| Source tier validity | Có | Tier 4/unknown bị block; Tier 3-only material bị block |
| Official source requirement | Có | Áp dụng cho quantitative final claim |
| Numeric consistency | Có | Sai tolerance là critical |
| Reconciliation status | Có | Material fact phải matched official hoặc manual reviewed |
| Catalyst evidence validity | Có | Event thiếu source/evidence/type/date bị block |
| Generic citation only | Có | Generic label không đủ trong final |

### Metrics

| Metric | Threshold final |
|---|---:|
| Quantitative citation coverage | 100% |
| Citation key resolution | 100% |
| Source ID validity | 100% |
| Official source coverage for material quantitative claims | 100% |
| Numeric mismatch rate above tolerance | 0% |
| Tier 3-only material claims | 0 |
| Generic citation labels | 0 |
| Catalyst events without evidence span | 0 |

### Required artifact: `citation_eval.json`

```json
{
  "run_id": "string",
  "ticker": "DHG",
  "claim_count": 0,
  "quantitative_claim_count": 0,
  "citation_coverage_ratio": 1.0,
  "source_tier_counts": {},
  "official_source_coverage": 1.0,
  "numeric_mismatches": [],
  "generic_citations": [],
  "tier3_only_material_claims": [],
  "unresolved_major_source_discrepancies": [],
  "export_blocked": false
}
```

---

## 5.5. Agent workflow and LLM judge evaluation

### Mục tiêu

Đánh giá agent ở lớp hành vi workflow: đúng vai trò, đúng quyền gọi tool, đúng output contract, không vượt evidence và không tự tạo số liệu tài chính. Agent evaluation không thay thế finance evaluation.

### Đối tượng cần đánh giá

| Vai trò/lớp | Cần đánh giá | Failure mode |
|---|---|---|
| ResearchService / PLAN role | Plan đúng scope, ticker, period và task registry không? | Plan sai phạm vi làm downstream sai |
| DataEvidence role | Tool calls đúng permission và artifact contract không? | Tool bypass hoặc thiếu evidence packet |
| FinancialAnalysisAgent | Chỉ diễn giải facts/ratios có sẵn không? | LLM tính lại số hoặc tạo metric mới |
| ForecastValuation role | Có tách deterministic valuation và narrative explanation không? | LLM tạo target price |
| ThesisReportAgent | Claim có source, đúng structure và không vượt evidence không? | Hallucination narrative |
| SeniorCriticAgent | Có phát hiện lỗi material và không tự sửa report không? | Critic cho pass dễ dãi |

### Framework sử dụng

| Framework | Vai trò |
|---|---|
| `pytest` trace tests | Tool permission, artifact manifest, workflow status |
| DeepEval | Agentic metrics và custom G-Eval rubric |
| OpenAI Evals | API-based graders với dataset và testing criteria |
| Langfuse | Trace, datasets, manual annotation, online/offline scores |
| Custom JSON schema validation | Output contract cho từng stage |

### Dataset cần xây

| Dataset | Mục đích |
|---|---|
| Golden successful traces | Baseline role/tool behavior |
| Seeded bad traces | Agent dùng tool sai, thiếu source, hallucinate, overrecommend |
| Bad report corpus | Kiểm tra SeniorCritic có bắt lỗi P0 không |
| Archetype prompt set | Kiểm tra narrative không áp template pharma cho hospital/distributor/equipment |

### Metrics

| Metric | Tool | Threshold |
|---|---|---:|
| Tool permission compliance | Custom gate | 100% |
| Output schema validity | Pydantic/JSON schema | 100% |
| Role adherence | DeepEval/OpenAI grader | >= 85% |
| Groundedness | Ragas/DeepEval/custom judge | >= 85% final narrative |
| No unauthorized financial calculation | Custom regex + judge | 100% compliance |
| Task completion | DeepEval agentic metric | >= 85% |
| Plan adherence | DeepEval agentic metric | >= 80% |
| Critic issue recall on seeded failures | Golden bad reports | >= 90% |

### LLM judge rubric

| Dimension | Scoring question |
|---|---|
| Evidence discipline | Output có chỉ dựa vào facts, valuation artifacts và cited evidence không? |
| Financial restraint | Agent có tránh tính toán hoặc tự tạo số liệu tài chính không? |
| Company specificity | Insight có riêng cho ticker và archetype không? |
| Materiality | Agent có ưu tiên driver ảnh hưởng forecast/valuation không? |
| Risk balance | Report có nêu điều kiện bác bỏ thesis và downside không? |
| Citation integrity | Claim material có citation rõ và citation support đúng claim không? |
| Professional tone | Phù hợp research report, không marketing, không overclaim không? |

### Required artifact: `agent_eval.json`

```json
{
  "run_id": "string",
  "ticker": "DHG",
  "trace_version": "agent_trace_v1",
  "tool_permission_compliance": 1.0,
  "output_schema_validity": 1.0,
  "role_adherence_score": 0.0,
  "groundedness_score": 0.0,
  "unauthorized_financial_calculation_count": 0,
  "critic_seeded_failure_recall": 0.0,
  "judge_model": "string",
  "judge_rubric_version": "agent_judge_v1",
  "advisory_findings": [],
  "blocking_failures": []
}
```

Lưu ý: `agent_eval.json` là advisory đối với các tiêu chí judge. Nó không được ghi đè `financial_eval.json`, `citation_eval.json`, `report_eval.json` hoặc `publication_readiness.json`.

---

## 5.6. Report quality evaluation

### Mục tiêu

Đánh giá báo cáo như một artifact cuối, bảo đảm báo cáo có cấu trúc chuyên nghiệp, số liệu đúng, citation đạt, valuation minh bạch, recommendation nhất quán và không bypass quy trình phê duyệt.

### Đối tượng cần đánh giá

| Đối tượng | Cần kiểm định |
|---|---|
| Report model | Có đủ section, table, chart, source, chart/table metadata không? |
| Recommendation | Không hiển thị BUY/HOLD/SELL nếu chưa approved |
| Target price | Chỉ hiển thị khi valuation publishable và approval cho phép |
| Narrative | Company-specific, material, không dùng template chung chung |
| Tables/charts | Numbered, sourced, unit rõ, không mâu thuẫn với artifact |
| Report-quality rubric | Score >= 85% và không failed gate |
| Export package | Manifest, formula traces, evidence packet, quality gate, PDF/HTML |
| Client-final authorization | Run approval, final approval, locked artifact, snapshot match |
| Post-render audit | HTML/PDF không lộ internal banner, generic source note, draft markers |

### Report-quality rubric đề xuất

| Nhóm | Trọng số | Điều kiện đạt |
|---|---:|---|
| Data correctness | 25 | Financial model integrity pass, no stale/mismatched snapshot |
| Financial model integrity | 25 | Forecast, BS, FCFF/FCFE, WACC, bridge, sensitivity pass |
| Domain depth | 15 | Company research pack, analyst insights, archetype-specific drivers pass |
| Valuation transparency | 15 | EV-to-equity bridge, WACC build-up, method status rõ |
| Citation quality | 10 | Claim-level citation, official source, no generic citation |
| Professional presentation | 10 | Sections, tables, charts, recommendation consistency pass |

### Decision rule

| Điều kiện | Decision |
|---|---|
| Score >= 85% và không failed deterministic gate | `allow_export` |
| Score >= 70 nhưng còn failed gate | `draft_only` |
| Score < 70 hoặc critical gate fail | `block_export` |

### Blocking conditions

| Condition | Severity |
|---|---|
| Report quality score < 85 | Critical |
| Any failed deterministic finance gate | Critical |
| Recommendation visible before approval | Critical |
| Target price visible from blocked valuation | Critical |
| Report artifact snapshot mismatch with valuation | Critical |
| Missing evidence packet or formula trace | Critical |
| PDF rendered from `report_candidate_model` as final | Critical |
| Missing numbered/sourced charts/tables | Warning in draft, critical in final |
| Missing final approval for client-final render | Critical |
| `publishable_final_report_model` not locked | Critical |
| Report-quality gate warning treated as final pass | Critical |
| Post-render client-final audit failed | Critical |

### Required artifact: `report_eval.json`

```json
{
  "rubric": "report_quality_v1",
  "run_id": "string",
  "ticker": "DHG",
  "score": 0,
  "decision": "block_export|draft_only|allow_export",
  "failed_gates": [],
  "section_scores": {},
  "report_artifacts": {
    "html": "path",
    "pdf": "path",
    "manifest": "path"
  },
  "post_render_audit": {
    "passed": false,
    "blockers": []
  },
  "publication_readiness": {
    "passed": false,
    "blocking_reasons": []
  }
}
```

---

## 5.7. Publication readiness evaluation

### Mục tiêu

Phân biệt rõ bản nháp nội bộ, bản đã qua gate, bản publishable và bản client-final đã được phê duyệt. Đây là lớp governance cuối trước khi render báo cáo final.

### Điều kiện pass tối thiểu

| Điều kiện | Bắt buộc final |
|---|---|
| Run status là `approved` | Có |
| Final report approval là `approved` | Có |
| `publishable_final_report_model` locked | Có |
| Report snapshot khớp valuation snapshot | Có |
| `PACKAGE_VALIDATION_GATE` pass | Có |
| Report-quality decision là `allow_export` | Có |
| Evidence packet artifact có storage path | Có |
| Formula trace artifact có storage path | Có |
| Post-render audit pass | Có |

### Required artifact: `publication_readiness.json`

```json
{
  "run_id": "string",
  "ticker": "DHG",
  "passed": false,
  "run_status": "approved|auto_exported|blocked|failed|needs_human_review",
  "final_report_approval": "approved|rejected|pending|missing",
  "locked_publishable_model": false,
  "package_validation_passed": false,
  "report_quality_allow_export": false,
  "snapshot_match": false,
  "evidence_packet_present": false,
  "formula_trace_present": false,
  "blocking_reasons": []
}
```

---

## 5.8. Observability, cost and latency evaluation

### Mục tiêu

Đánh giá khả năng vận hành dài hạn: trace, latency, cost, retry, external dependency failure, gate flakiness và khả năng scale sang nhiều ticker. Một hệ thống đạt chất lượng trên một run đơn lẻ nhưng không đo được cost/latency thì chưa sẵn sàng mở rộng.

### Đối tượng cần đánh giá

| Đối tượng | Metrics |
|---|---|
| End-to-end run | Duration, status, blocked stage, retry count |
| LLM calls | Token input/output, cost estimate, latency, model, prompt version |
| Retrieval | Query latency, backend used, hit count, fallback rate |
| OCR/PDF extraction | Pages processed, OCR confidence, extraction failure rate |
| Database/storage | Query latency, write retry count, artifact upload failures |
| PDF rendering | Renderer backend, duration, preflight pass/fail |
| Gates | Pass/fail trend, recurring blocker categories |
| Publication readiness | Approval status, authorization blocker, snapshot mismatch, locked artifact status |
| Post-render audit | Client-final display blocker, HTML/PDF artifact path, strict preflight result |

### Framework sử dụng

| Framework | Vai trò |
|---|---|
| Langfuse | Trace, score, dataset, experiment, online/offline eval |
| RuntimeStore/PostgreSQL | Run status, steps, artifacts, audit events |
| Python logging | Local diagnostics |
| Pytest performance smoke | Latency regression ở mức component |
| Cost ledger trong model adapter | Cost-to-serve theo run |

### Thresholds ban đầu

| Metric | Threshold cảnh báo |
|---|---:|
| Full DHG run duration | > baseline p95 + 30% |
| LLM retry rate | > 5% calls |
| Retrieval fallback rate | > 20% queries nếu embedding expected |
| OCR failure rate | > 5% pages material |
| Artifact upload failure | > 0 trong final |
| PDF render failure | > 0 trong final |
| Cost per full report | > budget guard soft limit |
| Gate flakiness | Same input, different gate result |

### Required artifact: `observability_eval.json`

```json
{
  "run_id": "string",
  "trace_url": "string",
  "duration_seconds": 0,
  "stage_durations": {},
  "llm": {
    "calls": 0,
    "tokens_input": 0,
    "tokens_output": 0,
    "estimated_cost_usd": 0.0,
    "retry_rate": 0.0
  },
  "retrieval": {
    "queries": 0,
    "p95_latency_ms": 0,
    "fallback_rate": 0.0
  },
  "blocking_gate_categories": [],
  "publication": {
    "readiness_passed": false,
    "authorization_blockers": [],
    "render_mode": "analyst_draft|client_final"
  }
}
```

---

## 6. Thiết kế benchmark để kết quả trung thực

## 6.1. Không benchmark ở cấp report tổng quát

Benchmark phải được thiết kế theo từng đơn vị lỗi:

| Evaluation unit | Mục đích |
|---|---|
| Fact-level | Bắt sai số liệu gốc, sai đơn vị, sai kỳ |
| Source-level | Bắt nguồn không official, stale, duplicate |
| Chunk-level | Bắt retrieval sai đoạn, mất page metadata |
| Claim-level | Bắt citation không support claim |
| Formula-step-level | Bắt sai bridge FCFF/FCFE/WACC/target price |
| Trace-level | Bắt agent gọi sai tool, sai quyền, sai role |
| Section-level | Bắt narrative chung chung, không đặc thù doanh nghiệp |
| Render-level | Bắt PDF/HTML hiển thị sai, lộ draft marker, missing source |

## 6.2. Benchmark phải có positive, negative, conflict và temporal sets

| Set | Nội dung | Mục đích |
|---|---|---|
| Positive golden | Facts, calculations, claims đúng từ official sources | Đo recall và correctness |
| Negative seeded | Sai unit, sai period, fake citation, missing source, blocked FCFE | Đo khả năng chặn lỗi |
| Conflict set | Vnstock/API/OCR khác official document | Đo reconciliation và source priority |
| Temporal set | Snapshot cũ, report dùng artifact cũ, catalyst mới | Đo freshness và snapshot immutability |
| Adversarial set | Prompt injection, yêu cầu fake citation, ép BUY | Đo guardrails |
| Human-quality set | Báo cáo mẫu FPTS, báo cáo hệ thống, reviewer labels | Đo domain depth và professional quality |

## 6.3. Chia tập benchmark

| Split | Tỷ lệ | Dùng cho |
|---|---:|---|
| Dev set | 40% | Debug parser, prompt, retriever |
| Calibration set | 20% | Calibrate LLM judge và rubric |
| Locked test set | 30% | Báo cáo kết quả chính thức |
| Regression canary | 10% | Chạy nhanh trong CI |

Không được dùng locked test set để chỉnh prompt hoặc chỉnh retriever. Mọi thay đổi parser, prompt, model hoặc retrieval policy phải được đánh giá trên dev/canary trước, sau đó mới báo kết quả locked test.

## 6.4. Human baseline và inter-reviewer calibration

Với các tiêu chí mềm như insight depth, storytelling, materiality và risk balance, cần ít nhất hai reviewer chấm độc lập trên một subset khóa. Sau đó tạo adjudicated labels để calibrate LLM judge.

Quy trình đề xuất:

```text
Step 1: Hai reviewer chấm 30 report sections theo rubric 1-5.
Step 2: Resolve disagreement để tạo adjudicated labels.
Step 3: Chạy DeepEval/OpenAI judge trên cùng set.
Step 4: So sánh judge-human agreement.
Step 5: Chỉ dùng judge cho online scoring nếu agreement đạt ngưỡng đã định.
```

## 6.5. Repeated evaluation để đo stability

| Test | Cách chạy |
|---|---|
| Same input repeatability | Cùng ticker, cùng snapshot, chạy 3 lần |
| Prompt/model regression | So sánh prompt/model version bằng Langfuse dataset experiments |
| Gate determinism | Same artifacts phải cho cùng gate result |
| Cost/latency p95 | Báo cáo p50/p95/p99, không chỉ average |
| Drift over time | Theo dõi score theo tuần và theo ticker/archetype |

---

## 7. CI và rollout plan

## 7.1. CI gate matrix

| CI job | Scope | Block merge |
|---|---|---|
| `unit-core` | `tests/unit/` core deterministic tests | Yes |
| `evaluation-gates` | `tests/evaluation/`, `tests/citations/`, `tests/reconciliation/`, `tests/unit/test_package_validation_gate.py`, `tests/unit/test_publication_readiness.py` | Yes |
| `finance-regression` | DCF, ratios, debt, dividend, sensitivity, valuation workings, governance invariants | Yes |
| `report-render-smoke` | HTML/PDF smoke, post-render audit, authorization-required client-final render | Yes nếu renderer required |
| `rag-golden` | Golden retrieval set | Warn in P1, block in P2 |
| `llm-judge-offline` | Small calibrated report/agent dataset | Warn initially, block after calibration |
| `integration-db` | Supabase/PostgreSQL live tests | Scheduled hoặc protected branch |

## 7.2. Lệnh kiểm thử đề xuất

### Data reliability

```bash
python -m pytest \
  tests/unit/test_data_quality.py \
  tests/unit/test_golden_provenance_required.py \
  tests/unit/test_ocr_promotion_gate.py \
  tests/unit/test_ocr_reconciliation_gate.py \
  tests/reconciliation/ \
  tests/dataops/ \
  tests/evaluation/test_final_source_gates.py
```

### Finance regression

```bash
python -m pytest \
  tests/unit/test_dcf.py \
  tests/unit/test_ratios.py \
  tests/unit/test_debt_schedule.py \
  tests/unit/test_dividend_schedule.py \
  tests/unit/test_sensitivity.py \
  tests/unit/test_export_gate.py \
  tests/unit/test_valuation_workings.py \
  tests/evaluation/test_client_final_governance.py
```

### Citation and package validation

```bash
python -m pytest \
  tests/citations/ \
  tests/evaluation/test_numeric_claim_gates.py \
  tests/evaluation/test_catalyst_evidence_gates.py \
  tests/evaluation/test_final_source_gates.py \
  tests/unit/test_claim_ledger.py \
  tests/unit/test_package_validation_gate.py
```

### Publication readiness and renderer smoke

```bash
python -m pytest \
  tests/unit/test_publication_readiness.py \
  tests/unit/test_export_gate.py \
  tests/unit/test_package_validation_gate.py \
  tests/evaluation/test_client_final_governance.py
```

## 7.3. Rollout phases

| Phase | Mục tiêu | Output |
|---|---|---|
| P0.1 | Đóng governance gap | Export fail-closed, no fast-render bypass, client-final authorization required |
| P0.2 | Chuẩn hóa deterministic eval packets | `data_quality`, `financial_eval`, `citation_eval`, `report_eval` |
| P0.3 | CI regression cho core gates | Unit/evaluation tests pass trong PR |
| P1.1 | RAG golden benchmark | `config/benchmarks/02_ragas_retrieval/golden_queries/`, hit-rate@k, Ragas pilot |
| P1.2 | Langfuse trace and dataset loop | Trace scores, failed trace datasets |
| P1.3 | LLM judge for narrative and agent | DeepEval/OpenAI Evals calibrated rubric |
| P2 | Archetype-aware evaluation | Threshold riêng cho pharma, distributor, hospital, equipment |
| P3 | Universe scaling readiness | Batch eval across pilot basket trước full active universe |

## 7.4. Acceptance thresholds by maturity

| Layer | P0 threshold | P1 threshold | P2 threshold |
|---|---:|---:|---:|
| Data critical failures | 0 | 0 | 0 |
| Finance critical failures | 0 | 0 | 0 |
| Citation coverage final | 100% | 100% | 100% |
| Report quality score | >= 85% | >= 85% | >= 90% published |
| RAG hit-rate@5 | Measured only | >= 90% | >= 95% |
| Ragas faithfulness | Measured only | >= 85% | >= 90% |
| Agent role adherence | Measured only | >= 85% | >= 90% |
| Cost per report | Baseline | <= baseline + 15% | Budgeted by archetype |

---

## 8. Thứ tự triển khai khuyến nghị

### P0 — Làm ngay

| Hành động | Kết quả mong đợi |
|---|---|
| Tạo `evaluation_packet` run-scoped | Mỗi report có bằng chứng đánh giá độc lập |
| Chuẩn hóa severity | `critical` block export, `warning` cho review, `info` cho diagnostics |
| Đóng fast-render bypass | Không render final từ `report_candidate_model` |
| Bắt buộc `PACKAGE_VALIDATION_GATE` trong export | Không cho artifact trôi nổi đi vào report |
| Bắt buộc `authorize_client_final` cho mode `client_final` | Tách auto-exported draft khỏi client-facing final |
| Seed negative fixtures | Chứng minh gate thất bại khi sai unit, thiếu source, duplicate fact |
| Pilot DHG và DBD | Hai ticker đại diện pass deterministic gates trước khi mở rộng |

### P1 — Sau khi P0 ổn định

| Hành động | Kết quả mong đợi |
|---|---|
| Thêm `Ragas` dependency trong eval extras | Có semantic RAG metrics |
| Tạo `config/benchmarks/02_ragas_retrieval/golden_queries/default.yaml` | Benchmark retrieval lặp lại được |
| Đưa query set và scores lên Langfuse datasets | So sánh regression theo model, prompt, retriever |
| Thêm `hypothesis` cho formula edge cases | Bắt lỗi denominator zero, negative debt, high growth |
| Thêm `Pandera` schema cho connector DataFrame | Lỗi schema bị bắt trước normalization |

### P2 — Sau khi có human calibration

| Hành động | Kết quả mong đợi |
|---|---|
| Thêm DeepEval hoặc OpenAI Evals | Chấm role adherence, groundedness, narrative quality |
| Dùng double-judge cho final report narrative | Giảm bias của một judge duy nhất |
| Tạo corpus FPTS-style reports mẫu | Calibration với human reviewer |
| Track score trend theo ticker/archetype | Biết template nào không đạt |

### P3 — Trước khi mở rộng universe

| Hành động | Kết quả mong đợi |
|---|---|
| Archetype-aware thresholds | Threshold riêng cho manufacturer, distributor, hospital/equipment |
| Batch eval trên pilot basket | DHG, DBD, IMP, DMC, TRA pass trước khi scale |
| Dashboard p50/p95/p99 theo stage | Xác định bottleneck OCR, LLM, retrieval hoặc PDF |
| Failed trace datasets | Biến lỗi production thành regression tests |

---

## 9. Definition of Done cho giai đoạn evaluation

Giai đoạn đánh giá được xem là đạt khi thỏa mãn các điều kiện sau:

| Nhóm | Điều kiện hoàn thành |
|---|---|
| Data | Mỗi run có `data_quality.json`, core facts có source, reconciliation và freshness status |
| Retrieval | Có `config/benchmarks/02_ragas_retrieval/golden_queries/`, hit-rate@5 được đo, evidence packet có page/source metadata |
| Finance | `financial_eval.json` có invariant result, formula trace, WACC decomposition, EV-to-equity bridge |
| Citation | `citation_eval.json` có claim-level coverage, source tier, official source requirement, numeric mismatch list |
| Agent | `agent_eval.json` có tool permission compliance, output schema validity, role adherence score |
| Report | `report_eval.json` có report quality score, failed gates, decision, post-render audit |
| Publication | `publication_readiness.json` chứng minh run approved, final approval, locked model, snapshot match |
| Observability | `observability_eval.json` có token cost, latency, retry, trace link, blocker categories |
| CI | P0 deterministic jobs block merge |
| Benchmark | Có positive, negative, conflict, temporal, adversarial và human-quality sets |
| Governance | LLM judge không được override deterministic gates |

---

## 10. Kết luận

Kế hoạch evaluation cho Vietnam Pharma Equity Research Agent phải được thiết kế theo hướng **deterministic-first, artifact-level, benchmark-versioned, human-calibrated và fail-closed**. Hệ thống không được chứng minh chất lượng bằng việc tạo ra một báo cáo trông chuyên nghiệp; nó phải chứng minh từng fact, từng formula, từng claim, từng citation, từng tool call và từng quyết định render đều có thể kiểm tra lại.

Framework stack tối thiểu nên triển khai theo thứ tự:

```text
P0: pytest + Pydantic + SQL constraints + custom finance/citation/governance gates
P1: Pandera + Ragas + Langfuse + Hypothesis
P2: DeepEval hoặc OpenAI Evals sau khi có human calibration
P3: Archetype-aware benchmark và universe-scale regression dashboard
```

Không nên mở rộng sang toàn bộ universe trước khi deterministic data gates, financial calculation gates, citation source provenance, report quality và publication readiness pass trên ít nhất các ticker pilot đại diện. Mở rộng quá sớm sẽ làm tăng chi phí debug và che mờ nguyên nhân lỗi giữa data gap, retrieval failure, archetype mismatch, valuation error và report-quality failure.
