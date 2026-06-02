"""Deterministic financial ratio calculations.

Input:  FactTable (line_item_code → period_key → float)
Output: RatioTable (ratio_key → period_key → float | None)

All arithmetic is explicit Python — no LLM involvement.
"""
from __future__ import annotations

from typing import Any

from backend.facts.normalizer import FactTable
RatioTable = dict[str, dict[str, float | None]]


def _get(table: FactTable, key: str, period: str) -> float | None:
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    return entry.value if hasattr(entry, "value") else float(entry)


def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0.0:
        return None
    return num / den


def _yoy_growth(curr: float | None, prev: float | None) -> float | None:
    if curr is None or prev is None or prev == 0.0:
        return None
    return (curr - prev) / abs(prev)


def _prefer(fact_table: FactTable, key: str, period: str, fallback: float | None) -> float | None:
    """Return the pre-computed derived value from fact_table if present, else fallback.

    Callers should pass the output of compute_derived() so that metrics like
    gross_margin, net_margin, debt_to_equity that are computed there are reused
    here rather than recomputed independently. This makes normalizer.compute_derived()
    the single source of truth for those formulas.
    """
    v = _get(fact_table, key, period)
    return v if v is not None else fallback


def compute_ratios(fact_table: FactTable) -> RatioTable:
    """Compute all ratio metrics for every available period.

    Expected contract: callers pass the output of normalizer.compute_derived()
    so that derived metrics (gross_margin, net_margin, ebitda_margin,
    debt_to_equity, free_cash_flow.total) are read from the table rather than
    recomputed. compute_derived() is the single source of truth for those formulas.

    Returns RatioTable where None means the ratio cannot be computed
    (missing inputs or division by zero).
    """
    all_periods = sorted({p for periods in fact_table.values() for p in periods})
    fy_periods = [p for p in all_periods if p.endswith("FY")]
    fy_periods_sorted = sorted(fy_periods)

    ratios: RatioTable = {}

    def _set(key: str, period: str, value: float | None) -> None:
        if value is not None:
            ratios.setdefault(key, {})[period] = round(value, 6)

    for period in fy_periods_sorted:
        rev = _get(fact_table, "revenue.net", period)
        gp = _get(fact_table, "gross_profit.total", period)
        ni = _get(fact_table, "net_income.parent", period)
        ebitda = _get(fact_table, "ebitda.total", period)
        ebit = _get(fact_table, "ebit.total", period)
        equity = _get(fact_table, "equity.parent", period)
        assets = _get(fact_table, "total_assets.ending", period)
        total_debt = _get(fact_table, "total_debt.ending", period)
        total_liab = _get(fact_table, "total_liabilities.ending", period)
        curr_assets = _get(fact_table, "current_assets.ending", period)
        curr_liab = _get(fact_table, "current_liabilities.ending", period)
        interest = _get(fact_table, "interest_expense.total", period)
        pbt = _get(fact_table, "profit_before_tax.total", period)
        eps = _get(fact_table, "eps.basic", period)
        ocf = _get(fact_table, "operating_cash_flow.total", period)
        capex = _get(fact_table, "capex.total", period)
        cash = _get(fact_table, "cash_and_equivalents.ending", period)
        inv = _get(fact_table, "inventory.ending", period)
        pbt_tax = _get(fact_table, "profit_before_tax.total", period)

        # Profitability — prefer values already in FactTable (from compute_derived)
        _set("gross_margin", period, _prefer(fact_table, "gross_margin", period, _safe_div(gp, rev)))
        _set("ebitda_margin", period, _prefer(fact_table, "ebitda_margin", period, _safe_div(ebitda, rev)))
        _set("ebit_margin", period, _safe_div(ebit, rev))
        _set("net_margin", period, _prefer(fact_table, "net_margin", period, _safe_div(ni, rev)))

        # Returns
        _set("roe", period, _safe_div(ni, equity))
        _set("roa", period, _safe_div(ni, assets))
        roa = _safe_div(ni, assets)
        # ROCE: use interest-bearing debt only; fall back to equity-only if debt missing
        roce_base = (equity or 0) + (total_debt or 0)
        _set("roce", period, _safe_div(ni, roce_base if roce_base > 0 else None))

        # Leverage: ONLY use interest-bearing debt — do NOT proxy with total_liabilities
        _set("debt_to_equity", period, _prefer(fact_table, "debt_to_equity", period, _safe_div(total_debt, equity)))
        _set("net_debt_to_equity", period,
             _safe_div(
                 ((total_debt or 0) - (cash or 0)) if total_debt is not None else None,
                 equity,
             ))
        # Interest coverage: use pbt + |interest| / |interest|
        if interest is not None and interest != 0.0 and pbt is not None:
            ebit_approx = pbt - interest  # interest_expense is negative in our data
            _set("interest_coverage", period, _safe_div(ebit_approx, abs(interest)))

        # Liquidity
        _set("current_ratio", period, _safe_div(curr_assets, curr_liab))
        if curr_assets is not None and inv is not None and curr_liab:
            _set("quick_ratio", period, _safe_div(curr_assets - inv, curr_liab))

        # Cash flow — CAPEX is stored negative (CFS outflow): FCF = OCF + CAPEX_signed
        # Prefer free_cash_flow.total from FactTable (set by compute_derived); recompute as fallback.
        _set("ocf_margin", period, _safe_div(ocf, rev))
        fcf_canonical = _get(fact_table, "free_cash_flow.total", period)
        fcf = fcf_canonical if fcf_canonical is not None else (
            (ocf + capex) if (ocf is not None and capex is not None) else None
        )
        if fcf is not None:
            _set("fcf_margin", period, _safe_div(fcf, rev))
            _set("fcf_absolute_bn", period, fcf)
        _set("ocf_to_net_income", period, _safe_div(ocf, ni))

        # Pharma-specific efficiency metrics
        # ROIC = EBIT(1-T) / Invested Capital; use net income / (equity + total_debt) as proxy
        if ni is not None and equity is not None:
            invested_capital = equity + (total_debt or 0.0)
            _set("roic", period, _safe_div(ni, invested_capital if invested_capital > 0 else None))

        # Inventory turnover (times/year) = COGS / avg_inventory (use ending as proxy)
        cogs_abs = abs(_get(fact_table, "cogs.total", period) or 0.0) or None
        if cogs_abs and inv and inv > 0:
            _set("inventory_turnover", period, _safe_div(cogs_abs, inv))

    # YoY growth rates (need consecutive periods)
    for i, period in enumerate(fy_periods_sorted):
        if i == 0:
            continue
        prev = fy_periods_sorted[i - 1]

        for metric, key in [
            ("revenue_growth", "revenue.net"),
            ("net_income_growth", "net_income.parent"),
            ("eps_growth", "eps.basic"),
            ("gross_profit_growth", "gross_profit.total"),
        ]:
            _set(metric, period, _yoy_growth(
                _get(fact_table, key, period),
                _get(fact_table, key, prev),
            ))

    return ratios


