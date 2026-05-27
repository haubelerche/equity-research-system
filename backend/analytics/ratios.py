"""Deterministic financial ratio computation.

Computes per-period ratios from a FactTable (taxonomy_key → period_key → value).

Market-price-dependent ratios (P/E, P/B, P/S, market_cap, EV/EBITDA) are labelled
with a ``_at_current_price`` suffix when only a single current price is available
(``has_historical_prices=False``), to make it explicit that these are NOT historical
P/E / P/B values.  When the caller supplies per-period historical prices
(``has_historical_prices=True``), the canonical keys (``pe``, ``pb``, …) are used.

Non-price-dependent ratios (``bvps``, ``ccc``, ``inventory_days``, ``receivable_days``,
``payable_days``) always use the same key regardless of the flag.

Period key format: "{fiscal_year}{fiscal_period}"  e.g. "2024FY", "2025Q1"
"""
from __future__ import annotations

from typing import Any

# Re-export FactTable type for callers that import from this module.
from backend.facts.normalizer import FactTable

# RatioTable: metric_name → period_key → value (float | str)
RatioTable = dict[str, dict[str, Any]]

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_PCT = {
    "gross_margin", "ebitda_margin", "net_margin",
    "roe", "roa", "revenue_growth", "net_income_growth", "eps_growth",
    "debt_to_equity",  # kept as ratio, formatted as % for display
}

_MULTIPLE = {
    "pe", "pb", "ps", "p_ocf", "ev_ebitda",
    "pe_at_current_price", "pb_at_current_price", "ps_at_current_price",
    "p_ocf_at_current_price", "ev_ebitda_at_current_price",
}

_CURRENCY_BN = {
    "market_cap_bn",
    "market_cap_at_current_price_bn",
}


def ratio_table_for_display(ratio_table: RatioTable) -> RatioTable:
    """Return a copy of ratio_table with float values formatted as display strings.

    Formatting rules:
    - _PCT keys  → "XX.X%"
    - _MULTIPLE  → "XX.Xx"   (1 decimal place, trailing 'x')
    - _CURRENCY_BN → "XX,XXX.X"  (comma thousands, 1 decimal, no 'x')
    - bvps       → "XX,XXX"  (integer VND, comma thousands)
    - fallback   → "XX.XX"   (2 decimal places, no 'x')
    """
    display: RatioTable = {}
    for metric, periods in ratio_table.items():
        display[metric] = {}
        for period, v in periods.items():
            if not isinstance(v, (int, float)):
                display[metric][period] = v
                continue
            if metric in _PCT:
                display[metric][period] = f"{v * 100:.1f}%"
            elif metric in _MULTIPLE:
                display[metric][period] = f"{v:.1f}x"
            elif metric in _CURRENCY_BN:
                display[metric][period] = f"{v:,.1f}"
            elif metric == "bvps":
                display[metric][period] = f"{v:,.0f}"
            else:
                display[metric][period] = f"{v:.2f}"
    return display


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _safe_div(num: float | None, den: float | None) -> float | None:
    if num is None or den is None:
        return None
    if den == 0.0:
        return None
    return num / den


def _get(table: FactTable, key: str, period: str) -> float | None:
    return table.get(key, {}).get(period)


# ---------------------------------------------------------------------------
# Core ratio computation
# ---------------------------------------------------------------------------

