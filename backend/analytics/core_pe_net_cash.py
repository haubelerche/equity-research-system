"""Core P/E + Net Cash per share valuation (Guidance Section 11).

For cash-rich companies whose balance sheet carries significant liquid financial
assets, a simple P/E multiple applied to reported EPS over-values the operating
business while under-crediting the cash hoard.  The correct decomposition is:

  Intrinsic value = Core EPS × Target Core P/E + Net Cash per share

Where:
  Core EPS       = EPS_Forward − after-tax financial income per share
  Net Cash/share = (Cash + Short-Term Investments − Total Debt) / Shares
  after-tax FI   = net_financial_income × (1 − effective_tax_rate)

The financial income component is derived from the fact table:
  net_financial_income = VAS_EBIT − pure_operating_EBIT
  pure_operating_EBIT  = gross_profit + selling_expense + admin_expense
  (selling/admin expenses are stored as negative values in the fact table)

All monetary values are in VND (shares) or VND bn (balance sheet aggregates).
All arithmetic is deterministic Python — no LLM involvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.analytics._entry import entry_value
from backend.analytics.forecasting import ForecastArtifact
from backend.facts.normalizer import FactTable


def _get(table: FactTable, key: str, period: str) -> float | None:
    if not period:
        return None
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    return entry_value(entry)


@dataclass
class CorePENetCashResult:
    ticker: str
    period: str                           # latest historical FY, e.g. "2025FY"

    # ── Inputs ──────────────────────────────────────────────────────────────
    eps_forward: float | None             # EPS_FY1 from forecast (VND/share)
    target_core_pe: float                 # e.g. 19.0×

    cash: float | None                    # cash_and_equivalents.ending (VND bn)
    short_term_investments: float | None  # short_term_investments.ending (VND bn)
    total_debt: float | None              # interest-bearing debt (VND bn)
    shares_mn: float | None               # shares outstanding (millions)

    # ── Financial income strip ───────────────────────────────────────────────
    vas_ebit: float | None                # VAS "lợi nhuận từ HĐKD" (incl. fin. income)
    pure_ebit: float | None               # gross_profit + SGA only
    net_financial_income_vnd_bn: float | None  # VAS_EBIT − pure_EBIT
    effective_tax_rate: float             # from forecast tax policy or default

    # ── Computed ─────────────────────────────────────────────────────────────
    net_cash_vnd_bn: float | None         # cash + STI − total_debt
    net_cash_per_share_vnd: float | None
    ati_per_share_vnd: float | None       # after-tax financial income per share
    core_eps_vnd: float | None
    target_price_vnd: float | None

    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _r(v: float | None, d: int = 2) -> float | None:
            return round(v, d) if v is not None else None

        return {
            "ticker": self.ticker,
            "period": self.period,
            "eps_forward_vnd": _r(self.eps_forward, 0),
            "target_core_pe": self.target_core_pe,
            "cash_vnd_bn": _r(self.cash),
            "short_term_investments_vnd_bn": _r(self.short_term_investments),
            "total_debt_vnd_bn": _r(self.total_debt),
            "shares_mn": _r(self.shares_mn, 3),
            "vas_ebit_vnd_bn": _r(self.vas_ebit),
            "pure_ebit_vnd_bn": _r(self.pure_ebit),
            "net_financial_income_vnd_bn": _r(self.net_financial_income_vnd_bn),
            "effective_tax_rate": self.effective_tax_rate,
            "net_cash_vnd_bn": _r(self.net_cash_vnd_bn),
            "net_cash_per_share_vnd": _r(self.net_cash_per_share_vnd, 0),
            "ati_per_share_vnd": _r(self.ati_per_share_vnd, 0),
            "core_eps_vnd": _r(self.core_eps_vnd, 0),
            "target_price_vnd": round(self.target_price_vnd, 0) if self.target_price_vnd is not None else None,
            "formula": (
                "target = core_eps x target_core_pe + net_cash_per_share; "
                "core_eps = eps_forward - ati_per_share; "
                "net_cash = cash + STI - total_debt"
            ),
            "warnings": self.warnings,
        }


def compute_core_pe_net_cash(
    ticker: str,
    fact_table: FactTable,
    forecast: ForecastArtifact,
    target_core_pe: float = 19.0,
    shares_mn: float | None = None,
    financial_income_already_excluded: bool = False,
) -> CorePENetCashResult:
    """Compute Core P/E + Net Cash valuation per Guidance Section 11.

    Args:
        target_core_pe: Peer-derived target P/E for the core operating business.
            Default 19.0× reflects Vietnamese pharma sector median (18-22× range).
            Should be validated with peer-group analysis before publication.
        shares_mn: Override shares outstanding. If None, reads from fact_table.
        financial_income_already_excluded: Set True when eps_forward is derived
            from a forecast net income that already excludes financial income
            (i.e. the forecast model stripped financial income before computing EPS).
            When True, the ATI-per-share subtraction is skipped to avoid
            double-stripping.  Default False assumes eps_forward is derived from
            TOTAL net income (including financial income).
    """
    warnings: list[str] = []

    fy_periods = forecast.historical_periods
    latest_fy = fy_periods[-1] if fy_periods else None

    if not latest_fy:
        return CorePENetCashResult(
            ticker=ticker, period="", eps_forward=None, target_core_pe=target_core_pe,
            cash=None, short_term_investments=None, total_debt=None, shares_mn=None,
            vas_ebit=None, pure_ebit=None, net_financial_income_vnd_bn=None,
            effective_tax_rate=0.20, net_cash_vnd_bn=None, net_cash_per_share_vnd=None,
            ati_per_share_vnd=None, core_eps_vnd=None, target_price_vnd=None,
            warnings=["No historical periods in forecast — cannot compute Core P/E + Net Cash."],
        )

    # ── EPS Forward (FY+1) ───────────────────────────────────────────────────
    eps_forward: float | None = None
    if forecast.forecast_years:
        fy1 = forecast.forecast_years[0]
        eps_forward = fy1.eps if (fy1.eps and fy1.eps > 0) else None
    if eps_forward is None:
        warnings.append("EPS_FY1 unavailable — Core P/E + Net Cash target price blocked.")

    # ── Balance sheet: cash, STI, debt ───────────────────────────────────────
    cash = _get(fact_table, "cash_and_equivalents.ending", latest_fy)
    sti  = _get(fact_table, "short_term_investments.ending", latest_fy)
    # Resolve total debt: prefer total_debt.ending, fall back to ST + LT components
    total_debt = _get(fact_table, "total_debt.ending", latest_fy)
    if total_debt is None:
        std = _get(fact_table, "short_term_debt.ending", latest_fy)
        ltd = _get(fact_table, "long_term_debt.ending", latest_fy)
        if std is not None or ltd is not None:
            total_debt = (std or 0.0) + (ltd or 0.0)

    if cash is None:
        warnings.append(f"[{latest_fy}] cash_and_equivalents.ending missing.")
    if sti is None:
        warnings.append(f"[{latest_fy}] short_term_investments.ending missing — net cash may be understated.")
    if total_debt is None:
        warnings.append(f"[{latest_fy}] total_debt missing — net cash cannot be computed.")

    # ── Shares outstanding ────────────────────────────────────────────────────
    if shares_mn is None:
        _entry = fact_table.get("shares_outstanding.ending", {}).get(latest_fy)
        if _entry is not None:
            raw = entry_value(_entry)
            shares_mn = raw / 1_000_000.0 if raw > 1_000_000 else raw
    if shares_mn is None:
        warnings.append("shares_outstanding missing — per-share calculations blocked.")

    # ── Financial income strip ────────────────────────────────────────────────
    # VAS "lợi nhuận từ HĐKD" (ebit.total) includes net financial income from STI.
    # Pure operating EBIT = gross_profit + selling_expense + admin_expense.
    # (selling/admin are stored as negatives; their sum with gross_profit gives EBIT.)
    vas_ebit   = _get(fact_table, "ebit.total", latest_fy)
    gross_p    = _get(fact_table, "gross_profit.total", latest_fy)
    sell_exp   = _get(fact_table, "selling_expense.total", latest_fy)
    admin_exp  = _get(fact_table, "admin_expense.total", latest_fy)

    pure_ebit: float | None = None
    net_fi: float | None = None
    if gross_p is not None and (sell_exp is not None or admin_exp is not None):
        pure_ebit = gross_p + (sell_exp or 0.0) + (admin_exp or 0.0)
    if vas_ebit is not None and pure_ebit is not None:
        net_fi = vas_ebit - pure_ebit
        if net_fi < 0:
            warnings.append(
                f"[{latest_fy}] Derived net_financial_income={net_fi:.3f} bn is negative — "
                "check ebit.total vs gross_profit/SGA inputs."
            )
            net_fi = 0.0

    # ── Effective tax rate ────────────────────────────────────────────────────
    eff_tax = 0.20  # default
    if forecast.tax_policy is not None:
        eff_tax = forecast.tax_policy.effective_tax_rate

    # ── Per-share calculations (facts in VND bn → VND/share) ─────────────────
    net_cash_bn: float | None = None
    net_cash_per_share: float | None = None
    ati_per_share: float | None = None
    core_eps: float | None = None
    target_price: float | None = None

    if total_debt is not None:
        net_cash_bn = (cash or 0.0) + (sti or 0.0) - total_debt

    if net_cash_bn is not None and shares_mn is not None and shares_mn > 0:
        net_cash_per_share = net_cash_bn * 1_000.0 / shares_mn  # bn → VND/share

    if net_fi is not None and shares_mn is not None and shares_mn > 0:
        ati_vnd_bn = net_fi * (1.0 - eff_tax)
        ati_per_share = ati_vnd_bn * 1_000.0 / shares_mn

    if eps_forward is not None:
        # Assumes eps_forward is derived from TOTAL net income (including financial
        # income).  If forecast NI already excludes financial income, set
        # financial_income_already_excluded=True to skip this subtraction and
        # avoid double-stripping financial income from EPS.
        if financial_income_already_excluded:
            core_eps = eps_forward
        else:
            core_eps = eps_forward - (ati_per_share or 0.0)
        if core_eps <= 0:
            warnings.append(
                f"core_eps={core_eps:.0f} VND is non-positive — financial income strip "
                "exceeds EPS_Forward; result unreliable."
            )
            core_eps = None

    if core_eps is not None and net_cash_per_share is not None:
        target_price = core_eps * target_core_pe + net_cash_per_share
    elif core_eps is not None:
        warnings.append("Net cash per share unavailable — target price excludes net cash adjustment.")
        target_price = core_eps * target_core_pe

    return CorePENetCashResult(
        ticker=ticker,
        period=latest_fy,
        eps_forward=eps_forward,
        target_core_pe=target_core_pe,
        cash=cash,
        short_term_investments=sti,
        total_debt=total_debt,
        shares_mn=shares_mn,
        vas_ebit=vas_ebit,
        pure_ebit=pure_ebit,
        net_financial_income_vnd_bn=net_fi,
        effective_tax_rate=eff_tax,
        net_cash_vnd_bn=net_cash_bn,
        net_cash_per_share_vnd=net_cash_per_share,
        ati_per_share_vnd=ati_per_share,
        core_eps_vnd=core_eps,
        target_price_vnd=target_price,
        warnings=warnings,
    )
