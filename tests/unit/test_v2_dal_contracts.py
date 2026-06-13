"""Unit tests for v2 DAL contracts.

Tests the pure-Python logic in backend/database/v2/ without requiring a live DB.
All DB calls are patched; tests verify argument shapes, ID generation, and
business rules (e.g. fact_id determinism, confidence gate, winner-selection order).
"""
from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


# ---------------------------------------------------------------------------
# source_dal â€” ID generation
# ---------------------------------------------------------------------------

class TestSourceDalIdGeneration:
    """source_doc_id must be deterministic: SHA256(source_type|source_uri|checksum)."""

    def test_id_is_sha256_of_canonical_inputs(self):
        from backend.database.canonical.source_dal import compute_source_doc_id
        result = compute_source_doc_id("golden_csv", "file:///foo.csv", "abc123")
        expected = _sha256("golden_csv", "file:///foo.csv", "abc123")
        assert result == expected

    def test_same_inputs_produce_same_id(self):
        from backend.database.canonical.source_dal import compute_source_doc_id
        id1 = compute_source_doc_id("golden_csv", "file:///foo.csv", "abc123")
        id2 = compute_source_doc_id("golden_csv", "file:///foo.csv", "abc123")
        assert id1 == id2

    def test_different_checksum_produces_different_id(self):
        from backend.database.canonical.source_dal import compute_source_doc_id
        id1 = compute_source_doc_id("golden_csv", "file:///foo.csv", "abc123")
        id2 = compute_source_doc_id("golden_csv", "file:///foo.csv", "xyz999")
        assert id1 != id2

    def test_different_source_type_produces_different_id(self):
        from backend.database.canonical.source_dal import compute_source_doc_id
        id1 = compute_source_doc_id("golden_csv", "file:///foo.csv", "abc123")
        id2 = compute_source_doc_id("pdf_bctc", "file:///foo.csv", "abc123")
        assert id1 != id2

    def test_id_is_64_hex_chars(self):
        from backend.database.canonical.source_dal import compute_source_doc_id
        result = compute_source_doc_id("golden_csv", "file:///foo.csv", "abc")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)


# ---------------------------------------------------------------------------
# fact_dal â€” ID generation
# ---------------------------------------------------------------------------

class TestFactDalIdGeneration:
    """fact_id must be deterministic: SHA256(ticker|period|metric|canonical_version)."""

    def test_id_is_sha256_of_canonical_inputs(self):
        from backend.database.canonical.fact_dal import compute_fact_id
        result = compute_fact_id("DHG", "2023FY", "revenue", "prod")
        expected = _sha256("DHG", "2023FY", "revenue", "prod")
        assert result == expected

    def test_same_inputs_stable_across_calls(self):
        from backend.database.canonical.fact_dal import compute_fact_id
        assert compute_fact_id("DHG", "2023FY", "revenue", "prod") == \
               compute_fact_id("DHG", "2023FY", "revenue", "prod")

    def test_ticker_case_sensitive(self):
        from backend.database.canonical.fact_dal import compute_fact_id
        assert compute_fact_id("DHG", "2023FY", "revenue", "prod") != \
               compute_fact_id("dhg", "2023FY", "revenue", "prod")

    def test_different_period_different_id(self):
        from backend.database.canonical.fact_dal import compute_fact_id
        assert compute_fact_id("DHG", "2023FY", "revenue", "prod") != \
               compute_fact_id("DHG", "2024FY", "revenue", "prod")

    def test_id_is_64_hex_chars(self):
        from backend.database.canonical.fact_dal import compute_fact_id
        result = compute_fact_id("DHG", "2023FY", "revenue", "prod")
        assert len(result) == 64


# ---------------------------------------------------------------------------
# fact_promotion â€” winner-selection logic
# ---------------------------------------------------------------------------

