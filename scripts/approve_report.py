"""Phase 9 — Human Review and Export.

Presents the latest report for a run to the reviewer, records the approval
decision in research.run_approvals, and exports the final approved report.

Usage:
    python scripts/approve_report.py --ticker DHG
    python scripts/approve_report.py --run-id run_dhg_20260526T...
    python scripts/approve_report.py --ticker DHG --decision reject --comment "WACC too low"
    python scripts/approve_report.py --ticker DHG --decision approve --reviewer "analyst_1"
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_env_file = Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip(chr(34)).strip(chr(39)))

import psycopg2

ROOT = Path(__file__).resolve().parents[1]
REPORTS_DIR = ROOT / "reports"
APPROVED_DIR = ROOT / "reports" / "approved"
RUN_LOG_DIR = ROOT / "artifacts" / "runs"
EVAL_DIR = ROOT / "artifacts" / "evaluation"


def _dsn() -> str:
    return os.getenv("DATABASE_URL", "postgresql://maer:maer_local@localhost:5432/maer_dev")


def _load_run_from_db(run_id: str) -> dict | None:
    try:
        conn = psycopg2.connect(_dsn())
        import psycopg2.extras
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM research.runs WHERE run_id=%s",
                (run_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _load_latest_run_log(ticker: str) -> tuple[str | None, dict]:
    logs = sorted(RUN_LOG_DIR.glob(f"{ticker.upper()}_*_run_log.json"), reverse=True)
    if not logs:
        return None, {}
    data = json.loads(logs[0].read_text(encoding="utf-8"))
    return data.get("run_id"), data


def _load_latest_report(ticker: str) -> tuple[Path | None, str]:
    files = sorted(REPORTS_DIR.glob(f"{ticker.upper()}_*.md"), reverse=True)
    if not files:
        return None, ""
    p = files[0]
    return p, p.read_text(encoding="utf-8")


def _load_latest_eval(ticker: str) -> dict:
    files = sorted(EVAL_DIR.glob(f"{ticker.upper()}_*_evaluation.json"), reverse=True)
    if not files:
        return {}
    return json.loads(files[0].read_text(encoding="utf-8"))


def _record_approval(conn, run_id: str, decision: str, reviewer: str, comment: str, approval_type: str = "final_report") -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO research.run_approvals
                (run_id, approval_stage, decision, reviewer, feedback_patch_json)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (run_id, approval_type, decision, reviewer, json.dumps({"comment": comment})),
        )
    conn.commit()


def _update_run_status(conn, run_id: str, status: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE research.runs SET status=%s, finished_at=NOW() WHERE run_id=%s",
            (status, run_id),
        )
    conn.commit()


def _export_report(report_path: Path, ticker: str, run_id: str) -> Path:
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out_name = f"{ticker}_{ts}_APPROVED_{run_id[:20]}.md"
    out_path = APPROVED_DIR / out_name
    shutil.copy2(report_path, out_path)
    return out_path


def approve_report(
    ticker: str | None = None,
    run_id: str | None = None,
    decision: str = "approve",
    reviewer: str = "analyst",
    comment: str = "",
    interactive: bool = True,
) -> dict:
    ticker_upper = (ticker or "").strip().upper()

    # ── Load run context ───────────────────────────────────────────────────────
    if run_id:
        run_data = _load_run_from_db(run_id) or {}
        if not ticker_upper and run_data:
            ticker_upper = run_data.get("ticker", "").upper()
    else:
        resolved_run_id, run_log = _load_latest_run_log(ticker_upper)
        run_id = resolved_run_id
        run_data = run_log

    if not ticker_upper:
        print("[approve_report] ERROR: Cannot determine ticker. Provide --ticker or --run-id.")
        sys.exit(1)

    # ── Load report and evaluation ─────────────────────────────────────────────
    report_path, report_text = _load_latest_report(ticker_upper)
    eval_data = _load_latest_eval(ticker_upper)

    print(f"\n{'='*60}")
    print(f"  HUMAN REVIEW — {ticker_upper}")
    print(f"  run_id: {run_id or 'N/A'}")
    print(f"  Report: {report_path.name if report_path else 'NOT FOUND'}")
    print(f"{'='*60}\n")

    if not report_path:
        print(f"[approve_report] ERROR: No report found for {ticker_upper}. Run generate_report.py first.")
        sys.exit(1)

    # ── Show evaluation gate summary ───────────────────────────────────────────
    if eval_data:
        overall = eval_data.get("overall_status", "UNKNOWN")
        blocked = eval_data.get("export_blocked", False)
        print(f"Evaluation status: {overall}")
        if blocked:
            print("⚠  EXPORT IS BLOCKED — critical evaluation gates failed.")
            print("   Fix the issues before approving.\n")
        for gate_name, gate in eval_data.get("gates", {}).items():
            status_str = "PASS" if gate.get("pass") else ("CRITICAL" if gate.get("critical_fail") else "WARN")
            print(f"  [{status_str}] {gate_name}")
        print()
    else:
        print("⚠  No evaluation found. Run evaluate_report.py first.\n")
        blocked = False

    # ── Show report excerpt ────────────────────────────────────────────────────
    print("── Report excerpt (first 50 lines) ──────────────────────")
    for line in report_text.splitlines()[:50]:
        print(f"  {line}")
    print("  [...]\n")

    # ── Interactive decision ───────────────────────────────────────────────────
    if interactive and decision not in ("approve", "reject"):
        print("Review the report above and evaluation summary.")
        if blocked:
            print("WARNING: Export is blocked due to critical evaluation failures.")
        while True:
            choice = input("Decision [approve/reject/skip]: ").strip().lower()
            if choice in ("approve", "reject", "skip"):
                decision = choice
                break
            print("Please enter 'approve', 'reject', or 'skip'.")
        if decision not in ("approve", "reject"):
            print("[approve_report] Review skipped.")
            return {"decision": "skip", "run_id": run_id, "ticker": ticker_upper}
        if not comment:
            comment = input("Comment (optional): ").strip()
        if not reviewer or reviewer == "analyst":
            reviewer = input("Reviewer ID (press Enter for 'analyst'): ").strip() or "analyst"

    if decision in ("approve", "approved") and eval_data.get("export_blocked"):
        print("[approve_report] ERROR: Cannot approve — export is blocked by evaluation gates.")
        print("  Fix critical evaluation failures before approving.")
        sys.exit(3)

    # Normalize decision to DB-valid values
    _decision_map = {"approve": "approved", "reject": "rejected"}
    db_decision = _decision_map.get(decision, decision)

    # ── Record decision ────────────────────────────────────────────────────────
    approval_ts = datetime.now(UTC).isoformat()
    conn = None
    try:
        conn = psycopg2.connect(_dsn())
        if run_id:
            _record_approval(conn, run_id, db_decision, reviewer, comment)
            new_status = "approved" if db_decision == "approved" else "cancelled"
            _update_run_status(conn, run_id, new_status)
    except Exception as exc:
        print(f"[approve_report] WARNING: DB record failed: {exc}")
    finally:
        if conn:
            conn.close()

    # ── Export if approved ─────────────────────────────────────────────────────
    exported_path: Path | None = None
    if db_decision == "approved":
        exported_path = _export_report(report_path, ticker_upper, run_id or "manual")
        print(f"[approve_report] Report approved and exported: {exported_path}")
    else:
        print(f"[approve_report] Report rejected by {reviewer}. Comment: {comment}")

    result = {
        "run_id": run_id,
        "ticker": ticker_upper,
        "decision": decision,
        "reviewer": reviewer,
        "comment": comment,
        "approved_at": approval_ts,
        "report_file": str(report_path),
        "exported_to": str(exported_path) if exported_path else None,
    }

    # Save approval record
    APPROVED_DIR.mkdir(parents=True, exist_ok=True)
    approval_log = APPROVED_DIR / f"{ticker_upper}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_approval.json"
    approval_log.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[approve_report] Approval record saved: {approval_log}")

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Human review and approval of a generated research report.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", help="Ticker to review (uses latest report)")
    parser.add_argument("--run-id", dest="run_id", help="Specific run_id to approve")
    parser.add_argument("--decision", choices=["approve", "reject"], default=None,
                        help="Decision (omit for interactive mode)")
    parser.add_argument("--reviewer", default="analyst", help="Reviewer ID")
    parser.add_argument("--comment", default="", help="Review comment")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.ticker and not args.run_id:
        print("ERROR: provide --ticker or --run-id")
        sys.exit(1)

    # Map CLI decision values to DB constraint values
    _decision_map = {"approve": "approved", "reject": "rejected"}
    cli_decision = args.decision
    interactive = cli_decision is None
    db_decision = _decision_map.get(cli_decision or "", cli_decision or "")
    result = approve_report(
        ticker=args.ticker,
        run_id=args.run_id,
        decision=db_decision,
        reviewer=args.reviewer,
        comment=args.comment,
        interactive=interactive,
    )
    print("[approve_report] done")


if __name__ == "__main__":
    main()
