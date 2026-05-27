"""Scheduled background jobs for the equity research pipeline.

Jobs:
  weekly_sync     — run ingest_ticker + build_facts for all active MVP tickers
  daily_prices    — refresh market price data (catalyst / price updates)
  monthly_valuation — recompute valuation artifacts for all active tickers

The scheduler uses APScheduler (BackgroundScheduler). It can run embedded
in the FastAPI server or as a standalone process.

Standalone usage:
    python -m backend.jobs.scheduler
    python -m backend.jobs.scheduler --run-now weekly_sync
    python -m backend.jobs.scheduler --run-now daily_prices --ticker DHG

Embedding in FastAPI: call start() on app startup and stop() on shutdown.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
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

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    _APScheduler_available = True
except ImportError:
    _APScheduler_available = False

logger = logging.getLogger(__name__)

MVP_TICKERS = ["DHG", "IMP", "DMC", "TRA", "DBD"]
MVP_FROM_YEAR = 2021
MVP_TO_YEAR = 2025


# ---------------------------------------------------------------------------
# Job implementations
# ---------------------------------------------------------------------------

def job_weekly_sync(ticker: str | None = None) -> dict:
    """Ingest + build_facts for one or all MVP tickers.

    Runs on Sunday at 02:00 UTC by default.
    Can be limited to a single ticker for ad-hoc runs.
    """
    tickers = [ticker.strip().upper()] if ticker else MVP_TICKERS
    results: dict[str, str] = {}
    for t in tickers:
        try:
            logger.info("[weekly_sync] Starting ingest for %s", t)
            from scripts.ingest_ticker import ingest_ticker
            ingest_ticker(ticker=t, years=list(range(MVP_FROM_YEAR, MVP_TO_YEAR + 1)))
        except Exception as exc:
            logger.warning("[weekly_sync] ingest_ticker failed for %s: %s", t, exc)

        try:
            logger.info("[weekly_sync] Building facts for %s", t)
            from scripts.build_facts import build_facts
            report, _ = build_facts(ticker=t, from_year=MVP_FROM_YEAR, to_year=MVP_TO_YEAR)
            gate = report.get("valuation_gate", "fail")
            results[t] = f"valuation_gate={gate}"
            logger.info("[weekly_sync] %s done: %s", t, results[t])
        except Exception as exc:
            results[t] = f"FAILED: {exc}"
            logger.error("[weekly_sync] build_facts failed for %s: %s", t, exc)

    logger.info("[weekly_sync] Complete: %s", results)
    return results


def job_daily_prices(ticker: str | None = None) -> dict:
    """Refresh price data and catalyst events for one or all MVP tickers.

    Runs Monday–Friday at 18:00 ICT (11:00 UTC) after market close.
    """
    tickers = [ticker.strip().upper()] if ticker else MVP_TICKERS
    results: dict[str, str] = {}
    for t in tickers:
        try:
            logger.info("[daily_prices] Refreshing prices for %s", t)
            from scripts.connectors.vnstock_price_connector import VnstockPriceConnector
            conn = VnstockPriceConnector()
            price = conn.get_current_price(t)
            results[t] = f"price={price}"
            logger.info("[daily_prices] %s: price=%s", t, price)
        except Exception as exc:
            results[t] = f"FAILED: {exc}"
            logger.warning("[daily_prices] price refresh failed for %s: %s", t, exc)

    logger.info("[daily_prices] Complete: %s", results)
    return results


def job_monthly_valuation(ticker: str | None = None) -> dict:
    """Recompute valuation artifacts for one or all MVP tickers.

    Runs on the 1st of each month at 03:00 UTC.
    """
    tickers = [ticker.strip().upper()] if ticker else MVP_TICKERS
    results: dict[str, str] = {}
    for t in tickers:
        try:
            logger.info("[monthly_valuation] Running valuation for %s", t)
            from scripts.run_valuation import run_valuation
            artifact = run_valuation(ticker=t, from_year=MVP_FROM_YEAR, to_year=MVP_TO_YEAR)
            dcf_base = artifact.get("dcf", {}).get("base", {})
            iv = dcf_base.get("intrinsic_value_per_share_vnd")
            results[t] = f"intrinsic={iv:.0f} VND" if iv else "intrinsic=N/A"
            logger.info("[monthly_valuation] %s done: %s", t, results[t])
        except Exception as exc:
            results[t] = f"FAILED: {exc}"
            logger.error("[monthly_valuation] valuation failed for %s: %s", t, exc)

    logger.info("[monthly_valuation] Complete: %s", results)
    return results


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

_JOB_REGISTRY: dict[str, dict] = {
    "weekly_sync": {
        "fn": job_weekly_sync,
        "description": "Ingest + build_facts for all MVP tickers",
        # Every Sunday at 02:00 UTC
        "cron": {"day_of_week": "sun", "hour": 2, "minute": 0},
    },
    "daily_prices": {
        "fn": job_daily_prices,
        "description": "Refresh market prices (Mon–Fri at 11:00 UTC)",
        "cron": {"day_of_week": "mon-fri", "hour": 11, "minute": 0},
    },
    "monthly_valuation": {
        "fn": job_monthly_valuation,
        "description": "Recompute valuation artifacts (1st of month at 03:00 UTC)",
        "cron": {"day": 1, "hour": 3, "minute": 0},
    },
}


# ---------------------------------------------------------------------------
# Scheduler lifecycle
# ---------------------------------------------------------------------------

_scheduler: "BackgroundScheduler | None" = None


def start() -> None:
    """Start the background scheduler. Safe to call multiple times."""
    global _scheduler
    if not _APScheduler_available:
        logger.warning("[scheduler] APScheduler not installed — scheduler disabled. pip install apscheduler")
        return
    if _scheduler is not None and _scheduler.running:
        return

    _scheduler = BackgroundScheduler(timezone="UTC")
    for job_id, spec in _JOB_REGISTRY.items():
        _scheduler.add_job(
            spec["fn"],
            trigger=CronTrigger(**spec["cron"]),
            id=job_id,
            name=spec["description"],
            max_instances=1,
            coalesce=True,  # skip missed runs
            misfire_grace_time=600,  # 10 min tolerance
        )
    _scheduler.start()
    logger.info("[scheduler] Started with %d jobs", len(_JOB_REGISTRY))
    for job_id, spec in _JOB_REGISTRY.items():
        logger.info("  - %s: %s", job_id, spec["description"])


def stop() -> None:
    """Gracefully stop the background scheduler."""
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] Stopped")
    _scheduler = None


def get_job_status() -> list[dict]:
    """Return current job status for health checks / API endpoints."""
    if _scheduler is None or not _scheduler.running:
        return [{"id": jid, "status": "scheduler_not_running"} for jid in _JOB_REGISTRY]

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
            "status": "scheduled",
        })
    return jobs


def run_job_now(job_id: str, ticker: str | None = None) -> dict:
    """Run a registered job immediately (ad-hoc, synchronous)."""
    spec = _JOB_REGISTRY.get(job_id)
    if spec is None:
        raise ValueError(f"Unknown job: {job_id!r}. Available: {list(_JOB_REGISTRY)}")
    logger.info("[scheduler] Running job '%s' immediately (ticker=%s)", job_id, ticker or "all")
    started_at = datetime.now(UTC).isoformat()
    result = spec["fn"](ticker=ticker)
    return {
        "job_id": job_id,
        "ticker": ticker,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "result": result,
    }


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Background scheduler for the equity research pipeline.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--run-now", metavar="JOB_ID", default=None,
                        help="Run a specific job immediately and exit. "
                             f"Available: {list(_JOB_REGISTRY)}")
    parser.add_argument("--ticker", default=None,
                        help="Limit --run-now to a single ticker.")
    parser.add_argument("--list-jobs", action="store_true",
                        help="List registered jobs and their schedules, then exit.")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = _parse_args()

    if args.list_jobs:
        print("\nRegistered jobs:")
        for job_id, spec in _JOB_REGISTRY.items():
            cron = spec["cron"]
            print(f"  {job_id}: {spec['description']}")
            print(f"    schedule: {cron}")
        return

    if args.run_now:
        try:
            result = run_job_now(args.run_now, ticker=args.ticker)
            print(f"\n[scheduler] Job '{args.run_now}' complete:")
            for t, status in result.get("result", {}).items():
                print(f"  {t}: {status}")
        except ValueError as exc:
            print(f"ERROR: {exc}")
            sys.exit(1)
        return

    if not _APScheduler_available:
        print("ERROR: APScheduler not installed. Run: pip install apscheduler")
        sys.exit(1)

    start()
    print("[scheduler] Running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        stop()
        print("[scheduler] Stopped.")


if __name__ == "__main__":
    main()
