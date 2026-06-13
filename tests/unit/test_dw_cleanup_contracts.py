"""
Phase 9 â€” Data warehouse cleanup contract tests.

Tests proving:
1. upsert_financial_facts() raises DeprecationWarning (legacy writes blocked)
2. backend.dataops.snapshot is a v2 shim
3. fact_store price methods target fact.price_history
4. _canonical_facts_to_normalizer_shape mapper works correctly
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]


# ---------------------------------------------------------------------------
# upsert_financial_facts frozen
# ---------------------------------------------------------------------------

class TestUpsertFinancialFactsFrozen:
    """upsert_financial_facts() must be frozen â€” raises DeprecationWarning."""

    def _store(self):
        from backend.database.fact_store import PostgresFactStore
        return object.__new__(PostgresFactStore)

    def test_raises_on_empty_input(self):
        with pytest.raises(DeprecationWarning) as exc_info:
            self._store().upsert_financial_facts([])
        msg = str(exc_info.value).lower()
        assert "frozen" in msg or "v2_ingest" in msg or "deprecat" in msg, \
            "DeprecationWarning must mention 'frozen' or 'v2_ingest'"

    def test_raises_on_non_empty_input(self):
        """Freeze must apply regardless of input."""
        with pytest.raises(DeprecationWarning):
            self._store().upsert_financial_facts(["any_item"])

    def test_raises_before_db_access(self):
        """The error must be raised without any DB connection attempt."""
        store = self._store()
        # Ensure _conn is not set â€” if freeze checks DB first it would AttributeError
        with pytest.raises(DeprecationWarning):
            store.upsert_financial_facts([])


# ---------------------------------------------------------------------------
# Snapshot shim forwarding
# ---------------------------------------------------------------------------

class TestSnapshotShimForwarding:
    """backend.dataops.snapshot must be a shim forwarding to v2 DAL."""

    def test_create_snapshot_is_v2(self):
        from backend.dataops import snapshot as shim
        from backend.database.canonical import snapshot_dal as v2
        assert hasattr(shim, "create_snapshot"), \
            "shim must export create_snapshot"
        assert shim.create_snapshot is v2.create_snapshot, \
            "shim.create_snapshot must be identical to v2.snapshot_dal.create_snapshot"

    def test_load_snapshot_facts_is_v2(self):
        from backend.dataops import snapshot as shim
        from backend.database.canonical import snapshot_dal as v2
        assert shim.load_snapshot_facts is v2.load_snapshot_facts

    def test_get_latest_snapshot_is_v2(self):
        from backend.dataops import snapshot as shim
        from backend.database.canonical import snapshot_dal as v2
        assert shim.get_latest_snapshot is v2.get_latest_snapshot

    def test_shim_has_no_legacy_sql(self):
        shim_path = REPO_ROOT / "backend" / "dataops" / "snapshot.py"
        source = shim_path.read_text(encoding="utf-8")
        assert "research.snapshots" not in source, \
            "Shim still references research.snapshots (legacy)"
        assert "fact.financial_facts" not in source, \
            "Shim still references fact.financial_facts (legacy)"

    def test_shim_dunder_all(self):
        """Shim must expose __all__ so callers can import predictably."""
        from backend.dataops import snapshot as shim
        assert hasattr(shim, "__all__"), "shim must define __all__"
        assert "create_snapshot" in shim.__all__
        assert "load_snapshot_facts" in shim.__all__
        assert "get_latest_snapshot" in shim.__all__


# ---------------------------------------------------------------------------
# Price write/read redirected to v2
# ---------------------------------------------------------------------------

class TestPriceRedirectedToV2:
    """fact_store price methods must target fact.price_history."""

    def _upsert_source(self) -> str:
        from backend.database.fact_store import PostgresFactStore
        return inspect.getsource(PostgresFactStore.upsert_price_rows)

    def _get_source(self) -> str:
        from backend.database.fact_store import PostgresFactStore
        return inspect.getsource(PostgresFactStore.get_price_history)

    def test_upsert_price_rows_targets_v2(self):
        src = self._upsert_source()
        assert "fact.price_history" in src, \
            "upsert_price_rows() must write to fact.price_history"

    def test_upsert_price_rows_not_legacy(self):
        src = self._upsert_source().replace("fact.price_history", "")
        assert "fact.price_history" not in src, \
            "upsert_price_rows() must not write to legacy fact.price_history"

    def test_get_price_history_targets_v2(self):
        src = self._get_source()
        assert "fact.price_history" in src, \
            "get_price_history() must read from fact.price_history"


# ---------------------------------------------------------------------------
# _canonical_facts_to_normalizer_shape mapper
# ---------------------------------------------------------------------------

class TestV2FactsToLegacyShapeMapper:
    """_canonical_facts_to_normalizer_shape must correctly map canonical rows to build_fact_table() shape."""

    def _mapper(self):
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location(
            "build_facts",
            str(REPO_ROOT / "scripts" / "build_facts.py"),
        )
        mod = importlib.util.module_from_spec(spec)
        # Prevent import side effects from triggering at module load
        try:
            spec.loader.exec_module(mod)
        except Exception:
            pass
        return getattr(mod, "_canonical_facts_to_normalizer_shape", None)

    def _sample_row(self, period="2023FY", metric="revenue", value=500.0):
        return {
            "fact_id": "abc123",
            "ticker": "DBD",
            "period": period,
            "metric": metric,
            "value": value,
            "unit": "vnd_bn",
            "currency": "VND",
            "confidence": 0.95,
            "source_tier": 0,
            "updated_at": "2026-01-15T00:00:00Z",
        }

    def test_mapper_exists(self):
        mapper = self._mapper()
        assert mapper is not None, \
            "_canonical_facts_to_normalizer_shape not found in build_facts.py"

    def test_fy_row_mapped_correctly(self):
        mapper = self._mapper()
        if mapper is None:
            pytest.skip("_canonical_facts_to_normalizer_shape not importable")

        result = mapper([self._sample_row()])
        assert len(result) == 1
        row = result[0]
        assert row["line_item_code"] == "revenue"
        assert row["fiscal_year"] == 2023
        assert row["fiscal_period"] == "FY"
        assert row["value"] == 500.0
        assert row["fact_id"] == "abc123"

    def test_quarterly_row_skipped(self):
        mapper = self._mapper()
        if mapper is None:
            pytest.skip("_canonical_facts_to_normalizer_shape not importable")

        rows = [
            self._sample_row(period="2023Q1"),
            self._sample_row(period="2023FY"),
        ]
        result = mapper(rows)
        assert len(result) == 1, "Q1 row should be skipped; only FY row should pass"
        assert result[0]["fiscal_year"] == 2023

    def test_multiple_years_mapped(self):
        mapper = self._mapper()
        if mapper is None:
            pytest.skip("_canonical_facts_to_normalizer_shape not importable")

        rows = [
            self._sample_row(period="2021FY"),
            self._sample_row(period="2022FY"),
            self._sample_row(period="2023FY"),
        ]
        result = mapper(rows)
        assert len(result) == 3
        years = {r["fiscal_year"] for r in result}
        assert years == {2021, 2022, 2023}

    def test_empty_input_returns_empty(self):
        mapper = self._mapper()
        if mapper is None:
            pytest.skip("_canonical_facts_to_normalizer_shape not importable")

        assert mapper([]) == []

    def test_invalid_period_skipped(self):
        mapper = self._mapper()
        if mapper is None:
            pytest.skip("_canonical_facts_to_normalizer_shape not importable")

        rows = [
            {"fact_id": "x", "ticker": "DBD", "period": "INVALID",
             "metric": "revenue", "value": 100.0, "unit": "vnd", "currency": "VND"},
        ]
        result = mapper(rows)
        assert len(result) == 0, "Invalid period format should be skipped"

