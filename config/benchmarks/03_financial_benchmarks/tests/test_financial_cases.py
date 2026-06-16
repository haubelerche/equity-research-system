from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
BENCHMARK = ROOT / "03_financial_benchmarks"
V2_CASES = BENCHMARK / "golden_valuation" / "valuation_cases.jsonl"
V3_CASES = BENCHMARK / "golden_valuation" / "finance_cases_v3.jsonl"
SENSITIVITY_GRID = BENCHMARK / "golden_valuation" / "sensitivity_grid.csv"
GOLDEN_RATIOS = BENCHMARK / "golden_ratios.csv"
STRICT_METRICS = BENCHMARK / "strict_metrics.yaml"

REQUIRED_V3_BASE_CHECKS = {
    "bs_balance",
    "eps_unit",
    "net_debt",
    "fcff_formula",
    "fcfe_formula",
    "wacc_gt_g",
    "ev_to_equity_bridge",
    "target_price_bridge",
    "fcff_sensitivity",
    "fcfe_sensitivity",
    "blend_sensitivity",
    "recommendation_consistency",
}
EXPECTED_RATIO_NAMES = {
    "gross_margin",
    "net_margin",
    "roe_simple",
    "asset_turnover",
    "current_ratio",
    "debt_to_equity",
    "net_debt_to_equity",
    "cfo_margin",
    "capex_to_revenue_abs",
}
STRICT_ARTIFACT_FIELDS = {
    "run_id",
    "dataset_version",
    "case_id",
    "ticker",
    "selected_methods",
    "inputs_used",
    "formula_trace",
    "computed_outputs",
    "sensitivity_grids",
    "publishability_decision",
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def recompute_dcf(case: dict[str, Any]) -> tuple[list[float], float, float, float]:
    inp = case["inputs"]
    years = int(inp.get("projection_years") or 5)
    base = float(inp["base_free_cash_flow_bn"])
    growth = float(inp["growth"])
    wacc = float(inp["wacc"])
    terminal_growth = float(inp["terminal_growth"])
    fcf = [base * ((1 + growth) ** i) for i in range(1, years + 1)]
    pv = [fcf[i] / ((1 + wacc) ** (i + 1)) for i in range(years)]
    terminal_value = fcf[-1] * (1 + terminal_growth) / (wacc - terminal_growth)
    enterprise_value = sum(pv) + terminal_value / ((1 + wacc) ** years)
    equity_value = enterprise_value - float(inp["net_debt_bn"])
    target_price = equity_value * 1e9 / float(inp["shares_outstanding"])
    return fcf, enterprise_value, equity_value, target_price


def assert_monotonic(values: list[float], *, increasing: bool) -> None:
    pairs = zip(values, values[1:])
    if increasing:
        assert all(left < right for left, right in pairs), values
    else:
        assert all(left > right for left, right in pairs), values


def test_strict_metric_contract_is_packaged() -> None:
    contract = yaml.safe_load(STRICT_METRICS.read_text(encoding="utf-8"))

    assert contract["benchmark"]["id"] == "03_financial_benchmarks_strict_v1"
    assert "all P0 metrics pass" in contract["benchmark"]["scoring_rule"]
    assert set(contract["benchmark"]["artifact_contract"]["must_include"]) == STRICT_ARTIFACT_FIELDS

    metrics = contract["metrics"]
    metric_ids = [metric["id"] for metric in metrics]
    assert len(metric_ids) == len(set(metric_ids))
    assert all(metric_id.startswith("finance.") for metric_id in metric_ids)
    assert "finance.artifact_present" in metric_ids
    assert "finance.golden_valuation_drift_errors" in metric_ids
    assert "finance.llm_tool_governance" in metric_ids

    p0_metrics = [metric for metric in metrics if metric["severity"] == "P0"]
    assert p0_metrics
    assert all(metric.get("threshold") in {0, 1.0, True} for metric in p0_metrics)


def test_v3_manifest_references_all_strict_finance_inputs() -> None:
    manifest = yaml.safe_load((BENCHMARK / "dataset_manifest_v3.yaml").read_text(encoding="utf-8"))
    datasets = set(manifest["datasets"])

    assert manifest["version"] == "20260615_v3"
    assert manifest["negative_cases"] == 6
    assert {
        "golden_valuation/finance_cases_v3.jsonl",
        "golden_ratios.csv",
        "golden_valuation/sensitivity_grid.csv",
        "strict_metrics.yaml",
    }.issubset(datasets)
    for relative_path in datasets:
        assert (BENCHMARK / relative_path).is_file(), relative_path


def test_v2_valuation_cases_recompute_and_remain_separate_from_v3_truth_set() -> None:
    cases = read_jsonl(V2_CASES)

    assert len(cases) == 14
    assert len({case["case_id"] for case in cases}) == len(cases)
    for case in cases:
        inp = case["inputs"]
        expected = case["expected_outputs"]
        tolerances = case["tolerances"]
        fcf, enterprise_value, equity_value, target_price = recompute_dcf(case)
        expected_net_debt = (
            float(inp["short_term_debt_bn"])
            + float(inp["long_term_debt_bn"])
            - float(inp["cash_and_equivalents_bn"])
            - float(inp["short_term_investments_bn"])
        )

        assert case["case_id"].endswith("_v2")
        assert inp["wacc"] > inp["terminal_growth"]
        assert inp["shares_outstanding"] > 0
        assert abs(expected_net_debt - expected["net_debt_bn"]) <= 0.001
        assert abs(enterprise_value - expected["enterprise_value_bn"]) <= tolerances["enterprise_value_bn_abs"]
        assert abs(equity_value - expected["equity_value_bn"]) <= tolerances["enterprise_value_bn_abs"]
        assert abs(target_price - expected["target_price_vnd"]) / max(abs(target_price), 1) <= tolerances["target_price_vnd_pct"]
        for actual, expected_fcf in zip(fcf, expected["fcf_projection_bn"]):
            assert abs(actual - expected_fcf) <= 0.001


def test_v3_finance_cases_cover_positive_negative_and_resist_constant_shortcuts() -> None:
    cases = read_jsonl(V3_CASES)
    case_ids = [case["case_id"] for case in cases]
    base_cases = [case for case in cases if case["case_type"] == "publishable_base"]
    negative_cases = [case for case in cases if case["case_type"] != "publishable_base"]

    assert len(cases) == 20
    assert len(case_ids) == len(set(case_ids))
    assert len(base_cases) == 14
    assert len(negative_cases) == 6

    for case in base_cases:
        inputs = case["inputs"]
        expected = case["expected"]
        required_checks = set(case["required_checks"])
        expected_net_debt = (
            float(inputs["interest_bearing_debt"])
            - float(inputs["cash"])
            - float(inputs["short_term_investments"])
        )

        assert case["case_id"].startswith(f"FIN_{case['ticker']}_")
        assert case["snapshot_id"].startswith(f"SNAP_{case['ticker']}_")
        assert required_checks == REQUIRED_V3_BASE_CHECKS
        assert inputs["shares_outstanding_mn"] > 0
        assert inputs["wacc"] > inputs["terminal_growth"]
        assert inputs["cost_of_equity"] > inputs["terminal_growth"]
        assert math.isclose(expected_net_debt, float(expected["net_debt"]), abs_tol=0.001)
        assert expected["publishable"] is True
        assert expected["rating"] in {"BUY", "HOLD", "SELL"}
        assert expected["fcff_target_price"] > 0
        assert expected["fcfe_target_price"] > 0
        assert expected["blend_target_price"] > 0

    for field in (
        "cash",
        "interest_bearing_debt",
        "short_term_investments",
        "wacc",
        "terminal_growth",
        "cost_of_equity",
    ):
        values = {case["inputs"][field] for case in base_cases}
        assert len(values) >= 4, f"{field} is too uniform for an anti-overfit benchmark"

    expected_failures = {case["expected_failure"] for case in negative_cases}
    assert all(failure.startswith("finance.") for failure in expected_failures)
    assert len(expected_failures) == len(negative_cases)
    assert Counter(case["severity"] for case in negative_cases) == {"P0": 5, "P1": 1}


def test_sensitivity_grid_shape_base_cell_and_monotonicity() -> None:
    cases = {case["case_id"]: case for case in read_jsonl(V2_CASES)}
    rows = read_csv(SENSITIVITY_GRID)
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["case_id"]].append(row)

    assert len(rows) == 350
    assert set(grouped) == set(cases)
    for case_id, case_rows in grouped.items():
        case = cases[case_id]
        wacc_points = sorted({float(row["wacc"]) for row in case_rows})
        growth_points = sorted({float(row["terminal_growth"]) for row in case_rows})
        base_wacc = float(case["inputs"]["wacc"])
        base_growth = float(case["inputs"]["terminal_growth"])
        base_target = float(case["expected_outputs"]["target_price_vnd"])
        tolerance = float(case["tolerances"]["target_price_vnd_pct"])

        assert len(case_rows) == 25
        assert len(wacc_points) == 5
        assert len(growth_points) == 5
        assert base_wacc in wacc_points
        assert base_growth in growth_points

        base_cells = [
            float(row["target_price_vnd"])
            for row in case_rows
            if float(row["wacc"]) == base_wacc and float(row["terminal_growth"]) == base_growth
        ]
        assert len(base_cells) == 1
        assert abs(base_cells[0] - base_target) / max(abs(base_target), 1) <= tolerance

        for growth in growth_points:
            values = [
                float(row["target_price_vnd"])
                for row in sorted(case_rows, key=lambda item: float(item["wacc"]))
                if float(row["terminal_growth"]) == growth
            ]
            assert_monotonic(values, increasing=False)
        for wacc in wacc_points:
            values = [
                float(row["target_price_vnd"])
                for row in sorted(case_rows, key=lambda item: float(item["terminal_growth"]))
                if float(row["wacc"]) == wacc
            ]
            assert_monotonic(values, increasing=True)


