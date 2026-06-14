"""Build ValuationInputPack from snapshot/production facts and manual packs."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from backend.facts.normalizer import FactEntry, FactTable
from backend.valuation.data_status import build_module_readiness
from backend.valuation.input_contract import ValuationInputPack, as_of_date_str, serialize_fact_table
from backend.valuation.manual_packs import DEFAULT_MANUAL_DIR, load_manual_packs


def _period_parts(period: str) -> tuple[int, str]:
    if period.endswith("FY"):
        return int(period[:4]), "FY"
    if "Q" in period:
        year, quarter = period.split("Q", 1)
        return int(year), f"Q{quarter}"
    return int(period[:4]), "FY"


def _load_fact_table_from_snapshot(snapshot_id: str) -> FactTable:
    from backend.dataops.snapshot import load_snapshot_facts
    from backend.facts.normalizer import build_fact_table, compute_derived, to_analytics_vnd_bn

    raw_facts = load_snapshot_facts(snapshot_id)
    return compute_derived(to_analytics_vnd_bn(build_fact_table(raw_facts)))


def _load_fact_table_from_production(ticker: str, from_year: int | None, to_year: int | None) -> FactTable:
    from backend.database.canonical.fact_dal import get_production_facts
    from backend.facts.normalizer import build_fact_table, compute_derived, to_analytics_vnd_bn

    rows = []
    for fact in get_production_facts(ticker=ticker, from_year=from_year, to_year=to_year):
        fiscal_year, fiscal_period = _period_parts(str(fact["period"]))
        rows.append({
            "id": fact.get("fact_id"),
            "line_item_code": fact["metric"],
            "fiscal_year": fiscal_year,
            "fiscal_period": fiscal_period,
            "value": fact["value"],
            "unit": fact.get("unit"),
            "source_id": fact.get("source_doc_id"),
            "source_uri": fact.get("source_uri"),
            "source_title": fact.get("source_title"),
            "source_tier": fact.get("source_tier"),
            "confidence": fact.get("confidence"),
            "connector_version": fact.get("ingestion_version"),
            "ingested_at": fact.get("updated_at"),
        })
    return compute_derived(to_analytics_vnd_bn(build_fact_table(rows)))


def _periods_from_fact_table(fact_table: FactTable, periods: list[str] | None) -> list[str]:
    if periods:
        return sorted(periods)
    return sorted(p for vals in fact_table.values() for p in vals if p.endswith("FY"))


def _latest_fact_value(fact_table: FactTable, metrics: tuple[str, ...], periods: list[str]) -> float | None:
    for period in reversed(periods):
        for metric in metrics:
            entry = fact_table.get(metric, {}).get(period)
            if entry is None:
                continue
            value = getattr(entry, "value", None)
            if value is None and isinstance(entry, dict):
                value = entry.get("value")
            if value is not None:
                return float(value)
    return None


def apply_market_inputs_to_fact_table(
    *,
    fact_table: FactTable,
    input_pack: ValuationInputPack,
    latest_period: str | None,
) -> None:
    """Inject accepted manual market facts that valuation engines expect as facts."""
    if not latest_period:
        return
    shares = input_pack.market.get("shares_outstanding")
    if shares is not None and shares > 0:
        fact_table.setdefault("shares_outstanding.ending", {})[latest_period] = FactEntry(
            value=float(shares),
            source_id="manual:shares_outstanding",
            source_title="data/manual/shares_outstanding.csv",
            source_tier=1,
            confidence=0.95,
            connector_version="manual_pack_v1",
        )


def build_valuation_input_pack(
    *,
    ticker: str,
    run_id: str,
    as_of_date: date | str,
    periods: list[str] | None = None,
    fact_table: FactTable | None = None,
    snapshot_id: str | None = None,
    from_year: int | None = None,
    to_year: int | None = None,
    current_price_vnd: float | None = None,
    manual_dir: str | Path = DEFAULT_MANUAL_DIR,
) -> ValuationInputPack:
    """Build the run-scoped input pack consumed by valuation."""
    ticker = ticker.strip().upper()
    if fact_table is None:
        if snapshot_id:
            fact_table = _load_fact_table_from_snapshot(snapshot_id)
        else:
            fact_table = _load_fact_table_from_production(ticker, from_year, to_year)

    pack_periods = _periods_from_fact_table(fact_table, periods)
    manual = load_manual_packs(ticker, as_of_date, manual_dir=manual_dir)

    market: dict[str, Any] = {}
    if current_price_vnd is not None:
        market.update({
            "price": current_price_vnd,
            "price_source": "market_snapshot_fallback",
            "status": "accepted",
        })
    market.update(manual.market)
    if manual.shares:
        market.update(manual.shares)
    elif "shares_outstanding" not in market:
        shares_from_facts = _latest_fact_value(
            fact_table,
            (
                "shares_outstanding.ending",
                "shares_outstanding.weighted_avg",
                "shares_outstanding.total",
            ),
            pack_periods,
        )
        if shares_from_facts is not None:
            market.update({
                "shares_outstanding": shares_from_facts,
                "shares_source": "reported_facts_or_market_snapshot",
            })

    peers = manual.peers
    debt_policy = manual.debt_policy or {
        "method": "stable_debt_unapproved",
        "status": "missing",
        "source": "manual_absent",
        "analyst_approved": False,
        "publishable": False,
    }
    corporate_actions = manual.corporate_actions or {
        "status": "no_action_recorded",
        "events": [],
        "source": "manual_absent",
    }
    tax_policy = manual.tax_policy
    wacc_assumptions = manual.wacc_assumptions
    working_capital_policy = manual.working_capital_policy or {
        "method": "percent_of_revenue_delta",
        "delta_nwc_ratio": 0.02,
        "status": "estimated",
        "source": "system_default",
        "publishable": True,
    }

    readiness = build_module_readiness(
        fact_table=fact_table,
        periods=pack_periods,
        market=market,
        peers=peers,
        debt_policy=debt_policy,
        corporate_actions=corporate_actions,
        working_capital_policy=working_capital_policy,
    )

    return ValuationInputPack(
        ticker=ticker,
        run_id=run_id,
        as_of_date=as_of_date_str(as_of_date),
        periods=pack_periods,
        facts=serialize_fact_table(fact_table),
        market=market,
        peers=peers,
        debt_policy=debt_policy,
        corporate_actions=corporate_actions,
        tax_policy=tax_policy,
        wacc_assumptions=wacc_assumptions,
        working_capital_policy=working_capital_policy,
        readiness=readiness,
        source_warnings=manual.warnings,
    )
