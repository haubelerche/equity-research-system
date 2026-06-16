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

PowerShell:

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe scripts/run_benchmark_suite.py --plans 02 --tickers DHG --skip-tests
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

```bash
cd 05_ops_cost_latency
pytest -q tests
```
