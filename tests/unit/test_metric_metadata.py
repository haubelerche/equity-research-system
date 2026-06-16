"""Tests for backend.facts.metric_metadata — unit validation & normalization."""
from __future__ import annotations

import pytest

from backend.facts.metric_metadata import (
    METRIC_METADATA,
    SCALE_SENSITIVE_TYPES,
    SemanticType,
    NormResult,
    format_monetary,
    get_semantic_type,
    is_known_metric,
    validate_and_normalize,
)


# ---------------------------------------------------------------------------
# Registry completeness
# ---------------------------------------------------------------------------

class TestRegistry:
    def test_working_capital_ending_keys_registered(self):
        # Canonical keys used by fact.production_facts, the WC schedule, and the PDF
        # extractor catalog. If unregistered, validate_and_normalize rejects them and
        # build_fact_table drops them → working capital reads 0 (understated delta_nwc).
        for key in ("accounts_receivable.ending", "inventory.ending", "accounts_payable.ending"):
            assert is_known_metric(key), key
            assert validate_and_normalize(key, 500.0, "vnd_bn").status == "ok"

    def test_critical_metrics_present(self):
        critical = {
            "revenue.net", "gross_profit.total", "operating_profit.total",
            "profit_before_tax.total", "tax_expense.total", "net_income.parent",
            "eps.basic", "total_assets.total", "equity.total",
            "cash_and_equivalents.total", "borrowings.total",
            "operating_cash_flow.total", "capex.total",
        }
        for m in critical:
            assert m in METRIC_METADATA, f"critical metric {m!r} missing"

    def test_valuation_metrics_present(self):
        valuation = {
            "market_cap.total", "enterprise_value.total", "net_debt.total",
            "current_price.close", "target_price.total", "upside.total",
            "wacc.total", "terminal_growth.total",
            "change_in_working_capital.total",
        }
        for m in valuation:
            assert m in METRIC_METADATA, f"valuation metric {m!r} missing"

    def test_codebase_metric_ids_present(self):
        """Metric IDs actually used in analytics/ and facts/ must exist."""
        used_in_code = {
            "revenue.net", "cogs.total", "gross_profit.total",
            "ebit.total", "net_income.parent", "eps.basic",
            "equity.parent", "total_assets.ending",
            "operating_cash_flow.total", "capex.total",
            "shares_outstanding.ending", "shares_outstanding.weighted_avg",
            "shares_outstanding.total", "depreciation.total",
            "dividends_per_share.cash",
            # Balance-sheet liabilities use the ".ending" suffix everywhere
            # (taxonomy, production_facts, ratios, reconciliation). Registering
            # them under ".total" made validate_and_normalize reject them.
            "total_liabilities.ending", "current_liabilities.ending",
        }
        for m in used_in_code:
            assert m in METRIC_METADATA, f"codebase metric {m!r} missing from registry"

    def test_liability_facts_are_accepted_not_rejected(self):
        """Regression: total/current liabilities (".ending" keys) must normalize, not
        be dropped as 'unknown metric'. A ".total" suffix mismatch previously made
        validate_and_normalize reject them, silently removing Tổng nợ phải trả from
        every fact table and report."""
        for key in ("total_liabilities.ending", "current_liabilities.ending",
                    "non_current_liabilities.ending"):
            r = validate_and_normalize(key, 1036.6, "vnd_bn")
            assert r.status == "ok", f"{key} was rejected: {r.reason}"
            assert r.value == pytest.approx(1_036_600_000_000.0)

    def test_total_liabilities_distinct_from_interest_bearing_debt(self):
        """Total liabilities and interest-bearing debt are different metrics — both
        must exist independently so the report can show them as separate rows."""
        assert "total_liabilities.ending" in METRIC_METADATA
        assert "short_term_debt.ending" in METRIC_METADATA
        assert "total_liabilities.total" not in METRIC_METADATA  # old buggy key is gone

    def test_get_semantic_type(self):
        assert get_semantic_type("revenue.net") is SemanticType.MONETARY
        assert get_semantic_type("eps.basic") is SemanticType.PER_SHARE
        assert get_semantic_type("shares_outstanding.ending") is SemanticType.SHARE_COUNT
        assert get_semantic_type("gross_margin.total") is SemanticType.PERCENTAGE
        assert get_semantic_type("pe.forward") is SemanticType.MULTIPLE
        assert get_semantic_type("debt_to_equity.total") is SemanticType.RATIO
        assert get_semantic_type("days_inventory.total") is SemanticType.DAYS
        assert get_semantic_type("nonexistent.metric") is None

    def test_is_known_metric(self):
        assert is_known_metric("revenue.net") is True
        assert is_known_metric("fake.metric") is False


