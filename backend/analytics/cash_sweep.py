"""Cash sweep reconciliation and equity roll-forward validation.

Validates that ending cash and equity can be reconstructed from opening balances
plus operating/investing/financing flows. Emits warnings when the delta in
Net Debt cannot be explained by the known cash flows.

All arithmetic is deterministic Python — no LLM involvement.
All monetary values in VND bn consistent with rest of codebase.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class CashSweepResult:
    """Result of one year's cash reconciliation sweep."""
    year_label: str
    opening_cash: float
    cfo: float
    capex: float                     # positive outflow
    dividends_paid: float            # positive outflow
    new_debt: float                  # positive = new borrowings
    debt_repaid: float               # positive = principal repaid
    equity_issuance: float
    delta_st_investments: float      # positive = increase (cash out to deposits)
    other: float
    computed_ending_cash: float
    reported_ending_cash: float | None
    reconciles: bool                 # abs(computed - reported) / max(1, abs(reported)) < tolerance
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "year_label": self.year_label,
            "opening_cash": self.opening_cash,
            "cfo": self.cfo,
            "capex": self.capex,
            "dividends_paid": self.dividends_paid,
            "new_debt": self.new_debt,
            "debt_repaid": self.debt_repaid,
            "equity_issuance": self.equity_issuance,
            "delta_st_investments": self.delta_st_investments,
            "other": self.other,
            "computed_ending_cash": self.computed_ending_cash,
            "reported_ending_cash": self.reported_ending_cash,
            "reconciles": self.reconciles,
            "warnings": self.warnings,
        }


def compute_cash_sweep(
    year_label: str,
    opening_cash: float,
    cfo: float,
    capex_positive: float,
    dividends_paid: float,
    new_debt: float = 0.0,
    debt_repaid: float = 0.0,
    equity_issuance: float = 0.0,
    delta_st_investments: float = 0.0,
    other: float = 0.0,
    reported_ending_cash: float | None = None,
    tolerance: float = 0.05,
) -> CashSweepResult:
    """Compute ending cash balance from opening balance plus all cash flow components.

    Formula:
        ending_cash = opening_cash
                    + CFO
                    - capex_positive        (investing outflow)
                    - dividends_paid        (financing outflow)
                    + new_debt              (financing inflow)
                    - debt_repaid           (financing outflow)
                    + equity_issuance       (financing inflow)
                    - delta_st_investments  (positive = cash deployed to ST investments)
                    + other                 (catch-all: FX, other investing/financing)

    Reconciliation check (when reported_ending_cash is provided):
        reconciles = abs(computed - reported) / max(1, abs(reported)) < tolerance

    Args:
        year_label: Period label e.g. "2025FY".
        opening_cash: Cash and cash equivalents at start of period (VND bn).
        cfo: Cash flow from operations (positive = inflow, VND bn).
        capex_positive: Capital expenditure as positive outflow (VND bn).
        dividends_paid: Dividends paid as positive outflow (VND bn).
        new_debt: New debt raised during period (VND bn).
        debt_repaid: Principal repaid during period (VND bn).
        equity_issuance: Proceeds from equity issuance (VND bn).
        delta_st_investments: Change in short-term investments/deposits
            (positive = cash deployed, VND bn).
        other: Residual / other cash movements (VND bn, signed).
        reported_ending_cash: Reported balance for reconciliation (VND bn, optional).
        tolerance: Fractional tolerance for reconciliation check (default 5%).

    Returns:
        CashSweepResult with computed ending cash and reconciliation status.
    """
    warnings: list[str] = []

    # Validate sign convention of inputs
    if capex_positive < 0:
        warnings.append(
            f"{year_label}: capex_positive is negative ({capex_positive:.2f}) — "
            "expected positive outflow; taking abs()."
        )
        capex_positive = abs(capex_positive)

    if dividends_paid < 0:
        warnings.append(
            f"{year_label}: dividends_paid is negative ({dividends_paid:.2f}) — "
            "expected positive outflow; taking abs()."
        )
        dividends_paid = abs(dividends_paid)

    if new_debt < 0:
        warnings.append(
            f"{year_label}: new_debt is negative ({new_debt:.2f}) — "
            "expected positive inflow; taking abs()."
        )
        new_debt = abs(new_debt)

    if debt_repaid < 0:
        warnings.append(
            f"{year_label}: debt_repaid is negative ({debt_repaid:.2f}) — "
            "expected positive outflow; taking abs()."
        )
        debt_repaid = abs(debt_repaid)

    computed_ending_cash = (
        opening_cash
        + cfo
        - capex_positive
        - dividends_paid
        + new_debt
        - debt_repaid
        + equity_issuance
        - delta_st_investments
        + other
    )

    reconciles = True
    if reported_ending_cash is not None:
        denom = max(1.0, abs(reported_ending_cash))
        rel_diff = abs(computed_ending_cash - reported_ending_cash) / denom
        reconciles = rel_diff < tolerance
        if not reconciles:
            warnings.append(
                f"{year_label}: Cash sweep does not reconcile — "
                f"computed {computed_ending_cash:.2f} vs reported "
                f"{reported_ending_cash:.2f} "
                f"(relative gap {rel_diff:.1%}, tolerance {tolerance:.0%})."
            )

    return CashSweepResult(
        year_label=year_label,
        opening_cash=opening_cash,
        cfo=cfo,
        capex=capex_positive,
        dividends_paid=dividends_paid,
        new_debt=new_debt,
        debt_repaid=debt_repaid,
        equity_issuance=equity_issuance,
        delta_st_investments=delta_st_investments,
        other=other,
        computed_ending_cash=computed_ending_cash,
        reported_ending_cash=reported_ending_cash,
        reconciles=reconciles,
        warnings=warnings,
    )


