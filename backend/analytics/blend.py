"""60% FCFF + 40% FCFE blended DCF target price.

Formula: Target Price_DCF = 0.60 × Price_FCFF + 0.40 × Price_FCFE
Source: Cẩm nang định giá cổ phiếu — 60% FCFF + 40% FCFE

Rationale (pharma sector): FCFF is more stable when capital structure changes;
FCFE reflects direct shareholder cash flows. 60/40 balances enterprise-level and
equity-level views for pharma companies with moderate, predictable debt.

This module contains only the blend arithmetic and quality checks.
Valuation inputs come from fcff.compute_fcff() and fcfe.compute_fcfe().

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FCFF_WEIGHT: float = 0.60
FCFE_WEIGHT: float = 0.40
_GAP_WARN_THRESHOLD: float = 0.25   # warn if |Price_FCFF/Price_FCFE - 1| > 25%
_TV_WARN_THRESHOLD: float = 0.70    # warn if PV(TV) / EV > 70%




@dataclass
class BlendResult:
    """Output of the 60/40 DCF blend.

    Attributes:
        price_fcff: Per-share price from FCFF model (VND/share).
        price_fcfe: Per-share price from FCFE model (VND/share).
        target_price_dcf: Blended target price = 0.60×FCFF + 0.40×FCFE (VND/share).
        upside_pct: (target_price - current_price) / current_price.
        margin_of_safety: (intrinsic_value - market_price) / intrinsic_value.
        valuation_gap_pct: |Price_FCFF / Price_FCFE − 1|; warn > 25%.
        is_draft_only: True if gap > 25% or only one price available (partial blend).
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
    valuation_gap_pct: float | None = None
    tv_weight_fcff: float | None = None   # PV(TV_FCFF) / EV_FCFF
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
            "valuation_gap_pct": round(self.valuation_gap_pct, 4) if self.valuation_gap_pct is not None else None,
            "tv_weight_fcff": round(self.tv_weight_fcff, 4) if self.tv_weight_fcff is not None else None,
            "is_draft_only": self.is_draft_only,
            "warnings": self.warnings,
            "formula": "Target Price_DCF = 0.60 × Price_FCFF + 0.40 × Price_FCFE",
        }




def blend_dcf(
    ticker: str,
    price_fcff: float | None,
    price_fcfe: float | None,
    current_price_vnd: float | None = None,
    pv_terminal_value_fcff: float | None = None,
    enterprise_value_fcff: float | None = None,
) -> BlendResult:
    """Compute blended DCF: 60% FCFF + 40% FCFE.

    Quality checks performed:
    1. Valuation gap: |Price_FCFF / Price_FCFE − 1| > 25% → warning (audit Net Borrowing/CAPEX/NWC)
    2. TV weight: PV(TV_FCFF) / EV_FCFF > 70% → warning (sensitivity analysis required)
    3. Partial availability: if one price is None, warn and use available only.

    Args:
        price_fcff: FCFF per-share target (VND). From FCFFResult.target_price_vnd.
        price_fcfe: FCFE per-share target (VND). From FCFEResult.target_price_vnd.
        current_price_vnd: Current market price (VND/share) for upside calculation.
        pv_terminal_value_fcff: PV of terminal value from FCFF model (VND bn).
        enterprise_value_fcff: Enterprise value from FCFF model (VND bn).
    """
    warnings: list[str] = []
    is_draft_only: bool = False

    # ── Quality check 1: valuation gap ────────────────────────────────────
    gap: float | None = None
    if price_fcff is not None and price_fcfe is not None and price_fcfe != 0:
        gap = abs(price_fcff / price_fcfe - 1)
        if gap > _GAP_WARN_THRESHOLD:
            is_draft_only = True
            warnings.append(
                f"FCFF vs FCFE gap = {gap:.1%} > 25% — "
                "cần kiểm tra Net Borrowing, CAPEX, NWC trước khi kết luận target price"
            )

    # ── Quality check 2: terminal value weight ────────────────────────────
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


    # ── Blend formula ──────────────────────────────────────────────────────
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

    # ── Upside and margin of safety ───────────────────────────────────────
    upside_pct: float | None = None
    margin_of_safety: float | None = None
    if target_price is not None and current_price_vnd and current_price_vnd > 0:
        upside_pct = (target_price - current_price_vnd) / current_price_vnd
        # Margin of Safety = (Intrinsic - Market) / Intrinsic
        margin_of_safety = (target_price - current_price_vnd) / target_price

    return BlendResult(
        ticker=ticker,
        price_fcff=price_fcff,
        price_fcfe=price_fcfe,
        target_price_dcf=target_price,
        current_price_vnd=current_price_vnd,
        upside_pct=upside_pct,
        margin_of_safety=margin_of_safety,
        valuation_gap_pct=gap,
        tv_weight_fcff=tv_weight,
        is_draft_only=is_draft_only,
        warnings=warnings,
    )
