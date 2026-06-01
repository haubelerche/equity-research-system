"""Writes 5 per-run artifact files per GOAL_OUTPUT.md schema.

Artifacts produced per run:
  artifacts/claim_ledgers/{run_id}_{ticker}_claim_ledger.json
  artifacts/source_manifests/{run_id}_{ticker}_source_manifest.json
  artifacts/valuation_results/{run_id}_{ticker}_valuation_result.json
  artifacts/eval_results/{run_id}_{ticker}_eval_result.json
  artifacts/run_logs/{run_id}_{ticker}_run_log.json
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTC = timezone.utc


# ---------------------------------------------------------------------------
# Data container
# ---------------------------------------------------------------------------

@dataclass
class RunArtifacts:
    run_id: str
    ticker: str
    report_date: str          # "2026-06-01"
    data_cutoff: str          # "2025-12-31"
    rating: str
    current_price: float
    target_price: float
    upside_pct: float         # e.g. 45.1 (not 0.451)
    wacc: float               # e.g. 0.10
    terminal_growth: float    # e.g. 0.02
    equity_value: float
    shares_outstanding: float
    implied_price: float
    gate_results: list[dict]  # list of {name, status, issues}
    claims: list[dict]        # citation records
    sources: list[dict]       # source records
    fcff_rows: list[dict]
    sensitivity: dict
    scenarios: dict
    assumptions: list[dict]
    report_status: str        # "DRAFT" | "NEEDS_REVIEW" etc.

    # Optional DCF components
    pv_fcff: float = 0.0
    terminal_value: float = 0.0
    pv_terminal_value: float = 0.0
    enterprise_value: float = 0.0
    cash_and_equivalents: float = 0.0
    debt: float = 0.0
    minority_interest: float = 0.0
    multiples: dict = field(default_factory=dict)
    generated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


# ---------------------------------------------------------------------------
# Gate name → slot mapping
# ---------------------------------------------------------------------------

_GATE_KEYWORDS: list[tuple[str, str]] = [
    ("source", "source_gate"),
    ("numeric", "numeric_consistency_gate"),
    ("valuation_repro", "valuation_reproducibility_gate"),
    ("reproducibility", "valuation_reproducibility_gate"),
    ("citation", "citation_gate"),
    ("risk", "risk_language_gate"),
    ("assumption", "human_assumption_approval"),
    ("final_review", "human_final_review"),
    ("human_final", "human_final_review"),
]

_ALL_GATE_SLOTS = [
    "source_gate",
    "numeric_consistency_gate",
    "valuation_reproducibility_gate",
    "citation_gate",
    "risk_language_gate",
    "human_assumption_approval",
    "human_final_review",
]


def _map_gate(name: str) -> str | None:
    """Map a gate result name to its canonical slot key."""
    lower = name.lower()
    for keyword, slot in _GATE_KEYWORDS:
        if keyword in lower:
            return slot
    return None


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

class ArtifactWriter:
    def __init__(self, base_dir: Path | str = "artifacts") -> None:
        self.base = Path(base_dir)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _dir(self, name: str) -> Path:
        """Return (and create) self.base / name."""
        p = self.base / name
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _fname(self, arts: RunArtifacts, kind: str) -> Path:
        """Return the target path for a given artifact kind directory.

        kind examples: "claim_ledgers", "source_manifests", …
        The filename suffix is the singular form (drop trailing 's').
        """
        # Strip trailing 's' to get singular: "claim_ledgers" → "claim_ledger"
        suffix = kind.rstrip("s") if kind.endswith("s") else kind
        return self._dir(kind) / f"{arts.run_id}_{arts.ticker}_{suffix}.json"

    @staticmethod
    def _dump(path: Path, obj: Any) -> None:
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

    # ------------------------------------------------------------------
    # 1. Claim ledger
    # ------------------------------------------------------------------

    def write_claim_ledger(self, arts: RunArtifacts) -> Path:
        path = self._fname(arts, "claim_ledgers")

        enriched: list[dict] = []
        for i, raw in enumerate(arts.claims, start=1):
            entry: dict = {
                "claim_id": f"CLM-{i:03d}",
                "run_id": arts.run_id,
                "section": raw.get("section", ""),
                "page": raw.get("page", 0),
                "claim_text": raw.get("claim_text", ""),
                "claim_type": raw.get("claim_type", "quantitative"),
                "ticker": arts.ticker,
                "period": raw.get("period", ""),
                "metric": raw.get("metric", ""),
                "value": raw.get("value", None),
                "unit": raw.get("unit", ""),
                "source_refs": raw.get("source_refs", []),
                "artifact_refs": raw.get("artifact_refs", []),
                "support_status": raw.get("support_status", "supported"),
                "confidence": raw.get("confidence", 0.8),
                "review_status": raw.get("review_status", "pending"),
            }
            enriched.append(entry)

        doc = {
            "run_id": arts.run_id,
            "ticker": arts.ticker,
            "generated_at": arts.generated_at,
            "claims": enriched,
        }
        self._dump(path, doc)
        return path

    # ------------------------------------------------------------------
    # 2. Source manifest
    # ------------------------------------------------------------------

    def write_source_manifest(self, arts: RunArtifacts) -> Path:
        path = self._fname(arts, "source_manifests")

        enriched: list[dict] = []
        for i, raw in enumerate(arts.sources, start=1):
            entry: dict = {
                "source_id": f"SRC-{i:03d}",
                "run_id": arts.run_id,
                "ticker": arts.ticker,
                "source_type": raw.get("source_type", ""),
                "source_name": raw.get("source_name", raw.get("title", "")),
                "publisher": raw.get("publisher", ""),
                "published_date": raw.get("published_date", ""),
                "retrieval_timestamp": raw.get(
                    "retrieval_timestamp", arts.generated_at
                ),
                "period": raw.get("period", ""),
                "url_or_path": raw.get("url_or_path", raw.get("url", "")),
                "reliability_tier": raw.get("reliability_tier", "third_party_data"),
                "checksum": raw.get("checksum", ""),
                "parser_version": raw.get("parser_version", "v1.0"),
                "used_sections": raw.get("used_sections", []),
            }
            enriched.append(entry)

        doc = {
            "run_id": arts.run_id,
            "ticker": arts.ticker,
            "generated_at": arts.generated_at,
            "sources": enriched,
        }
        self._dump(path, doc)
        return path

    # ------------------------------------------------------------------
    # 3. Valuation result
    # ------------------------------------------------------------------

    def write_valuation_result(self, arts: RunArtifacts) -> Path:
        path = self._fname(arts, "valuation_results")

        fcff_dcf: dict = {
            "wacc": arts.wacc,
            "terminal_growth": arts.terminal_growth,
            "pv_fcff": arts.pv_fcff,
            "terminal_value": arts.terminal_value,
            "pv_terminal_value": arts.pv_terminal_value,
            "enterprise_value": arts.enterprise_value,
            "cash_and_equivalents": arts.cash_and_equivalents,
            "debt": arts.debt,
            "minority_interest": arts.minority_interest,
            "equity_value": arts.equity_value,
            "shares_outstanding": arts.shares_outstanding,
            "implied_price": arts.implied_price,
        }

        repro_hash = (
            "sha256:"
            + hashlib.sha256(
                json.dumps(fcff_dcf, sort_keys=True).encode()
            ).hexdigest()
        )

        doc: dict = {
            "run_id": arts.run_id,
            "ticker": arts.ticker,
            "valuation_date": arts.report_date,
            "currency": "VND",
            "base_year": arts.data_cutoff[:4],
            "current_price": arts.current_price,
            "target_price": arts.target_price,
            "upside_downside": round(arts.upside_pct / 100, 6),
            "rating_model_output": arts.rating,
            "fcff_dcf": fcff_dcf,
            "multiples": arts.multiples,
            "sensitivity": arts.sensitivity,
            "scenarios": arts.scenarios,
            "assumptions": arts.assumptions,
            "reproducibility_hash": repro_hash,
        }
        self._dump(path, doc)
        return path

    # ------------------------------------------------------------------
    # 4. Eval result
    # ------------------------------------------------------------------

    def write_eval_result(self, arts: RunArtifacts) -> Path:
        path = self._fname(arts, "eval_results")

        # Build gate slots — start all as pending
        gates: dict[str, dict] = {slot: {"status": "pending"} for slot in _ALL_GATE_SLOTS}

        n_pass = n_fail = n_warn = 0
        for gr in arts.gate_results:
            slot = _map_gate(gr.get("name", ""))
            status = gr.get("status", "pending").lower()
            if slot:
                gates[slot] = {
                    "status": status,
                    "issues": gr.get("issues", []),
                }
            if status == "pass":
                n_pass += 1
            elif status == "fail":
                n_fail += 1
            elif status == "warn":
                n_warn += 1

        if n_fail > 0:
            overall = "CRITICAL_FAIL"
        elif n_warn > 0:
            overall = "WARN_NEEDS_REVIEW"
        else:
            overall = "PASS"

        doc: dict = {
            "run_id": arts.run_id,
            "ticker": arts.ticker,
            "evaluated_at": arts.generated_at,
            "report_status": arts.report_status,
            "overall_status": overall,
            "gates": gates,
            "n_pass": n_pass,
            "n_fail": n_fail,
            "n_warn": n_warn,
            "export_blocked": n_fail > 0,
            "generated_at": arts.generated_at,
        }
        self._dump(path, doc)
        return path

    # ------------------------------------------------------------------
    # 5. Run log
    # ------------------------------------------------------------------

    def write_run_log(
        self,
        arts: RunArtifacts,
        stages: list[dict] | None = None,
    ) -> Path:
        path = self._fname(arts, "run_logs")

        if stages is None:
            stages = [
                {"stage": "data_ingestion", "status": "done"},
                {"stage": "canonical_facts", "status": "done"},
                {"stage": "valuation", "status": "done"},
                {"stage": "report_generation", "status": "done"},
                {"stage": "evaluation", "status": arts.report_status.lower()},
            ]

        # Build artifact filename references (just the filename, not full path)
        def _basename(kind: str) -> str:
            suffix = kind.rstrip("s") if kind.endswith("s") else kind
            return f"{arts.run_id}_{arts.ticker}_{suffix}.json"

        doc: dict = {
            "run_id": arts.run_id,
            "ticker": arts.ticker,
            "run_type": "full_report",
            "status": arts.report_status,
            "created_at": arts.generated_at,
            "updated_at": arts.generated_at,
            "stages": stages,
            "errors": [],
            "artifacts": {
                "claim_ledger": _basename("claim_ledgers"),
                "source_manifest": _basename("source_manifests"),
                "valuation_result": _basename("valuation_results"),
                "eval_result": _basename("eval_results"),
            },
        }
        self._dump(path, doc)
        return path

    # ------------------------------------------------------------------
    # write_all
    # ------------------------------------------------------------------

    def write_all(self, arts: RunArtifacts) -> dict[str, Path]:
        """Write all 5 artifacts and return a dict of {key: Path}."""
        return {
            "claim_ledger": self.write_claim_ledger(arts),
            "source_manifest": self.write_source_manifest(arts),
            "valuation_result": self.write_valuation_result(arts),
            "eval_result": self.write_eval_result(arts),
            "run_log": self.write_run_log(arts),
        }
