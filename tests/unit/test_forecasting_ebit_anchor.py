"""Unit tests for anchoring forecast EBIT to historical EBIT margin.

Root cause (2026-06-19): when ``sga.total`` is missing from the source facts,
forecasting defaulted SG&A to 20% of revenue. For a low-gross-margin company
(e.g. a pharma distributor with ~10% gross margin) this drove EBIT margin to
``gross_margin - 0.20 ≈ -10%``, flipping a historically profitable company into
forecast losses and a negative DCF equity value.

The fix anchors the forecast EBIT margin to the historically observed EBIT
margin (``ebit.total`` / ``revenue.net``, falling back to
``operating_profit.total``) whenever the SG&A line item is unavailable, so the
forecast can never invert a profitable company.
"""
from __future__ import annotations

import statistics

from backend.analytics.forecasting import run_forecast
from backend.facts.normalizer import FactTable


def _dht_like_missing_sga() -> FactTable:
    """DHT 2022-2025: ~10% gross margin, positive EBIT, but sga.total absent.

    Historical EBIT margin (ebit.total / revenue.net):
      2022FY: 106.5 / 1837.4 = 5.80%
      2024FY:  73.0 / 2086.4 = 3.50%
      2025FY:  49.9 / 2402.0 = 2.08%
      → median ≈ 3.50%   (the forecast must land near this, not -10%)
    """
    return {
        "revenue.net": {
            "2022FY": 1837.4, "2023FY": 1999.3, "2024FY": 2086.4, "2025FY": 2402.0,
        },
        "gross_profit.total": {
            "2022FY": 187.3, "2023FY": 203.3, "2024FY": 219.8, "2025FY": 209.2,
        },
        # Real operating profit is in the facts and is POSITIVE.
        "ebit.total": {
            "2022FY": 106.5, "2024FY": 73.0, "2025FY": 49.9,
        },
        "interest_expense.total": {
            "2022FY": -14.3, "2023FY": -20.1, "2024FY": -13.4, "2025FY": -13.1,
        },
        "profit_before_tax.total": {
            "2022FY": 123.2, "2023FY": 110.3, "2024FY": 95.2, "2025FY": 73.3,
        },
        "tax_expense.total": {
            "2022FY": -24.6, "2023FY": -22.1, "2024FY": -19.0, "2025FY": -14.7,
        },
        # sga.total intentionally omitted — the source facts lack it.
    }


def _expected_hist_ebit_margin(table: FactTable) -> float:
    ratios = []
    for p, ebit in table["ebit.total"].items():
        rev = table["revenue.net"].get(p)
        if ebit is not None and rev:
            ratios.append(ebit / rev)
    return statistics.median(ratios)


class TestEbitAnchoredToHistoryWhenSgaMissing:
    def test_forecast_ebit_is_positive(self):
        table = _dht_like_missing_sga()
        artifact = run_forecast("DHT", table, n_years=5)
        for fy in artifact.forecast_years:
            assert fy.ebit is not None and fy.ebit > 0, (
                f"Year {fy.year}: EBIT should stay positive for a historically "
                f"profitable company, got {fy.ebit}"
            )

    def test_forecast_ebit_margin_matches_historical(self):
        table = _dht_like_missing_sga()
        expected = _expected_hist_ebit_margin(table)
        artifact = run_forecast("DHT", table, n_years=5)
        for fy in artifact.forecast_years:
            assert fy.ebit_margin is not None
            assert abs(fy.ebit_margin - expected) < 0.01, (
                f"Year {fy.year}: EBIT margin {fy.ebit_margin:.4f} should anchor to "
                f"historical median {expected:.4f}"
            )

    def test_sga_does_not_default_to_twenty_percent(self):
        """The SG&A ratio must reflect the gross-profit-to-EBIT bridge, not 0.20."""
        table = _dht_like_missing_sga()
        artifact = run_forecast("DHT", table, n_years=1)
        sga_ratio = artifact.drivers["sga_to_revenue"]["value"]
        assert sga_ratio != 0.20, "SG&A should not fall back to the 20% default"
        assert sga_ratio < 0.10, (
            f"SG&A ratio should be small for a ~10% gross-margin distributor, got {sga_ratio}"
        )
