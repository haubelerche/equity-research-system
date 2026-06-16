"""Working capital schedule — driver-based NWC and delta_nwc per forecast year.

NWC = accounts_receivable + inventory - accounts_payable

Historical drivers (days of revenue or COGS):
  ar_days   = AR / (revenue / 365)          median across history
  inv_days  = inventory / (|cogs| / 365)    median across history
  ap_days   = AP / (|cogs| / 365)           median across history

Forecast NWC_t:
  AR_t  = ar_days  × revenue_t / 365
  Inv_t = inv_days × |cogs_t|  / 365
  AP_t  = ap_days  × |cogs_t|  / 365
  NWC_t = AR_t + Inv_t - AP_t

delta_nwc_t = NWC_t - NWC_{t-1}
  Positive delta_nwc means working capital absorbed cash → reduces FCF.

All monetary values in VND bn.
All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from backend.analytics._entry import entry_value
from backend.facts.normalizer import FactTable


def _get(table: FactTable, key: str, period: str) -> float | None:
    # Use the canonical entry_value: the fact table holds FactEntry objects in real
    # runs (build_fact_table), not raw floats/dicts. Reading entry directly returned
    # None for FactEntry → AR/inventory/AP collapsed to 0 → understated NWC/delta_nwc.
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    return entry_value(entry)


@dataclass
class WCYear:
    label: str
    accounts_receivable: float | None
    inventory: float | None
    accounts_payable: float | None
    net_working_capital: float | None    # AR + Inv - AP
    delta_nwc: float | None              # NWC_t - NWC_{t-1}; positive = cash consumed

    def to_dict(self) -> dict[str, Any]:
        def _r(v: float | None) -> float | None:
            return round(v, 2) if v is not None else None
        return {
            "label": self.label,
            "accounts_receivable": _r(self.accounts_receivable),
            "inventory": _r(self.inventory),
            "accounts_payable": _r(self.accounts_payable),
            "net_working_capital": _r(self.net_working_capital),
            "delta_nwc": _r(self.delta_nwc),
        }


@dataclass
class WorkingCapitalSchedule:
    ticker: str
    ar_days: float | None           # days receivable (historical median)
    inv_days: float | None          # days inventory  (historical median)
    ap_days: float | None           # days payable    (historical median)
    historical_rows: list[WCYear]   # derived from canonical facts
    forecast_rows: list[WCYear]     # projected using drivers
    warnings: list[str] = field(default_factory=list)

    def nwc_schedule(self) -> dict[str, float | None]:
        """Return {label: nwc} for all forecast rows."""
        return {row.label: row.net_working_capital for row in self.forecast_rows}

    def delta_nwc_schedule(self) -> dict[str, float | None]:
        """Return {label: delta_nwc} for all forecast rows."""
        return {row.label: row.delta_nwc for row in self.forecast_rows}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "ar_days": round(self.ar_days, 1) if self.ar_days is not None else None,
            "inv_days": round(self.inv_days, 1) if self.inv_days is not None else None,
            "ap_days": round(self.ap_days, 1) if self.ap_days is not None else None,
            "historical_rows": [r.to_dict() for r in self.historical_rows],
            "forecast_rows": [r.to_dict() for r in self.forecast_rows],
            "warnings": self.warnings,
        }


def build_working_capital_schedule(
    ticker: str,
    fact_table: FactTable,
    fy_periods: list[str],
    forecast_labels: list[str],
    forecast_revenues: dict[str, float],      # {label: revenue_bn}
    forecast_cogs: dict[str, float],          # {label: cogs_bn} — signed negative
) -> WorkingCapitalSchedule:
    """Build historical and forecast working capital schedules.

    Args:
        forecast_revenues: forecast revenue per label (VND bn, positive).
        forecast_cogs:     forecast COGS per label (VND bn, negative sign convention).
    """
    warnings: list[str] = []

    # ── Historical drivers ────────────────────────────────────────────────────
    ar_day_vals: list[float] = []
    inv_day_vals: list[float] = []
    ap_day_vals: list[float] = []
    historical_rows: list[WCYear] = []

    prev_nwc: float | None = None

    for p in fy_periods:
        ar  = _get(fact_table, "accounts_receivable.ending", p)
        inv = _get(fact_table, "inventory.ending", p)
        ap  = _get(fact_table, "accounts_payable.ending", p)
        rev = _get(fact_table, "revenue.net", p)
        cogs = _get(fact_table, "cogs.total", p)

        nwc: float | None = None
        if ar is not None and inv is not None and ap is not None:
            nwc = ar + inv - ap

        delta: float | None = (nwc - prev_nwc) if (nwc is not None and prev_nwc is not None) else None

        historical_rows.append(WCYear(
            label=p,
            accounts_receivable=ar,
            inventory=inv,
            accounts_payable=ap,
            net_working_capital=nwc,
            delta_nwc=delta,
        ))

        # Days calculations for driver derivation
        if ar is not None and rev and rev > 0:
            ar_day_vals.append(ar / (rev / 365.0))
        cogs_abs = abs(cogs) if cogs is not None else None
        if inv is not None and cogs_abs and cogs_abs > 0:
            inv_day_vals.append(inv / (cogs_abs / 365.0))
        if ap is not None and cogs_abs and cogs_abs > 0:
            ap_day_vals.append(ap / (cogs_abs / 365.0))

        prev_nwc = nwc

    ar_days  = statistics.median(ar_day_vals)  if ar_day_vals  else None
    inv_days = statistics.median(inv_day_vals) if inv_day_vals else None
    ap_days  = statistics.median(ap_day_vals)  if ap_day_vals  else None

    if ar_days is None:
        warnings.append(f"{ticker}: no historical AR data — AR forecast will be 0 (delta_nwc may be understated)")
    if inv_days is None:
        warnings.append(f"{ticker}: no historical inventory data — inventory forecast will be 0")
    if ap_days is None:
        warnings.append(f"{ticker}: no historical AP data — AP forecast will be 0 (delta_nwc may be overstated)")

    # ── Forecast rows ─────────────────────────────────────────────────────────
    # Seed the forecast from a driver-normalized opening NWC. Using the raw
    # latest balance can create an artificial first-year cash-flow shock when
    # the latest year is temporarily depressed or elevated versus normalized
    # collection/inventory/payment days.
    latest_period = fy_periods[-1] if fy_periods else ""
    latest_rev = _get(fact_table, "revenue.net", latest_period)
    latest_cogs = _get(fact_table, "cogs.total", latest_period)
    latest_cogs_abs = abs(latest_cogs) if latest_cogs is not None else None
    normalized_opening_nwc: float | None = None
    if latest_rev is not None and latest_cogs_abs is not None:
        normalized_opening_nwc = (
            ((ar_days or 0.0) / 365.0) * latest_rev
            + ((inv_days or 0.0) / 365.0) * latest_cogs_abs
            - ((ap_days or 0.0) / 365.0) * latest_cogs_abs
        )
    reported_opening_nwc = historical_rows[-1].net_working_capital if historical_rows else None
    prev_nwc = normalized_opening_nwc if normalized_opening_nwc is not None else reported_opening_nwc
    if normalized_opening_nwc is not None and reported_opening_nwc is not None:
        opening_gap = normalized_opening_nwc - reported_opening_nwc
        if abs(opening_gap) > max(abs(reported_opening_nwc) * 0.15, 50.0):
            warnings.append(
                f"{ticker}: first forecast delta_nwc uses normalized opening NWC "
                f"({normalized_opening_nwc:.1f}) instead of reported NWC "
                f"({reported_opening_nwc:.1f}); normalization gap={opening_gap:.1f}"
            )

    forecast_rows: list[WCYear] = []

    for label in forecast_labels:
        rev_f  = forecast_revenues.get(label)
        cogs_f = forecast_cogs.get(label)
        cogs_f_abs = abs(cogs_f) if cogs_f is not None else None

        if rev_f is not None and cogs_f_abs is not None:
            ar_f  = (ar_days  / 365.0) * rev_f     if ar_days  is not None else 0.0
            inv_f = (inv_days / 365.0) * cogs_f_abs if inv_days is not None else 0.0
            ap_f  = (ap_days  / 365.0) * cogs_f_abs if ap_days  is not None else 0.0
            nwc_f: float | None = ar_f + inv_f - ap_f
        else:
            ar_f = inv_f = ap_f = None
            nwc_f = None
            warnings.append(f"{label}: missing revenue or COGS for NWC forecast")

        delta_f: float | None = (nwc_f - prev_nwc) if (nwc_f is not None and prev_nwc is not None) else None

        forecast_rows.append(WCYear(
            label=label,
            accounts_receivable=ar_f,
            inventory=inv_f,
            accounts_payable=ap_f,
            net_working_capital=nwc_f,
            delta_nwc=delta_f,
        ))
        prev_nwc = nwc_f

    return WorkingCapitalSchedule(
        ticker=ticker,
        ar_days=ar_days,
        inv_days=inv_days,
        ap_days=ap_days,
        historical_rows=historical_rows,
        forecast_rows=forecast_rows,
        warnings=warnings,
    )
