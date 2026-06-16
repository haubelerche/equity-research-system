# Run Benchmarks v3

## 1. Structural check inside this package

```bash
python scripts/benchmark_scorecard_v3.py
pytest -q tests
```

## 2. Data quality / Pandera

- Dataset: `shared/golden_financials/all_benchmark_facts_v3.csv`.
- Schema: `01_pandera_data_quality/pandera_schema_v3.py`.
- Runtime artifact expected: `data_quality_eval.json`.

Trong repo chính, nối schema này vào output sau `build_facts` và trước valuation/report.

## 3. RAG / Ragas

- Query set: `02_ragas_retrieval/golden_queries/golden_query_index_v3.csv`.
- Official-like chunks: `02_ragas_retrieval/golden_chunks/official_like_chunks_v3.jsonl`.
- Ragas samples: `02_ragas_retrieval/ragas/ragas_samples_v3.jsonl`.

RAG score là diagnostic. Nếu nó tạo citation sai hoặc claim thiếu nguồn, lỗi phải bị bắt ở `06_citation_provenance`.

## 4. Financial model

- Cases: `03_financial_benchmarks/golden_valuation/finance_cases_v3.jsonl`.
- Artifact examples: `03_financial_benchmarks/artifact_examples/financial_eval_*.json`.

Finance gates phải chạy deterministic; LLM judge không được xác nhận công thức hoặc target price.

## 5. Agent / DeepEval

- Cases: `04_deepeval_agent/deepeval_cases/agent_trace_cases_v3.jsonl`.
- Output schema: `04_deepeval_agent/output_schemas/agent_stage_output.schema.json`.

## 6. Citation, report quality, publication readiness

Ba domain mới cần được đưa vào dashboard/live evaluation:

- `06_citation_provenance/`
- `07_report_quality/`
- `08_publication_readiness/`

Client-final phải đi qua publication readiness. `auto_exported` chỉ là draft publishable.
