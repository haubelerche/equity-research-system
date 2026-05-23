"""Phase 3 gate invariant tests."""
import pytest
from datetime import UTC, datetime
from backend.facts.normalizer import build_validation_status_table, FactTable
from backend.facts.completeness import build_fy_validation_report


def test_build_validation_status_table_import():
    """Smoke: function exists and is importable."""
    assert callable(build_validation_status_table)


REQUIRED_PERIODS = ["2021FY", "2022FY", "2023FY", "2024FY", "2025FY"]
CORE_KEYS = [
    "revenue.net",
    "net_income.parent",
    "total_assets.ending",
    "equity.parent",
    "operating_cash_flow.total",
]


def _make_full_table(status: str = "accepted") -> tuple[FactTable, dict]:
    """Return (fact_table, validation_status_table) fully populated for 2021-2025FY."""
    table: FactTable = {key: {p: 1000.0 for p in REQUIRED_PERIODS} for key in CORE_KEYS}
    vstatus = {key: {p: status for p in REQUIRED_PERIODS} for key in CORE_KEYS}
    return table, vstatus


def _call_report(table: FactTable, vstatus: dict, periods_available=None, periods_missing=None):
    if periods_available is None:
        periods_available = list(REQUIRED_PERIODS)
    if periods_missing is None:
        periods_missing = []
    return build_fy_validation_report(
        ticker="DHG",
        table=table,
        raw_facts=[],
        required_periods=REQUIRED_PERIODS,
        periods_available=periods_available,
        periods_missing=periods_missing,
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=vstatus,
    )


def test_all_accepted_passes_all_gates():
    table, vstatus = _make_full_table("accepted")
    report = _call_report(table, vstatus)
    assert report["coverage_gate"] == "pass"
    assert report["core_keys_gate"] == "pass"
    assert report["source_validation_gate"] == "pass"
    assert report["valuation_gate"] == "pass"
    assert report["valuation_ready"] is True
    assert report["run_status"] == "ok"
    assert report["annual_reports_collected"] == 5


def test_needs_review_blocks_valuation_gate():
    table, vstatus = _make_full_table("needs_review")
    report = _call_report(table, vstatus)
    assert report["coverage_gate"] == "pass"
    assert report["core_keys_gate"] == "pass"
    assert report["source_validation_gate"] == "fail"
    assert report["valuation_gate"] == "fail"
    assert report["valuation_ready"] is False
    assert report["run_status"] == "needs_human_verification"
    assert len(report["blocking_reasons"]) > 0


def test_three_periods_passes_coverage_gate():
    """>=3 periods is sufficient — does not require all 5."""
    table = {key: {p: 1000.0 for p in ["2022FY", "2023FY", "2024FY"]} for key in CORE_KEYS}
    vstatus = {key: {p: "accepted" for p in ["2022FY", "2023FY", "2024FY"]} for key in CORE_KEYS}
    report = build_fy_validation_report(
        ticker="DHG",
        table=table,
        raw_facts=[],
        required_periods=REQUIRED_PERIODS,
        periods_available=["2022FY", "2023FY", "2024FY"],
        periods_missing=["2021FY", "2025FY"],
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=vstatus,
    )
    assert report["coverage_gate"] == "pass"
    assert report["annual_reports_collected"] == 3


def test_two_periods_fails_coverage_gate():
    """< 3 periods fails coverage gate."""
    table = {key: {p: 1000.0 for p in ["2023FY", "2024FY"]} for key in CORE_KEYS}
    vstatus = {key: {p: "accepted" for p in ["2023FY", "2024FY"]} for key in CORE_KEYS}
    report = build_fy_validation_report(
        ticker="DHG",
        table=table,
        raw_facts=[],
        required_periods=REQUIRED_PERIODS,
        periods_available=["2023FY", "2024FY"],
        periods_missing=["2021FY", "2022FY", "2025FY"],
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=vstatus,
    )
    assert report["coverage_gate"] == "fail"
    assert report["valuation_ready"] is False
    assert report["annual_reports_collected"] == 2


