from pathlib import Path
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def percentile(values, p):
    values = sorted(values)
    if not values:
        return 0
    k = int(round((len(values) - 1) * p))
    return values[k]


def test_ops_traces_within_budget_for_golden_runs():
    traces = pd.read_csv(ROOT / "05_ops_cost_latency" / "golden_run_traces.csv")
    rubric = yaml.safe_load((ROOT / "05_ops_cost_latency" / "ops_cost_latency_rubric.yaml").read_text(encoding="utf-8"))
    warm = traces[traces.run_type == "warm"].total_duration_seconds.tolist()
    cold = traces[traces.run_type == "cold"].total_duration_seconds.tolist()
    assert percentile(warm, 0.95) <= rubric["latency_budgets_seconds"]["warm_full_report_p95"]
    assert percentile(cold, 0.95) <= rubric["latency_budgets_seconds"]["cold_full_report_p95"]
    assert traces.estimated_cost_usd.max() <= rubric["cost_budgets_usd"]["soft_full_report"]
    assert traces.artifact_upload_failures.sum() == 0
    assert traces.pdf_render_failures.sum() == 0
