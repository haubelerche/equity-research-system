"""Unit tests for backend/evaluation/citation_coverage.py"""
import pytest
from backend.evaluation.citation_coverage import (
    VAGUE_SOURCE_PATTERNS,
    is_vague_source,
    check_citation_not_vague,
    check_citation_has_required_fields,
    run_citation_coverage_gate,
)


# ── is_vague_source ───────────────────────────────────────────────────────────

class TestIsVagueSource:
    @pytest.mark.parametrize("source", [
        "API",
        "api",
        "hệ thống",
        "Hệ Thống",
        "system",
        "System",
        "DATABASE",
        "database",
        "dữ liệu thị trường",
        "market data",
        "Market Data",
        "internal",
        "nội bộ",
        "unknown",
        "N/A",
        "none",
        "",
        "   ",
    ])
    def test_vague_patterns_detected(self, source):
        assert is_vague_source(source) is True

    @pytest.mark.parametrize("source", [
        "HOSE Quarterly Report 2023",
        "DHG Annual Report 2022",
        "VPBank Research Note Q3-2023",
        "Cafef.vn 2023-11-15",
        "SSI Research — Sector Update 2023",
        "Vietstock 2023-Q4",
        "Bloomberg Terminal export 2023-12-01",
        "IMP Prospectus 2022",
    ])
    def test_specific_sources_not_vague(self, source):
        assert is_vague_source(source) is False


# ── check_citation_not_vague ──────────────────────────────────────────────────

class TestCheckCitationNotVague:
    def test_valid_citation_passes(self):
        result = check_citation_not_vague({"id": "c1", "source": "DHG Annual Report 2022"})
        assert result["passed"] is True
        assert result["reason"] is None

    def test_vague_source_fails(self):
        result = check_citation_not_vague({"id": "c1", "source": "API"})
        assert result["passed"] is False
        assert "vague" in result["reason"].lower() or "pattern" in result["reason"].lower()

    def test_empty_source_fails(self):
        result = check_citation_not_vague({"id": "c1", "source": ""})
        assert result["passed"] is False

    def test_none_source_fails(self):
        result = check_citation_not_vague({"id": "c1", "source": None})
        assert result["passed"] is False

    def test_missing_source_key_fails(self):
        result = check_citation_not_vague({"id": "c1"})
        assert result["passed"] is False

    def test_whitespace_only_fails(self):
        result = check_citation_not_vague({"id": "c1", "source": "   "})
        assert result["passed"] is False


# ── check_citation_has_required_fields ────────────────────────────────────────

class TestCheckCitationHasRequiredFields:
    def _full_citation(self):
        return {
            "id": "c1",
            "source": "DHG Annual Report 2022",
            "year": "2022",
            "page": "42",
            "claim_type": "quantitative",
        }

    def test_full_citation_passes(self):
        result = check_citation_has_required_fields(self._full_citation())
        assert result["passed"] is True
        assert result["issues"] == []

    def test_missing_year_fails(self):
        cit = self._full_citation()
        del cit["year"]
        result = check_citation_has_required_fields(cit)
        assert result["passed"] is False
        assert any("date" in issue.lower() or "year" in issue.lower() for issue in result["issues"])

    def test_date_field_satisfies_year_requirement(self):
        cit = self._full_citation()
        del cit["year"]
        cit["date"] = "2022-12-31"
        result = check_citation_has_required_fields(cit)
        assert result["passed"] is True

    def test_missing_page_and_section_fails_for_quantitative(self):
        cit = self._full_citation()
        del cit["page"]
        result = check_citation_has_required_fields(cit, required_for_quantitative=True)
        assert result["passed"] is False

    def test_section_satisfies_page_requirement(self):
        cit = self._full_citation()
        del cit["page"]
        cit["section"] = "Financial Statements"
        result = check_citation_has_required_fields(cit, required_for_quantitative=True)
        assert result["passed"] is True

    def test_chunk_id_satisfies_page_requirement(self):
        cit = self._full_citation()
        del cit["page"]
        cit["chunk_id"] = "dhg_2022_chunk_023"
        result = check_citation_has_required_fields(cit, required_for_quantitative=True)
        assert result["passed"] is True

    def test_not_required_for_quantitative_skips_page(self):
        cit = {"id": "c1", "source": "DHG Report 2022", "year": "2022"}
        result = check_citation_has_required_fields(cit, required_for_quantitative=False)
        assert result["passed"] is True

    def test_vague_source_fails_required_fields(self):
        cit = {"id": "c1", "source": "Database", "year": "2022", "page": "1"}
        result = check_citation_has_required_fields(cit)
        assert result["passed"] is False