def test_missing_core_key_blocks_core_keys_gate():
    table = {key: {p: 1000.0 for p in REQUIRED_PERIODS} for key in CORE_KEYS}
    del table["revenue.net"]
    vstatus = {key: {p: "accepted" for p in REQUIRED_PERIODS} for key in CORE_KEYS if key != "revenue.net"}
    report = _call_report(table, vstatus)
    assert report["core_keys_gate"] == "fail"
    assert report["valuation_gate"] == "fail"
    assert report["valuation_ready"] is False


def test_no_validation_status_table_blocks_source_gate():
    """When no validation_status_table is passed, source_validation_gate must fail."""
    table, _ = _make_full_table("accepted")
    report = build_fy_validation_report(
        ticker="DHG",
        table=table,
        raw_facts=[],
        required_periods=REQUIRED_PERIODS,
        periods_available=list(REQUIRED_PERIODS),
        periods_missing=[],
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=None,
    )
    assert report["source_validation_gate"] == "fail"
    assert report["valuation_ready"] is False


def test_mixed_status_one_needs_review_blocks():
    """If even one core key/period is needs_review, source_validation_gate fails."""
    table, vstatus = _make_full_table("accepted")
    vstatus["revenue.net"]["2021FY"] = "needs_review"
    report = _call_report(table, vstatus)
    assert report["source_validation_gate"] == "fail"
    assert report["valuation_ready"] is False
    reasons = " ".join(report["blocking_reasons"])
    assert "revenue.net" in reasons
    assert "2021FY" in reasons


from scripts.build_facts import _filter_facts, _is_allowed_fy


def test_is_allowed_fy_accepts_valid_periods():
    assert _is_allowed_fy("2021FY", 2021, 2025) is True
    assert _is_allowed_fy("2025FY", 2021, 2025) is True
    assert _is_allowed_fy("2023FY", 2021, 2025) is True


def test_is_allowed_fy_rejects_quarterly():
    assert _is_allowed_fy("2023Q1", 2021, 2025) is False
    assert _is_allowed_fy("2024Q4", 2021, 2025) is False
    assert _is_allowed_fy("2026Q1", 2021, 2025) is False


def test_is_allowed_fy_rejects_out_of_range():
    assert _is_allowed_fy("2020FY", 2021, 2025) is False
    assert _is_allowed_fy("2026FY", 2021, 2025) is False


def _make_raw_fact(taxonomy_key: str, fiscal_year: int, fiscal_period: str) -> dict:
    return {
        "taxonomy_key": taxonomy_key,
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "value": 1000.0,
        "confidence": 0.9,
        "validation_status": "accepted",
        "ingested_at": "2026-01-01T00:00:00+00:00",
    }


def test_filter_facts_keeps_fy_only():
    raw = [
        _make_raw_fact("revenue.net", 2022, "FY"),
        _make_raw_fact("revenue.net", 2022, "Q1"),
        _make_raw_fact("revenue.net", 2026, "Q1"),
        _make_raw_fact("revenue.net", 2020, "FY"),  # out of range
    ]
    kept, forbidden = _filter_facts(raw, 2021, 2025)
    assert len(kept) == 1
    assert kept[0]["fiscal_period"] == "FY"
    assert "2022Q1" in forbidden
    assert "2026Q1" in forbidden
    assert "2020FY" in forbidden


def test_filter_facts_2026q1_is_forbidden():
    raw = [_make_raw_fact("revenue.net", 2026, "Q1")]
    kept, forbidden = _filter_facts(raw, 2021, 2025)
    assert kept == []
    assert "2026Q1" in forbidden


def test_filter_facts_empty_input():
    kept, forbidden = _filter_facts([], 2021, 2025)
    assert kept == []
    assert forbidden == []