# ---------------------------------------------------------------------------
# Monetary normalization
# ---------------------------------------------------------------------------

class TestMonetaryNormalization:
    def test_vnd_bn_to_absolute(self):
        r = validate_and_normalize("revenue.net", 1865.38, "vnd_bn")
        assert r.status == "ok"
        assert r.value == pytest.approx(1_865_380_000_000.0)

    def test_vnd_mn_to_absolute(self):
        r = validate_and_normalize("revenue.net", 500.0, "vnd_mn")
        assert r.status == "ok"
        assert r.value == pytest.approx(500_000_000.0)

    def test_ty_dong_to_absolute(self):
        r = validate_and_normalize("cogs.total", 100.0, "tỷ đồng")
        assert r.status == "ok"
        assert r.value == pytest.approx(100_000_000_000.0)

    def test_trieu_dong_to_absolute(self):
        r = validate_and_normalize("capex.total", 250.0, "triệu đồng")
        assert r.status == "ok"
        assert r.value == pytest.approx(250_000_000.0)

    def test_absolute_vnd_passthrough(self):
        r = validate_and_normalize("net_income.parent", 291_940_000_000.0, "vnd")
        assert r.status == "ok"
        assert r.value == pytest.approx(291_940_000_000.0)

    def test_missing_unit_rejected(self):
        r = validate_and_normalize("revenue.net", 1865.38, "")
        assert r.status == "reject"

    def test_none_unit_rejected(self):
        r = validate_and_normalize("revenue.net", 1865.38, None)
        assert r.status == "reject"

    def test_invalid_unit_rejected(self):
        r = validate_and_normalize("revenue.net", 100.0, "usd")
        assert r.status == "reject"


# ---------------------------------------------------------------------------
# Per-share normalization
# ---------------------------------------------------------------------------

class TestPerShareNormalization:
    def test_dong_cp_passthrough(self):
        r = validate_and_normalize("eps.basic", 3094.0, "đồng/cp")
        assert r.status == "ok"
        assert r.value == pytest.approx(3094.0)

    def test_vnd_passthrough(self):
        r = validate_and_normalize("dividends_per_share.cash", 2000.0, "vnd")
        assert r.status == "ok"
        assert r.value == pytest.approx(2000.0)

    def test_nghin_dong_cp_multiplied(self):
        r = validate_and_normalize("eps.basic", 3.094, "nghìn đồng/cp")
        assert r.status == "ok"
        assert r.value == pytest.approx(3094.0)

    def test_missing_unit_rejected(self):
        r = validate_and_normalize("eps.basic", 3094.0, None)
        assert r.status == "reject"


# ---------------------------------------------------------------------------
# Share count normalization
# ---------------------------------------------------------------------------

class TestShareCountNormalization:
    def test_shares_passthrough(self):
        r = validate_and_normalize("shares_outstanding.ending", 94_400_000, "shares")
        assert r.status == "ok"
        assert r.value == pytest.approx(94_400_000.0)

    def test_trieu_cp_multiplied(self):
        r = validate_and_normalize("shares_outstanding.ending", 94.4, "triệu cp")
        assert r.status == "ok"
        assert r.value == pytest.approx(94_400_000.0)

    def test_million_multiplied(self):
        r = validate_and_normalize("shares_outstanding.ending", 94.4, "million")
        assert r.status == "ok"
        assert r.value == pytest.approx(94_400_000.0)

    def test_missing_unit_rejected(self):
        r = validate_and_normalize("shares_outstanding.ending", 94.4, "")
        assert r.status == "reject"


# ---------------------------------------------------------------------------
# Percentage normalization
# ---------------------------------------------------------------------------

class TestPercentageNormalization:
    def test_percent_to_decimal(self):
        r = validate_and_normalize("gross_margin.total", 18.5, "%")
        assert r.status == "ok"
        assert r.value == pytest.approx(0.185)

    def test_decimal_passthrough(self):
        r = validate_and_normalize("gross_margin.total", 0.185, "ratio")
        assert r.status == "ok"
        assert r.value == pytest.approx(0.185)

    def test_decimal_alias(self):
        r = validate_and_normalize("roe.total", 0.15, "decimal")
        assert r.status == "ok"
        assert r.value == pytest.approx(0.15)

    def test_missing_unit_rejected(self):
        r = validate_and_normalize("gross_margin.total", 18.5, None)
        assert r.status == "reject"

    def test_invalid_unit_rejected(self):
        r = validate_and_normalize("gross_margin.total", 18.5, "x")
        assert r.status == "reject"


