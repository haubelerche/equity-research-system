"""Typed contract for the valuation input pack MVP."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from backend.facts.normalizer import FactTable


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def serialize_fact_table(fact_table: FactTable) -> dict[str, dict[str, dict[str, Any]]]:
    """Serialize FactTable into JSON-safe reported facts."""
    serialized: dict[str, dict[str, dict[str, Any]]] = {}
    for metric, periods in sorted(fact_table.items()):
        metric_rows: dict[str, dict[str, Any]] = {}
        for period, entry in sorted(periods.items()):
            if isinstance(entry, dict):
                value = entry.get("value")
                fact_id = entry.get("fact_id") or entry.get("id")
                source_id = entry.get("source_id")
                source_uri = entry.get("source_uri") or entry.get("src_uri") or ""
                source_title = entry.get("source_title") or entry.get("src_title") or ""
                source_tier = entry.get("source_tier")
                confidence = entry.get("confidence")
                connector_version = entry.get("connector_version") or ""
                ingested_at = entry.get("ingested_at")
            else:
                value = getattr(entry, "value", None)
                fact_id = getattr(entry, "fact_id", None)
                source_id = getattr(entry, "source_id", None)
                source_uri = getattr(entry, "source_uri", "")
                source_title = getattr(entry, "source_title", "")
                source_tier = getattr(entry, "source_tier", None)
                confidence = getattr(entry, "confidence", None)
                connector_version = getattr(entry, "connector_version", "")
                ingested_at = getattr(entry, "ingested_at", None)
            metric_rows[period] = {
                "value": value,
                "fact_id": fact_id,
                "source_id": source_id,
                "source_uri": source_uri,
                "source_title": source_title,
                "source_tier": source_tier,
                "confidence": confidence,
                "connector_version": connector_version,
                "ingested_at": _json_value(ingested_at),
            }
        serialized[metric] = metric_rows
    return serialized


@dataclass
class ValuationInputPack:
    ticker: str
    run_id: str
    as_of_date: str
    periods: list[str]
    facts: dict[str, dict[str, dict[str, Any]]]
    market: dict[str, Any] = field(default_factory=dict)
    peers: dict[str, Any] = field(default_factory=dict)
    debt_policy: dict[str, Any] = field(default_factory=dict)
    corporate_actions: dict[str, Any] = field(default_factory=dict)
    tax_policy: dict[str, Any] = field(default_factory=dict)
    wacc_assumptions: dict[str, Any] = field(default_factory=dict)
    working_capital_policy: dict[str, Any] = field(default_factory=dict)
    readiness: dict[str, Any] = field(default_factory=dict)
    source_warnings: list[str] = field(default_factory=list)
    schema_version: str = "1.0"

    @property
    def has_peer_dataset(self) -> bool:
        return bool(
            self.peers.get("peer_group")
            and (
                self.peers.get("peer_pe_median") is not None
                or self.peers.get("peer_ev_ebitda_median") is not None
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "ticker": self.ticker,
            "run_id": self.run_id,
            "as_of_date": self.as_of_date,
            "periods": self.periods,
            "facts": self.facts,
            "market": self.market,
            "peers": self.peers,
            "debt_policy": self.debt_policy,
            "corporate_actions": self.corporate_actions,
            "tax_policy": self.tax_policy,
            "wacc_assumptions": self.wacc_assumptions,
            "working_capital_policy": self.working_capital_policy,
            "readiness": self.readiness,
            "source_warnings": self.source_warnings,
        }


def as_of_date_str(value: date | str) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)
