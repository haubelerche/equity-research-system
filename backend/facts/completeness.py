"""FY-aware completeness and freshness scoring for the canonical fact set.

For MVP, the required fiscal periods are exactly 2021FY–2025FY.
Gate passes only when all five FY periods are present AND all core keys
exist for each required period.

Produces a structured report consumed by build_facts.py and downstream
evaluation gates.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.facts.normalizer import FactTable, periods_sorted


# Keys that MUST be present in every required FY period to pass the gate.
CORE_FY_KEYS: list[str] = [
    "revenue.net",
    "net_income.parent",
    "total_assets.ending",
    "equity.parent",
    "operating_cash_flow.total",
]

# Legacy full required-key list retained for reference / derived metrics.
REQUIRED_KEYS: list[str] = [
    "revenue.net",
    "cogs.total",
    "gross_profit.total",
    "net_income.parent",
    "eps.basic",
    "cash_and_equivalents.ending",
    "inventory.ending",
    "equity.parent",
    "operating_cash_flow.total",
    "capex.total",
]

RECOMMENDED_KEYS: list[str] = [
    "sga.total",
    "ebit.total",
    "ebitda.total",
    "total_debt.ending",
    "free_cash_flow.total",
]

FRESHNESS_THRESHOLD_DAYS = 400


def _year_from_period(period: str) -> int | None:
    try:
        return int(period[:4])
    except (ValueError, IndexError):
        return None


def build_fy_validation_report(
    ticker: str,
    table: FactTable,
    raw_facts: list[dict],
    required_periods: list[str],
    periods_available: list[str],
    periods_missing: list[str],
    forbidden_periods: list[str],
    generated_at: datetime,
    validation_status_table: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the three-tier FY gate report for a ticker.

    Tier 1 — coverage_gate:         >= 3 FY periods collected in range.
    Tier 2 — core_keys_gate:        all CORE_FY_KEYS present for every collected period.
    Tier 3 — source_validation_gate: all CORE_FY_KEYS for every collected period
                                      have validation_status == 'accepted'.

    valuation_ready=True ONLY when all three tiers pass.
    """
    blocking_reasons: list[str] = []
    MIN_FY_PERIODS = 3

    # --- Per-core-key coverage status (checked against periods_available only) ---
    core_keys: dict[str, Any] = {}
    for key in CORE_FY_KEYS:
        key_data = table.get(key, {})
        missing_for_key = [p for p in periods_available if p not in key_data]
        if not missing_for_key:
            status = "present"
        elif len(missing_for_key) == len(periods_available):
            status = "missing"
        else:
            status = "partial"
        core_keys[key] = {"status": status, "missing_periods": missing_for_key}

    # --- Tier 1: coverage_gate ---
    annual_reports_collected = len(periods_available)
    if annual_reports_collected < MIN_FY_PERIODS:
        coverage_gate = "fail"
        blocking_reasons.append(
            f"insufficient_annual_reports: collected {annual_reports_collected}, minimum {MIN_FY_PERIODS}"
        )
    else:
        coverage_gate = "pass"

    # --- Tier 2: core_keys_gate ---
    core_failures = [k for k, v in core_keys.items() if v["status"] != "present"]
    if core_failures:
        core_keys_gate = "fail"
        blocking_reasons.append(
            f"missing_core_keys: {', '.join(core_failures[:3])}"
        )
    else:
        core_keys_gate = "pass"

    # --- Tier 3: source_validation_gate ---
    non_accepted: list[dict[str, str]] = []
    if validation_status_table is None:
        source_validation_gate = "fail"
        blocking_reasons.append(
            "no validation_status_table provided — cannot verify source acceptance"
        )
    else:
        for key in CORE_FY_KEYS:
            for period in periods_available:
                status = validation_status_table.get(key, {}).get(period, "unknown")
                if status != "accepted":
                    non_accepted.append({"key": key, "period": period, "status": status})
        if non_accepted:
            source_validation_gate = "fail"
            for item in non_accepted[:5]:
                blocking_reasons.append(
                    f"validation_status={item['status']} for {item['key']} @ {item['period']}"
                )
        else:
            source_validation_gate = "pass"

    # --- Overall valuation_gate ---
    all_pass = (
        coverage_gate == "pass"
        and core_keys_gate == "pass"
        and source_validation_gate == "pass"
    )
    valuation_gate = "pass" if all_pass else "fail"
    valuation_ready = all_pass

    # run_status
    if coverage_gate == "fail" or core_keys_gate == "fail":
        run_status = "needs_fallback"
    elif source_validation_gate == "fail":
        run_status = "needs_human_verification"
    else:
        run_status = "ok"

    # --- Freshness ---
    ingested_ats: list[datetime] = []
    for row in raw_facts:
        ia = row.get("ingested_at")
        if ia is not None:
            if isinstance(ia, str):
                try:
                    ia = datetime.fromisoformat(ia)
                except ValueError:
                    ia = None
            if ia is not None:
                ingested_ats.append(ia)

    now = datetime.now(UTC)
    most_recent_ingested = max(ingested_ats) if ingested_ats else None
    data_age_days: int | None = None
    if most_recent_ingested is not None:
        if most_recent_ingested.tzinfo is None:
            most_recent_ingested = most_recent_ingested.replace(tzinfo=UTC)
        data_age_days = (now - most_recent_ingested).days

    latest_fy = max((int(p[:4]) for p in periods_available), default=None)

    return {
        "ticker": ticker,
        "generated_at": generated_at.isoformat(),
        "period_mode": "year",
        "required_periods": required_periods,
        "periods_available": periods_available,
        "periods_missing": periods_missing,
        "annual_reports_collected": annual_reports_collected,
        "forbidden_periods_found": forbidden_periods,
        "forbidden_periods_ignored": forbidden_periods,
        "core_keys": core_keys,
        # Three-tier gate
        "coverage_gate": coverage_gate,
        "core_keys_gate": core_keys_gate,
        "source_validation_gate": source_validation_gate,
        "non_accepted_facts": non_accepted,
        "valuation_gate": valuation_gate,
        # Top-level summary
        "valuation_ready": valuation_ready,
        "run_status": run_status,
        "blocking_reasons": blocking_reasons,
        # Freshness
        "latest_fiscal_year": latest_fy,
        "latest_period": f"{latest_fy}FY" if latest_fy else None,
        "data_age_days": data_age_days,
        "most_recent_ingested_at": (
            most_recent_ingested.isoformat() if most_recent_ingested else None
        ),
    }


