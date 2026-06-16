# Cách chạy benchmark

## 1. Kiểm tra nhanh dataset package

```bash
python scripts/benchmark_scorecard.py
```

## 2. Pandera

```bash
cd 01_pandera_data_quality
pytest -q tests
```

## 3. Ragas

Run benchmark 2 through the project runner so the result is written to the
dashboard artifact `output/evaluation/eval_result/benchmark_suite/retrieval_eval.json`.
Use the repository virtualenv; the system Python on this workstation has shown
`PIL` / `huggingface_hub` import failures that make RAGAS unavailable.
The representative RAG scope is DHG because its 2022-2025 official-document
coverage exercises the same query/retrieval pattern as the wider pharma universe.

PowerShell:

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe scripts/run_benchmark_suite.py --plans 02 --cohort rag_representative_dhg --skip-tests
```

If a fresh DHG artifact already exists and the goal is only to refresh the
dashboard-visible aggregate without paying live RAGAS latency again:

```powershell
.venv\Scripts\python.exe scripts/run_benchmark_suite.py --plans 02 --cohort rag_representative_dhg --reuse-existing
```

Validation:

```powershell
.venv\Scripts\python.exe -m pytest -q config/benchmarks/02_ragas_retrieval/tests tests/unit/test_ragas_live.py tests/unit/test_project_evaluator.py
```

## 4. Finance

Run the finance fixture tests once, then run benchmark plan 03 through the
project runner so the result is written to the dashboard artifact
`output/evaluation/eval_result/benchmark_suite/financial_eval.json`.

PowerShell:

```powershell
.venv\Scripts\python.exe -m pytest -q config/benchmarks/03_financial_benchmarks/tests
.venv\Scripts\python.exe scripts/run_benchmark_suite.py --plans 03 --skip-tests
```

## 5. DeepEval

Map mỗi row trong `04_deepeval_agent/deepeval_cases/agent_cases.jsonl` thành `LLMTestCase`, rồi chạy các custom GEval metrics: role adherence, groundedness, task completion, plan adherence, critic issue recall.

## 6. Ops

The dataset package is named `05_ops_cost_latency`, but the dashboard artifact
is emitted by project plan `07` as `observability_eval.json`.

Validate the fixture package first:

```powershell
.venv\Scripts\python.exe -m pytest -q config\benchmarks\05_ops_cost_latency\tests
```

Then refresh the dashboard-visible benchmark artifact:

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe scripts\run_benchmark_suite.py --plans 07 --skip-tests
```
