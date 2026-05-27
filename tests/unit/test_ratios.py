"""Unit tests for backend.analytics.ratios."""
from __future__ import annotations

import pytest

from backend.analytics.ratios import (
    compute_market_ratios,
    compute_ratios,
    detect_abnormal_movements,
    ratio_table_for_display,
)
from backend.facts.normalizer import FactTable


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_fact_table() -> FactTable:
    """Minimal fact table with two FY periods for DHG-like data."""
    return {
        "revenue.net": {"2023FY": 3_000.0, "2024FY": 3_300.0},  # bn VND
        "net_income.parent": {"2023FY": 300.0, "2024FY": 350.0},
        "gross_profit.total": {"2023FY": 900.0, "2024FY": 1_000.0},
        "ebitda.total": {"2023FY": 450.0, "2024FY": 500.0},
        "equity.parent": {"2023FY": 2_000.0, "2024FY": 2_300.0},
        "total_assets.ending": {"2023FY": 4_000.0, "2024FY": 4_500.0},
        "total_debt.ending": {"2023FY": 500.0, "2024FY": 400.0},
        "cash_and_equivalents.ending": {"2023FY": 200.0, "2024FY": 250.0},
        "operating_cash_flow.total": {"2023FY": 350.0, "2024FY": 400.0},
        "shares_outstanding.mn": {"2023FY": 135.0, "2024FY": 135.0},
        # eps in VND/share
        "eps.basic": {"2023FY": 5_000.0, "2024FY": 6_000.0},
    }


PRICE_VND = 94_400.0
SHARES_MN = 135.0


# ---------------------------------------------------------------------------
# Test: has_historical_prices=False  → _at_current_price keys
# ---------------------------------------------------------------------------

class TestMarketRatiosWithoutHistoricalPrices:
    """When has_historical_prices=False (default), market-dependent keys must use
    _at_current_price / _at_current_price_bn suffixes."""

    def setup_method(self):
        self.table = _make_fact_table()
        self.result = compute_market_ratios(
            self.table,
            market_price_vnd=PRICE_VND,
            shares_mn=SHARES_MN,
            # has_historical_prices defaults to False
        )

    def test_pe_key_is_at_current_price(self):
        assert "pe_at_current_price" in self.result, "Expected pe_at_current_price key"
        assert "pe" not in self.result, "Should NOT have bare 'pe' key"

    def test_pb_key_is_at_current_price(self):
        assert "pb_at_current_price" in self.result
        assert "pb" not in self.result

    def test_ps_key_is_at_current_price(self):
        assert "ps_at_current_price" in self.result
        assert "ps" not in self.result

    def test_p_ocf_key_is_at_current_price(self):
        assert "p_ocf_at_current_price" in self.result
        assert "p_ocf" not in self.result

    def test_ev_ebitda_key_is_at_current_price(self):
        assert "ev_ebitda_at_current_price" in self.result
        assert "ev_ebitda" not in self.result

    def test_market_cap_key_is_at_current_price_bn(self):
        assert "market_cap_at_current_price_bn" in self.result
        assert "market_cap_bn" not in self.result

    def test_market_ratios_without_historical_prices_uses_current_price_keys(self):
        """Consolidated check: _at_current_price variants present, bare variants absent."""
        expected_present = {
            "pe_at_current_price",
            "pb_at_current_price",
            "ps_at_current_price",
            "p_ocf_at_current_price",
            "ev_ebitda_at_current_price",
            "market_cap_at_current_price_bn",
        }
        expected_absent = {"pe", "pb", "ps", "p_ocf", "ev_ebitda", "market_cap_bn"}
        for k in expected_present:
            assert k in self.result, f"Missing expected key: {k}"
        for k in expected_absent:
            assert k not in self.result, f"Should not have bare key: {k}"

    def test_market_cap_is_identical_across_periods(self):
        """Current price → market_cap must be identical for all periods (exposing the
        limitation, not hiding it)."""
        caps = self.result.get("market_cap_at_current_price_bn", {})
        assert len(caps) > 1, "Expected multiple periods"
        values = list(caps.values())
        assert all(v == values[0] for v in values), (
            "market_cap_at_current_price_bn should be identical across periods "
            f"when a single price is used; got {caps}"
        )

    def test_pe_values_differ_across_periods(self):
        """P/E across periods differs because EPS differs even though price is the same."""
        pes = self.result.get("pe_at_current_price", {})
        assert len(pes) == 2
        assert pes["2023FY"] != pes["2024FY"]