def compute_market_ratios(
    fact_table: FactTable,
    market_price_vnd: float | None,
    shares_mn: float | None,
) -> RatioTable:
    """Compute valuation and market-based ratios requiring price + shares outstanding.

    Keys added: pe, pb, ps, p_ocf, ev_ebitda, bvps, market_cap_bn,
                ccc (cash conversion cycle in days), inventory_days,
                receivable_days, payable_days.

    All per-share arithmetic uses shares_mn (millions of shares).
    Market cap in VND bn = price * shares_mn / 1000.
    BVPS in VND = equity_bn * 1e9 / (shares_mn * 1e6).
    """
    all_periods = sorted({p for periods in fact_table.values() for p in periods})
    fy_periods = sorted(p for p in all_periods if p.endswith("FY"))

    ratios: RatioTable = {}

    def _set(key: str, period: str, value: float | None) -> None:
        if value is not None:
            ratios.setdefault(key, {})[period] = round(value, 6)

    for period in fy_periods:
        rev = _get(fact_table, "revenue.net", period)
        ni = _get(fact_table, "net_income.parent", period)
        equity = _get(fact_table, "equity.parent", period)
        ebitda = _get(fact_table, "ebitda.total", period)
        ocf = _get(fact_table, "operating_cash_flow.total", period)
        total_debt = _get(fact_table, "total_debt.ending", period)
        cash = _get(fact_table, "cash_and_equivalents.ending", period)
        eps_vnd = _get(fact_table, "eps.basic", period)
        inv = _get(fact_table, "inventory.ending", period)
        receivables = _get(fact_table, "accounts_receivable.ending", period)
        payables = _get(fact_table, "accounts_payable.ending", period)
        cogs = _get(fact_table, "cogs.total", period)

        # Per-share basis (all values in tỷ VND, shares in millions)
        # BVPS (VND) = equity (tỷ VND) × 1e9 / (shares_mn × 1e6)
        if equity is not None and shares_mn and shares_mn > 0:
            bvps = (equity * 1e9) / (shares_mn * 1e6)   # VND/share
            _set("bvps", period, bvps)
        else:
            bvps = None

        # Market cap (tỷ VND) = price × shares_mn × 1e6 / 1e9
        market_cap_bn: float | None = None
        if market_price_vnd and shares_mn and shares_mn > 0:
            market_cap_bn = (market_price_vnd * shares_mn * 1e6) / 1e9
            _set("market_cap_bn", period, market_cap_bn)

        # P/E
        if market_price_vnd and eps_vnd and eps_vnd > 0:
            _set("pe", period, market_price_vnd / eps_vnd)

        # P/B
        if market_price_vnd and bvps and bvps > 0:
            _set("pb", period, market_price_vnd / bvps)

        # P/S  = market_cap_bn / revenue_bn
        if market_cap_bn and rev and rev > 0:
            _set("ps", period, market_cap_bn / rev)

        # P/OCF
        if market_cap_bn and ocf and ocf != 0:
            _set("p_ocf", period, market_cap_bn / ocf)

        # EV/EBITDA: EV = market_cap + net_debt
        if market_cap_bn and ebitda and ebitda > 0:
            net_debt_bn = (total_debt or 0) - (cash or 0)
            ev = market_cap_bn + net_debt_bn
            _set("ev_ebitda", period, ev / ebitda)

        # Cash conversion cycle (days)
        # Days = (value / revenue) × 365; COGS used for inventory and payables
        if rev and rev > 0:
            _cogs = abs(cogs) if cogs is not None else None
            if receivables is not None:
                inv_days = (receivables / rev) * 365
                _set("receivable_days", period, inv_days)
            if inv is not None and _cogs and _cogs > 0:
                inv_turn_days = (inv / _cogs) * 365
                _set("inventory_days", period, inv_turn_days)
            if payables is not None and _cogs and _cogs > 0:
                pay_days = (payables / _cogs) * 365
                _set("payable_days", period, pay_days)

        # CCC = receivable_days + inventory_days - payable_days
        rec = ratios.get("receivable_days", {}).get(period)
        inv_d = ratios.get("inventory_days", {}).get(period)
        pay_d = ratios.get("payable_days", {}).get(period)
        if rec is not None or inv_d is not None or pay_d is not None:
            ccc = (rec or 0) + (inv_d or 0) - (pay_d or 0)
            _set("ccc", period, ccc)

    return ratios