@dataclass
class EquityRollForwardResult:
    """Result of one year's equity roll-forward validation."""
    year_label: str
    opening_equity: float
    net_income: float
    dividends_paid: float            # positive = paid out
    equity_issuance: float
    buybacks: float
    oci: float
    computed_ending_equity: float
    reported_ending_equity: float | None
    reconciles: bool
    dividends_deducted: bool         # True if dividends_paid > 0 (sanity check)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "year_label": self.year_label,
            "opening_equity": self.opening_equity,
            "net_income": self.net_income,
            "dividends_paid": self.dividends_paid,
            "equity_issuance": self.equity_issuance,
            "buybacks": self.buybacks,
            "oci": self.oci,
            "computed_ending_equity": self.computed_ending_equity,
            "reported_ending_equity": self.reported_ending_equity,
            "reconciles": self.reconciles,
            "dividends_deducted": self.dividends_deducted,
            "warnings": self.warnings,
        }


def check_equity_roll_forward(
    year_label: str,
    opening_equity: float,
    net_income: float,
    dividends_paid: float,
    reported_ending_equity: float | None = None,
    equity_issuance: float = 0.0,
    buybacks: float = 0.0,
    oci: float = 0.0,
    tolerance: float = 5.0,
) -> EquityRollForwardResult:
    """Validate equity roll-forward using the standard statement of changes in equity.

    Formula:
        ending_equity = opening_equity
                      + net_income
                      - dividends_paid
                      + equity_issuance
                      - buybacks
                      + oci

    Reconciliation check (when reported_ending_equity is provided):
        reconciles = abs(computed - reported) < tolerance  (absolute VND bn)

    Args:
        year_label: Period label e.g. "2025FY".
        opening_equity: Shareholders' equity at start of period (VND bn).
        net_income: Net income attributable to parent (VND bn).
        dividends_paid: Dividends paid as positive outflow (VND bn).
        reported_ending_equity: Reported equity for reconciliation (VND bn, optional).
        equity_issuance: Proceeds from share issuance (VND bn).
        buybacks: Share buyback cash outflow as positive (VND bn).
        oci: Other comprehensive income (signed, VND bn).
        tolerance: Absolute tolerance in VND bn (default 5.0 bn).

    Returns:
        EquityRollForwardResult with computed ending equity and reconciliation status.
    """
    warnings: list[str] = []

    dividends_deducted = dividends_paid > 0

    if dividends_paid < 0:
        warnings.append(
            f"{year_label}: dividends_paid is negative ({dividends_paid:.2f}) — "
            "expected positive outflow; taking abs()."
        )
        dividends_paid = abs(dividends_paid)
        dividends_deducted = True

    if not dividends_deducted:
        warnings.append(
            f"{year_label}: dividends_paid = 0 — verify this company does not pay "
            "dividends; if historical dividends exist this may be an omission."
        )

    computed_ending_equity = (
        opening_equity
        + net_income
        - dividends_paid
        + equity_issuance
        - buybacks
        + oci
    )

    reconciles = True
    if reported_ending_equity is not None:
        abs_diff = abs(computed_ending_equity - reported_ending_equity)
        reconciles = abs_diff < tolerance
        if not reconciles:
            warnings.append(
                f"{year_label}: Equity roll-forward does not reconcile — "
                f"computed {computed_ending_equity:.2f} vs reported "
                f"{reported_ending_equity:.2f} "
                f"(absolute gap {abs_diff:.2f} VND bn, tolerance {tolerance:.1f} bn)."
            )

    return EquityRollForwardResult(
        year_label=year_label,
        opening_equity=opening_equity,
        net_income=net_income,
        dividends_paid=dividends_paid,
        equity_issuance=equity_issuance,
        buybacks=buybacks,
        oci=oci,
        computed_ending_equity=computed_ending_equity,
        reported_ending_equity=reported_ending_equity,
        reconciles=reconciles,
        dividends_deducted=dividends_deducted,
        warnings=warnings,
    )


