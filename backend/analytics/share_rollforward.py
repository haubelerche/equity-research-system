"""Share roll-forward schedule — diluted shares per forecast year.

Tracks year-on-year changes in share count from:
  - ESOP vesting (share_issuance_esop_mn)
  - Private placements / rights issues (share_issuance_placement_mn)
  - Bonus share / stock dividend issuances (share_issuance_bonus_mn)
  - Buybacks (share_buyback_mn)

If no corporate action data is provided, shares are held constant from the
most-recent known count, and a warning is emitted so the caller knows
diluted EPS and target price may be overstated relative to a post-dilution basis.

Diluted shares = ending shares + unvested ESOP options/warrants.
  When unvested ESOP grant data is absent, diluted_shares = ending_shares.

All share counts in millions.
All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

from backend.facts.normalizer import FactTable

_SHARE_FACT_KEYS = (
    "shares_outstanding.ending",
    "shares_outstanding.weighted_avg",
    "shares_outstanding.total",
)


def _get_shares(table: FactTable, key: str, period: str) -> float | None:
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    value = entry.get("value") if isinstance(entry, dict) else entry
    try:
        v = float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if v is None or v <= 0:
        return None
    # Normalise to millions — canonical facts may store absolute count
    return v / 1_000_000 if v > 1_000_000 else v


def _latest_known_shares(table: FactTable, fy_periods: list[str]) -> float | None:
    """Return the most-recent ending shares outstanding in millions."""
    for p in reversed(fy_periods):
        for key in _SHARE_FACT_KEYS:
            s = _get_shares(table, key, p)
            if s is not None:
                return s
    return None


@dataclass
class ShareRollRow:
    label: str
    beginning_shares_mn: float | None
    share_issuance_mn: float          # ESOP + placement + bonus
    share_buyback_mn: float
    ending_shares_mn: float | None
    diluted_shares_mn: float | None   # ending + unvested options (when available)
    method: str                       # "stable" | "corporate_action" | "missing"
    warning: str | None = None

    def to_dict(self) -> dict[str, Any]:
        def _r(v: float | None) -> float | None:
            return round(v, 3) if v is not None else None
        return {
            "label": self.label,
            "beginning_shares_mn": _r(self.beginning_shares_mn),
            "share_issuance_mn": round(self.share_issuance_mn, 3),
            "share_buyback_mn": round(self.share_buyback_mn, 3),
            "ending_shares_mn": _r(self.ending_shares_mn),
            "diluted_shares_mn": _r(self.diluted_shares_mn),
            "method": self.method,
            "warning": self.warning,
        }


@dataclass
class ShareRollForward:
    ticker: str
    base_shares_mn: float | None
    forecast_rows: list[ShareRollRow]
    warnings: list[str] = field(default_factory=list)

    def diluted_shares_schedule(self) -> dict[str, float | None]:
        """Return {label: diluted_shares_mn} for downstream EPS and target-price use."""
        return {row.label: row.diluted_shares_mn for row in self.forecast_rows}

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "base_shares_mn": round(self.base_shares_mn, 3) if self.base_shares_mn else None,
            "forecast_rows": [r.to_dict() for r in self.forecast_rows],
            "warnings": self.warnings,
        }


@dataclass
class CorporateAction:
    """One corporate action that changes the share count."""
    forecast_label: str                # "2026F", "2027F", ...
    issuance_mn: float = 0.0           # new shares issued (ESOP + placement + bonus)
    buyback_mn: float = 0.0            # shares repurchased
    unvested_options_mn: float = 0.0   # for diluted-share dilution


def build_share_rollforward(
    ticker: str,
    fact_table: FactTable,
    fy_periods: list[str],
    forecast_labels: list[str],
    corporate_actions: list[CorporateAction] | None = None,
    base_shares_override_mn: float | None = None,
) -> ShareRollForward:
    """Build a share roll-forward schedule for forecast years.

    Args:
        base_shares_override_mn: if provided, use this as starting shares (e.g. from
            vnstock market snapshot) instead of canonical facts.
        corporate_actions: list of known corporate actions per label. When empty or None,
            shares are held constant and a warning is emitted.
    """
    warnings: list[str] = []
    ca_by_label: dict[str, CorporateAction] = {}
    if corporate_actions:
        for ca in corporate_actions:
            ca_by_label[ca.forecast_label] = ca

    # Determine base shares
    if base_shares_override_mn is not None and base_shares_override_mn > 0:
        base_shares = base_shares_override_mn
    else:
        base_shares = _latest_known_shares(fact_table, fy_periods)

    if base_shares is None:
        warnings.append(
            f"{ticker}: no shares_outstanding fact available — share roll-forward cannot be built. "
            "EPS and target price are blocked."
        )
        rows = [
            ShareRollRow(
                label=lbl,
                beginning_shares_mn=None,
                share_issuance_mn=0.0,
                share_buyback_mn=0.0,
                ending_shares_mn=None,
                diluted_shares_mn=None,
                method="missing",
                warning="Shares outstanding unavailable — EPS blocked",
            )
            for lbl in forecast_labels
        ]
        return ShareRollForward(ticker=ticker, base_shares_mn=None, forecast_rows=rows, warnings=warnings)

    if not ca_by_label:
        warnings.append(
            f"{ticker}: no corporate action data provided — shares held constant at {base_shares:.3f}mn. "
            "Private placement / ESOP dilution is NOT modelled. Diluted EPS and target price/share may be overstated."
        )

    rows: list[ShareRollRow] = []
    current_shares = base_shares

    for label in forecast_labels:
        ca = ca_by_label.get(label)
        issuance = ca.issuance_mn if ca else 0.0
        buyback  = ca.buyback_mn  if ca else 0.0
        unvested = ca.unvested_options_mn if ca else 0.0

        ending   = current_shares + issuance - buyback
        diluted  = ending + unvested

        method = "corporate_action" if ca else "stable"
        w = None
        if ca and (issuance > 0 or buyback > 0):
            w = (
                f"Corporate action in {label}: +{issuance:.3f}mn issued, "
                f"-{buyback:.3f}mn bought back → ending {ending:.3f}mn"
            )

        rows.append(ShareRollRow(
            label=label,
            beginning_shares_mn=current_shares,
            share_issuance_mn=issuance,
            share_buyback_mn=buyback,
            ending_shares_mn=ending,
            diluted_shares_mn=diluted,
            method=method,
            warning=w,
        ))
        current_shares = ending

    return ShareRollForward(
        ticker=ticker,
        base_shares_mn=base_shares,
        forecast_rows=rows,
        warnings=warnings,
    )