def detect_abnormal_movements(
    ratios: RatioTable,
    market_ratios: RatioTable,
    fy_periods: list[str],
    rel_threshold: float = 0.25,
    margin_threshold_pp: float = 5.0,
) -> list[dict]:
    """Flag ratio movements that exceed thresholds.

    Rules:
    - Relative change > rel_threshold (25%) for ratio/EPS/EPS growth
    - Margin change > margin_threshold_pp percentage points
    - Sign flip (positive → negative or vice versa)
    Returns list of {metric, period, prev, curr, change, flag_reason}.
    """
    _MARGIN_KEYS = {"gross_margin", "net_margin", "ebitda_margin", "ebit_margin", "roe", "roa"}
    _REL_KEYS = {"revenue_growth", "net_income_growth", "eps_growth", "pe", "pb", "ev_ebitda",
                 "debt_to_equity", "current_ratio"}

    flags: list[dict] = []
    combined = {**ratios, **market_ratios}

    for i, period in enumerate(fy_periods):
        if i == 0:
            continue
        prev_period = fy_periods[i - 1]

        for metric, period_vals in combined.items():
            curr = period_vals.get(period)
            prev = period_vals.get(prev_period)
            if curr is None or prev is None or prev == 0:
                continue

            flag_reason: str | None = None

            if metric in _MARGIN_KEYS:
                change_pp = (curr - prev) * 100
                if abs(change_pp) > margin_threshold_pp:
                    flag_reason = f"Thay đổi {change_pp:+.1f}pp > {margin_threshold_pp}pp"
            elif metric in _REL_KEYS:
                rel_change = (curr - prev) / abs(prev)
                if abs(rel_change) > rel_threshold:
                    flag_reason = f"Thay đổi {rel_change:+.1%} > {rel_threshold:.0%}"

            if prev > 0 and curr < 0:
                flag_reason = (flag_reason or "") + " | Đổi dấu âm"
            elif prev < 0 and curr > 0:
                flag_reason = (flag_reason or "") + " | Đổi dấu dương"

            if flag_reason:
                flags.append({
                    "metric": metric,
                    "period": period,
                    "prev_period": prev_period,
                    "prev": round(prev, 4),
                    "curr": round(curr, 4),
                    "flag_reason": flag_reason.strip(" |"),
                })

    return flags


def ratio_table_for_display(ratios: RatioTable, periods: list[str]) -> dict[str, dict[str, str]]:
    """Format ratio values as display strings for reporting."""
    _PCT = {
        "gross_margin", "ebitda_margin", "ebit_margin", "net_margin",
        "roe", "roa", "roce", "roic", "ocf_margin", "fcf_margin",
        "revenue_growth", "net_income_growth", "eps_growth", "gross_profit_growth",
    }
    out: dict[str, dict[str, str]] = {}
    for key, period_vals in ratios.items():
        out[key] = {}
        for p in periods:
            v = period_vals.get(p)
            if v is None:
                out[key][p] = "—"
            elif key in _PCT:
                out[key][p] = f"{v * 100:.1f}%"
            else:
                out[key][p] = f"{v:.2f}x"
    return out
