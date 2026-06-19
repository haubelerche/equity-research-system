"""Market-anchored governance for report headline target prices.

The raw valuation model remains available for audit, but the client-facing
headline target must stay inside a small market sanity band unless a future
workflow explicitly introduces analyst-approved exceptional disclosure.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal


# Symmetric ±40% band, matching the valuation policy's MARKET_SANITY_BAND. The policy
# already blocks (or requires a reconciling bridge for) any target more than 40% from
# market, so the display band is the same single sanity rule — not a second, tighter
# governor that would flatten every legitimate target back to the current price.
DEFAULT_HEADLINE_TARGET_DOWNSIDE_BAND = 0.40
DEFAULT_HEADLINE_TARGET_UPSIDE_BAND = 0.40

TargetAdjustment = Literal[
    "none",
    "clamped_low",
    "clamped_high",
    "market_anchor_neutral",
    "missing_current_price",
]


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed) or parsed <= 0:
        return None
    return parsed


def _safe_upper(value: float) -> float:
    return float(math.floor(value))


def _safe_lower(value: float) -> float:
    return float(math.ceil(value))


@dataclass(frozen=True)
class HeadlineTargetGovernance:
    current_price_vnd: float | None
    raw_model_target_vnd: float | None
    headline_target_vnd: float | None
    target_adjustment: TargetAdjustment
    target_band_low_vnd: float | None
    target_band_high_vnd: float | None
    headline_downside_band_pct: float
    headline_upside_band_pct: float
    raw_upside: float | None
    headline_upside: float | None
    raw_model_target_source: str | None = None
    warnings: tuple[str, ...] = ()

    @property
    def has_raw_model_target(self) -> bool:
        return self.raw_model_target_vnd is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_price_vnd": self.current_price_vnd,
            "raw_model_target_vnd": self.raw_model_target_vnd,
            "headline_target_vnd": self.headline_target_vnd,
            "target_adjustment": self.target_adjustment,
            "target_band_low_vnd": self.target_band_low_vnd,
            "target_band_high_vnd": self.target_band_high_vnd,
            "headline_downside_band_pct": self.headline_downside_band_pct,
            "headline_upside_band_pct": self.headline_upside_band_pct,
            "headline_band_pct": self.headline_upside_band_pct,
            "raw_upside": self.raw_upside,
            "headline_upside": self.headline_upside,
            "raw_model_target_source": self.raw_model_target_source,
            "has_raw_model_target": self.has_raw_model_target,
            "warnings": list(self.warnings),
        }


def build_headline_target_governance(
    *,
    current_price_vnd: Any,
    raw_model_target_vnd: Any = None,
    raw_model_target_source: str | None = None,
    downside_band_pct: float = DEFAULT_HEADLINE_TARGET_DOWNSIDE_BAND,
    upside_band_pct: float = DEFAULT_HEADLINE_TARGET_UPSIDE_BAND,
) -> HeadlineTargetGovernance:
    """Return the display-safe headline target and an auditable adjustment trace."""
    current = _positive_float(current_price_vnd)
    raw = _positive_float(raw_model_target_vnd)
    warnings: list[str] = []

    if current is None:
        warnings.append("headline_target_missing_current_price")
        return HeadlineTargetGovernance(
            current_price_vnd=None,
            raw_model_target_vnd=raw,
            headline_target_vnd=None,
            target_adjustment="missing_current_price",
            target_band_low_vnd=None,
            target_band_high_vnd=None,
            headline_downside_band_pct=downside_band_pct,
            headline_upside_band_pct=upside_band_pct,
            raw_upside=None,
            headline_upside=None,
            raw_model_target_source=raw_model_target_source,
            warnings=tuple(warnings),
        )

    lower = _safe_lower(current * (1.0 - downside_band_pct))
    upper = _safe_upper(current * (1.0 + upside_band_pct))
    if lower > upper:
        lower = upper = round(current, 0)

    raw_upside = (raw / current - 1.0) if raw is not None else None
    if raw is None:
        headline = round(current, 0)
        adjustment: TargetAdjustment = "market_anchor_neutral"
        warnings.append("headline_target_market_anchor_neutral")
    elif raw < lower:
        headline = lower
        adjustment = "clamped_low"
        warnings.append("headline_target_clamped_low")
    elif raw > upper:
        headline = upper
        adjustment = "clamped_high"
        warnings.append("headline_target_clamped_high")
    else:
        rounded = round(raw, 0)
        headline = min(max(rounded, lower), upper)
        adjustment = "none"

    headline_upside = headline / current - 1.0
    return HeadlineTargetGovernance(
        current_price_vnd=current,
        raw_model_target_vnd=raw,
        headline_target_vnd=headline,
        target_adjustment=adjustment,
        target_band_low_vnd=lower,
        target_band_high_vnd=upper,
        headline_downside_band_pct=downside_band_pct,
        headline_upside_band_pct=upside_band_pct,
        raw_upside=raw_upside,
        headline_upside=headline_upside,
        raw_model_target_source=raw_model_target_source,
        warnings=tuple(warnings),
    )
