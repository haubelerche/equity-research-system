# Executable Evaluation Datasets

The project evaluator only reports a professional framework as `executed` when
the corresponding versioned dataset exists and the framework call succeeds.
Missing datasets or credentials produce `not_evaluable`; they never produce a
fabricated zero or pass.

## Ragas

Create `config/eval/ragas/<TICKER>.json` as a JSON list. Each item must follow
the Ragas single-turn shape used by `backend/evaluation/framework_adapters.py`:

```json
[
  {
    "question": "What was revenue in 2025?",
    "contexts": ["Retrieved evidence span"],
    "answer": "Revenue was ...",
    "ground_truth": "Reference answer"
  }
]
```

Ragas requires configured model-provider credentials. Execution errors are
stored in `ragas_execution.reason` and semantic metrics remain not evaluated.

## DeepEval

Create `config/eval/deepeval/<TICKER>.json` as a JSON list:

```json
[
  {
    "input": "Assigned task and role constraints",
    "actual_output": "Agent output",
    "expected_output": "Reference behavior",
    "retrieval_context": ["Evidence supplied to the agent"]
  }
]
```

DeepEval runs fixed G-Eval rubrics for role adherence, groundedness, task
completion, and plan adherence. These scores are diagnostics and cannot
override deterministic financial, citation, or publication gates.

## Metric Evidence

Every emitted metric contains:

- evaluator framework, version, and execution status;
- formula, numerator, denominator, aggregation, and per-sample results;
- threshold profile and rationale;
- sample size, dataset version, artifact references, failed examples, and
  remediation guidance.
