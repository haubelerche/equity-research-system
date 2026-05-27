"""DataFoundationAgent — orchestrates the data foundation layer.

Responsibilities:
  - Trigger ingest + build_facts for a ticker (with DQ gate check)
  - Assess data readiness before research runs
  - Coordinate scheduled refreshes via the job registry
  - Report data foundation status for a ticker

This is a deterministic orchestration agent, NOT an LLM agent.
LLMs are not used in this module — all logic is code-driven.

Usage (standalone):
    python -m backend.agents.data_foundation_agent --ticker DHG
    python -m backend.agents.data_foundation_agent --ticker DHG --ingest
    python -m backend.agents.data_foundation_agent --ticker DHG --run-job weekly_sync
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_env_file = Path(__file__).resolve().parents[2] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            _v = _v.strip().strip('"').strip("'")
            os.environ.setdefault(_k.strip(), _v)

ROOT = Path(__file__).resolve().parents[2]
FACTS_DIR = ROOT / "artifacts" / "facts"

MVP_TICKERS = ["DHG", "IMP", "DMC", "TRA", "DBD"]
MVP_FROM_YEAR = 2021
MVP_TO_YEAR = 2025


class DataFoundationAgent:
    """Coordinates the data foundation for one or more tickers.

    Workflow:
        1. assess()     — check current data status without running anything
        2. prepare()    — ingest + build_facts, returns DQ report
        3. is_ready()   — quick check: is this ticker ready for valuation?
    """

    def __init__(
        self,
        ticker: str,
        from_year: int = MVP_FROM_YEAR,
        to_year: int = MVP_TO_YEAR,
    ) -> None:
        self.ticker = ticker.strip().upper()
        self.from_year = from_year
        self.to_year = to_year

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def assess(self) -> dict:
        """Return current data foundation status without running ingestion.

        Reads the latest fact artifact from disk and checks DB fact counts.
        """
        status: dict = {
            "ticker": self.ticker,
            "assessed_at": datetime.now(UTC).isoformat(),
            "latest_fact_artifact": None,
            "valuation_gate": None,
            "annual_reports_collected": None,
            "periods_available": [],
            "db_fact_count": None,
            "ready": False,
        }

        # Load latest fact report artifact from disk
        latest_artifact = self._latest_fact_artifact()
        if latest_artifact:
            status["latest_fact_artifact"] = latest_artifact.name
            try:
                data = json.loads(latest_artifact.read_text(encoding="utf-8"))
                # Artifact stores DQ report under "validation" key
                report = data.get("validation") or {}
                status["valuation_gate"] = report.get("valuation_gate") or data.get("valuation_gate")
                status["annual_reports_collected"] = (
                    report.get("annual_reports_collected") or data.get("annual_reports_collected")
                )
                status["periods_available"] = (
                    data.get("periods_available")
                    or report.get("periods_available")
                    or []
                )
                status["ready"] = status["valuation_gate"] == "pass"
            except Exception as exc:
                status["artifact_error"] = str(exc)
        else:
            status["artifact_note"] = "No fact artifact found — run prepare() first"

        # DB fact count
        try:
            status["db_fact_count"] = self._count_db_facts()
        except Exception as exc:
            status["db_note"] = f"DB check skipped: {exc}"

        return status

    def prepare(self, strict: bool = False) -> tuple[dict, dict]:
        """Run ingest + build_facts for this ticker.

        Returns (dq_report, artifact_summary).
        Raises RuntimeError if DQ gate fails and strict=True.
        """
        print(f"[DataFoundationAgent] Preparing data foundation for {self.ticker}...")

        # Step 1: Ingest
        try:
            print(f"[DataFoundationAgent] Step 1/2 — Ingesting {self.ticker}...")
            from scripts.ingest_ticker import ingest_ticker
            ingest_ticker(
                ticker=self.ticker,
                years=list(range(self.from_year, self.to_year + 1)),
            )
        except Exception as exc:
            print(f"[DataFoundationAgent] WARNING: ingest_ticker failed: {exc}")
            print(f"[DataFoundationAgent] Proceeding with existing data...")

        # Step 2: Build facts
        print(f"[DataFoundationAgent] Step 2/2 — Building facts for {self.ticker}...")
        from scripts.build_facts import build_facts
        report, artifact = build_facts(
            ticker=self.ticker,
            from_year=self.from_year,
            to_year=self.to_year,
            strict=strict,
        )

        gate = report.get("valuation_gate", "fail")
        print(f"[DataFoundationAgent] DQ gate: {gate}")

        if strict and gate != "pass":
            raise RuntimeError(
                f"DQ gate failed for {self.ticker}: "
                f"{report.get('blocking_reasons', [])}"
            )

        return report, artifact

    def is_ready(self) -> bool:
        """Quick check: is this ticker ready for valuation?"""
        status = self.assess()
        return bool(status.get("ready"))

    # ------------------------------------------------------------------
    # Batch operations (class methods)
    # ------------------------------------------------------------------

    @classmethod
    def assess_all(cls, tickers: list[str] | None = None) -> dict[str, dict]:
        """Assess all tickers and return a readiness summary."""
        tickers = tickers or MVP_TICKERS
        return {t: cls(t).assess() for t in tickers}

    @classmethod
    def readiness_report(cls, tickers: list[str] | None = None) -> dict:
        """Print and return a formatted readiness report for all tickers."""
        tickers = tickers or MVP_TICKERS
        statuses = cls.assess_all(tickers)

        ready = [t for t, s in statuses.items() if s.get("ready")]
        not_ready = [t for t, s in statuses.items() if not s.get("ready")]

        print(f"\n{'='*60}")
        print(f"  DATA FOUNDATION READINESS REPORT")
        print(f"  {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
        print(f"{'='*60}")
        for ticker in tickers:
            s = statuses[ticker]
            gate = s.get("valuation_gate") or "UNKNOWN"
            collected = s.get("annual_reports_collected") or 0
            periods = s.get("periods_available") or []
            status_icon = "READY" if s.get("ready") else "NOT READY"
            print(f"\n  {ticker}: [{status_icon}]")
            print(f"    valuation_gate: {gate}")
            print(f"    annual_reports: {collected}")
            print(f"    periods: {', '.join(periods) or 'none'}")
            if not s.get("ready"):
                note = s.get("artifact_note", f"gate={gate}")
                print(f"    note: {note}")
        print(f"\n{'='*60}")
        print(f"  Ready ({len(ready)}): {', '.join(ready) or 'none'}")
        print(f"  Not ready ({len(not_ready)}): {', '.join(not_ready) or 'none'}")
        print(f"{'='*60}\n")

        return {
            "assessed_at": datetime.now(UTC).isoformat(),
            "ready": ready,
            "not_ready": not_ready,
            "details": statuses,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _latest_fact_artifact(self) -> Path | None:
        files = sorted(FACTS_DIR.glob(f"{self.ticker}_*_fact_report.json"), reverse=True)
        return files[0] if files else None

    def _count_db_facts(self) -> int:
        import psycopg2
        conn = psycopg2.connect(os.getenv("DATABASE_URL", ""))
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM fact.financial_facts
                    WHERE ticker = %s AND fiscal_period = 'FY'
                      AND validation_status = 'accepted'
                    """,
                    (self.ticker,),
                )
                row = cur.fetchone()
                return row[0] if row else 0
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="DataFoundationAgent — assess and prepare ticker data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", default=None, help="Ticker (e.g. DHG); omit for all MVP tickers")
    parser.add_argument("--ingest", action="store_true", help="Run ingest + build_facts (prepare mode)")
    parser.add_argument("--all", action="store_true", help="Assess all MVP tickers")
    parser.add_argument("--run-job", default=None,
                        help="Trigger a scheduler job immediately (weekly_sync, daily_prices, monthly_valuation)")
    parser.add_argument("--from-year", type=int, default=MVP_FROM_YEAR, dest="from_year")
    parser.add_argument("--to-year", type=int, default=MVP_TO_YEAR, dest="to_year")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.run_job:
        from backend.jobs.scheduler import run_job_now
        result = run_job_now(args.run_job, ticker=args.ticker)
        print(f"[DataFoundationAgent] Job '{args.run_job}' complete:")
        for t, status in result.get("result", {}).items():
            print(f"  {t}: {status}")
        return

    if args.all or not args.ticker:
        DataFoundationAgent.readiness_report()
        return

    agent = DataFoundationAgent(
        ticker=args.ticker,
        from_year=args.from_year,
        to_year=args.to_year,
    )

    if args.ingest:
        report, artifact = agent.prepare()
        gate = report.get("valuation_gate", "fail")
        print(f"\n[DataFoundationAgent] {args.ticker}: valuation_gate={gate}")
        print(f"[DataFoundationAgent] ready={agent.is_ready()}")
    else:
        status = agent.assess()
        print(f"\n[DataFoundationAgent] Status for {args.ticker}:")
        for k, v in status.items():
            if k != "ticker":
                print(f"  {k}: {v}")
        print(f"\n[DataFoundationAgent] ready={status['ready']}")

    print("[DataFoundationAgent] done")


if __name__ == "__main__":
    main()
