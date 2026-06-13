"""Regression: harness stamps deterministic lineage so LLM artifacts validate.

The LLM must not be required to emit run_id/ticker/checksum (Python owns lineage).
Before the fix, agent payloads failed FinancialAnalysis validation on those
required fields and the run stalled at needs_review.
"""
from __future__ import annotations

from backend.harness.contracts import validate_agent_artifact
from backend.harness.runner import ResearchGraphRunner
from backend.harness.state import ResearchGraphState


def _state() -> ResearchGraphState:
    return ResearchGraphState(
        run_id="run_dhg_test",
        ticker="DHG",
        run_type="full_report",
        objective="test",
        policy={},
        flags={},
    )


def test_lineage_injected_and_payload_validates():
    # Domain content only — no run_id/ticker/checksum, as the LLM would return.
    payload = {
        "historical_periods": ["2022", "2023", "2024"],
        "latest_period": "2024",
        "financial_risks": ["leverage"],
    }
    ResearchGraphRunner._inject_artifact_lineage(_state(), payload)

    assert payload["run_id"] == "run_dhg_test"
    assert payload["ticker"] == "DHG"
    assert isinstance(payload["checksum"], str) and len(payload["checksum"]) == 64

    artifact = validate_agent_artifact("FinancialAnalysis", payload)
    assert artifact.run_id == "run_dhg_test"
    assert artifact.ticker == "DHG"


def test_lineage_is_deterministic_for_same_domain_content():
    a = {"latest_period": "2024", "financial_risks": ["x"]}
    b = {"latest_period": "2024", "financial_risks": ["x"]}
    ResearchGraphRunner._inject_artifact_lineage(_state(), a)
    ResearchGraphRunner._inject_artifact_lineage(_state(), b)
    assert a["checksum"] == b["checksum"]


def test_lineage_overrides_model_supplied_identity():
    # Even if the model fabricates run_id/ticker, Python's authoritative values win.
    payload = {"latest_period": "2024", "run_id": "WRONG", "ticker": "ZZZ"}
    ResearchGraphRunner._inject_artifact_lineage(_state(), payload)
    assert payload["run_id"] == "run_dhg_test"
    assert payload["ticker"] == "DHG"


def test_non_dict_payload_is_ignored():
    ResearchGraphRunner._inject_artifact_lineage(_state(), "not a dict")  # no raise


def test_repair_backfills_latest_period_and_validates():
    # Model omitted latest_period and returned a malformed evidence_request (dict items).
    payload = {
        "historical_periods": ["2022", "2023", "2024"],
        "evidence_request": {
            "requested_items": [
                {"item": "Full 2023FY cash flow statement"},
                {"item": "Segment revenue breakdown"},
            ],
        },
    }
    ResearchGraphRunner._inject_artifact_lineage(_state(), payload)
    ResearchGraphRunner._repair_agent_payload(payload)

    assert payload["latest_period"] == "2024"
    assert payload["evidence_request"]["requested_items"] == [
        "Full 2023FY cash flow statement",
        "Segment revenue breakdown",
    ]
    assert payload["evidence_request"]["reason"]
    assert payload["evidence_request"]["request_id"]

    artifact = validate_agent_artifact("FinancialAnalysis", payload)
    assert artifact.latest_period == "2024"
    assert artifact.evidence_request.requested_items[0] == "Full 2023FY cash flow statement"


def test_repair_drops_uncoercible_evidence_request():
    payload = {"latest_period": "2024", "evidence_request": "please send more data"}
    ResearchGraphRunner._repair_agent_payload(payload)
    assert payload["evidence_request"] is None


def test_repair_normalizes_forecast_aliases_without_fabricating_balance_check():
    payload = {
        "producer": "forecast_valuation_agent",
        "forecast_horizon": ["2026F", "2027F"],
        "driver_assumptions": {
            "revenue_drivers": {
                "channel_product_drivers": {
                    "otc": {"label": "unresolved", "growth_assumption": "unresolved"},
                },
                "revenue_growth_by_year": {"base_case": {"2026F": 0.05}},
            },
            "gross_margin_drivers": {
                "gross_margin_by_year": {"base_case": {"2026F": 0.45}},
                "driver_narrative": "mix",
            },
            "opex_drivers": {
                "sga_as_pct_revenue": {
                    "forecast_assumption": {"base_case": {"2026F": 0.25}},
                },
            },
        },
        "working_capital_forecast": {
            "forecast_assumptions": {
                "base_case": {"dso_days": 20, "dio_days": 100, "dpo_days": 40},
            },
        },
        "capex_depreciation_forecast": {
            "forecast_assumptions": {
                "base_case": {"depreciation_bn_estimated": {"2026F": 10}},
            },
        },
        "debt_cash_interest_forecast": {
            "base_period_position": {"short_term_debt_2025FY": 0},
            "forecast_assumptions": {
                "interest_expense_forecast_bn": {"2026F": 0},
                "new_debt_issuance": "none",
            },
        },
        "income_statement_forecast": {
            "base_case": {"2026F": {"eps_basic_vnd_estimated": 1000}},
        },
        "cash_flow_forecast": {"base_case": {"2026F": {"fcff_estimated": 10}}},
        "quality_checks": {
            "2023fy_anomaly_treatment": {"status": "PASS"},
            "driver_traceability": {"status": "PASS"},
            "gross_margin_consistency": {"status": "PASS"},
            "fcff_vs_net_income": {"status": "PASS"},
        },
        "limitations": [{"description": "segment data unavailable"}],
    }

    ResearchGraphRunner._inject_artifact_lineage(_state(), payload)
    ResearchGraphRunner._repair_agent_payload(payload)

    assert payload["forecast_horizon"]["explicit_years"] == [2026, 2027]
    assert payload["limitations"] == ["segment data unavailable"]
    assert payload["working_capital_forecast"]["receivable_days"] == 20
    assert payload["capex_and_depreciation"]["depreciation"] == {"2026F": 10}
    assert payload["eps_forecast"] == {"2026F": 1000}
    assert payload["forecast_quality_checks"]["balance_sheet_balance_check"]["status"] == "fail"

    artifact = validate_agent_artifact("ForecastValuationArtifact", payload)
    assert artifact.forecast_horizon.start_year == 2026