def check_debt_flow_mismatch(
    year_label: str,
    net_debt_opening: float,
    net_debt_closing: float,
    net_borrowing: float,
    delta_cash: float,
    delta_st_investments: float = 0.0,
    tolerance: float = 5.0,
) -> dict:
    """Check whether the change in net debt can be explained by financing and cash flows.

    Net Debt = Total Debt - Cash - ST Investments

    Therefore:
        ΔNet_Debt = net_borrowing - delta_cash - delta_st_investments

    Any unexplained residual beyond tolerance suggests a data error, missing flow,
    or reclassification.

    Args:
        year_label: Period label e.g. "2025FY".
        net_debt_opening: Net debt at start of period (VND bn, positive = net debtor).
        net_debt_closing: Net debt at end of period (VND bn).
        net_borrowing: New debt raised minus principal repaid (VND bn, signed).
        delta_cash: Ending cash minus opening cash (VND bn, signed).
        delta_st_investments: Change in ST investments/deposits
            (positive = increase, VND bn).
        tolerance: Absolute tolerance in VND bn for mismatch warning (default 5.0 bn).

    Returns:
        dict with keys:
            "year_label": str
            "reconciles": bool
            "delta_net_debt": float      — actual change in net debt
            "expected_delta": float      — expected change from flows
            "residual": float            — unexplained gap
            "warnings": list[str]
    """
    warnings: list[str] = []

    delta_net_debt = net_debt_closing - net_debt_opening

    # Expected ΔNet_Debt = net_borrowing - delta_cash - delta_sti
    # (more borrowing → more net debt; more cash → less net debt)
    expected_delta = net_borrowing - delta_cash - delta_st_investments

    residual = delta_net_debt - expected_delta
    reconciles = abs(residual) < tolerance

    if not reconciles:
        warnings.append(
            f"{year_label}: Debt flow mismatch — ΔNet_Debt = {delta_net_debt:.2f} "
            f"but expected {expected_delta:.2f} from (net_borrowing={net_borrowing:.2f}, "
            f"delta_cash={delta_cash:.2f}, delta_sti={delta_st_investments:.2f}); "
            f"unexplained residual {residual:.2f} VND bn "
            f"(tolerance {tolerance:.1f} bn). "
            "Check for FX revaluation, debt reclassification, or missing flows."
        )

    return {
        "year_label": year_label,
        "reconciles": reconciles,
        "delta_net_debt": delta_net_debt,
        "expected_delta": expected_delta,
        "residual": residual,
        "warnings": warnings,
    }


# ── Minimum Cash Policy ───────────────────────────────────────────────────────

@dataclass
class MinimumCashPolicy:
    """Company-level minimum operating cash threshold.

    Per plan §4: if ending_cash < minimum_cash, new borrowing is required.
    The policy is a model assumption and must be marked as such.

    Default for Vietnam pharma (if no analyst input):
        minimum_cash = MAX(50 VND bn, 5% revenue, 45 days cash opex)

    All monetary values in VND bn.
    """
    absolute_floor_bn: float = 50.0           # hard floor in VND bn
    pct_of_revenue: float = 0.05              # 5% of forecast revenue
    days_opex: float = 45.0                   # 45 days of cash operating expenses
    source: str = "model_default_unapproved"  # "analyst_approved" when signed off

    @property
    def is_approved(self) -> bool:
        return self.source == "analyst_approved"

    def compute(
        self,
        revenue_bn: float | None = None,
        cash_opex_daily_bn: float | None = None,
    ) -> float:
        """Return the minimum cash for one forecast year (VND bn)."""
        candidates = [self.absolute_floor_bn]
        if revenue_bn and revenue_bn > 0:
            candidates.append(self.pct_of_revenue * revenue_bn)
        if cash_opex_daily_bn and cash_opex_daily_bn > 0:
            candidates.append(self.days_opex * cash_opex_daily_bn)
        return max(candidates)

    def to_dict(self) -> dict:
        return {
            "absolute_floor_bn": self.absolute_floor_bn,
            "pct_of_revenue": self.pct_of_revenue,
            "days_opex": self.days_opex,
            "source": self.source,
            "is_approved": self.is_approved,
        }