def compute_ratios(fact_table: FactTable) -> RatioTable:
    """Compute non-price-dependent ratios for every period in fact_table.

    Returns a RatioTable keyed by metric_name → period_key → float.
    """
    all_periods: list[str] = sorted(
        {p for periods in fact_table.values() for p in periods}
    )

    result: RatioTable = {}

    for period in all_periods:
        def get(key: str) -> float | None:
            return _get(fact_table, key, period)

        # --- Growth rates (require previous FY) ---
        # Handled in compute_growth_ratios below; kept out of here for clarity.

        # --- Profitability ---
        rev = get("revenue.net")
        ni = get("net_income.parent")
        gp = get("gross_profit.total")
        ebitda = get("ebitda.total")

        gross_margin = _safe_div(gp, rev)
        if gross_margin is not None:
            result.setdefault("gross_margin", {})[period] = round(gross_margin, 6)

        ebitda_margin = _safe_div(ebitda, rev)
        if ebitda_margin is not None:
            result.setdefault("ebitda_margin", {})[period] = round(ebitda_margin, 6)

        net_margin = _safe_div(ni, rev)
        if net_margin is not None:
            result.setdefault("net_margin", {})[period] = round(net_margin, 6)

        # --- Balance-sheet ratios ---
        equity = get("equity.parent")
        total_assets = get("total_assets.ending")
        total_debt = get("total_debt.ending")

        roe = _safe_div(ni, equity)
        if roe is not None:
            result.setdefault("roe", {})[period] = round(roe, 6)

        roa = _safe_div(ni, total_assets)
        if roa is not None:
            result.setdefault("roa", {})[period] = round(roa, 6)

        de = _safe_div(total_debt, equity)
        if de is not None:
            result.setdefault("debt_to_equity", {})[period] = round(de, 6)

        current_assets = get("current_assets.ending")
        current_liabilities = get("current_liabilities.ending")
        current_ratio = _safe_div(current_assets, current_liabilities)
        if current_ratio is not None:
            result.setdefault("current_ratio", {})[period] = round(current_ratio, 4)

        # --- Per-share (non-price-dependent) ---
        shares_mn = get("shares_outstanding.mn")
        if shares_mn and shares_mn > 0:
            shares_units = shares_mn * 1_000_000

            if equity is not None:
                bvps = equity * 1_000_000_000 / shares_units  # equity in bn VND → VND/share
                result.setdefault("bvps", {})[period] = round(bvps, 2)

        # --- Working capital / CCC ---
        cogs = get("cogs.total")
        inventory = get("inventory.ending")
        receivables = get("receivables.ending")
        payables = get("payables.ending")

        inv_days = None
        if cogs and cogs != 0 and inventory is not None:
            inv_days = inventory / (cogs / 365)
            result.setdefault("inventory_days", {})[period] = round(inv_days, 1)

        rec_days = None
        if rev and rev != 0 and receivables is not None:
            rec_days = receivables / (rev / 365)
            result.setdefault("receivable_days", {})[period] = round(rec_days, 1)

        pay_days = None
        if cogs and cogs != 0 and payables is not None:
            pay_days = payables / (cogs / 365)
            result.setdefault("payable_days", {})[period] = round(pay_days, 1)

        if inv_days is not None and rec_days is not None and pay_days is not None:
            result.setdefault("ccc", {})[period] = round(inv_days + rec_days - pay_days, 1)

    return result


def compute_growth_ratios(fact_table: FactTable) -> RatioTable:
    """Compute YoY growth rates for FY periods.

    Pairs consecutive FY periods (e.g. 2023FY → 2024FY) and computes:
    - revenue_growth
    - net_income_growth
    - eps_growth
    """
    fy_periods = sorted(
        p for periods in fact_table.values() for p in periods if p.endswith("FY")
    )
    fy_periods = sorted(set(fy_periods))

    result: RatioTable = {}

    for i in range(1, len(fy_periods)):
        prev = fy_periods[i - 1]
        curr = fy_periods[i]

        def get(key: str, period: str) -> float | None:
            return _get(fact_table, key, period)

        for metric_key, fact_key in [
            ("revenue_growth", "revenue.net"),
            ("net_income_growth", "net_income.parent"),
            ("eps_growth", "eps.basic"),
        ]:
            prev_v = get(fact_key, prev)
            curr_v = get(fact_key, curr)
            growth = _safe_div(curr_v - prev_v if (curr_v is not None and prev_v is not None) else None, prev_v)
            if growth is not None:
                result.setdefault(metric_key, {})[curr] = round(growth, 6)

    return result


