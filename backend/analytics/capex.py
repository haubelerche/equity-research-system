"""CAPEX sign convention validation and balance-sheet-based CAPEX computation.

Convention used throughout this codebase:
    CAPEX_positive = positive number representing cash outflow (e.g. 50 tỷ)
    ForecastYear.capex stored as negative (CFS convention): -50 tỷ
    fcff.py and fcfe.py convert via: capex_positive = abs(fy.capex)

This module provides:
    compute_capex_from_balance_sheet() — derive CAPEX_positive from gross PP&E deltas
    validate_capex_series()           — audit a series for sign errors and anomalies
    audit_capex_entry()               — check a single CAPEX value and emit warnings

All arithmetic is deterministic Python — no LLM involvement.
All monetary values in VND bn consistent with rest of codebase.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CapexAuditResult:
    year_label: str
    capex_positive: float                # always >= 0
    source: str                          # "balance_sheet" | "cfs_direct" | "zero_net_disposal"
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "year_label": self.year_label,
            "capex_positive": self.capex_positive,
            "source": self.source,
            "warnings": self.warnings,
        }


def compute_capex_from_balance_sheet(
    gross_tangible_ppe_current: float,
    gross_tangible_ppe_prior: float,
    intangible_gross_current: float = 0.0,
    intangible_gross_prior: float = 0.0,
    wip_current: float = 0.0,
    wip_prior: float = 0.0,
    disposed_gross_value: float = 0.0,
    year_label: str = "",
) -> CapexAuditResult:
    """Compute CAPEX_positive from gross balance sheet asset deltas.

    Formula:
        CAPEX_positive = ΔGross_Tangible_PPE + ΔIntangible + ΔWIP + Disposals_gross

    Where:
        Δ = current - prior  (positive means additions)
        disposed_gross_value = gross book value of assets removed from the register
            (always >= 0; adds back because disposal reduces ending balance
             but was not a cash outflow for additions)

    If computed result < 0 (net disposal year where disposals exceed additions):
        CAPEX_positive is set to 0.0 and source is "zero_net_disposal".

    Args:
        gross_tangible_ppe_current: Gross tangible PP&E at period end (VND bn).
        gross_tangible_ppe_prior: Gross tangible PP&E at prior period end (VND bn).
        intangible_gross_current: Gross intangible assets at period end (VND bn).
        intangible_gross_prior: Gross intangible assets at prior period end (VND bn).
        wip_current: Construction-in-progress / WIP at period end (VND bn).
        wip_prior: Construction-in-progress / WIP at prior period end (VND bn).
        disposed_gross_value: Gross book value of assets disposed/retired (VND bn).
        year_label: Human-readable period label, e.g. "2025FY".

    Returns:
        CapexAuditResult with capex_positive >= 0.
    """
    warnings: list[str] = []

    delta_tangible = gross_tangible_ppe_current - gross_tangible_ppe_prior
    delta_intangible = intangible_gross_current - intangible_gross_prior
    delta_wip = wip_current - wip_prior

    # Disposals reduce ending gross balance; add back to recover gross additions
    disposed = abs(disposed_gross_value)

    raw_capex = delta_tangible + delta_intangible + delta_wip + disposed

    if raw_capex < 0:
        # Net disposal year: more gross assets removed than added
        warnings.append(
            f"{year_label}: Net disposal year — computed gross additions "
            f"({raw_capex:.2f} VND bn) are negative; setting CAPEX_positive = 0."
        )
        return CapexAuditResult(
            year_label=year_label,
            capex_positive=0.0,
            source="zero_net_disposal",
            warnings=warnings,
        )

    return CapexAuditResult(
        year_label=year_label,
        capex_positive=raw_capex,
        source="balance_sheet",
        warnings=warnings,
    )


def audit_capex_entry(
    capex: float,
    year_label: str,
    revenue: float | None = None,
    depreciation: float | None = None,
) -> dict:
    """Single-entry CAPEX audit.

    Accepts CAPEX in either sign convention:
    - If capex < 0 (CFS convention: negative outflow), converts via abs() and warns.
    - If capex >= 0, treats as CAPEX_positive directly.

    Emits warnings for:
    - Negative input (converted to positive).
    - CAPEX/Revenue > 30%: unusual intensity requiring explanation.
    - CAPEX < 50% of D&A: potential asset base deterioration.

    Args:
        capex: CAPEX value in VND bn (positive outflow or negative CFS convention).
        year_label: Period label e.g. "2025FY".
        revenue: Revenue in VND bn for intensity check (optional).
        depreciation: D&A in VND bn for coverage check (optional).

    Returns:
        dict with keys:
            "year_label": str
            "capex_positive": float  (always >= 0)
            "warnings": list[str]
    """
    warnings: list[str] = []
    capex_positive: float

    if capex < 0:
        capex_positive = abs(capex)
        warnings.append(
            f"{year_label}: CAPEX input is negative ({capex:.2f} VND bn) — "
            "interpreted as CFS-convention outflow; converted to positive via abs()."
        )
    else:
        capex_positive = capex

    if revenue is not None and revenue > 0:
        intensity = capex_positive / revenue
        if intensity > 0.30:
            warnings.append(
                f"{year_label}: CAPEX/Revenue = {intensity:.1%} exceeds 30% — "
                "requires explanation."
            )

    if depreciation is not None and depreciation > 0:
        if capex_positive < 0.5 * depreciation:
            warnings.append(
                f"{year_label}: CAPEX ({capex_positive:.2f}) < 50% of D&A "
                f"({depreciation:.2f}) — asset base may be deteriorating."
            )

    return {
        "year_label": year_label,
        "capex_positive": capex_positive,
        "warnings": warnings,
    }


def validate_capex_series(
    entries: list[dict],
) -> list[dict]:
    """Validate a multi-year CAPEX series.

    Each entry dict must have:
        "year": str        — period label
        "capex": float     — CAPEX value (positive outflow or negative CFS convention)
        "revenue": float | None   — optional, for intensity check
        "depreciation": float | None  — optional, for D&A coverage check

    Series-level checks applied after per-entry audit:
    - Consecutive underspend: if capex < 0.5 * depreciation for 3+ consecutive years,
      emit a series-level warning.

    Returns:
        list[dict]: one audit dict per entry (from audit_capex_entry),
        with an additional "series_warnings" key on the last entry containing
        any series-level findings.
    """
    if not entries:
        return []

    results: list[dict] = []

    for entry in entries:
        year = entry.get("year", "")
        capex = float(entry.get("capex", 0.0))
        revenue = entry.get("revenue")
        depreciation = entry.get("depreciation")

        audit = audit_capex_entry(
            capex=capex,
            year_label=year,
            revenue=float(revenue) if revenue is not None else None,
            depreciation=float(depreciation) if depreciation is not None else None,
        )
        results.append(audit)

    # Series-level: detect 3+ consecutive years of CAPEX < 50% D&A
    series_warnings: list[str] = []
    consecutive_underspend = 0
    underspend_years: list[str] = []

    for i, (entry, result) in enumerate(zip(entries, results)):
        depreciation = entry.get("depreciation")
        capex_positive = result["capex_positive"]
        if depreciation is not None and float(depreciation) > 0:
            if capex_positive < 0.5 * float(depreciation):
                consecutive_underspend += 1
                underspend_years.append(result["year_label"])
            else:
                consecutive_underspend = 0
                underspend_years = []
        else:
            # No depreciation data — reset counter
            consecutive_underspend = 0
            underspend_years = []

        if consecutive_underspend >= 3:
            years_str = ", ".join(underspend_years)
            series_warnings.append(
                f"CAPEX < 50% of D&A for 3+ consecutive years ({years_str}) — "
                "sustained underinvestment risk; asset base may be deteriorating."
            )
            # Reset to avoid duplicate series warning
            consecutive_underspend = 0
            underspend_years = []

    # Attach series warnings to last entry
    results[-1]["series_warnings"] = series_warnings

    return results
