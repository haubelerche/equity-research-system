"""Unit tests for scripts/evaluate_citations.py � citation coverage gates.

All tests are purely deterministic (no DB required). DB-dependent gate 2
(source_id_exists) is patched to always return True.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Make project root importable
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.evaluate_citations import (
    _find_citation_refs,
    _find_quantitative_claims,
    _has_nearby_citation,
    evaluate_citations,
    _CITATION_WINDOW,
)


# -- helpers -------------------------------------------------------------------

def _write_report(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "report.md"
    p.write_text(content, encoding="utf-8")
    return p


def _write_citation_map(tmp_path: Path, ticker: str, citation_map: dict) -> None:
    artifacts = tmp_path / "artifacts" / "reports"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / f"{ticker}_20240101_citation.json").write_text(
        json.dumps({"citation_map": citation_map}), encoding="utf-8"
    )


# -- _find_citation_refs --------------------------------------------------------

class TestFindCitationRefs:
    def test_finds_inline_ref(self):
        text = "Doanh thu d?t 2,450 tỷ VND[^dhg_rev_2023] trong nam."
        refs = _find_citation_refs(text)
        assert len(refs) == 1
        assert refs[0][1] == "dhg_rev_2023"

    def test_ignores_definition_line(self):
        text = "[^dhg_rev_2023]: Báo cáo tài chính kiểm toán 2023.\n"
        refs = _find_citation_refs(text)
        assert refs == []

    def test_multiple_refs(self):
        text = "Revenue[^r1] and profit[^r2] are shown."
        refs = _find_citation_refs(text)
        keys = [k for _, k in refs]
        assert "r1" in keys
        assert "r2" in keys

    def test_no_refs(self):
        assert _find_citation_refs("Kh�ng c� tr�ch d?n n�o.") == []


# -- _find_quantitative_claims -------------------------------------------------

class TestFindQuantitativeClaims:
    def test_t_vnd(self):
        text = "Doanh thu 2,450 tỷ VND đạt kỷ lục."
        claims = _find_quantitative_claims(text)
        assert len(claims) == 1
        assert "2,450" in claims[0][1]

    def test_percentage(self):
        text = "Bi�n l?i nhu?n g?p tang 32.5%."
        claims = _find_quantitative_claims(text)
        assert len(claims) == 1
        assert "32.5%" in claims[0][1]

    def test_no_unit_no_match(self):
        # Bare number without VND/t?/% should NOT match
        claims = _find_quantitative_claims("S? li?u nam 2024.")
        assert claims == []

    def test_multiple_claims(self):
        text = "Revenue 1,000 tỷ VND, margin 25%, EPS 8,500 VND."
        claims = _find_quantitative_claims(text)
        assert len(claims) >= 2


# -- _has_nearby_citation ------------------------------------------------------

class TestHasNearbyCitation:
    def test_within_window(self):
        refs = [(50, "k1")]
        assert _has_nearby_citation(60, refs, _CITATION_WINDOW) is True

    def test_outside_window(self):
        refs = [(300, "k1")]
        assert _has_nearby_citation(0, refs, _CITATION_WINDOW) is False

    def test_empty_refs(self):
        assert _has_nearby_citation(10, [], _CITATION_WINDOW) is False

    def test_exactly_at_boundary(self):
        refs = [(_CITATION_WINDOW, "k1")]
        assert _has_nearby_citation(0, refs, _CITATION_WINDOW) is True


# -- evaluate_citations (integration, no DB) -----------------------------------

@pytest.fixture()
def patch_source_exists():
    """Patch _source_id_exists to always return True (no DB needed)."""
    with patch("scripts.evaluate_citations._source_id_exists", return_value=True):
        yield


@pytest.fixture()
def patch_load_citation_map(tmp_path):
    """Patch _load_citation_map to load from tmp_path."""
    def _loader(ticker: str) -> dict:
        f = tmp_path / "artifacts" / "reports" / f"{ticker}_20240101_citation.json"
        if f.exists():
            return json.loads(f.read_text())["citation_map"]
        return {}
    with patch("scripts.evaluate_citations._load_citation_map", side_effect=_loader):
        yield


class TestEvaluateCitations:
    def test_all_gates_pass(self, tmp_path, patch_source_exists, patch_load_citation_map):
        citation_map = {
            "dhg/2023fy/revenue.net": {
                "source_id": "src_dhg_2023",
                "source_title": "Báo cáo tài chính kiểm toán DHG 2023",
                "value": 2450.0,
                "unit": "vnd_bn",
            }
        }
        _write_citation_map(tmp_path, "DHG", citation_map)

        report = "Doanh thu 2,450 tỷ VND[^dhg/2023fy/revenue.net] d?t k? l?c.\n\n"
        report += "[^dhg/2023fy/revenue.net]: Báo cáo tài chính kiểm toán DHG 2023\n"
        path = _write_report(tmp_path, report)

        result = evaluate_citations("DHG", path)
        assert result["status"] == "PASS"
        assert result["export_allowed"] is True
        assert result["gates"]["citation_key_resolution"]["pass"] is True
        assert result["gates"]["quantitative_citation_coverage"]["pass"] is True

    def test_unresolved_citation_key_fails(self, tmp_path, patch_source_exists, patch_load_citation_map):
        _write_citation_map(tmp_path, "DHG", {})
        report = "Doanh thu 2,450 tỷ VND[^missing_key] tang tru?ng.\n"
        path = _write_report(tmp_path, report)

        result = evaluate_citations("DHG", path)
        assert result["status"] == "FAIL"
        assert result["export_allowed"] is False
        assert "citation_key_resolution" in result["critical_fails"]

    def test_uncited_quantitative_claim_blocks_export(self, tmp_path, patch_source_exists, patch_load_citation_map):
        citation_map = {
            "dhg/2023fy/revenue.net": {
                "source_id": "src_dhg_2023",
                "source_title": "B�o c�o ki?m to�n DHG 2023",
            }
        }
        _write_citation_map(tmp_path, "DHG", citation_map)
        # No citation tag near the number
        report = "Lợi nhuận ròng đạt 250 tỷ VND trong năm tài chính này.\n"
        path = _write_report(tmp_path, report)

        result = evaluate_citations("DHG", path)
        # Any uncited quantitative claim is critical � blocks final export
        assert result["gates"]["quantitative_citation_coverage"]["pass"] is False
        assert result["gates"]["quantitative_citation_coverage"]["critical"] is True
        assert result["export_allowed"] is False

    def test_uncited_claim_strict_same_as_default(self, tmp_path, patch_source_exists, patch_load_citation_map):
        _write_citation_map(tmp_path, "DHG", {})
        report = "Lợi nhuận 250 tỷ VND không có trích dẫn.\n"
        path = _write_report(tmp_path, report)

        result = evaluate_citations("DHG", path, strict=True)
        # Always critical when uncited claims exist
        assert result["gates"]["quantitative_citation_coverage"]["critical"] is True
        assert result["export_allowed"] is False

    def test_forbidden_label_warns(self, tmp_path, patch_source_exists, patch_load_citation_map):
        citation_map = {
            "dhg/2023fy/revenue.net": {
                "source_id": "src_dhg_2023",
                "source_title": "báo cáo tài chính (vnstock api)",  # forbidden
            }
        }
        _write_citation_map(tmp_path, "DHG", citation_map)
        report = "Doanh thu 2,450 tỷ VND[^dhg/2023fy/revenue.net].\n"
        report += "[^dhg/2023fy/revenue.net]: ngu?n vnstock\n"
        path = _write_report(tmp_path, report)

        result = evaluate_citations("DHG", path)
        assert result["gates"]["no_forbidden_labels"]["pass"] is False
        assert result["gates"]["no_forbidden_labels"]["critical"] is False  # warning only
        # Should not block export
        assert result["export_allowed"] is True

    def test_missing_report_file(self, tmp_path, patch_source_exists):
        result = evaluate_citations("DHG", tmp_path / "nonexistent.md")
        assert result["status"] == "error"
        assert result["export_allowed"] is False

    def test_empty_report_no_claims_passes(self, tmp_path, patch_source_exists, patch_load_citation_map):
        _write_citation_map(tmp_path, "DHG", {})
        path = _write_report(tmp_path, "��y l� b�o c�o kh�ng c� s? li?u t�i ch�nh c? th?.\n")
        result = evaluate_citations("DHG", path)
        # No quantitative claims means 100% coverage
        assert result["quantitative_claims"] == 0
        assert result["coverage_rate"] == 1.0
