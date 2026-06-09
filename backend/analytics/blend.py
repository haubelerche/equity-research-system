"""60% FCFF + 40% FCFE blended target price.

Formula: Target Price = 0.60 × Price_FCFF + 0.40 × Price_FCFE

Rationale (VN pharma sector):
- FCFF (60%): enterprise-level intrinsic value via WACC discount.
- FCFE (40%): equity-level intrinsic value via Re discount; captures
  leverage effects and provides independent equity valuation cross-check.

P/E Forward is retained as a supplementary cross-check only and does NOT
enter the official blend.

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FCFF_WEIGHT: float = 0.60
FCFE_WEIGHT: float = 0.40
_FCFF_FCFE_GAP_THRESHOLD: float = 0.25  # block blend if |Price_FCFF/Price_FCFE - 1| > 25%
_TV_WARN_THRESHOLD: float = 0.70        # warn if PV(TV) / EV > 70%


@dataclass
class BlendResult:
    """Output of the 60/40 FCFF + FCFE blend.

    Attributes:
        price_fcff: Per-share price from FCFF DCF model (VND/share).
        price_fcfe: Per-share price from FCFE DCF model (VND/share).
        target_price_dcf: Blended target = 0.60×FCFF + 0.40×FCFE (VND/share).
        upside_pct: (target_price - current_price) / current_price.
        margin_of_safety: (intrinsic_value - market_price) / intrinsic_value.
        fcff_fcfe_gap_pct: |Price_FCFF / Price_FCFE - 1|; warn > 25%.
        is_draft_only: True if gap > 25% or only one price available.
    """
    ticker: str
    price_fcff: float | None
    price_fcfe: float | None
    target_price_dcf: float | None
    current_price_vnd: float | None
    upside_pct: float | None
    margin_of_safety: float | None
    fcff_weight: float = FCFF_WEIGHT
    fcfe_weight: float = FCFE_WEIGHT
    fcff_fcfe_gap_pct: float | None = None      # |Price_FCFF/Price_FCFE - 1|
    tv_weight_fcff: float | None = None         # PV(TV_FCFF) / EV_FCFF
    is_draft_only: bool = False
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _r(v: float | None, d: int = 0) -> float | None:
            return round(v, d) if v is not None else None

        return {
            "ticker": self.ticker,
            "price_fcff_vnd": _r(self.price_fcff),
            "price_fcfe_vnd": _r(self.price_fcfe),
            "fcff_weight": self.fcff_weight,
            "fcfe_weight": self.fcfe_weight,
            "target_price_dcf_vnd": _r(self.target_price_dcf),
            "current_price_vnd": _r(self.current_price_vnd),
            "upside_pct": round(self.upside_pct, 4) if self.upside_pct is not None else None,
            "margin_of_safety": round(self.margin_of_safety, 4) if self.margin_of_safety is not None else None,
            "fcff_fcfe_gap_pct": round(self.fcff_fcfe_gap_pct, 4) if self.fcff_fcfe_gap_pct is not None else None,
            "tv_weight_fcff": round(self.tv_weight_fcff, 4) if self.tv_weight_fcff is not None else None,
            "is_draft_only": self.is_draft_only,
            "warnings": self.warnings,
            "formula": "Target Price = 0.60 × Price_FCFF + 0.40 × Price_FCFE",
        }


def blend_dcf(
    ticker: str,
    price_fcff: float | None,
    price_fcfe: float | None,
    current_price_vnd: float | None = None,
    pv_terminal_value_fcff: float | None = None,
    enterprise_value_fcff: float | None = None,
) -> BlendResult:
    """Compute blended target: 60% FCFF + 40% FCFE.

    Quality checks:
    1. FCFF/FCFE gap: |Price_FCFF/Price_FCFE - 1| > 25% → draft-only + warning
    2. TV weight: PV(TV_FCFF) / EV_FCFF > 70% → warning
    3. Partial availability: if one price is None, fall back with warning.
    """
    warnings: list[str] = []
    is_draft_only: bool = False

    # ── Quality check 1: FCFF/FCFE gap gate (25% threshold) ──────────────
    fcff_fcfe_gap: float | None = None
    if price_fcff is not None and price_fcfe is not None and price_fcfe != 0:
        fcff_fcfe_gap = abs(price_fcff / price_fcfe - 1)
        if fcff_fcfe_gap > _FCFF_FCFE_GAP_THRESHOLD:
            is_draft_only = True
            warnings.append(
                f"FCFF/FCFE valuation gap = {fcff_fcfe_gap:.1%} > 25% — "
                "blend blocked: audit net borrowing, net debt, CAPEX, NWC before publishing target price."
            )

    # ── Quality check 2: terminal value weight ───────────────────────
    tv_weight: float | None = None
    if (
        pv_terminal_value_fcff is not None
        and enterprise_value_fcff is not None
        and enterprise_value_fcff > 0
    ):
        tv_weight = pv_terminal_value_fcff / enterprise_value_fcff
        if tv_weight > _TV_WARN_THRESHOLD:
            warnings.append(
                f"Terminal value chiếm {tv_weight:.1%} EV — "
                "kết quả phụ thuộc mạnh vào giả định tăng trưởng dài hạn, "
                "bắt buộc có sensitivity analysis"
            )

    # ── Blend formula ────────────────────────────────────────────
    target_price: float | None = None
    if price_fcff is not None and price_fcfe is not None:
        target_price = FCFF_WEIGHT * price_fcff + FCFE_WEIGHT * price_fcfe
    elif price_fcff is not None:
        is_draft_only = True
        warnings.append(
            "Price_FCFE không có — dùng 100% FCFF. "
            "Không đúng trọng số 60/40; kết quả cần phê duyệt thủ công."
        )
        target_price = price_fcff
    elif price_fcfe is not None:
        is_draft_only = True
        warnings.append(
            "Price_FCFF không có — dùng 100% FCFE. "
            "Không đúng trọng số 60/40; kết quả cần phê duyệt thủ công."
        )
        target_price = price_fcfe

    # ── Upside and margin of safety ──────────────────────────────
    upside_pct: float | None = None
    margin_of_safety: float | None = None
    if target_price is not None and current_price_vnd and current_price_vnd > 0:
        upside_pct = (target_price - current_price_vnd) / current_price_vnd
        margin_of_safety = (target_price - current_price_vnd) / target_price

    return BlendResult(
        ticker=ticker,
        price_fcff=price_fcff,
        price_fcfe=price_fcfe,
        target_price_dcf=target_price,
        current_price_vnd=current_price_vnd,
        upside_pct=upside_pct,
        margin_of_safety=margin_of_safety,
        fcff_fcfe_gap_pct=fcff_fcfe_gap,
        tv_weight_fcff=tv_weight,
        is_draft_only=is_draft_only,
        warnings=warnings,
    )