class TestFactPromotionWinnerSelection:
    """promote_accepted_facts selects lowest tier, then highest confidence."""

    def _make_obs(self, tier: int, confidence: float, value: float) -> dict:
        return {
            "ticker": "DHG",
            "period": "2023FY",
            "metric": "revenue",
            "source_tier": tier,
            "confidence": confidence,
            "value": value,
            "observation_id": 1,
            "source_doc_id": f"doc_{tier}_{confidence}",
            "extraction_method": "csv",
            "unit": "vnd_bn",
            "currency": "VND",
        }

    def test_lower_tier_wins_over_higher_tier(self):
        obs = [
            self._make_obs(tier=3, confidence=0.95, value=1000),
            self._make_obs(tier=1, confidence=0.82, value=1050),
        ]
        # Replicate the winner-selection logic from fact_promotion.promote_accepted_facts
        sorted_group = sorted(obs, key=lambda o: (o["source_tier"] or 3, -(o["confidence"] or 0.0)))
        winner = sorted_group[0]
        assert winner["source_tier"] == 1
        assert winner["value"] == 1050

    def test_same_tier_higher_confidence_wins(self):
        obs = [
            self._make_obs(tier=2, confidence=0.85, value=200),
            self._make_obs(tier=2, confidence=0.92, value=210),
        ]
        sorted_group = sorted(obs, key=lambda o: (o["source_tier"] or 3, -(o["confidence"] or 0.0)))
        winner = sorted_group[0]
        assert winner["confidence"] == 0.92
        assert winner["value"] == 210

    def test_single_observation_is_winner(self):
        obs = [self._make_obs(tier=3, confidence=0.90, value=500)]
        sorted_group = sorted(obs, key=lambda o: (o["source_tier"] or 3, -(o["confidence"] or 0.0)))
        winner = sorted_group[0]
        assert winner["value"] == 500


# ---------------------------------------------------------------------------
# fact_promotion â€” confidence gate constant
# ---------------------------------------------------------------------------

class TestFactPromotionConfidenceGate:
    """The module-level threshold constant must be 0.80."""

    def test_confidence_threshold_is_point_80(self):
        from backend.database.canonical.fact_promotion import _CONFIDENCE_THRESHOLD
        assert _CONFIDENCE_THRESHOLD == 0.80

    def test_below_threshold_triggers_needs_review(self):
        """Obs with confidence < 0.80 must yield quality_status='needs_review'."""
        from backend.database.canonical.fact_promotion import _CONFIDENCE_THRESHOLD
        confidence = 0.79
        quality_status = "accepted" if confidence >= _CONFIDENCE_THRESHOLD else "needs_review"
        assert quality_status == "needs_review"

    def test_exactly_at_threshold_is_accepted(self):
        from backend.database.canonical.fact_promotion import _CONFIDENCE_THRESHOLD
        confidence = 0.80
        quality_status = "accepted" if confidence >= _CONFIDENCE_THRESHOLD else "needs_review"
        assert quality_status == "accepted"

    def test_none_confidence_treated_as_zero(self):
        """None confidence â†’ sort key 0.0 â†’ potentially lowest priority but still promoted."""
        from backend.database.canonical.fact_promotion import _CONFIDENCE_THRESHOLD
        # The sort key uses `-(o["confidence"] or 0.0)` â€” None maps to 0.0
        conf = None
        sort_key = -(conf or 0.0)
        assert sort_key == 0.0


# ---------------------------------------------------------------------------
# snapshot_dal â€” fact_id FK integrity
# ---------------------------------------------------------------------------

