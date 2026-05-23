"""Deterministic fact normalization and derived metric computation.

Takes a list of raw FinancialFact dicts from the DB and returns a structured
FactTable: a dict keyed by taxonomy_key → period_key → value.

Derived metrics computed here (not stored in DB — sourced from the spec):
  free_cash_flow.total  = operating_cash_flow.total - capex.total
  gross_margin          = gross_profit.total / revenue.net
  ebitda_margin         = ebitda.total / revenue.net
  net_margin            = net_income.parent / revenue.net
  debt_to_equity        = total_debt.ending / equity.parent
"""
from __future__ import annotations

from typing import Any


# Period key format: "{fiscal_year}{fiscal_period}" e.g. "2024FY", "2025Q1"
FactTable = dict[str, dict[str, float]]


def _period_key(fiscal_year: int, fiscal_period: str) -> str:
    return f"{fiscal_year}{fiscal_period}"


def build_fact_table(raw_facts: list[dict[str, Any]]) -> FactTable:
    """Convert flat fact rows from DB into a nested dict: taxonomy_key → period → value.

    When multiple rows exist for the same (taxonomy_key, period), the row with the
    highest confidence is kept; ties are broken by latest ingested_at.
    """
    # Collect best row per (taxonomy_key, period)
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in raw_facts:
        key = (row["taxonomy_key"], _period_key(row["fiscal_year"], row["fiscal_period"]))
        existing = best.get(key)
        if existing is None:
            best[key] = row
        else:
            row_conf = row.get("confidence") or 0.0
            ex_conf = existing.get("confidence") or 0.0
            if row_conf > ex_conf:
                best[key] = row
            elif row_conf == ex_conf:
                if str(row.get("ingested_at", "")) > str(existing.get("ingested_at", "")):
                    best[key] = row

    table: FactTable = {}
    for (taxonomy_key, period), row in best.items():
        if taxonomy_key not in table:
            table[taxonomy_key] = {}
        table[taxonomy_key][period] = float(row["value"])

    return table


def build_validation_status_table(raw_facts: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Return validation_status for each (taxonomy_key, period).

    Uses the same tie-breaking as build_fact_table: highest confidence wins,
    then latest ingested_at. Unknown validation_status is treated as 'unknown'.
    """
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in raw_facts:
        key = (row["taxonomy_key"], _period_key(row["fiscal_year"], row["fiscal_period"]))
        existing = best.get(key)
        if existing is None:
            best[key] = row
        else:
            row_conf = row.get("confidence") or 0.0
            ex_conf = existing.get("confidence") or 0.0
            if row_conf > ex_conf:
                best[key] = row
            elif row_conf == ex_conf:
                if str(row.get("ingested_at", "")) > str(existing.get("ingested_at", "")):
                    best[key] = row

    status_table: dict[str, dict[str, str]] = {}
    for (taxonomy_key, period), row in best.items():
        if taxonomy_key not in status_table:
            status_table[taxonomy_key] = {}
        status_table[taxonomy_key][period] = str(row.get("validation_status") or "unknown")
    return status_table


def _safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator == 0.0:
        return None
    return numerator / denominator


def compute_derived(table: FactTable) -> FactTable:
    """Add derived metrics to the table. Operates on a copy — does not mutate input."""
    derived: FactTable = {}

    # Collect all periods across the base facts
    all_periods: set[str] = set()
    for periods in table.values():
        all_periods.update(periods.keys())

    for period in sorted(all_periods):
        def get(key: str) -> float | None:
            return table.get(key, {}).get(period)

        # free_cash_flow.total = operating_cash_flow.total - capex.total
        ocf = get("operating_cash_flow.total")
        capex = get("capex.total")
        if ocf is not None and capex is not None:
            derived.setdefault("free_cash_flow.total", {})[period] = ocf - capex

        # gross_margin = gross_profit.total / revenue.net
        gp = get("gross_profit.total")
        rev = get("revenue.net")
        gm = _safe_div(gp, rev)
        if gm is not None:
            derived.setdefault("gross_margin", {})[period] = round(gm, 6)

        # ebitda_margin = ebitda.total / revenue.net
        ebitda = get("ebitda.total")
        em = _safe_div(ebitda, rev)
        if em is not None:
            derived.setdefault("ebitda_margin", {})[period] = round(em, 6)

        # net_margin = net_income.parent / revenue.net
        ni = get("net_income.parent")
        nm = _safe_div(ni, rev)
        if nm is not None:
            derived.setdefault("net_margin", {})[period] = round(nm, 6)

        # debt_to_equity = total_debt.ending / equity.parent
        debt = get("total_debt.ending")
        eq = get("equity.parent")
        de = _safe_div(debt, eq)
        if de is not None:
            derived.setdefault("debt_to_equity", {})[period] = round(de, 6)

    # Merge derived into a new table
    merged = {k: dict(v) for k, v in table.items()}
    for k, v in derived.items():
        merged[k] = v
    return merged


def periods_sorted(table: FactTable) -> list[str]:
    """Return all period keys in the table, sorted chronologically."""
    all_p: set[str] = set()
    for periods in table.values():
        all_p.update(periods.keys())
    return sorted(all_p)
