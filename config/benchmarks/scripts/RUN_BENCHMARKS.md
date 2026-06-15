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

Pseudo-code:

```python
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import context_precision, context_recall, faithfulness, answer_relevancy
import json
rows = [json.loads(x) for x in open('02_ragas_retrieval/ragas/ragas_samples.jsonl', encoding='utf-8')]
ds = Dataset.from_list(rows)
result = evaluate(ds, metrics=[context_precision, context_recall, faithfulness, answer_relevancy])
```

## 4. Finance

```bash
cd 03_financial_benchmarks
pytest -q tests
```

## 5. DeepEval

Map mỗi row trong `04_deepeval_agent/deepeval_cases/agent_cases.jsonl` thành `LLMTestCase`, rồi chạy các custom GEval metrics: role adherence, groundedness, task completion, plan adherence, critic issue recall.

## 6. Ops

```bash
cd 05_ops_cost_latency
pytest -q tests
```
