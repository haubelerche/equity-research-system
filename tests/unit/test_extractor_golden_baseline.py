"""Golden baseline regression test for VietnameseBCTCExtractor label → metric_id mapping.

Validates that the YAML metric dictionary correctly maps each manually verified
DHG 2021 label to its canonical metric_id. If YAML patterns change, this test
catches mapping regressions before they silently corrupt extracted facts.

Golden source: tests/fixtures/golden_facts/DHG_2021_facts.csv
Verified by: haubelerche  2026-05-30
"""
from __future__ import annotations

import csv
from pathlib import Path

import pytest

from backend.documents.pdf_extractor import _map_label_to_metric, _slug_label

_GOLDEN_CSV = (
    Path(__file__).resolve().parents[2]
    / "tests" / "fixtures" / "golden_facts" / "DHG_2021_facts.csv"
)


def _load_golden() -> list[dict]:
    with _GOLDEN_CSV.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


# ---------------------------------------------------------------------------
# Label → metric_id mapping regression
# ---------------------------------------------------------------------------

class TestGoldenLabelMapping:
    """Each canonical_label_vi in the golden CSV must map to the correct metric_id."""

    @pytest.mark.parametrize("row", _load_golden())
    def test_label_maps_to_correct_metric(self, row):
        label = row["canonical_label_vi"]
        expected = row["metric_id"]
        slug = _slug_label(label)
        result = _map_label_to_metric(slug)
        assert result == expected, (
            f"Label {label!r} (slug={slug!r}) mapped to {result!r}, "
            f"expected {expected!r}"
        )


# ---------------------------------------------------------------------------
# Golden fixture self-consistency checks
# ---------------------------------------------------------------------------

class TestGoldenFixtureConsistency:
    def test_fixture_file_exists(self):
        assert _GOLDEN_CSV.exists(), f"Golden fixture missing: {_GOLDEN_CSV}"

    def test_fixture_has_required_columns(self):
        rows = _load_golden()
        assert rows, "Golden fixture is empty"
        required = {"metric_id", "canonical_label_vi", "fiscal_year", "value", "unit", "statement_type"}
        missing = required - set(rows[0].keys())
        assert not missing, f"Golden fixture missing columns: {missing}"

    def test_all_metric_ids_are_canonical(self):
        """All metric_ids use dot-notation, not the old snake_case format."""
        rows = _load_golden()
        for row in rows:
            mid = row["metric_id"]
            assert "." in mid, (
                f"metric_id {mid!r} uses old snake_case format — should be dot-notation "
                f"(e.g. 'revenue.net' not 'revenue_net')"
            )

    def test_fiscal_year_is_2021(self):
        rows = _load_golden()
        for row in rows:
            assert row["fiscal_year"] == "2021", (
                f"Expected fiscal_year=2021, got {row['fiscal_year']!r}"
            )

    def test_values_are_numeric(self):
        rows = _load_golden()
        for row in rows:
            try:
                float(row["value"])
            except ValueError:
                pytest.fail(f"Non-numeric value in golden fixture: {row['value']!r} for {row['metric_id']}")

    def test_dhg_2021_has_eight_entries(self):
        """Exact count check — fails if entries are accidentally added or removed."""
        rows = _load_golden()
        assert len(rows) == 8, (
            f"Expected 8 golden entries for DHG 2021, got {len(rows)}. "
            f"Update this count intentionally when adding new verified facts."
        )

    def test_covers_all_three_statements(self):
        rows = _load_golden()
        statements = {row["statement_type"] for row in rows}
        assert "income_statement" in statements
        assert "balance_sheet" in statements
        assert "cash_flow" in statements
