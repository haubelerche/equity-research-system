# Thiết kế benchmark 5 phần

## 1. Vì sao cần 5 benchmark tách biệt

Một hệ thống equity research có kiểm soát không nên dùng một điểm tổng hợp duy nhất. Sai dữ liệu, sai retrieval, sai valuation, sai role agent và vượt ngân sách/độ trễ là các lỗi khác bản chất. Vì vậy bộ benchmark này tách thành 5 nhóm:

| Nhóm | Tool chính | Câu hỏi kiểm định | Artifact đầu ra |
|---|---|---|---|
| Data quality | Pandera | Facts có đúng schema, đúng kỳ, đúng nguồn, đủ metric trọng yếu không? | `data_quality.json` |
| Retrieval quality | Ragas | Evidence có đúng ticker/năm/chunk/source tier và câu trả lời có faithful không? | `retrieval_eval.json` |
| Financial correctness | pytest + domain rubrics | Ratios/DCF/bridge/sensitivity có tái lập và không vi phạm invariant không? | `financial_eval.json` |
| Agent workflow | DeepEval | Agent có giữ vai trò, không vượt quyền, không bịa claim/số liệu không? | `agent_eval.json` |
| Ops, cost, latency | pandas/pytest + trace rubric | Run có đạt SLA, budget, retry, manifest/cost ledger không? | `observability_eval.json` |

## 2. Golden dataset tối thiểu nên có

Với mỗi ticker, bộ tối thiểu gồm:

- 4 năm FY: 2022, 2023, 2024, 2025.
- 4 nhóm statement: income statement, balance sheet, cash flow, capital structure.
- Khoảng 28-32 material canonical keys mỗi ticker.
- 32 retrieval queries/ticker + 1 unanswerable control.
- 1 valuation case/ticker + 25 sensitivity points/ticker.
- 5 agent role cases/ticker + seeded critic cases.
- 1 run trace/ticker + negative ops fixtures.

## 3. Quy tắc score

Điểm tổng hợp đề xuất:

| Benchmark | Trọng số | Critical fail |
|---|---:|---|
| Pandera data quality | 25 | duplicate fact, missing material source, schema invalid |
| Ragas retrieval | 20 | hit-rate@5 < 90%, source-tier miss for material query |
| Financial benchmark | 25 | valuation bridge mismatch, WACC <= g, unreconciled net debt |
| DeepEval agent | 20 | unauthorized tool, LLM-generated valuation, unsupported numeric claim |
| Ops/cost/latency | 10 | hard budget, PDF/storage failure, missing manifest/cost ledger |

Pass nghiên cứu: `suite_score >= 90`, không có critical fail, và từng nhóm đạt ngưỡng riêng trong `shared/acceptance_thresholds.yaml`.
