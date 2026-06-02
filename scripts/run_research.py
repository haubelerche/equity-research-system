"""Canonical harness entrypoint for one-ticker equity research runs.

Production usage:
    python scripts/run_research.py --ticker DHG
    python scripts/run_research.py --ticker DHG --from-year 2021 --to-year 2025 --ocr

This script submits work to `backend.harness.runner.ResearchGraphRunner`.
Render-only and pre-harness flows must stay outside this production path.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

MVP_FROM_YEAR = 2021
MVP_TO_YEAR = 2025


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _run_id(ticker: str) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    digest = hashlib.sha256(f"{ticker}_{ts}".encode()).hexdigest()[:10]
    return f"run_{ticker.lower()}_{ts}_{digest}"


def _default_flags() -> dict[str, bool]:
    return {
        "factsChanged": False,
        "catalystChanged": False,
        "valuationChanged": False,
        "thesisNeedsRefresh": False,
        "citationsNeedRefresh": False,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit a production research run through the harness.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--from-year", type=int, default=MVP_FROM_YEAR, dest="from_year")
    parser.add_argument("--to-year", type=int, default=MVP_TO_YEAR, dest="to_year")
    parser.add_argument("--report-type", default="full_report", dest="run_type")
    parser.add_argument(
        "--ocr",
        action="store_true",
        default=False,
        help="Enable OCR for scanned official PDFs when the ingest stage runs.",
    )
    return parser.parse_args(argv)


def submit_harness_run(args: argparse.Namespace) -> str:
    from backend.harness.runner import ResearchGraphRunner
    from backend.orchestrator import RunContext
    from backend.runtime_store import RuntimeStore
    from backend.settings import settings
    from backend.universe_registration import ensure_ticker_registered_from_universe

    ticker = args.ticker.strip().upper()
    run_id = _run_id(ticker)
    objective = f"full_pipeline_{args.run_type}_{ticker}"
    policy = {
        "budget_policy": settings.default_budget_policy,
        "soft_budget_usd": settings.soft_budget_usd,
        "hard_budget_usd": settings.hard_budget_usd,
        "fallback_model": settings.fallback_model,
        "period_scope": {
            "period_type": "FY",
            "from_year": args.from_year,
            "to_year": args.to_year,
        },
        "export_gate_policy": "config/harness/export_gate_policy.yml",
    }

    store = RuntimeStore(dsn=settings.database_url)
    store.check_schema_version()
    ensure_ticker_registered_from_universe(store, ticker)
    store.create_run(
        run_id=run_id,
        ticker=ticker,
        run_type=args.run_type,
        objective=objective,
        flags=_default_flags(),
        config_snapshot_json=policy,
        requested_by="run_research_cli",
    )

    runner = ResearchGraphRunner(store=store)
    runner.execute(
        RunContext(
            run_id=run_id,
            ticker=ticker,
            run_type=args.run_type,
            objective=objective,
            policy=policy,
            flags=_default_flags(),
            from_year=args.from_year,
            to_year=args.to_year,
            ocr=args.ocr,
        )
    )
    return run_id


def main(argv: list[str] | None = None) -> None:
    _load_dotenv()
    args = parse_args(argv)
    run_id = submit_harness_run(args)
    print(f"[run_research] harness run_id={run_id}")
    print("[run_research] graph pauses for deterministic gates and required HITL approvals")


if __name__ == "__main__":
    main()
