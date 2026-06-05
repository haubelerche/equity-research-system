"""Net debt bridge — EV-to-equity bridge with explicit blocking.

Net Debt = Total Interest-Bearing Debt
         - Cash and Cash Equivalents
         - Short-Term Investments

Equity Value (from EV) = Enterprise Value
                        - Net Debt
                        - Minority Interest
                        + Non-Operating Assets

Blocking rule (master plan invariant 2.3 / checklist item 15):
  If total_debt fact is missing, the bridge status is BLOCKED.
  A target price of None is returned; callers must not publish a final rating.

All monetary values in VND bn.
All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from backend.facts.normalizer import FactTable

BridgeStatus = Literal["ok", "warned", "blocked"]


def _get(table: FactTable, key: str, period: str) -> float | None:
    if not period:
        return None
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    if hasattr(entry, "value"):
        value = entry.value
    elif isinstance(entry, dict):
        value = entry.get("value")
    else:
        value = entry
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _interest_bearing_debt(table: FactTable, period: str) -> tuple[float | None, list[str]]:
    """Resolve interest-bearing debt from total debt or component facts."""
    total_debt = _get(table, "total_debt.ending", period)
    if total_debt is not None:
        return total_debt, ["total_debt.ending"]

    st_borrowings = _get(table, "short_term_borrowings.ending", period)
    lt_borrowings = _get(table, "long_term_borrowings.ending", period)
    if st_borrowings is not None or lt_borrowings is not None:
        return (st_borrowings or 0.0) + (lt_borrowings or 0.0), [
            k for k, v in (
                ("short_term_borrowings.ending", st_borrowings),
                ("long_term_borrowings.ending", lt_borrowings),
            ) if v is not None
        ]

    st_debt = _get(table, "short_term_debt.ending", period)
    lt_debt = _get(table, "long_term_debt.ending", period)
    if st_debt is not None or lt_debt is not None:
        return (st_debt or 0.0) + (lt_debt or 0.0), [
            k for k, v in (
                ("short_term_debt.ending", st_debt),
                ("long_term_debt.ending", lt_debt),
            ) if v is not None
        ]

    return None, []


@dataclass
class NetDebtBridge:
    """Full EV-to-equity bridge with provenance for every component.

    status:
        "ok"      — all components resolved; bridge is trustworthy.
        "warned"  — optional components (short_term_investments, minority_interest,
                    non_operating_assets) missing; net_debt may differ from reality
                    but the bridge can proceed with caveats.
        "blocked" — total_debt missing; equity value cannot be computed from EV.
                    target_price must NOT be published.
    """
    period: str                          # e.g. "2025FY"

    total_debt: float | None             # interest-bearing debt (ST + LT borrowings)
    cash: float | None                   # cash and cash equivalents
    short_term_investments: float | None # liquid ST investments (treasury bills, deposits)
    minority_interest: float | None      # non-controlling interest deducted from EV
    non_operating_assets: float | None   # added back to equity value

    net_debt: float | None               # = total_debt - cash - short_term_investments
    equity_value_from_ev: float | None   # = EV - net_debt - minority_interest + non_op_assets

    status: BridgeStatus
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)

    @property
    def is_blocked(self) -> bool:
        return self.status == "blocked"

    def to_dict(self) -> dict[str, Any]:
        def _r(v: float | None) -> float | None:
            return round(v, 2) if v is not None else None
        return {
            "period": self.period,
            "total_debt": _r(self.total_debt),
            "cash": _r(self.cash),
            "short_term_investments": _r(self.short_term_investments),
            "minority_interest": _r(self.minority_interest),
            "non_operating_assets": _r(self.non_operating_assets),
            "net_debt": _r(self.net_debt),
            "equity_value_from_ev": _r(self.equity_value_from_ev),
            "status": self.status,
            "warnings": self.warnings,
            "missing_fields": self.missing_fields,
            "formula": (
                "net_debt = total_debt - cash - short_term_investments; "
                "equity_value = EV - net_debt - minority_interest + non_operating_assets"
            ),
        }


def build_net_debt_bridge(
    fact_table: FactTable,
    period: str,
    enterprise_value: float | None = None,
    minority_interest_override: float | None = None,
    non_operating_assets_override: float | None = None,
) -> NetDebtBridge:
    """Build the net debt bridge for a given period.

    Args:
        enterprise_value: If provided, also computes equity_value_from_ev.
        minority_interest_override: Use if fact_table doesn't carry minority interest.
        non_operating_assets_override: Use if analyst provides non-operating investments.
    """
    warnings: list[str] = []
    missing: list[str] = []

    total_debt, debt_sources = _interest_bearing_debt(fact_table, period)
    cash       = _get(fact_table, "cash_and_equivalents.ending", period)
    st_inv     = _get(fact_table, "short_term_investments.ending", period)
    mi         = minority_interest_override or _get(fact_table, "minority_interest.ending", period)
    noa        = non_operating_assets_override

    # Determine status
    status: BridgeStatus = "ok"

    if total_debt is None:
        missing.append("total_debt.ending")
        warnings.append(
            f"[{period}] total_debt.ending missing — EV-to-equity bridge BLOCKED. "
            "Target price cannot be published until debt fact is sourced."
        )
        status = "blocked"

    if cash is None:
        missing.append("cash_and_equivalents.ending")
        warnings.append(
            f"[{period}] cash_and_equivalents.ending missing — net_debt may be overstated."
        )
        if status != "blocked":
            status = "warned"

    if st_inv is None:
        missing.append("short_term_investments.ending")
        if status == "ok":
            status = "warned"

    if total_debt is not None and "total_debt.ending" not in debt_sources:
        warnings.append(
            f"[{period}] total_debt.ending missing; derived interest-bearing debt from "
            f"{' + '.join(debt_sources)}."
        )

    # Compute net debt (0 substitution only when NOT blocked)
    if status != "blocked":
        net_debt: float | None = (total_debt or 0.0) - (cash or 0.0) - (st_inv or 0.0)
    else:
        net_debt = None

    # Compute equity value from EV
    equity_value_from_ev: float | None = None
    if enterprise_value is not None and net_debt is not None:
        equity_value_from_ev = (
            enterprise_value
            - net_debt
            - (mi or 0.0)
            + (noa or 0.0)
        )

    return NetDebtBridge(
        period=period,
        total_debt=total_debt,
        cash=cash,
        short_term_investments=st_inv,
        minority_interest=mi,
        non_operating_assets=noa,
        net_debt=net_debt,
        equity_value_from_ev=equity_value_from_ev,
        status=status,
        warnings=warnings,
        missing_fields=missing,
    )
