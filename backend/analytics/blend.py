"""60% FCFF + 40% P/E Forward blended target price.

Formula: Target Price = 0.60 × Price_FCFF + 0.40 × Price_PE_Forward
         where Price_PE_Forward = EPS_FY1 × Target_P/E

Rationale (VN pharma sector):
- FCFF (60%): enterprise-level intrinsic value, independent of capital structure.
- P/E Forward (40%): market-relative anchor; captures sector sentiment and
  near-term earnings power; avoids the leverage-assumption sensitivity that
  made FCFE unreliable when Net Borrowing data is incomplete.

Previous blend (FCFF + FCFE) was replaced because FCFE requires a complete
net-borrowing schedule; when debt data is missing the FCFE price is artificially
low and pulls the blend well below fair value.

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FCFF_WEIGHT: float = 0.60
PE_WEIGHT: float = 0.40
_GAP_WARN_THRESHOLD: float = 0.40   # warn if |Price_FCFF/Price_PE - 1| > 40%
_TV_WARN_THRESHOLD: float = 0.70    # warn if PV(TV) / EV > 70%


@dataclass
class BlendResult:
    """Output of the 60/40 FCFF + P/E Forward blend.

    Attributes:
        price_fcff: Per-share price from FCFF DCF model (VND/share).
        price_pe_forward: Per-share price from P/E forward model (VND/share).
        target_price_dcf: Blended target = 0.60×FCFF + 0.40×P/E_Forward (VND/share).
        upside_pct: (target_price - current_price) / current_price.
        margin_of_safety: (intrinsic_value - market_price) / intrinsic_value.
        valuation_gap_pct: |Price_FCFF / Price_PE - 1|; warn > 40%.
        is_draft_only: True if gap > 40% or only one price available.
    """
    ticker: str
    price_fcff: float | None
    price_pe_forward: float | None
    target_price_dcf: float | None
    current_price_vnd: float | None
    upside_pct: float | None
    margin_of_safety: float | None
    fcff_weight: float = FCFF_WEIGHT
    pe_weight: float = PE_WEIGHT
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
            "price_pe_forward_vnd": _r(self.price_pe_forward),
            "fcff_weight": self.fcff_weight,
            "pe_weight": self.pe_weight,
            "target_price_dcf_vnd": _r(self.target_price_dcf),
            "current_price_vnd": _r(self.current_price_vnd),
            "upside_pct": round(self.upside_pct, 4) if self.upside_pct is not None else None,
            "margin_of_safety": round(self.margin_of_safety, 4) if self.margin_of_safety is not None else None,
            "valuation_gap_pct": round(self.valuation_gap_pct, 4) if self.valuation_gap_pct is not None else None,
            "tv_weight_fcff": round(self.tv_weight_fcff, 4) if self.tv_weight_fcff is not None else None,
            "is_draft_only": self.is_draft_only,
            "warnings": self.warnings,
            "formula": "Target Price = 0.60 × Price_FCFF + 0.40 × Price_PE_Forward",
        }


def blend_dcf(
    ticker: str,
    price_fcff: float | None,
    price_pe_forward: float | None,
    current_price_vnd: float | None = None,
    pv_terminal_value_fcff: float | None = None,
    enterprise_value_fcff: float | None = None,
    # Legacy param — accepted but ignored (kept so old call-sites don't crash)
    price_fcfe: float | None = None,
) -> BlendResult:
    """Compute blended target: 60% FCFF + 40% P/E Forward.

    Quality checks:
    1. Valuation gap: |Price_FCFF / Price_PE - 1| > 40% → warning
    2. TV weight: PV(TV_FCFF) / EV_FCFF > 70% → warning
    3. Partial availability: if one price is None, fall back with warning.
    """
    warnings: list[str] = []
    is_draft_only: bool = False

    # ── Quality check 1: FCFF vs P/E gap ──────────────────────────────────
    gap: float | None = None
    if price_fcff is not None and price_pe_forward is not None and price_pe_forward != 0:
        gap = abs(price_fcff / price_pe_forward - 1)
        if gap > _GAP_WARN_THRESHOLD:
            is_draft_only = True
            warnings.append(
                f"FCFF vs P/E Forward gap = {gap:.1%} > 40% — "
                "kiểm tra lại giả định tăng trưởng EPS và WACC trước khi kết luận target price"
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
    if price_fcff is not None and price_pe_forward is not None:
        target_price = FCFF_WEIGHT * price_fcff + PE_WEIGHT * price_pe_forward
    elif price_fcff is not None:
        is_draft_only = True
        warnings.append(
            "Price_PE_Forward không có (EPS_FY1 unavailable) — dùng 100% FCFF. "
            "Không đúng trọng số 60/40; kết quả cần phê duyệt thủ công."
        )
        target_price = price_fcff
    elif price_pe_forward is not None:
        is_draft_only = True
        warnings.append(
            "Price_FCFF không có — dùng 100% P/E Forward. "
            "Không đúng trọng số 60/40; kết quả cần phê duyệt thủ công."
        )
        target_price = price_pe_forward

    # ── Upside and margin of safety ───────────────────────────────────────
    upside_pct: float | None = None
    margin_of_safety: float | None = None
    if target_price is not None and current_price_vnd and current_price_vnd > 0:
        upside_pct = (target_price - current_price_vnd) / current_price_vnd
        margin_of_safety = (target_price - current_price_vnd) / target_price

    return BlendResult(
        ticker=ticker,
        price_fcff=price_fcff,
        price_pe_forward=price_pe_forward,
        target_price_dcf=target_price,
        current_price_vnd=current_price_vnd,
        upside_pct=upside_pct,
        margin_of_safety=margin_of_safety,
        valuation_gap_pct=gap,
        tv_weight_fcff=tv_weight,
        is_draft_only=is_draft_only,
        warnings=warnings,
    )