# ---------------------------------------------------------------------------
# Test: has_historical_prices=True  → standard keys
# ---------------------------------------------------------------------------

class TestMarketRatiosWithHistoricalPrices:
    """When has_historical_prices=True, canonical keys (pe, pb, …) must be used."""

    def setup_method(self):
        self.table = _make_fact_table()
        self.result = compute_market_ratios(
            self.table,
            market_price_vnd=PRICE_VND,
            shares_mn=SHARES_MN,
            has_historical_prices=True,
        )

    def test_market_ratios_with_historical_prices_uses_standard_keys(self):
        """Consolidated check: canonical keys present, _at_current_price variants absent."""
        expected_present = {"pe", "pb", "ps", "p_ocf", "ev_ebitda", "market_cap_bn"}
        expected_absent = {
            "pe_at_current_price", "pb_at_current_price", "ps_at_current_price",
            "p_ocf_at_current_price", "ev_ebitda_at_current_price",
            "market_cap_at_current_price_bn",
        }
        for k in expected_present:
            assert k in self.result, f"Missing expected canonical key: {k}"
        for k in expected_absent:
            assert k not in self.result, f"Should not have suffixed key: {k}"

    def test_pe_present_and_numeric(self):
        pes = self.result.get("pe", {})
        assert len(pes) > 0
        for period, v in pes.items():
            assert isinstance(v, float), f"pe[{period}] should be float, got {type(v)}"


# ---------------------------------------------------------------------------
# Test: bvps always uses the same key
# ---------------------------------------------------------------------------

class TestBvpsKeyUnchanged:
    """bvps is not price-dependent — its key must be 'bvps' regardless of flag."""

    def test_bvps_key_unchanged_regardless_of_historical_flag_false(self):
        table = _make_fact_table()
        ratios = compute_ratios(table)
        assert "bvps" in ratios, "Expected 'bvps' key in compute_ratios output"
        assert "bvps_at_current_price" not in ratios

    def test_bvps_key_unchanged_regardless_of_historical_flag(self):
        """Even when calling compute_market_ratios, bvps is NOT in its output
        (bvps is computed by compute_ratios, not compute_market_ratios)."""
        table = _make_fact_table()
        for flag in (False, True):
            mkt = compute_market_ratios(table, PRICE_VND, SHARES_MN, has_historical_prices=flag)
            assert "bvps_at_current_price" not in mkt, (
                f"bvps_at_current_price should never appear (flag={flag})"
            )
            # bvps itself is owned by compute_ratios, not compute_market_ratios
            assert "bvps" not in mkt, (
                f"bvps should not be produced by compute_market_ratios (flag={flag})"
            )

    def test_bvps_value_is_correct(self):
        table = _make_fact_table()
        ratios = compute_ratios(table)
        # equity 2024FY = 2300 bn VND, shares = 135e6
        # bvps = 2300e9 / 135e6 = 17037.04 VND/share
        bvps_2024 = ratios["bvps"]["2024FY"]
        expected = 2_300 * 1_000_000_000 / (135 * 1_000_000)
        assert abs(bvps_2024 - expected) < 1.0, f"bvps_2024={bvps_2024}, expected≈{expected}"


# ---------------------------------------------------------------------------
# Test: non-price-dependent keys never get suffixed
# ---------------------------------------------------------------------------