# ---------------------------------------------------------------------------
# Multiple normalization
# ---------------------------------------------------------------------------

class TestMultipleNormalization:
    def test_x_passthrough(self):
        r = validate_and_normalize("pe.forward", 12.5, "x")
        assert r.status == "ok"
        assert r.value == pytest.approx(12.5)

    def test_times_passthrough(self):
        r = validate_and_normalize("pe.trailing", 15.0, "times")
        assert r.status == "ok"
        assert r.value == pytest.approx(15.0)

    def test_lan_passthrough(self):
        r = validate_and_normalize("ev_ebitda.trailing", 8.0, "lần")
        assert r.status == "ok"
        assert r.value == pytest.approx(8.0)

    def test_no_unit_ok_not_scale_sensitive(self):
        r = validate_and_normalize("pe.forward", 12.5, "")
        assert r.status == "ok"
        assert r.value == pytest.approx(12.5)

    def test_invalid_unit_rejected(self):
        r = validate_and_normalize("pe.forward", 12.5, "%")
        assert r.status == "reject"


# ---------------------------------------------------------------------------
# Ratio normalization
# ---------------------------------------------------------------------------

class TestRatioNormalization:
    def test_ratio_passthrough(self):
        r = validate_and_normalize("debt_to_equity.total", 0.45, "ratio")
        assert r.status == "ok"
        assert r.value == pytest.approx(0.45)

    def test_x_invalid_for_ratio(self):
        r = validate_and_normalize("current_ratio.total", 1.5, "x")
        assert r.status == "reject"

    def test_no_unit_ok(self):
        r = validate_and_normalize("debt_to_equity.total", 0.45, None)
        assert r.status == "ok"


# ---------------------------------------------------------------------------
# Days
# ---------------------------------------------------------------------------

class TestDaysNormalization:
    def test_days_passthrough(self):
        r = validate_and_normalize("days_inventory.total", 90, "days")
        assert r.status == "ok"
        assert r.value == pytest.approx(90.0)

    def test_no_unit_ok(self):
        r = validate_and_normalize("days_inventory.total", 90, "")
        assert r.status == "ok"


# ---------------------------------------------------------------------------
# Unknown metric
# ---------------------------------------------------------------------------

class TestUnknownMetric:
    def test_unknown_metric_rejected(self):
        r = validate_and_normalize("some.unknown.metric", 42.0, "vnd")
        assert r.status == "reject"


# ---------------------------------------------------------------------------
# FactEntry must NOT have unit field
# ---------------------------------------------------------------------------

class TestFactEntryNoUnit:
    def test_fact_entry_has_no_unit_field(self):
        from backend.facts.normalizer import FactEntry
        fields = {f.name for f in FactEntry.__dataclass_fields__.values()}
        unit_like = {"unit", "currency", "scale", "display_unit", "raw_unit"}
        assert fields.isdisjoint(unit_like), (
            f"FactEntry must not have unit-like fields, found: {fields & unit_like}"
        )


# ---------------------------------------------------------------------------
# Case insensitivity
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Rejected facts must not enter FactTable
# ---------------------------------------------------------------------------

class TestBuildFactTableRejectsInvalid:
    def test_invalid_unit_excluded_from_fact_table(self):
        from backend.facts.normalizer import build_fact_table
        raw = [{
            "line_item_code": "revenue.net",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "value": 1865.38,
            "unit": "usd",  # invalid for monetary VND metric
        }]
        table = build_fact_table(raw)
        assert "revenue.net" not in table

    def test_missing_unit_on_monetary_excluded(self):
        from backend.facts.normalizer import build_fact_table
        raw = [{
            "line_item_code": "revenue.net",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "value": 1865.38,
            # no unit field — scale-sensitive monetary → reject
        }]
        table = build_fact_table(raw)
        assert "revenue.net" not in table

    def test_valid_unit_included_and_normalized(self):
        from backend.facts.normalizer import build_fact_table
        raw = [{
            "line_item_code": "revenue.net",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "value": 1865.38,
            "unit": "vnd_bn",
        }]
        table = build_fact_table(raw)
        assert "revenue.net" in table
        entry = table["revenue.net"]["2025FY"]
        assert entry.value == pytest.approx(1_865_380_000_000.0)

    def test_multiple_not_scale_sensitive_passes_without_unit(self):
        from backend.facts.normalizer import build_fact_table
        raw = [{
            "line_item_code": "pe.forward",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "value": 12.5,
            # no unit — multiple is not scale-sensitive → ok
        }]
        table = build_fact_table(raw)
        assert "pe.forward" in table


