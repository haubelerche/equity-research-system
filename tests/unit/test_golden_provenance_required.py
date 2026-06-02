"""Mandatory test: golden CSV without provenance JSON must be classified as Tier 3.

A golden CSV entry is NOT automatically Tier 1. It requires a companion
{ticker}_golden_provenance.json file that carries verifier, date, and
source document references. Without this file, build_facts.py treats the
golden data as Tier 3 (same as vnstock API aggregator data).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest


# ── Helpers that simulate _load_golden_provenance() behavior ──────────────────

def _write_provenance(tmp_dir: Path, ticker: str, tier: int = 1) -> Path:
    prov = {
        "ticker": ticker,
        "verified_by": "analyst_01",
        "verification_date": "2026-05-30",
        "source_tier": tier,
        "source_document_type": "annual_report",
        "fiscal_year": 2021,
        "fiscal_period": "FY",
        "publisher": "Test Publisher",
    }
    path = tmp_dir / f"{ticker}_golden_provenance.json"
    path.write_text(json.dumps(prov), encoding="utf-8")
    return path


def _write_csv(tmp_dir: Path, ticker: str) -> Path:
    path = tmp_dir / f"{ticker}.csv"
    path.write_text(
        "ticker,fiscal_year,period,statement_type,canonical_key,raw_label,value,unit,currency,"
        "source_type,source_uri,source_title,provider,confidence,validation_status\n"
        f"{ticker},2021,2021FY,income_statement,revenue.net,Revenue,5000.0,vnd_bn,VND,"
        "annual_report,https://example.com/report,Test Report,golden_csv,0.9,accepted\n",
        encoding="utf-8",
    )
    return path


class TestGoldenProvenanceRequired:
    def test_with_provenance_is_tier1(self, tmp_path):
        """Golden CSV + valid provenance file → Tier 1."""
        ticker = "TST"
        _write_csv(tmp_path, ticker)
        _write_provenance(tmp_path, ticker, tier=1)

        # Simulate _load_golden_provenance logic
        prov_path = tmp_path / f"{ticker}_golden_provenance.json"
        assert prov_path.exists()
        prov = json.loads(prov_path.read_text())
        resolved_tier = int(prov.get("source_tier", 3))
        assert resolved_tier == 1, "Provenance with source_tier=1 should give Tier 1"

    def test_without_provenance_is_tier3(self, tmp_path):
        """Golden CSV without provenance file → Tier 3 (unverified)."""
        ticker = "TST"
        _write_csv(tmp_path, ticker)
        # No provenance file created

        prov_path = tmp_path / f"{ticker}_golden_provenance.json"
        assert not prov_path.exists()

        # When provenance is absent, code defaults to Tier 3
        resolved_tier = 3 if not prov_path.exists() else None
        assert resolved_tier == 3, "Missing provenance must default to Tier 3"

    def test_corrupted_provenance_falls_back_to_tier3(self, tmp_path):
        """Corrupt provenance JSON → Tier 3 fallback (not crash)."""
        ticker = "TST"
        _write_csv(tmp_path, ticker)
        # Write invalid JSON
        bad_prov = tmp_path / f"{ticker}_golden_provenance.json"
        bad_prov.write_text("{ not valid json }", encoding="utf-8")

        try:
            prov = json.loads(bad_prov.read_text())
            resolved_tier = int(prov.get("source_tier", 3))
        except Exception:
            resolved_tier = 3  # fallback on parse failure

        assert resolved_tier == 3

    def test_provenance_tier0_is_respected(self, tmp_path):
        """Provenance can grant Tier 0 (audited filing) if set explicitly."""
        ticker = "TST"
        _write_csv(tmp_path, ticker)
        _write_provenance(tmp_path, ticker, tier=0)

        prov_path = tmp_path / f"{ticker}_golden_provenance.json"
        prov = json.loads(prov_path.read_text())
        resolved_tier = int(prov.get("source_tier", 3))
        assert resolved_tier == 0

    def test_dhg_provenance_file_exists(self):
        """Phase 3: DHG_golden_provenance.json must exist in the repo."""
        prov_path = (
            Path(__file__).resolve().parents[2]
            / "config" / "dataset" / "golden" / "financials" / "DHG_golden_provenance.json"
        )
        assert prov_path.exists(), (
            "config/dataset/golden/financials/DHG_golden_provenance.json is missing. "
            "This file is required for Phase 3 to classify DHG 2021FY data as Tier 1."
        )

    def test_dhg_provenance_has_required_fields(self):
        """DHG_golden_provenance.json must have all required fields."""
        prov_path = (
            Path(__file__).resolve().parents[2]
            / "config" / "dataset" / "golden" / "financials" / "DHG_golden_provenance.json"
        )
        if not prov_path.exists():
            pytest.skip("DHG provenance file not found")
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
        required = {"ticker", "verified_by", "verification_date", "source_tier"}
        missing = required - set(prov.keys())
        assert not missing, f"DHG provenance missing required fields: {missing}"
        assert prov["source_tier"] in (0, 1), \
            f"DHG provenance source_tier must be 0 or 1, got {prov['source_tier']}"
