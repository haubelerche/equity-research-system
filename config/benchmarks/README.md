# VN Pharma Benchmark Suite 20260615

`config/benchmarks` is the single canonical benchmark package for this
repository. The old root-level `benchmarks/` mirror and legacy threshold
registries were removed to avoid dashboard/runtime drift.

The active benchmark domains are:

1. `01_pandera_data_quality`
2. `02_ragas_retrieval`
3. `03_financial_benchmarks`
4. `04_deepeval_agent`
5. `05_ops_cost_latency`
6. `06_citation_provenance`
7. `07_report_quality`
8. `08_publication_readiness`

The canonical metric contract is `shared/metric_registry_v3.yaml`. Runtime
normalization reads this registry directly; do not add parallel threshold files.

Run the structural package check from the repository root:

```powershell
.venv\Scripts\python.exe config\benchmarks\scripts\benchmark_scorecard.py
.venv\Scripts\python.exe -m pytest -q config\benchmarks\tests
```