# ── run_citation_coverage_gate ────────────────────────────────────────────────

class TestRunCitationCoverageGate:
    def _good_citation(self, cid="c1", claim_type="quantitative"):
        return {
            "id": cid,
            "source": f"DHG Annual Report 2022",
            "claim_type": claim_type,
            "year": "2022",
            "page": "42",
            "is_analyst_estimate": False,
        }

    def test_all_valid_citations_passes(self):
        citations = [self._good_citation(cid=str(i)) for i in range(5)]
        r = run_citation_coverage_gate(citations)
        assert r["passed"] is True
        assert r["status"] == "pass"
        assert r["summary"]["coverage_ratio"] == 1.0

    def test_empty_citation_map_passes(self):
        r = run_citation_coverage_gate([])
        assert r["passed"] is True
        assert r["summary"]["coverage_ratio"] == 1.0

    def test_vague_source_on_quantitative_fails(self):
        citations = [
            self._good_citation("c1"),
            {"id": "c2", "source": "API", "claim_type": "quantitative", "year": "2022"},
        ]
        r = run_citation_coverage_gate(citations)
        assert r["passed"] is False
        assert r["summary"]["vague_source_count"] == 1
        assert any("vague" in reason.lower() for reason in r["blocking_reasons"])

    def test_vague_qualitative_citation_does_not_block(self):
        citations = [
            self._good_citation("c1"),
            {"id": "c2", "source": "API", "claim_type": "qualitative", "year": "2022"},
        ]
        r = run_citation_coverage_gate(citations)
        assert r["passed"] is True

    def test_coverage_below_threshold_fails(self):
        # 1 good + 4 vague = 20% coverage < 80% threshold
        citations = [self._good_citation("c1")]
        for i in range(4):
            citations.append({
                "id": f"vague_{i}",
                "source": "System",
                "claim_type": "quantitative",
            })
        r = run_citation_coverage_gate(citations, min_coverage_ratio=0.80)
        assert r["passed"] is False
        assert r["summary"]["coverage_ratio"] < 0.80

    def test_coverage_at_threshold_passes(self):
        # 8 good + 2 vague = 80% coverage
        citations = [self._good_citation(str(i)) for i in range(8)]
        for i in range(2):
            citations.append({
                "id": f"vague_{i}",
                "source": "Database",
                "claim_type": "quantitative",
            })
        r = run_citation_coverage_gate(citations, min_coverage_ratio=0.80)
        assert r["passed"] is False  # also blocked by vague_source check

    def test_missing_fields_produces_warnings_not_blocking(self):
        # Citations with no year/page: check 3 triggers warn, not fail
        citations = [
            {"id": "c1", "source": "DHG Annual Report 2022", "claim_type": "quantitative"},
        ]
        r = run_citation_coverage_gate(citations)
        # gate passes (not vague, coverage=1.0) but has non-blocking warn issues
        assert r["passed"] is True
        warn_issues = [i for i in r["issues"] if i.get("severity") == "warn"]
        assert len(warn_issues) > 0

    def test_summary_fields_present(self):
        r = run_citation_coverage_gate([self._good_citation()])
        summary = r["summary"]
        assert "total_citations" in summary
        assert "quantitative_citations" in summary
        assert "covered" in summary
        assert "coverage_ratio" in summary
        assert "vague_source_count" in summary

    def test_only_qualitative_citations_passes(self):
        citations = [
            {"id": "c1", "source": "Market report", "claim_type": "qualitative"},
            {"id": "c2", "source": "API", "claim_type": "qualitative"},  # vague but qualitative
        ]
        r = run_citation_coverage_gate(citations)
        assert r["passed"] is True
        assert r["summary"]["quantitative_citations"] == 0

    def test_gate_name_is_correct(self):
        r = run_citation_coverage_gate([])
        assert r["gate"] == "CITATION_COVERAGE"

    def test_blocking_issues_have_correct_structure(self):
        citations = [
            {"id": "c1", "source": "API", "claim_type": "quantitative"},
        ]
        r = run_citation_coverage_gate(citations)
        assert r["passed"] is False
        for issue in r["issues"]:
            assert "issue_id" in issue
            assert "severity" in issue
            assert "message" in issue
            assert "blocking" in issue