# ---------------------------------------------------------------------------
# Legacy helpers kept for any callers that have not migrated yet.
# ---------------------------------------------------------------------------

def score_completeness(table: FactTable, periods: list[str]) -> dict[str, Any]:
    required_present: list[str] = []
    required_missing: list[str] = []
    recommended_present: list[str] = []
    recommended_missing: list[str] = []
    per_key: dict[str, dict[str, Any]] = {}

    for key in REQUIRED_KEYS:
        key_periods = table.get(key, {})
        covered = [p for p in periods if p in key_periods]
        per_key[key] = {
            "required": True,
            "covered_periods": covered,
            "missing_periods": [p for p in periods if p not in key_periods],
        }
        (required_present if covered else required_missing).append(key)

    for key in RECOMMENDED_KEYS:
        key_periods = table.get(key, {})
        covered = [p for p in periods if p in key_periods]
        per_key[key] = {
            "required": False,
            "covered_periods": covered,
            "missing_periods": [p for p in periods if p not in key_periods],
        }
        (recommended_present if covered else recommended_missing).append(key)

    n_required = len(REQUIRED_KEYS)
    completeness_score = len(required_present) / n_required if n_required > 0 else 0.0
    per_period: dict[str, float] = {
        p: round(sum(1 for k in REQUIRED_KEYS if p in table.get(k, {})) / n_required, 4)
        for p in periods
    }

    return {
        "completeness_score": round(completeness_score, 4),
        "required_present": required_present,
        "required_missing": required_missing,
        "recommended_present": recommended_present,
        "recommended_missing": recommended_missing,
        "per_key": per_key,
        "per_period": per_period,
    }


def score_freshness(periods: list[str], ingested_at_values: list[datetime]) -> dict[str, Any]:
    now = datetime.now(UTC)
    current_year = now.year
    years = [y for y in (_year_from_period(p) for p in periods) if y is not None]
    latest_year = max(years) if years else None
    most_recent_ingested = max(ingested_at_values) if ingested_at_values else None
    data_age_days: int | None = None
    if most_recent_ingested is not None:
        if most_recent_ingested.tzinfo is None:
            most_recent_ingested = most_recent_ingested.replace(tzinfo=UTC)
        data_age_days = (now - most_recent_ingested).days

    if latest_year is None:
        freshness_score, freshness_status = 0.0, "no_data"
    elif latest_year >= current_year - 1:
        freshness_score, freshness_status = 1.0, "current"
    elif latest_year == current_year - 2:
        freshness_score, freshness_status = 0.5, "stale"
    else:
        freshness_score, freshness_status = 0.0, "very_stale"

    if data_age_days is not None and data_age_days > FRESHNESS_THRESHOLD_DAYS:
        freshness_score = min(freshness_score, 0.5)
        freshness_status = "stale_ingestion"

    return {
        "freshness_score": round(freshness_score, 4),
        "freshness_status": freshness_status,
        "latest_fiscal_year": latest_year,
        "data_age_days": data_age_days,
        "most_recent_ingested_at": most_recent_ingested.isoformat() if most_recent_ingested else None,
    }


def build_validation_report(
    ticker: str,
    table: FactTable,
    raw_facts: list[dict],
    generated_at: datetime,
) -> dict[str, Any]:
    """Legacy report builder — use build_fy_validation_report for new code."""
    periods = periods_sorted(table)
    completeness = score_completeness(table=table, periods=periods)
    ingested_ats: list[datetime] = []
    for row in raw_facts:
        ia = row.get("ingested_at")
        if ia is not None:
            if isinstance(ia, str):
                try:
                    ia = datetime.fromisoformat(ia)
                except ValueError:
                    ia = None
            if ia is not None:
                ingested_ats.append(ia)
    freshness = score_freshness(periods=periods, ingested_at_values=ingested_ats)
    overall_score = round(0.7 * completeness["completeness_score"] + 0.3 * freshness["freshness_score"], 4)
    if overall_score >= 0.8 and not completeness["required_missing"]:
        gate_status = "pass"
    elif completeness["required_missing"]:
        gate_status = "warn_missing_required"
    else:
        gate_status = "warn_low_score"
    return {
        "ticker": ticker,
        "generated_at": generated_at.isoformat(),
        "periods": periods,
        "fact_count": sum(len(v) for v in table.values()),
        "completeness": completeness,
        "freshness": freshness,
        "overall_score": overall_score,
        "gate_status": gate_status,
    }