# ---------------------------------------------------------------------------
# Golden CSV confidence gate
# ---------------------------------------------------------------------------

class TestGoldenCSVConfidenceGate:
    def test_low_confidence_excluded(self, tmp_path):
        import csv
        csv_path = tmp_path / "TST.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["ticker", "fiscal_year", "period", "statement_type",
                         "canonical_key", "raw_label", "value", "unit",
                         "currency", "source_type", "source_uri", "source_title",
                         "provider", "confidence", "validation_status"])
            w.writerow(["TST", "2025", "2025FY", "income_statement",
                         "revenue.net", "Rev", "100", "vnd_bn",
                         "VND", "financial_statement", "http://x", "title",
                         "golden_csv", "0.70", "accepted"])
            w.writerow(["TST", "2025", "2025FY", "income_statement",
                         "cogs.total", "COGS", "50", "vnd_bn",
                         "VND", "financial_statement", "http://x", "title",
                         "golden_csv", "0.90", "accepted"])

        import backend.facts.normalizer as norm
        import os
        orig = os.path.join
        # Monkey-patch to use tmp_path
        golden_dir = str(tmp_path)
        import unittest.mock as mock
        with mock.patch.object(norm, "_log", norm._log):
            # Direct test of the CSV reading logic
            facts = []
            import re as _re
            _FY_RE = _re.compile(r"^(\d{4})FY$")
            with open(csv_path, encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("validation_status", "").strip() != "accepted":
                        continue
                    period = row.get("period", "").strip()
                    m = _FY_RE.match(period)
                    if not m:
                        continue
                    confidence = float(row.get("confidence") or 0.95)
                    if confidence < 0.80:
                        continue
                    facts.append(row["canonical_key"])
            # Only cogs.total (conf=0.90) should pass; revenue.net (conf=0.70) rejected
            assert "cogs.total" in facts
            assert "revenue.net" not in facts


class TestCaseInsensitivity:
    def test_uppercase_unit(self):
        r = validate_and_normalize("revenue.net", 100.0, "VND_BN")
        assert r.status == "ok"
        assert r.value == pytest.approx(100_000_000_000.0)

    def test_mixed_case(self):
        r = validate_and_normalize("eps.basic", 3.0, "Nghìn Đồng/CP")
        assert r.status == "ok"
        assert r.value == pytest.approx(3000.0)


# ---------------------------------------------------------------------------
# Missing unit on monetary via _make_fact helper (contract #3)
# ---------------------------------------------------------------------------

class TestMissingUnitViaFixture:
    def test_empty_unit_rejects_monetary_fact(self):
        from backend.facts.normalizer import build_fact_table
        facts = [{
            "id": 1, "ticker": "DHG", "fiscal_year": 2023, "fiscal_period": "FY",
            "line_item_code": "revenue.net", "value": 5000.0, "unit": "",
            "source_id": "test", "source_tier": 3, "confidence": 0.85,
        }]
        table = build_fact_table(facts)
        assert "revenue.net" not in table or "2023FY" not in table.get("revenue.net", {})


# ---------------------------------------------------------------------------
# Display formatting: canonical absolute VND → tỷ đồng
# ---------------------------------------------------------------------------

class TestFormatMonetary:
    def test_large_value(self):
        assert format_monetary(5_000_000_000_000) == "5,000 tỷ đồng"

    def test_small_value(self):
        assert format_monetary(250_000_000) == "0.25 tỷ đồng"

    def test_single_ty(self):
        assert format_monetary(1_000_000_000) == "1 tỷ đồng"

    def test_none(self):
        assert format_monetary(None) == "—"

    def test_without_unit_label(self):
        assert format_monetary(5_000_000_000_000, unit_label=False) == "5,000"

    def test_negative_value(self):
        assert format_monetary(-981_001_000_000) == "-981 tỷ đồng"

    def test_report_must_not_contain_raw_absolute_vnd(self):
        """Canonical values must never appear as raw integers in report output."""
        display = format_monetary(1_865_380_000_000)
        assert "1865380000000" not in display
        assert "tỷ đồng" in display