def test_golden_ratios_have_expected_panel_layout_and_numeric_values() -> None:
    rows = read_csv(GOLDEN_RATIOS)
    keys = {(row["ticker"], row["fiscal_year"], row["ratio"]) for row in rows}

    assert len(rows) == 504
    assert len(keys) == len(rows)
    assert {row["fiscal_year"] for row in rows} == {"2022", "2023", "2024", "2025"}
    assert {row["ratio"] for row in rows} == EXPECTED_RATIO_NAMES
    assert {row["formula_version"] for row in rows} == {"ratio_v1"}
    assert {row["source"] for row in rows} == {"derived_from_golden_financials"}

    tickers = {row["ticker"] for row in rows}
    assert len(tickers) == 14
    for ticker in tickers:
        ticker_rows = [row for row in rows if row["ticker"] == ticker]
        assert len(ticker_rows) == 36
        for year in ("2022", "2023", "2024", "2025"):
            assert {row["ratio"] for row in ticker_rows if row["fiscal_year"] == year} == EXPECTED_RATIO_NAMES

    for row in rows:
        value = float(row["value"])
        assert math.isfinite(value)


def test_financial_artifact_examples_keep_release_gate_metric_contract() -> None:
    required_metric_fields = {
        "metric_id",
        "metric_name",
        "category",
        "layer",
        "metric_type",
        "scope",
        "severity",
        "blocks_publish",
        "threshold_operator",
        "threshold",
        "unit",
        "owner",
        "value",
        "status",
        "sample_size",
        "failed_examples",
        "remediation_hint",
        "dataset_version",
        "benchmark_suite_version",
        "evaluated_at",
    }

    for path in sorted((BENCHMARK / "artifact_examples").glob("financial_eval_*.json")):
        artifact = json.loads(path.read_text(encoding="utf-8"))
        metrics = artifact["metrics"]

        assert artifact["artifact_name"] == "financial_eval"
        assert artifact["schema_version"] == "20260615_v3"
        assert artifact["summary"]["metric_count"] == len(metrics)
        assert metrics
        for metric in metrics:
            assert required_metric_fields.issubset(metric)
            assert metric["category"] == "financial_model"
            assert metric["severity"] in {"P0", "P1", "P2", "P3"}
            if metric["severity"] == "P0":
                assert metric["blocks_publish"] is True
            if metric["status"] == "fail":
                assert metric["failed_examples"]
