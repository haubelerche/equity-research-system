from __future__ import annotations

import json
from datetime import UTC, datetime

from backend.reporting.citation_artifact_writer import (
    build_citation_artifact,
    write_citation_artifact,
    write_final_citation_artifacts,
)


def test_citation_artifact_writer_preserves_generate_report_contract(tmp_path) -> None:
    generated_at = datetime(2026, 6, 1, tzinfo=UTC)
    cmap = {
        "DHG/2025FY/revenue.net": {
            "source_tier": 1,
            "official_document_id": "doc_001",
        },
        "DHG/2025FY/net_income.parent": {
            "source_tier": 3,
            "official_document_id": None,
        },
    }
    gate = {"export_decision": "BLOCKED", "blocking_reasons": ["tier3_only_material_fact"]}
    artifact = build_citation_artifact(
        ticker="DHG",
        snapshot_id="snap_001",
        generated_at=generated_at,
        report_path=tmp_path / "report.md",
        forecast_path=tmp_path / "forecast.json",
        fcff_path=tmp_path / "fcff.json",
        fcfe_path=tmp_path / "fcfe.json",
        blend_path=tmp_path / "blend.json",
        report_type="full_report",
        mode="final",
        export_blocked=True,
        source_tier_gate=gate,
        citation_map=cmap,
        claims_used=[("DHG", 2025, "revenue.net")],
        evidence_chunks_used=4,
        facts_in_snapshot=12,
        draft_rating="UNDER_REVIEW",
        fcff_upside_pct=None,
        dcf_upside_pct=None,
    )

    path = write_citation_artifact(
        artifact=artifact,
        output_dir=tmp_path,
        ticker="DHG",
        timestamp="20260601T000000",
        report_type="full_report",
        mode="final",
    )
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["ticker"] == "DHG"
    assert written["citation_path"] == str(path)
    assert written["claims"] == [{"ticker": "DHG", "year": 2025, "metric": "revenue.net"}]

    write_final_citation_artifacts(
        ticker="DHG",
        citation_artifact=written,
        claims_used=[("DHG", 2025, "revenue.net")],
        citation_map=cmap,
        output_dir=tmp_path,
    )
    assert (tmp_path / "DHG_final_citation_map.json").exists()
    audit = (tmp_path / "DHG_final_citation_audit.md").read_text(encoding="utf-8")
    assert "Final export decision: BLOCKED" in audit
    assert "Quantitative claims with official source: 1" in audit