class TestNonPriceKeysUnchanged:
    """inventory_days, receivable_days, payable_days, ccc should never be suffixed."""

    def test_working_capital_keys_unchanged(self):
        table: FactTable = {
            "revenue.net": {"2024FY": 3_000.0},
            "cogs.total": {"2024FY": 2_100.0},
            "inventory.ending": {"2024FY": 420.0},
            "receivables.ending": {"2024FY": 200.0},
            "payables.ending": {"2024FY": 150.0},
            "shares_outstanding.mn": {"2024FY": 135.0},
            "equity.parent": {"2024FY": 2_000.0},
        }
        ratios = compute_ratios(table)
        for k in ("inventory_days", "receivable_days", "payable_days", "ccc"):
            if k in ratios:
                assert f"{k}_at_current_price" not in ratios, f"{k} should not be suffixed"


# ---------------------------------------------------------------------------
# Test: ratio_table_for_display formatting
# ---------------------------------------------------------------------------

class TestRatioTableForDisplay:
    def test_multiple_formatted_with_x(self):
        rt = {"pe_at_current_price": {"2024FY": 15.733}}
        display = ratio_table_for_display(rt)
        assert display["pe_at_current_price"]["2024FY"] == "15.7x"

    def test_pe_formatted_with_x(self):
        rt = {"pe": {"2024FY": 12.5}}
        display = ratio_table_for_display(rt)
        assert display["pe"]["2024FY"] == "12.5x"

    def test_pct_formatted_with_percent(self):
        rt = {"gross_margin": {"2024FY": 0.3030}}
        display = ratio_table_for_display(rt)
        assert display["gross_margin"]["2024FY"] == "30.3%"

    def test_market_cap_bn_formatted_without_x(self):
        rt = {"market_cap_at_current_price_bn": {"2024FY": 12_755.3}}
        display = ratio_table_for_display(rt)
        assert display["market_cap_at_current_price_bn"]["2024FY"] == "12,755.3"

    def test_bvps_formatted_as_integer_vnd(self):
        rt = {"bvps": {"2024FY": 17037.04}}
        display = ratio_table_for_display(rt)
        assert display["bvps"]["2024FY"] == "17,037"

    def test_fallback_no_x_suffix(self):
        rt = {"some_unknown_metric": {"2024FY": 3.14}}
        display = ratio_table_for_display(rt)
        # fallback should NOT append 'x'
        assert display["some_unknown_metric"]["2024FY"] == "3.14"
        assert not display["some_unknown_metric"]["2024FY"].endswith("x")


# ---------------------------------------------------------------------------
# Test: detect_abnormal_movements includes _at_current_price variants
# ---------------------------------------------------------------------------

class TestDetectAbnormalMovements:
    def test_pe_at_current_price_detected(self):
        rt = {"pe_at_current_price": {"2022FY": 10.0, "2023FY": 20.0, "2024FY": 20.0}}
        flags = detect_abnormal_movements(rt, threshold=0.5)
        assert any(f["metric"] == "pe_at_current_price" for f in flags), (
            "Should flag pe_at_current_price movement"
        )

    def test_pe_bare_detected(self):
        rt = {"pe": {"2022FY": 10.0, "2023FY": 20.0}}
        flags = detect_abnormal_movements(rt, threshold=0.5)
        assert any(f["metric"] == "pe" for f in flags)

    def test_ev_ebitda_at_current_price_detected(self):
        rt = {"ev_ebitda_at_current_price": {"2022FY": 5.0, "2023FY": 10.0}}
        flags = detect_abnormal_movements(rt, threshold=0.5)
        assert any(f["metric"] == "ev_ebitda_at_current_price" for f in flags)

    def test_no_flag_when_change_below_threshold(self):
        rt = {"pe_at_current_price": {"2022FY": 10.0, "2023FY": 11.0}}
        flags = detect_abnormal_movements(rt, threshold=0.5)
        assert not flags

    def test_non_rel_key_not_flagged(self):
        # inventory_days is not in _REL_KEYS → should not appear in flags
        rt = {"inventory_days": {"2022FY": 30.0, "2023FY": 100.0}}
        flags = detect_abnormal_movements(rt, threshold=0.5)
        assert not any(f["metric"] == "inventory_days" for f in flags)
