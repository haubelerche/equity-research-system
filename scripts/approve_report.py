"""Run-scoped human approval wrapper for the canonical harness.

Production approval must go through ResearchGraphRunner.handle_approval().
This script intentionally does not load "latest" reports or copy files into an
approved folder, because that bypasses deterministic export gates.

Usage:
    python scripts/approve_report.py --run-id run_dhg_20260526T... --decision approve --reviewer analyst_1
    python scripts/approve_report.py --run-id run_dhg_20260526T... --stage assumptions --decision reject --comment "Revise WACC"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_env_file = ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip(chr(34)).strip(chr(39)))


def approve_report(
    *,
    run_id: str,
    decision: str,
    reviewer: str,
    comment: str = "",
    stage: str = "final",
) -> dict:
    from backend.harness.runner import ResearchGraphRunner
    from backend.runtime_store import RuntimeStore
    from backend.settings import settings

    store = RuntimeStore(dsn=settings.database_url)
    runner = ResearchGraphRunner(store=store)
    runner.handle_approval(
        run_id=run_id,
        stage=stage,
        decision=decision,
        reviewer=reviewer,
        feedback_patch={"comment": comment, "source": "approve_report_cli"},
    )
    result = {
        "run_id": run_id,
        "stage": stage,
        "decision": decision,
        "reviewer": reviewer,
        "comment": comment,
        "approved_at": datetime.now(UTC).isoformat(),
        "approval_path": "ResearchGraphRunner.handle_approval",
    }
    print(json.dumps(result, indent=2, default=str))
    return result


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record a run-scoped human approval through the harness.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", help="Deprecated and disabled: production approval requires --run-id")
    parser.add_argument("--run-id", dest="run_id", help="Specific run_id to approve")
    parser.add_argument("--stage", choices=["assumptions", "final", "valuation_assumptions", "final_report"], default="final")
    parser.add_argument("--decision", choices=["approve", "reject", "approved", "rejected", "needs_revision"], required=True)
    parser.add_argument("--reviewer", required=True, help="Reviewer ID")
    parser.add_argument("--comment", default="", help="Review comment")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.ticker:
        print("ERROR: production approval is run-scoped. Use --run-id; --ticker approval is disabled.")
        return 2
    if not args.run_id:
        print("ERROR: provide --run-id")
        return 1
    approve_report(
        run_id=args.run_id,
        stage=args.stage,
        decision=args.decision,
        reviewer=args.reviewer,
        comment=args.comment,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
