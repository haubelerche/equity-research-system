"""Comprehensive sensitivity analysis for 60% FCFF + 40% FCFE DCF valuation.

Official blend: Target Price = 0.60 × Price_FCFF + 0.40 × Price_FCFE

Implements all sensitivity matrices required by the valuation handbook:

1. build_fcff_sensitivity_table  — WACC × terminal_growth → Price_FCFF
2. build_fcfe_sensitivity_table  — Re × terminal_growth   → Price_FCFE
3. build_blend_sensitivity_table — Price_FCFF × Price_FCFE → Target Price_DCF (60/40)
4. build_pe_sensitivity_table    — EPS_FY1 × Target P/E   → Target Price_PE (supplementary)
5. build_ev_ebitda_sensitivity_table — EBITDA_FY1 × EV/EBITDA multiple → Price (supplementary)
6. build_sensitivity_table       — backward-compatible WACC × g (simplified FCF from dcf.py)

Quality check helpers:
- compute_tv_weight(pv_tv, ev) → float + warning flag
- compute_valuation_gap(price_fcff, price_fcfe) → float + warning flag

All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import replace as _dc_replace
from typing import Any

from backend.analytics.dcf import DCFAssumptions, FactTable, run_dcf

# ── Default grid ranges (from valuation handbook) ─────────────────────────────
_DEFAULT_WACC_RANGE = [0.08, 0.09, 0.10, 0.11, 0.12]
_DEFAULT_RE_RANGE   = [0.09, 0.10, 0.11, 0.12, 0.13]
_DEFAULT_G_RANGE    = [0.02, 0.025, 0.03, 0.035, 0.04]

_TV_WARN_THRESHOLD  = 0.70   # PV(TV) / EV
_GAP_WARN_THRESHOLD = 0.25   # |Price_FCFF/Price_FCFE - 1|


def _centered_range(base: float, step: float = 0.01, points_each_side: int = 2) -> list[float]:
    return [
        round(base + i * step, 4)
        for i in range(-points_each_side, points_each_side + 1)
        if base + i * step > 0
    ]


# ── Quality check helpers ──────────────────────────────────────────────────────

def compute_tv_weight(
    pv_terminal_value: float | None,
    enterprise_value: float | None,
) -> dict[str, Any]:
    """Return TV weight and warning if weight > 70%.

    Returns:
        {"tv_weight": float|None, "warning": str|None, "status": "ok"|"high"|"critical"}
    """
    if pv_terminal_value is None or enterprise_value is None or enterprise_value <= 0:
        return {"tv_weight": None, "warning": None, "status": "unknown"}

    weight = pv_terminal_value / enterprise_value
    if weight > 0.85:
        status = "critical"
        warning = (
            f"Terminal value chiếm {weight:.1%} EV — rất rủi ro. "
            "Không nên kết luận target price nếu không có luận cứ tăng trưởng dài hạn."
        )
    elif weight > _TV_WARN_THRESHOLD:
        status = "high"
        warning = (
            f"Terminal value chiếm {weight:.1%} EV — bắt buộc sensitivity "
            "WACC × g và cảnh báo trong báo cáo."
        )
    else:
        status = "ok"
        warning = None

    return {"tv_weight": round(weight, 4), "warning": warning, "status": status}


def compute_valuation_gap(
    price_fcff: float | None,
    price_fcfe: float | None,
) -> dict[str, Any]:
    """Return percentage gap between FCFF and FCFE target prices and a warning.

    Gap = |Price_FCFF / Price_FCFE − 1|. Warn if > 25%.

    Returns:
        {"gap_pct": float|None, "warning": str|None, "status": "ok"|"high"|"invalid"}
    """
    if price_fcff is None or price_fcfe is None or price_fcfe == 0:
        return {"gap_pct": None, "warning": None, "status": "invalid"}

    gap = abs(price_fcff / price_fcfe - 1)
    if gap > _GAP_WARN_THRESHOLD:
        status = "high"
        warning = (
            f"FCFF vs FCFE gap = {gap:.1%} > 25% — "
            "cần kiểm tra Net Borrowing, Net Debt, CAPEX và NWC trước khi xuất target price."
        )
    else:
        status = "ok"
        warning = None

    return {"gap_pct": round(gap, 4), "warning": warning, "status": status}


# ── 1. FCFF sensitivity: WACC × terminal_growth ───────────────────────────────

def build_fcff_sensitivity_table(
    ticker: str,
    forecast: Any,           # ForecastArtifact from forecasting.py
    fact_table: FactTable,
    base_wacc_assumptions: Any | None = None,   # WACCAssumptions from fcff.py
    wacc_range: list[float] | None = None,
    g_range: list[float] | None = None,
    shares_mn: float | None = None,
    current_price_vnd: float | None = None,
    base_terminal_growth: float | None = None,
) -> dict[str, Any]:
    """WACC × terminal_growth sensitivity for FCFF.

    Each cell = Price_FCFF (VND/share) or None if WACC ≤ g.

    Returns:
        {
          "wacc_range": [...],
          "g_range": [...],
          "matrix": {"0.080": {"0.02": 95000, ...}, ...},
          "unit": "VND/share",
          "warnings": [...],
        }
    """
    from backend.analytics.fcff import WACCAssumptions, compute_fcff

    if g_range is None:
        g_range = _DEFAULT_G_RANGE
    if base_terminal_growth is None:
        base_terminal_growth = 0.03 if 0.03 in g_range else g_range[len(g_range) // 2]
    if base_wacc_assumptions is None:
        base_wacc_assumptions = WACCAssumptions()
    if wacc_range is None:
        base_wacc = base_wacc_assumptions.wacc_override or base_wacc_assumptions.cost_of_equity
        wacc_range = _centered_range(base_wacc)

    matrix: dict[str, dict[str, float | None]] = {}
    all_warnings: list[str] = []

    for wacc_val in wacc_range:
        w_key = f"{wacc_val:.3f}"
        matrix[w_key] = {}
        for g_val in g_range:
            g_key = _g_key(g_val)
            if wacc_val <= g_val:
                matrix[w_key][g_key] = None   # INVALID: WACC must exceed g
                continue
            # Override WACC directly while preserving all other assumptions
            assumptions = _dc_replace(base_wacc_assumptions, wacc_override=wacc_val)
            result = compute_fcff(
                ticker=ticker,
                forecast=forecast,
                fact_table=fact_table,
                current_price_vnd=current_price_vnd,
                terminal_growth=g_val,
                wacc_assumptions=assumptions,
                shares_mn=shares_mn,
            )
            all_warnings.extend(result.warnings)
            val = result.target_price_vnd
            matrix[w_key][g_key] = round(val, 0) if val is not None else None

    return {
        "wacc_range": wacc_range,
        "g_range": g_range,
        "matrix": matrix,
        "unit": "VND/share (Price_FCFF)",
        "base_wacc": round(base_wacc_assumptions.wacc_override or base_wacc_assumptions.cost_of_equity, 4),
        "base_terminal_growth": round(base_terminal_growth, 4),
        "warnings": list(dict.fromkeys(all_warnings)),
    }


# ── 2. FCFE sensitivity: Re × terminal_growth ─────────────────────────────────

def build_fcfe_sensitivity_table(
    ticker: str,
    forecast: Any,           # ForecastArtifact
    fact_table: FactTable,
    base_coe_assumptions: Any | None = None,    # CostOfEquityAssumptions from fcfe.py
    re_range: list[float] | None = None,
    g_range: list[float] | None = None,
    shares_mn: float | None = None,
    current_price_vnd: float | None = None,
    net_borrowing_schedule: dict[str, float] | None = None,
    base_terminal_growth: float | None = None,
) -> dict[str, Any]:
    """Re × terminal_growth sensitivity for FCFE.

    Each cell = Price_FCFE (VND/share) or None if Re ≤ g.

    Args:
        net_borrowing_schedule: {label: net_borrowing} from debt_schedule.net_borrowing_schedule().
            Passed through to every compute_fcfe call so the grid uses driver-based NB,
            not the stable-leverage (NB=0) default.

    Returns:
        {
          "re_range": [...],
          "g_range": [...],
          "matrix": {"0.090": {"0.02": 88000, ...}, ...},
          "unit": "VND/share",
          "warnings": [...],
        }
    """
    from backend.analytics.fcfe import CostOfEquityAssumptions, compute_fcfe

    if g_range is None:
        g_range = _DEFAULT_G_RANGE
    if base_terminal_growth is None:
        base_terminal_growth = 0.03 if 0.03 in g_range else g_range[len(g_range) // 2]
    if base_coe_assumptions is None:
        base_coe_assumptions = CostOfEquityAssumptions()
    if re_range is None:
        re_range = _centered_range(base_coe_assumptions.cost_of_equity)

    matrix: dict[str, dict[str, float | None]] = {}
    all_warnings: list[str] = []

    for re_val in re_range:
        r_key = f"{re_val:.3f}"
        matrix[r_key] = {}
        for g_val in g_range:
            g_key = _g_key(g_val)
            if re_val <= g_val:
                matrix[r_key][g_key] = None   # INVALID: Re must exceed g
                continue
            # Override Re directly via re_override
            assumptions = _dc_replace(base_coe_assumptions, re_override=re_val)
            result = compute_fcfe(
                ticker=ticker,
                forecast=forecast,
                fact_table=fact_table,
                current_price_vnd=current_price_vnd,
                terminal_growth=g_val,
                cost_of_equity_assumptions=assumptions,
                shares_mn=shares_mn,
                net_borrowing_schedule=net_borrowing_schedule,
            )
            all_warnings.extend(result.warnings)
            val = result.target_price_vnd
            matrix[r_key][g_key] = round(val, 0) if val is not None else None

    return {
        "re_range": re_range,
        "g_range": g_range,
        "matrix": matrix,
        "unit": "VND/share (Price_FCFE)",
        "base_re": round(base_coe_assumptions.cost_of_equity, 4),
        "base_terminal_growth": round(base_terminal_growth, 4),
        "warnings": list(dict.fromkeys(all_warnings)),
    }


# ── 3. Blend sensitivity: Price_FCFF × Price_FCFE → Target Price_DCF ──────────

def build_blend_sensitivity_table(
    price_fcff_range: list[float],
    price_fcfe_range: list[float],
    current_price_vnd: float | None = None,
    fcff_weight: float = 0.60,
    fcfe_weight: float = 0.40,
) -> dict[str, Any]:
    """60/40 blend sensitivity grid.

    Rows = Price_FCFF values, Columns = Price_FCFE values.
    Each cell = fcff_weight × Price_FCFF + fcfe_weight × Price_FCFE.

    Returns:
        {
          "price_fcff_range": [...],
          "price_fcfe_range": [...],
          "matrix": {
              "95000": {"80000": 89000, "90000": 93000, ...},
              ...
          },
          "unit": "VND/share (Target Price_DCF)",
          "formula": "0.60 × Price_FCFF + 0.40 × Price_FCFE",
        }
    """
    matrix: dict[str, dict[str, float]] = {}
    for p_fcff in price_fcff_range:
        row_key = str(int(round(p_fcff, 0)))
        matrix[row_key] = {}
        for p_fcfe in price_fcfe_range:
            col_key = str(int(round(p_fcfe, 0)))
            blend = round(fcff_weight * p_fcff + fcfe_weight * p_fcfe, 0)
            matrix[row_key][col_key] = blend

    # Compute upside range if market price provided
    upside_range: dict[str, Any] = {}
    if current_price_vnd and current_price_vnd > 0:
        all_blends = [
            fcff_weight * pf + fcfe_weight * pe
            for pf in price_fcff_range
            for pe in price_fcfe_range
        ]
        upside_range = {
            "min_upside": round(min(all_blends) / current_price_vnd - 1, 4),
            "max_upside": round(max(all_blends) / current_price_vnd - 1, 4),
            "current_price_vnd": current_price_vnd,
        }

    return {
        "price_fcff_range": price_fcff_range,
        "price_fcfe_range": price_fcfe_range,
        "matrix": matrix,
        "unit": "VND/share (Target Price_DCF)",
        "formula": f"{fcff_weight} × Price_FCFF + {fcfe_weight} × Price_FCFE",
        "upside_range": upside_range,
    }


# ── 4. P/E sensitivity: EPS_FY1 × Target P/E ─────────────────────────────────

def build_pe_sensitivity_table(
    eps_fy1_range: list[float],
    target_pe_range: list[float],
    current_price_vnd: float | None = None,
    pe_label: str = "Forward P/E",
) -> dict[str, Any]:
    """EPS_FY1 × Target P/E → Target Price_PE.

    Formula: Target Price_PE = EPS_FY1 × Target Forward P/E

    Rows = EPS values (VND/share), Columns = P/E multiples.

    Args:
        eps_fy1_range: List of EPS_FY1 values (VND/share).
        target_pe_range: List of P/E multiples (e.g. [12, 14, 16, 18, 20]).
        current_price_vnd: For upside computation in each cell.
        pe_label: "Trailing P/E" or "Forward P/E" — label only, no calc change.

    Returns:
        {
          "eps_range": [...],
          "pe_range": [...],
          "matrix": {"5000": {"12": 60000, "14": 70000, ...}, ...},
          "unit": "VND/share",
          "formula": "EPS_FY1 × Target P/E",
        }
    """
    matrix: dict[str, dict[str, Any]] = {}
    for eps in eps_fy1_range:
        eps_key = str(int(round(eps, 0)))
        matrix[eps_key] = {}
        for pe in target_pe_range:
            pe_key = str(pe)
            target = round(eps * pe, 0)
            if current_price_vnd and current_price_vnd > 0:
                upside = round(target / current_price_vnd - 1, 4)
                matrix[eps_key][pe_key] = {"price": target, "upside": upside}
            else:
                matrix[eps_key][pe_key] = {"price": target}

    return {
        "eps_range": eps_fy1_range,
        "pe_range": target_pe_range,
        "matrix": matrix,
        "unit": "VND/share",
        "pe_label": pe_label,
        "formula": "EPS_FY1 × Target P/E",
    }


# ── 5. EV/EBITDA sensitivity: EBITDA_FY1 × Multiple ──────────────────────────

def build_ev_ebitda_sensitivity_table(
    ebitda_fy1_range: list[float],
    target_multiple_range: list[float],
    net_debt_vnd_bn: float,
    shares_mn: float,
    minority_interest_vnd_bn: float = 0.0,
    non_operating_assets_vnd_bn: float = 0.0,
    current_price_vnd: float | None = None,
) -> dict[str, Any]:
    """EBITDA_FY1 × EV/EBITDA → Target Price via EV bridge.

    Formula:
        Target EV = EBITDA_FY1 × Multiple
        Equity Value = Target EV − Net Debt − Minority Interest + Non-operating Assets
        Price = Equity Value / Shares × 1000   (VND bn / mn shares × 1000 = VND/share)

    Critical: must bridge EV → Equity Value using net debt; do NOT skip this step.

    Args:
        ebitda_fy1_range: List of EBITDA values (VND bn).
        target_multiple_range: List of EV/EBITDA multiples.
        net_debt_vnd_bn: Net Debt = total_debt − cash (VND bn). Negative = net cash.
        shares_mn: Diluted shares outstanding (millions).
        minority_interest_vnd_bn: Minority interest deducted from EV (VND bn).
        non_operating_assets_vnd_bn: Non-operating investments added to Equity Value (VND bn).
        current_price_vnd: For upside computation (optional).
    """
    if shares_mn <= 0:
        return {
            "ebitda_range": ebitda_fy1_range,
            "multiple_range": target_multiple_range,
            "matrix": {},
            "unit": "VND/share",
            "warnings": ["shares_mn ≤ 0 — EV/EBITDA price cannot be computed"],
        }

    warnings: list[str] = []
    matrix: dict[str, dict[str, Any]] = {}

    for ebitda in ebitda_fy1_range:
        ebitda_key = str(int(round(ebitda, 0)))
        matrix[ebitda_key] = {}
        for mult in target_multiple_range:
            mult_key = str(mult)
            target_ev = ebitda * mult  # VND bn
            # EV → Equity Value bridge
            equity_val = target_ev - net_debt_vnd_bn - minority_interest_vnd_bn + non_operating_assets_vnd_bn
            if equity_val <= 0:
                matrix[ebitda_key][mult_key] = None
                warnings.append(
                    f"EBITDA={ebitda:.0f}bn × {mult}x → Equity Value âm ({equity_val:.0f}bn) — omitted"
                )
                continue
            price = round((equity_val / shares_mn) * 1_000, 0)  # VND/share
            if current_price_vnd and current_price_vnd > 0:
                upside = round(price / current_price_vnd - 1, 4)
                matrix[ebitda_key][mult_key] = {"price": price, "upside": upside}
            else:
                matrix[ebitda_key][mult_key] = {"price": price}

    return {
        "ebitda_range": ebitda_fy1_range,
        "multiple_range": target_multiple_range,
        "matrix": matrix,
        "unit": "VND/share",
        "formula": "Price = (EBITDA × Multiple − Net Debt − Minority Interest + Non-op Assets) / Shares × 1000",
        "net_debt_vnd_bn": net_debt_vnd_bn,
        "shares_mn": shares_mn,
        "warnings": list(dict.fromkeys(warnings)),
    }


# ── 6. Backward-compatible: simplified DCF WACC × g (uses dcf.py OCF-CAPEX FCF) ──

def build_sensitivity_table(
    ticker: str,
    fact_table: FactTable,
    base_assumptions: DCFAssumptions | None = None,
    wacc_range: list[float] | None = None,
    g_range: list[float] | None = None,
) -> dict[str, Any]:
    """WACC × terminal_growth sensitivity using simplified FCF = OCF − CAPEX.

    DEPRECATED in favour of build_fcff_sensitivity_table() which uses the
    proper FCFF = EBIT(1−T) + D&A − CAPEX − ΔNWC formula.
    Retained for backward compatibility with run_valuation.py.

    Returns:
        {
          "wacc_range": [...],
          "g_range": [...],
          "matrix": {"0.080": {"0.02": 45000, ...}, ...},
          "unit": "VND/share (simplified FCF = OCF − CAPEX)",
          "warnings": [...],
        }
    """
    if base_assumptions is None:
        base_assumptions = DCFAssumptions()
    if wacc_range is None:
        wacc_range = _DEFAULT_WACC_RANGE
    if g_range is None:
        g_range = _DEFAULT_G_RANGE

    matrix: dict[str, dict[str, float | None]] = {}
    all_warnings: list[str] = []

    for wacc in wacc_range:
        w_key = f"{wacc:.3f}"
        matrix[w_key] = {}
        for g in g_range:
            g_key = _g_key(g)
            if wacc <= g:
                matrix[w_key][g_key] = None
                continue
            assumptions = DCFAssumptions(
                wacc=wacc,
                terminal_growth=g,
                forecast_years=base_assumptions.forecast_years,
                fcf_growth_override=base_assumptions.fcf_growth_override,
            )
            result = run_dcf(ticker, fact_table, assumptions, scenario="sensitivity")
            all_warnings.extend(result.warnings)
            val = result.intrinsic_value_per_share_vnd
            matrix[w_key][g_key] = round(val, 0) if val is not None else None

    return {
        "wacc_range": wacc_range,
        "g_range": g_range,
        "matrix": matrix,
        "unit": "VND/share (simplified FCF = OCF − CAPEX)",
        "warnings": list(dict.fromkeys(all_warnings)),
    }


# ── 7. Operating sensitivity: revenue_growth × gross_margin → target price ────

def build_operating_sensitivity_table(
    ticker: str,
    fact_table: Any,
    base_forecast: Any,                    # ForecastArtifact from forecasting.py
    base_wacc_assumptions: Any | None = None,
    revenue_growth_range: list[float] | None = None,
    gross_margin_range: list[float] | None = None,
    shares_mn: float | None = None,
    current_price_vnd: float | None = None,
    terminal_growth: float = 0.03,
) -> dict[str, Any]:
    """Revenue growth rate × gross margin → FCFF target price.

    Varies two operating drivers independently while holding WACC and terminal
    growth fixed. Each cell re-runs the income statement forecast and FCFF
    valuation from scratch so EBIT, depreciation and CAPEX all update correctly.

    Rows: revenue_growth values (e.g. [-0.05, 0.00, 0.05, 0.10, 0.15]).
    Columns: gross_margin values (e.g. [0.38, 0.40, 0.43, 0.46, 0.49]).
    Cells: Price_FCFF (VND/share) or None if WACC invalid.

    Returns:
        {
          "revenue_growth_range": [...],
          "gross_margin_range": [...],
          "matrix": {"0.05": {"0.40": 55000, ...}, ...},
          "unit": "VND/share (Price_FCFF)",
          "base_revenue_growth": float | None,
          "base_gross_margin": float | None,
          "warnings": [...],
        }
    """
    from backend.analytics.forecasting import run_forecast, ForecastAssumptions
    from backend.analytics.fcff import WACCAssumptions, compute_fcff

    if base_wacc_assumptions is None:
        base_wacc_assumptions = WACCAssumptions()

    # Default ranges centred on base drivers
    base_rev_growth = base_forecast.revenue_cagr
    base_gross_margin_val = base_forecast.drivers.get("gross_margin", {}).get("value")

    if revenue_growth_range is None:
        if base_rev_growth is not None:
            revenue_growth_range = _centered_range(base_rev_growth, step=0.025, points_each_side=2)
        else:
            revenue_growth_range = [-0.05, 0.00, 0.05, 0.10, 0.15]

    if gross_margin_range is None:
        if base_gross_margin_val is not None:
            gross_margin_range = _centered_range(base_gross_margin_val, step=0.02, points_each_side=2)
        else:
            gross_margin_range = [0.35, 0.38, 0.41, 0.44, 0.47]

    matrix: dict[str, dict[str, float | None]] = {}
    all_warnings: list[str] = []

    for rev_g in revenue_growth_range:
        rg_key = f"{rev_g:.4f}".rstrip("0").rstrip(".")
        matrix[rg_key] = {}
        for gm in gross_margin_range:
            gm_key = f"{gm:.4f}".rstrip("0").rstrip(".")
            assump = ForecastAssumptions(
                revenue_growth_override=rev_g,
                gross_margin_override=gm,
                assumption_status="operating_sensitivity",
            )
            try:
                forecast_s = run_forecast(
                    ticker=ticker,
                    fact_table=fact_table,
                    assumptions=assump,
                    shares_mn=shares_mn,
                )
                result = compute_fcff(
                    ticker=ticker,
                    forecast=forecast_s,
                    fact_table=fact_table,
                    current_price_vnd=current_price_vnd,
                    terminal_growth=terminal_growth,
                    wacc_assumptions=base_wacc_assumptions,
                    shares_mn=shares_mn,
                )
                all_warnings.extend(result.warnings)
                val = result.target_price_vnd
                matrix[rg_key][gm_key] = round(val, 0) if val is not None else None
            except Exception as exc:
                all_warnings.append(
                    f"operating_sensitivity [{rev_g:.1%} growth, {gm:.1%} margin]: {exc}"
                )
                matrix[rg_key][gm_key] = None

    return {
        "revenue_growth_range": revenue_growth_range,
        "gross_margin_range": gross_margin_range,
        "matrix": matrix,
        "unit": "VND/share (Price_FCFF)",
        "base_revenue_growth": round(base_rev_growth, 4) if base_rev_growth is not None else None,
        "base_gross_margin": round(base_gross_margin_val, 4) if base_gross_margin_val is not None else None,
        "formula": "revenue_growth × gross_margin → income statement → FCFF → Price_FCFF",
        "warnings": list(dict.fromkeys(all_warnings)),
    }


# ── Helper ─────────────────────────────────────────────────────────────────────

def _g_key(g: float) -> str:
    """Consistent string key for terminal growth values."""
    return f"{g:.4f}".rstrip("0").rstrip(".")