def check_minimum_cash(
    year_label: str,
    ending_cash: float,
    minimum_cash: float,
) -> dict:
    """Return gate result for ending cash vs. minimum cash threshold.

    If ending_cash < minimum_cash → new_borrowing_required (for debt schedule).
    If ending_cash >= minimum_cash → no new borrowing triggered by cash floor.
    """
    shortfall = minimum_cash - ending_cash
    return {
        "year_label": year_label,
        "ending_cash": round(ending_cash, 2),
        "minimum_cash": round(minimum_cash, 2),
        "shortfall": round(shortfall, 2) if shortfall > 0 else 0.0,
        "new_borrowing_required": shortfall > 0,
        "gate": "PASS" if ending_cash >= minimum_cash else "WARN",
    }


# ── CashSweepArtifact ─────────────────────────────────────────────────────────

@dataclass
class CashSweepArtifact:
    """Multi-year cash sweep artifact for forecast periods.

    Per plan §4:
    - If the cash identity fails for any year → status = "failed"
    - A "failed" artifact signals that debt schedule (and therefore FCFE) cannot be
      derived from cash sweep; the pipeline must block downstream publishable artifacts.

    Cash identity per year:
        ending_cash = opening_cash + CFO - CAPEX - dividends
                    + new_borrowing - debt_repaid
                    + equity_issuance - delta_st_investments + other
    """
    ticker: str
    year_results: list[CashSweepResult]
    minimum_cash_policy: MinimumCashPolicy | None = None
    status: Literal["approved", "pending", "failed"] = "pending"
    warnings: list[str] = field(default_factory=list)

    @property
    def all_reconcile(self) -> bool:
        return all(r.reconciles for r in self.year_results)

    @property
    def is_debt_publishable(self) -> bool:
        """True if cash sweep succeeded and can be used to derive net borrowing."""
        return self.status != "failed" and self.all_reconcile

    def net_borrowing_schedule(self) -> dict[str, float]:
        """Return {year_label: new_debt - debt_repaid} for each sweep year."""
        return {
            r.year_label: r.new_debt - r.debt_repaid
            for r in self.year_results
        }

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "status": self.status,
            "all_reconcile": self.all_reconcile,
            "is_debt_publishable": self.is_debt_publishable,
            "minimum_cash_policy": self.minimum_cash_policy.to_dict() if self.minimum_cash_policy else None,
            "year_results": [r.to_dict() for r in self.year_results],
            "warnings": self.warnings,
        }


def build_cash_sweep_artifact(
    ticker: str,
    year_inputs: list[dict],
    minimum_cash_policy: MinimumCashPolicy | None = None,
    tolerance: float = 0.05,
) -> CashSweepArtifact:
    """Build a multi-year CashSweepArtifact from per-year cash flow inputs.

    Each element of year_inputs must be a dict with keys matching compute_cash_sweep()
    arguments (year_label, opening_cash, cfo, capex_positive, dividends_paid, etc.).

    Status rules:
        "failed"  — any year does not reconcile (when reported_ending_cash provided)
        "pending" — no reported_ending_cash supplied (cannot verify)
        "approved" — all years reconcile (caller must promote after analyst sign-off)
    """
    warnings: list[str] = []
    results: list[CashSweepResult] = []

    for inp in year_inputs:
        result = compute_cash_sweep(
            year_label=inp["year_label"],
            opening_cash=inp["opening_cash"],
            cfo=inp["cfo"],
            capex_positive=inp["capex_positive"],
            dividends_paid=inp.get("dividends_paid", 0.0),
            new_debt=inp.get("new_debt", 0.0),
            debt_repaid=inp.get("debt_repaid", 0.0),
            equity_issuance=inp.get("equity_issuance", 0.0),
            delta_st_investments=inp.get("delta_st_investments", 0.0),
            other=inp.get("other", 0.0),
            reported_ending_cash=inp.get("reported_ending_cash"),
            tolerance=tolerance,
        )
        results.append(result)
        warnings.extend(result.warnings)

    has_reported = any(inp.get("reported_ending_cash") is not None for inp in year_inputs)
    if not has_reported:
        status: Literal["approved", "pending", "failed"] = "pending"
        warnings.append(
            "CashSweepArtifact: no reported_ending_cash supplied — "
            "reconciliation not verifiable; status = pending."
        )
    elif all(r.reconciles for r in results):
        status = "approved"
    else:
        status = "failed"
        warnings.append(
            "CashSweepArtifact: one or more years fail cash identity reconciliation — "
            "net borrowing from this sweep cannot be used for publishable FCFE."
        )

    return CashSweepArtifact(
        ticker=ticker,
        year_results=results,
        minimum_cash_policy=minimum_cash_policy,
        status=status,
        warnings=warnings,
    )