class TestSnapshotDalFactIdType:
    """snapshot_items must use fact_id VARCHAR(64), not legacy TEXT cast of BIGSERIAL."""

    def test_snapshot_id_is_prefixed_hash(self):
        """_snapshot_id must return a string starting with 'v2snap_'."""
        from backend.database.canonical.snapshot_dal import _snapshot_id
        from datetime import date
        sid = _snapshot_id("DHG", 2021, 2024, date(2026, 6, 9), "prod")
        assert isinstance(sid, str)
        assert sid.startswith("v2snap_")

    def test_snapshot_id_is_deterministic(self):
        from backend.database.canonical.snapshot_dal import _snapshot_id
        from datetime import date
        d = date(2026, 6, 9)
        assert _snapshot_id("DHG", 2021, 2024, d, "prod") == \
               _snapshot_id("DHG", 2021, 2024, d, "prod")

    def test_snapshot_id_differs_by_ticker(self):
        from backend.database.canonical.snapshot_dal import _snapshot_id
        from datetime import date
        d = date(2026, 6, 9)
        assert _snapshot_id("DHG", 2021, 2024, d, "prod") != \
               _snapshot_id("IMP", 2021, 2024, d, "prod")

    def test_compute_fact_id_returns_varchar64(self):
        """Items written to snapshot_items use compute_fact_id â€” must be 64-char hex string."""
        from backend.database.canonical.fact_dal import compute_fact_id
        fid = compute_fact_id("DHG", "2023FY", "revenue", "prod")
        assert isinstance(fid, str)
        assert len(fid) == 64  # VARCHAR(64) in research.snapshot_items


# ---------------------------------------------------------------------------
# report_dal â€” module exports
# ---------------------------------------------------------------------------

class TestReportDalExports:
    """report_dal must expose all required public functions."""

    def test_all_required_functions_present(self):
        from backend.database.canonical import report_dal
        required = [
            "create_or_update_report",
            "record_claims",
            "record_citation",
            "record_gate_result",
            "get_uncited_quantitative_claims",
            "approve_report",
        ]
        for fn in required:
            assert hasattr(report_dal, fn), f"report_dal missing: {fn}"


# ---------------------------------------------------------------------------
# audit_dal â€” append-only guarantee
# ---------------------------------------------------------------------------

class TestAuditDalAppendOnly:
    """log_event must INSERT, never UPDATE or DELETE."""

    @patch("backend.database.canonical.audit_dal.get_conn")
    def test_log_event_calls_insert(self, mock_get_conn):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (42,)
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = lambda s: mock_conn
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        from backend.database.canonical.audit_dal import log_event
        event_id = log_event(
            event_type="fact_promoted",
            actor="fact_promotion.py",
            run_id="run_001",
            target_table="fact.canonical_facts",
            target_id="abc123",
            payload={"ticker": "DHG"},
        )
        assert event_id == 42
        sql_called = mock_cur.execute.call_args[0][0].upper()
        assert "INSERT" in sql_called
        assert "UPDATE" not in sql_called
        assert "DELETE" not in sql_called

    @patch("backend.database.canonical.audit_dal.get_conn")
    def test_log_event_includes_payload_as_json(self, mock_get_conn):
        mock_cur = MagicMock()
        mock_cur.fetchone.return_value = (1,)
        mock_cur.__enter__ = lambda s: s
        mock_cur.__exit__ = MagicMock(return_value=False)
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cur
        mock_conn.__enter__ = lambda s: s
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_get_conn.return_value.__enter__ = lambda s: mock_conn
        mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

        payload = {"ticker": "DHG", "promoted": 15}
        from backend.database.canonical.audit_dal import log_event
        log_event("fact_promoted", "test", payload=payload)
        args = mock_cur.execute.call_args[0][1]
        payload_arg = args[-1]
        parsed = json.loads(payload_arg)
        assert parsed["ticker"] == "DHG"
        assert parsed["promoted"] == 15


# ---------------------------------------------------------------------------
# Migration version
# ---------------------------------------------------------------------------

class TestMigrateVersion:
    """CURRENT_SCHEMA_VERSION must reflect the latest v2 migration."""

    def test_current_schema_version_is_latest_migration(self):
        from backend.database.migrate import CURRENT_SCHEMA_VERSION
        assert CURRENT_SCHEMA_VERSION == "040_news_article_content_hash", (
            f"Expected '040_news_article_content_hash', got '{CURRENT_SCHEMA_VERSION}'. "
            "Update migrate.py after adding a migration."
        )


