"""Period-label display convention: actuals as <YEAR>A, forecasts as <YEAR>F.

The report header previously mixed '2025FY' (actuals) with '2026F' (forecasts),
which looks inconsistent. Display actuals with a single-letter 'A' suffix so the
column headers read uniformly (2024A 2025A 2026F ...). Fact lookups must keep
working because canonical fact keys still use the 'FY' suffix.
"""
from __future__ import annotations

from backend.reporting.client_report_view_model import _derive_periods, _to_fact_period


def _facts() -> dict[str, dict[str, dict[str, float]]]:
    return {
        "revenue.net": {
            "2023FY": {"value": 1.0},
            "2024FY": {"value": 1.0},
            "2025FY": {"value": 1.0},
        }
    }


def _forecast() -> dict[str, object]:
    return {"forecast_years": [{"label": "2026F"}, {"label": "2027F"}]}


def test_actual_periods_use_single_letter_a_suffix() -> None:
    periods = _derive_periods(_facts(), _forecast())

    assert periods == ["2023A", "2024A", "2025A", "2026F", "2027F"]


def test_actual_a_label_still_resolves_to_canonical_fy_fact_key() -> None:
    # Display label '2025A' must map back to the '2025FY' canonical fact key.
    assert _to_fact_period("2025A") == "2025FY"