def compute_market_ratios(
    fact_table: FactTable,
    market_price_vnd: float | None,
    shares_mn: float | None,
    has_historical_prices: bool = False,
) -> RatioTable:
    """Compute market-price-dependent ratios for every period in fact_table.

    Parameters
    ----------
    fact_table:
        Normalized fact table from ``build_fact_table`` / ``compute_derived``.
    market_price_vnd:
        Current market price in VND.  When ``has_historical_prices=False`` this
        single price is applied to ALL periods — the resulting ratio keys are
        suffixed with ``_at_current_price`` to signal this explicitly.
    shares_mn:
        Shares outstanding in millions (used as a fallback if not in fact_table).
    has_historical_prices:
        When ``True``, the caller guarantees that ``market_price_vnd`` is the
        correct per-period price (historical price for that FY) and the canonical
        keys (``pe``, ``pb``, ``ps``, ``p_ocf``, ``ev_ebitda``, ``market_cap_bn``)
        are used.

        When ``False`` (default), the single current price is applied across all
        periods and keys are prefixed to make this transparent:
        ``pe_at_current_price``, ``pb_at_current_price``, ``ps_at_current_price``,
        ``p_ocf_at_current_price``, ``ev_ebitda_at_current_price``,
        ``market_cap_at_current_price_bn``.

    Returns
    -------
    RatioTable with market ratios keyed by the appropriate naming convention.
    """
    if market_price_vnd is None:
        return {}

    all_periods: list[str] = sorted(
        {p for periods in fact_table.values() for p in periods}
    )

    result: RatioTable = {}

    # Key name helper
    def _key(base: str) -> str:
        if has_historical_prices:
            return base
        suffix_map = {
            "pe": "pe_at_current_price",
            "pb": "pb_at_current_price",
            "ps": "ps_at_current_price",
            "p_ocf": "p_ocf_at_current_price",
            "ev_ebitda": "ev_ebitda_at_current_price",
            "market_cap_bn": "market_cap_at_current_price_bn",
        }
        return suffix_map.get(base, base)

    price = market_price_vnd  # single current price applied to all periods

    for period in all_periods:
        def get(key: str) -> float | None:
            return _get(fact_table, key, period)

        # Resolve shares: prefer fact_table, fall back to parameter
        sh_mn = get("shares_outstanding.mn") or shares_mn
        if not sh_mn or sh_mn <= 0:
            continue  # cannot compute any market ratio without share count

        shares_units = sh_mn * 1_000_000

        # market_cap in tỷ VND (bn VND)
        market_cap_bn = price * shares_units / 1_000_000_000
        result.setdefault(_key("market_cap_bn"), {})[period] = round(market_cap_bn, 1)

        # EPS in VND/share — fact stored in bn VND, convert: eps_bn * 1e9 / shares_units
        eps_bn = get("eps.basic")  # stored in bn VND in fact table? Check taxonomy.
        # eps.basic may be stored as VND/share directly (no unit conversion needed).
        # Convention: eps.basic is in VND/share (already per-share).
        eps_vnd = eps_bn  # treat as VND/share

        pe = _safe_div(price, eps_vnd)
        if pe is not None:
            result.setdefault(_key("pe"), {})[period] = round(pe, 2)

        # BVPS in VND/share
        equity_bn = get("equity.parent")  # bn VND
        if equity_bn is not None:
            bvps = equity_bn * 1_000_000_000 / shares_units
            pb = _safe_div(price, bvps)
            if pb is not None:
                result.setdefault(_key("pb"), {})[period] = round(pb, 2)

        # Revenue in bn VND → revenue per share in VND
        rev_bn = get("revenue.net")
        if rev_bn is not None:
            rps = rev_bn * 1_000_000_000 / shares_units
            ps = _safe_div(price, rps)
            if ps is not None:
                result.setdefault(_key("ps"), {})[period] = round(ps, 2)

        # Operating cash flow per share
        ocf_bn = get("operating_cash_flow.total")
        if ocf_bn is not None:
            ocf_per_share = ocf_bn * 1_000_000_000 / shares_units
            p_ocf = _safe_div(price, ocf_per_share)
            if p_ocf is not None:
                result.setdefault(_key("p_ocf"), {})[period] = round(p_ocf, 2)

        # EV/EBITDA: EV = market_cap + total_debt - cash (all in bn VND)
        ebitda_bn = get("ebitda.total")
        if ebitda_bn is not None and ebitda_bn != 0:
            total_debt_bn = get("total_debt.ending") or 0.0
            cash_bn = get("cash_and_equivalents.ending") or 0.0
            ev_bn = market_cap_bn + total_debt_bn - cash_bn
            ev_ebitda = _safe_div(ev_bn, ebitda_bn)
            if ev_ebitda is not None:
                result.setdefault(_key("ev_ebitda"), {})[period] = round(ev_ebitda, 2)

    return result


# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

_REL_KEYS = {
    "revenue_growth", "net_income_growth", "eps_growth",
    "pe", "pb", "ev_ebitda",
    "debt_to_equity", "current_ratio",
    "pe_at_current_price", "pb_at_current_price", "ev_ebitda_at_current_price",
}


def detect_abnormal_movements(
    ratio_table: RatioTable,
    threshold: float = 0.5,
) -> list[dict[str, Any]]:
    """Flag metrics where consecutive period values change by more than ``threshold``.

    Returns a list of dicts: {metric, period_from, period_to, value_from, value_to, pct_change}.
    Only metrics in ``_REL_KEYS`` are checked (relative / ratio metrics).
    Absolute metrics (e.g. margin %) should use absolute-difference thresholds — extend
    this function separately.
    """
    flags: list[dict[str, Any]] = []

    for metric, periods in ratio_table.items():
        if metric not in _REL_KEYS:
            continue
        sorted_periods = sorted(periods.keys())
        for i in range(1, len(sorted_periods)):
            prev_p = sorted_periods[i - 1]
            curr_p = sorted_periods[i]
            prev_v = periods[prev_p]
            curr_v = periods[curr_p]
            if not isinstance(prev_v, (int, float)) or not isinstance(curr_v, (int, float)):
                continue
            if prev_v == 0:
                continue
            pct_change = (curr_v - prev_v) / abs(prev_v)
            if abs(pct_change) > threshold:
                flags.append({
                    "metric": metric,
                    "period_from": prev_p,
                    "period_to": curr_p,
                    "value_from": prev_v,
                    "value_to": curr_v,
                    "pct_change": round(pct_change, 4),
                })

    return flags