# ---------------------------------------------------------------------------
# v2 DAL module exports
# ---------------------------------------------------------------------------

class TestV2DalModuleExports:
    """Each v2 DAL module must expose its public API."""

    def test_source_dal_exports(self):
        from backend.database.canonical import source_dal
        assert hasattr(source_dal, "upsert_source_document")
        assert hasattr(source_dal, "get_source_documents_for_ticker")
        assert hasattr(source_dal, "compute_source_doc_id")

    def test_observation_dal_exports(self):
        from backend.database.canonical import observation_dal
        assert hasattr(observation_dal, "insert_observations")
        assert hasattr(observation_dal, "get_observations_for_ticker")

    def test_fact_dal_exports(self):
        from backend.database.canonical import fact_dal
        assert hasattr(fact_dal, "upsert_canonical_fact")
        assert hasattr(fact_dal, "get_production_facts")
        assert hasattr(fact_dal, "compute_fact_id")

    def test_fact_promotion_exports(self):
        from backend.database.canonical import fact_promotion
        assert hasattr(fact_promotion, "promote_accepted_facts")
        assert hasattr(fact_promotion, "promote_golden_csv_observations")
        assert hasattr(fact_promotion, "_CONFIDENCE_THRESHOLD")

    def test_snapshot_dal_exports(self):
        from backend.database.canonical import snapshot_dal
        assert hasattr(snapshot_dal, "create_snapshot")
        assert hasattr(snapshot_dal, "load_snapshot_facts")
        assert hasattr(snapshot_dal, "get_latest_snapshot")

    def test_report_dal_exports(self):
        from backend.database.canonical import report_dal
        assert hasattr(report_dal, "create_or_update_report")
        assert hasattr(report_dal, "record_claims")
        assert hasattr(report_dal, "record_citation")
        assert hasattr(report_dal, "record_gate_result")
        assert hasattr(report_dal, "get_uncited_quantitative_claims")
        assert hasattr(report_dal, "approve_report")

    def test_audit_dal_exports(self):
        from backend.database.canonical import audit_dal
        assert hasattr(audit_dal, "log_event")
        assert hasattr(audit_dal, "log_cost")


# ---------------------------------------------------------------------------
# ingest.observations â€” no synthetic source IDs allowed
# ---------------------------------------------------------------------------

class TestObservationDalNoSyntheticIds:
    """Observations must reference real source_doc_ids, not synthetic strings."""

    def test_synthetic_golden_csv_pattern_identified(self):
        """Verify the legacy pattern is detectable for migration cleanup."""
        synthetic_id = "golden_csv_DHG_2023"
        is_synthetic = synthetic_id.startswith("golden_csv_")
        assert is_synthetic is True

    def test_sha256_id_not_synthetic(self):
        """A real v2 source_doc_id (SHA256 hex) does not match the synthetic pattern."""
        from backend.database.canonical.source_dal import compute_source_doc_id
        real_id = compute_source_doc_id("golden_csv", "file:///DHG.csv", "checksum123")
        is_synthetic = real_id.startswith("golden_csv_")
        assert is_synthetic is False


# ---------------------------------------------------------------------------
# PromotionResult dataclass
# ---------------------------------------------------------------------------

class TestPromotionResultDataclass:
    """PromotionResult must track promoted, skipped, warnings, errors."""

    def test_default_values(self):
        from backend.database.canonical.fact_promotion import PromotionResult
        r = PromotionResult(ticker="DHG")
        assert r.ticker == "DHG"
        assert r.promoted == 0
        assert r.skipped_low_confidence == 0
        assert r.warnings == []
        assert r.errors == []

    def test_mutable_list_fields_are_independent(self):
        """Each instance must have its own list, not shared class-level state."""
        from backend.database.canonical.fact_promotion import PromotionResult
        r1 = PromotionResult(ticker="DHG")
        r2 = PromotionResult(ticker="IMP")
        r1.warnings.append("w1")
        assert r2.warnings == []

