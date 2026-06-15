# VN Pharma Benchmark Suite 20260615 v3

Bộ benchmark này cập nhật `vn_pharma_benchmark_suite_20260615` theo các tài liệu mới ngày 13-15/06/2026. Phiên bản v3 không chỉ giữ 5 nhóm công nghệ ban đầu, mà mở rộng thành 8 miền đánh giá đúng với runtime/evaluation dashboard hiện hành:

1. `01_pandera_data_quality` — chất lượng dữ liệu và fact canonical.
2. `02_ragas_retrieval` — RAG, golden queries, evidence retrieval và faithfulness.
3. `03_financial_benchmarks` — tính toán tài chính, valuation invariants và formula trace.
4. `04_deepeval_agent` — agent workflow, LLM judge, tool permission và output schema.
5. `05_ops_cost_latency` — observability, cost, retry, fallback và latency.
6. `06_citation_provenance` — citation resolver, claim ledger, numeric support và source tier.
7. `07_report_quality` — report rubric, completeness, forecast rationale và valuation transparency.
8. `08_publication_readiness` — package validation, locked model, approval boundary và snapshot match.

## Các thay đổi lớn so với v2

- Thêm `metric_registry_v3.yaml` với schema metric thống nhất: category, layer, metric type, scope, severity, blocks_publish, threshold, owner và remediation hint.
- Thêm JSON schema cho 8 run-scoped evaluation artifacts: `data_quality_eval`, `rag_eval`, `financial_eval`, `citation_eval`, `agent_eval`, `report_quality_eval`, `observability_eval`, `publication_readiness_eval`.
- Tách riêng citation và report quality thay vì trộn vào RAG/agent.
- Mở rộng financial cases cho accounting invariants, share count, target bridge, WACC/terminal growth, net debt, FCFE debt schedule, recommendation consistency và valuation publishability.
- Mở rộng data fixtures bằng `snapshot_id`, `source_doc_id`, `source_tier`, `reconciliation_status`, `freshness_status`, `promotion_status` và OCR state.
- Thêm dashboard crosswalk để mapping từng metric về UI, release gate, diagnostic hoặc observability.
- Đính kèm `docs_reference/` gồm toàn bộ tài liệu mới dùng để thiết kế benchmark.

## Chạy kiểm tra cấu trúc

```bash
cd vn_pharma_benchmark_suite_20260615_v3
python scripts/benchmark_scorecard_v3.py
pytest -q tests
```

Lưu ý: các test này kiểm tra structural validity của benchmark package. Khi tích hợp vào repo chính, các framework thực tế như Pandera, Ragas, DeepEval, Langfuse và gate runtime của dự án phải được gọi từ CI/runtime tương ứng.
