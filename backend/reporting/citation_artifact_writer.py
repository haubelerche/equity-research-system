from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


def build_citation_artifact(
    *,
    ticker: str,
    snapshot_id: str,
    generated_at: datetime,
    report_path: Path,
    forecast_path: Path,
    fcff_path: Path,
    fcfe_path: Path,
    blend_path: Path,
    report_type: str,
    mode: str,
    export_blocked: bool,
    source_tier_gate: dict[str, Any],
    citation_map: dict[str, Any],
    claims_used: list[tuple[str, int, str]],
    evidence_chunks_used: int,
    facts_in_snapshot: int,
    draft_rating: str,
    fcff_upside_pct: float | None,
    dcf_upside_pct: float | None,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "snapshot_id": snapshot_id,
        "generated_at": generated_at.isoformat(),
        "report_path": str(report_path),
        "forecast_path": str(forecast_path),
        "fcff_path": str(fcff_path),
        "fcfe_path": str(fcfe_path),
        "blend_path": str(blend_path),
        "report_type": report_type,
        "mode": mode,
        "export_blocked": export_blocked,
        "source_tier_gate": source_tier_gate,
        "citation_map": citation_map,
        "claims": [{"ticker": t, "year": y, "metric": m} for t, y, m in claims_used],
        "evidence_chunks_used": evidence_chunks_used,
        "facts_in_snapshot": facts_in_snapshot,
        "draft_rating": draft_rating,
        "fcff_upside_pct": fcff_upside_pct,
        "dcf_upside_pct": dcf_upside_pct,
    }


def write_citation_artifact(
    *,
    artifact: dict[str, Any],
    output_dir: Path,
    ticker: str,
    timestamp: str,
    report_type: str,
    mode: str,
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{ticker}_{timestamp}_{report_type}_{mode}_citation.json"
    artifact["citation_path"] = str(path)
    path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    return path


def write_final_citation_artifacts(
    *,
    ticker: str,
    citation_artifact: dict[str, Any],
    claims_used: list[tuple[str, int, str]],
    citation_map: dict[str, Any],
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{ticker}_final_citation_map.json").write_text(
        json.dumps(citation_artifact, indent=2, default=str),
        encoding="utf-8",
    )

    quant_keys = [key for key, record in citation_map.items() if not record.get("is_derived", False)]
    with_official = [
        key for key in quant_keys
        if citation_map[key].get("official_document_id") is not None
    ]
    tier3_only = [
        key for key in quant_keys
        if citation_map[key].get("official_document_id") is None
        and (citation_map[key].get("source_tier") is None or citation_map[key].get("source_tier") >= 3)
    ]
    gate = citation_artifact["source_tier_gate"]
    audit = [
        f"# {ticker} Final Citation Audit (Phase 6)",
        "",
        f"- Generated: {citation_artifact['generated_at']}",
        "- Mode: final",
        f"- Total quantitative claims: {len(quant_keys)}",
        f"- Quantitative claims with official source: {len(with_official)}",
        f"- Quantitative claims with Tier 3 only: {len(tier3_only)}",
        "- Catalyst claims: (see catalyst section) ",
        f"- **Final export decision: {gate['export_decision']}**",
        "",
        "## Blocking reasons (first 25)",
        "",
    ]
    audit += [f"- {reason}" for reason in gate["blocking_reasons"][:25]] or ["- (none)"]
    (output_dir / f"{ticker}_final_citation_audit.md").write_text(
        "\n".join(audit),
        encoding="utf-8",
    )
