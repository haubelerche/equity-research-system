"""Financial fact reconciliation — Source-Provenance Rebuild, Phase 4.

Compares vnstock/provider-derived (Tier 3) facts against official-document facts and
promotes only verified facts into final-report usage (fact.verified_financial_facts).

Pure core (`reconcile_one`, `is_promotable`) is fully unit-testable without a DB.
`reconcile_ticker` is the DB-driven orchestrator.

Tolerance rule (plan default):
    diff_pct <= 0.5%  -> matched_official
    diff_pct >  0.5%  -> manual_review_required

Promotion rule: only `matched_official` or `manual_reviewed` are promoted. Never promote
`missing_official`, `mismatch`, or `manual_review_required` (until a human reviews it).
"""
from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_TOLERANCE_PCT = 0.5

PROMOTABLE_STATUSES: frozenset[str] = frozenset({"matched_official", "manual_reviewed"})
VALID_STATUSES: frozenset[str] = frozenset({
    "matched_official", "mismatch", "missing_official",
    "missing_api", "manual_review_required", "manual_reviewed",
})


@dataclass
class ReconciliationResult:
    ticker: str
    fiscal_year: int
    metric_id: str
    api_value: float | None
    official_value: float | None
    diff_abs: float | None
    diff_pct: float | None
    status: str
    acquisition_source_id: str | None = None
    official_document_id: int | None = None
    notes: str = ""

    @property
    def promotable(self) -> bool:
        return self.status in PROMOTABLE_STATUSES

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker, "fiscal_year": self.fiscal_year,
            "metric_id": self.metric_id, "api_value": self.api_value,
            "official_value": self.official_value, "diff_abs": self.diff_abs,
            "diff_pct": self.diff_pct, "status": self.status,
            "acquisition_source_id": self.acquisition_source_id,
            "official_document_id": self.official_document_id, "notes": self.notes,
        }


def reconcile_one(
    api_value: float | None,
    official_value: float | None,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
) -> tuple[str, float | None, float | None]:
    """Compare one API value against one official value.

    Returns (status, diff_abs, diff_pct).
    """
    if official_value is None and api_value is None:
        return "missing_official", None, None
    if official_value is None:
        return "missing_official", None, None
    if api_value is None:
        return "missing_api", None, None

    diff_abs = abs(api_value - official_value)
    denom = abs(official_value)
    if denom == 0:
        # Official is zero: matched only if API is also (near) zero.
        diff_pct = 0.0 if diff_abs == 0 else float("inf")
    else:
        diff_pct = diff_abs / denom * 100.0

    status = "matched_official" if diff_pct <= tolerance_pct else "manual_review_required"
    return status, diff_abs, diff_pct


def is_promotable(status: str) -> bool:
    return status in PROMOTABLE_STATUSES


def reconcile_pair(
    ticker: str,
    fiscal_year: int,
    metric_id: str,
    api_value: float | None,
    official_value: float | None,
    *,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    acquisition_source_id: str | None = None,
    official_document_id: int | None = None,
) -> ReconciliationResult:
    status, diff_abs, diff_pct = reconcile_one(api_value, official_value, tolerance_pct)
    notes = ""
    if status == "missing_official":
        notes = "No official-document fact for this metric/year — cannot verify."
    elif status == "missing_api":
        notes = "Official fact present but no API/provider fact to cross-check."
    elif status == "manual_review_required":
        notes = f"diff {diff_pct:.2f}% exceeds tolerance {tolerance_pct}% — needs analyst review."
    return ReconciliationResult(
        ticker=ticker, fiscal_year=fiscal_year, metric_id=metric_id,
        api_value=api_value, official_value=official_value,
        diff_abs=diff_abs, diff_pct=diff_pct, status=status,
        acquisition_source_id=acquisition_source_id,
        official_document_id=official_document_id, notes=notes,
    )


@dataclass
class ReconciliationSummary:
    ticker: str
    total: int = 0
    matched: int = 0
    mismatch: int = 0
    missing_official: int = 0
    missing_api: int = 0
    manual_review_required: int = 0
    promoted: int = 0
    results: list[ReconciliationResult] = field(default_factory=list)

    def record(self, r: ReconciliationResult) -> None:
        self.total += 1
        self.results.append(r)
        if r.status == "matched_official":
            self.matched += 1
        elif r.status == "mismatch":
            self.mismatch += 1
        elif r.status == "missing_official":
            self.missing_official += 1
        elif r.status == "missing_api":
            self.missing_api += 1
        elif r.status == "manual_review_required":
            self.manual_review_required += 1

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker, "total": self.total, "matched": self.matched,
            "mismatch": self.mismatch, "missing_official": self.missing_official,
            "missing_api": self.missing_api,
            "manual_review_required": self.manual_review_required,
            "promoted": self.promoted,
        }


def reconcile_ticker(
    ticker: str,
    from_year: int,
    to_year: int,
    *,
    tolerance_pct: float = DEFAULT_TOLERANCE_PCT,
    canonical_version: str = "v_legacy",
    promote: bool = True,
    promote_official_only: bool = False,
    store=None,
) -> ReconciliationSummary:
    """DB-driven reconciliation for a ticker over a fiscal-year range.

    Loads Tier-3 API canonical facts and official-document observations, compares them
    per (year, metric), persists results to fact.fact_reconciliation, and promotes
    matched facts by linking canonical_facts to the official document.

    promote_official_only: when True, official-only facts (status=missing_api —
      i.e. official doc exists but no Tier-3 API counterpart) are inserted as new
      canonical facts with canonical_version='v_official' and status='manual_reviewed'.
      Use when the source year has no API data (e.g. 2021FY vnstock gap).
    """
    import psycopg2.extras as _extras

    from backend.database.fact_store import PostgresFactStore
    from backend.database.official_documents import OfficialDocumentRegistry

    store = store or PostgresFactStore()
    reg = OfficialDocumentRegistry(store)
    summary = ReconciliationSummary(ticker=ticker)

    periods = [f"{y}FY" for y in range(from_year, to_year + 1)]

    with store.conn() as conn:
        with conn.cursor(cursor_factory=_extras.DictCursor) as cur:
            # API/provider canonical facts (the current Tier-3 source of truth).
            cur.execute(
                """
                SELECT fact_id, period, metric, value, source_tier
                FROM fact.canonical_facts
                WHERE ticker=%s AND canonical_version=%s AND period = ANY(%s)
                """,
                (ticker, canonical_version, periods),
            )
            api_facts = {(r["period"], r["metric"]): r for r in cur.fetchall()}

            # Official-document observations (Phase 3 output).
            cur.execute(
                """
                SELECT o.period, o.metric, o.value, o.official_document_id
                FROM fact.fact_observations o
                WHERE o.ticker=%s AND o.period = ANY(%s)
                  AND o.official_document_id IS NOT NULL
                """,
                (ticker, periods),
            )
            official_facts = {(r["period"], r["metric"]): r for r in cur.fetchall()}

        all_keys = set(api_facts) | set(official_facts)
        for period, metric in sorted(all_keys):
            year = int(period[:4])
            api_row = api_facts.get((period, metric))
            off_row = official_facts.get((period, metric))
            r = reconcile_pair(
                ticker, year, metric,
                api_value=float(api_row["value"]) if api_row else None,
                official_value=float(off_row["value"]) if off_row else None,
                tolerance_pct=tolerance_pct,
                official_document_id=off_row["official_document_id"] if off_row else None,
            )
            summary.record(r)

            # Persist comparison row.
            with conn.cursor() as wcur:
                wcur.execute(
                    """
                    INSERT INTO fact.fact_reconciliation
                    (ticker, period, metric, candidate_observation_ids,
                     api_value, official_value, diff_abs, diff_pct,
                     reconciliation_status, official_document_id, tolerance_pct,
                     requires_review)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ticker, period, metric) DO UPDATE SET
                        api_value=EXCLUDED.api_value,
                        official_value=EXCLUDED.official_value,
                        diff_abs=EXCLUDED.diff_abs,
                        diff_pct=EXCLUDED.diff_pct,
                        reconciliation_status=EXCLUDED.reconciliation_status,
                        official_document_id=EXCLUDED.official_document_id,
                        tolerance_pct=EXCLUDED.tolerance_pct,
                        requires_review=EXCLUDED.requires_review
                    """,
                    (
                        ticker, period, metric, [],
                        r.api_value, r.official_value, r.diff_abs, r.diff_pct,
                        r.status, r.official_document_id, tolerance_pct,
                        r.status == "manual_review_required",
                    ),
                )

            # Promote matched facts (API + official agree) → mark existing canonical fact.
            if promote and r.promotable and api_row and r.official_document_id:
                reg.mark_fact_verified(
                    fact_id=api_row["fact_id"],
                    official_document_id=r.official_document_id,
                    reconciliation_status=r.status,
                    verified_by="reconcile_financial_facts",
                )
                summary.promoted += 1

            # Official-only facts (no API counterpart) → insert new canonical fact.
            elif (promote and promote_official_only
                    and r.status == "missing_api"
                    and off_row and r.official_document_id):
                off_value = float(off_row["value"])
                reg.insert_official_canonical_fact(
                    ticker=ticker,
                    period=period,
                    metric=metric,
                    value=off_value,
                    official_document_id=r.official_document_id,
                    unit="vnd_bn",
                    source_tier=0,
                    verified_by="reconcile_financial_facts_official_only",
                )
                # Update reconciliation row to reflect manual_reviewed
                with conn.cursor() as wcur:
                    wcur.execute(
                        """
                        UPDATE fact.fact_reconciliation
                        SET reconciliation_status='manual_reviewed', requires_review=FALSE
                        WHERE ticker=%s AND period=%s AND metric=%s
                        """,
                        (ticker, period, metric),
                    )
                summary.promoted += 1

    return summary
