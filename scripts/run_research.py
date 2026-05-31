"""Phase 8 — Stateful Research Workflow.

Orchestrates the full one-ticker research pipeline:

  1. build_facts  — ingest + normalize + DQ gate + snapshot
  2. run_valuation — ratios, DCF, multiples, sensitivity
  3. build_index  — evidence chunk indexing
  4. generate_report — template-based report with citations
  5. evaluate_report — numeric consistency, citation coverage, etc.

Each step is logged to research.runs and research.run_steps.
The run halts at the first critical failure.

Usage:
    python scripts/run_research.py --ticker DHG
    python scripts/run_research.py --ticker DHG --report-type full_report
    python scripts/run_research.py --ticker DHG --skip-ingest  (reuse existing facts)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

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
RUN_LOG_DIR = ROOT / "artifacts" / "runs"

MVP_FROM_YEAR = 2021
MVP_TO_YEAR = 2025


def _dsn() -> str:
    return os.getenv("DATABASE_URL", "postgresql://maer:maer_local@localhost:5432/maer_dev")


def _run_id(ticker: str) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    h = hashlib.sha256(f"{ticker}_{ts}".encode()).hexdigest()[:10]
    return f"run_{ticker.lower()}_{ts}_{h}"


def _db_create_run(conn, run_id: str, ticker: str, run_type: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO research.runs
                (run_id, ticker, run_type, objective, status, current_stage)
            VALUES (%s, %s, %s, %s, 'running', 'started')
            ON CONFLICT (run_id) DO NOTHING
            """,
            (run_id, ticker, run_type, f"full_pipeline_{run_type}_{ticker}"),
        )
    conn.commit()


def _db_update_run(conn, run_id: str, status: str, snapshot_id: str | None = None, error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE research.runs
            SET status=%s,
                finished_at=CASE WHEN %s IN ('report_ready','failed','needs_human_review') THEN NOW() ELSE finished_at END,
                snapshot_id=COALESCE(%s, snapshot_id)
            WHERE run_id=%s
            """,
            (status, status, snapshot_id, run_id),
        )
    conn.commit()


def _db_add_step(conn, run_id: str, step_name: str, status: str, output: dict | None = None, error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO research.run_steps
                (run_id, step_name, agent_name, status, started_at, ended_at,
                 metadata_json, error_message)
            VALUES (%s, %s, 'pipeline', %s, NOW(), NOW(), %s::jsonb, %s)
            """,
            (run_id, step_name, status, json.dumps(output or {}), error),
        )
    conn.commit()


class StepFailed(Exception):
    pass


class ResearchRunner:
    def __init__(self, ticker: str, run_type: str, from_year: int, to_year: int, skip_ingest: bool) -> None:
        self.ticker = ticker.strip().upper()
        self.run_type = run_type
        self.from_year = from_year
        self.to_year = to_year
        self.skip_ingest = skip_ingest
        self.run_id = _run_id(self.ticker)
        self.trace: list[dict] = []
        self.conn: psycopg2.connection | None = None

    def _log(self, step: str, status: str, detail: str = "") -> None:
        ts = datetime.now(UTC).isoformat()
        entry = {"ts": ts, "step": step, "status": status, "detail": detail}
        self.trace.append(entry)
        icon = "✓" if status == "ok" else ("✗" if status == "fail" else "…")
        print(f"[run_research] {icon} {step}: {detail or status}")

    def _step(self, name: str, fn) -> dict:
        print(f"\n[run_research] ── {name} ──────────────────────────────")
        try:
            result = fn()
            self._log(name, "ok", str(result)[:200] if result else "")
            if self.conn:
                safe = self._safe_dict(result) if isinstance(result, dict) else {"result": str(result)[:500]}
                _db_add_step(self.conn, self.run_id, name, "completed", output=safe)
            return result or {}
        except Exception as exc:
            tb = traceback.format_exc()
            self._log(name, "fail", str(exc))
            if self.conn:
                _db_add_step(self.conn, self.run_id, name, "failed", error=str(exc)[:1000])
            raise StepFailed(f"{name} failed: {exc}") from exc

    @staticmethod
    def _safe_dict(d) -> dict:
        """Convert dict to JSON-safe form (handles Decimal etc)."""
        return json.loads(json.dumps(d, default=str)) if isinstance(d, dict) else {}

    def run(self) -> dict:
        print(f"\n{'='*60}")
        print(f"  RESEARCH RUN — {self.ticker}")
        print(f"  run_id: {self.run_id}")
        print(f"  type: {self.run_type}")
        print(f"{'='*60}\n")

        try:
            self.conn = psycopg2.connect(_dsn())
            _db_create_run(self.conn, self.run_id, self.ticker, self.run_type)
        except Exception as exc:
            print(f"[run_research] WARNING: DB connection failed — run will not be logged: {exc}")
            self.conn = None

        snap_id: str | None = None
        val_artifact: dict = {}
        index_summary: dict = {}
        citation_data: dict = {}
        eval_result: dict = {}
        status = "completed"
        error_msg: str | None = None

        try:
            # ── Step 1: Build facts (ingest + DQ gate + snapshot) ─────────────
            if not self.skip_ingest:
                def _build_facts():
                    from scripts.build_facts import build_facts
                    report, artifact = build_facts(
                        ticker=self.ticker,
                        from_year=self.from_year,
                        to_year=self.to_year,
                        strict=True,
                    )
                    dq_gate = report.get("valuation_gate", "fail")
                    if dq_gate != "pass":
                        raise RuntimeError(f"DQ gate failed: {dq_gate}. Gates: {report.get('gates', {})}")
                    return {"valuation_gate": dq_gate, "snapshot_id": artifact.get("snapshot_id")}

                facts_result = self._step("build_facts", _build_facts)
                snap_id = facts_result.get("snapshot_id")
            else:
                print("[run_research] Skipping ingest (--skip-ingest)")
                # Load latest snapshot
                from backend.dataops.snapshot import get_latest_snapshot
                snap = get_latest_snapshot(self.ticker, self.from_year, self.to_year)
                if snap:
                    snap_id = snap["snapshot_id"]
                    self._log("build_facts", "ok", f"Reusing snapshot {snap_id}")
                else:
                    self._log("build_facts", "warn", "No existing snapshot found — continuing without")

            if self.conn and snap_id:
                _db_update_run(self.conn, self.run_id, "running", snapshot_id=snap_id)

            # ── Step 2: Auto-ingest official documents BEFORE valuation ────────
            # Auto-ingest official documents BEFORE valuation so promoted verified facts
            # are available to the valuation engine during this run.
            def _auto_ingest_official():
                from scripts.auto_ingest_official_documents import AutoIngestConfig, run_pipeline as _run_auto_ingest
                _auto_cfg = AutoIngestConfig(
                    ticker=self.ticker,
                    from_year=self.from_year,
                    to_year=self.to_year,
                    dry_run=False,
                    channels=["cafef", "pdf"],
                )
                _auto_results = _run_auto_ingest(_auto_cfg)
                _total_promoted = sum(r.promoted for r in _auto_results)
                return {"promoted": _total_promoted, "results": len(_auto_results)}

            try:
                auto_ingest_result = self._step("auto_ingest_official_documents", _auto_ingest_official)
                print(f"[run_research] Auto-ingest complete: {auto_ingest_result.get('promoted')} fact(s) promoted to verified")
            except StepFailed:
                print("[run_research] WARNING: auto-ingest failed — report will use Tier 3 facts")

            # ── Step 3: Run valuation ──────────────────────────────────────────
            def _run_valuation():
                from scripts.run_valuation import run_valuation
                artifact = run_valuation(
                    ticker=self.ticker,
                    from_year=self.from_year,
                    to_year=self.to_year,
                )
                dcf_base = artifact.get("dcf", {}).get("base", {})
                return {
                    "snapshot_id": artifact.get("snapshot_id"),
                    "facts_count": artifact.get("multiples", {}).get("shares_mn"),
                    "dcf_intrinsic": dcf_base.get("intrinsic_value_per_share_vnd"),
                }

            val_result = self._step("run_valuation", _run_valuation)
            # Always use the snapshot from the latest valuation run
            snap_id = val_result.get("snapshot_id") or snap_id

            # ── Step 4: Build evidence index ───────────────────────────────────
            def _build_index():
                from scripts.build_index import build_index
                return build_index(
                    ticker=self.ticker,
                    years=list(range(self.from_year, self.to_year + 1)),
                )

            index_summary = self._step("build_index", _build_index)

            # ── Step 5: Generate report ────────────────────────────────────────
            def _generate_report():
                from scripts.generate_report import generate_report
                return generate_report(
                    ticker=self.ticker,
                    from_year=self.from_year,
                    to_year=self.to_year,
                    report_type=self.run_type,
                    snapshot_id=snap_id,
                )

            citation_data = self._step("generate_report", _generate_report)

            # ── Step 6: Evaluate report ────────────────────────────────────────
            def _evaluate_report():
                from scripts.evaluate_report import evaluate_report
                return evaluate_report(ticker=self.ticker)

            eval_result = self._step("evaluate_report", _evaluate_report)

            if eval_result.get("any_critical_fail"):
                status = "needs_human_review"
                error_msg = "Evaluation critical gates failed — human review required"
                self._log("gate_check", "fail", error_msg)
            else:
                status = "report_ready"
                self._log("gate_check", "ok", f"Overall: {eval_result.get('overall_status')}")

        except StepFailed as exc:
            status = "failed"
            error_msg = str(exc)
        except Exception as exc:
            status = "failed"
            error_msg = f"Unexpected error: {exc}"
            traceback.print_exc()

        if self.conn:
            _db_update_run(self.conn, self.run_id, status, error=error_msg)
            self.conn.close()

        # ── Save run log ───────────────────────────────────────────────────────
        run_log = {
            "run_id": self.run_id,
            "ticker": self.ticker,
            "run_type": self.run_type,
            "status": status,
            "from_year": self.from_year,
            "to_year": self.to_year,
            "snapshot_id": snap_id,
            "error": error_msg,
            "trace": self.trace,
            "index_summary": index_summary,
            "citation_data": citation_data,
            "eval_result": eval_result,
            "generated_at": datetime.now(UTC).isoformat(),
        }

        RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        log_path = RUN_LOG_DIR / f"{self.ticker}_{ts}_{self.run_id}_run_log.json"
        log_path.write_text(json.dumps(run_log, indent=2, default=str), encoding="utf-8")

        print(f"\n{'='*60}")
        print(f"  RUN COMPLETE — {self.ticker}")
        print(f"  Status: {status.upper()}")
        print(f"  run_id: {self.run_id}")
        print(f"  snapshot_id: {snap_id or 'N/A'}")
        if error_msg:
            print(f"  Error: {error_msg}")
        print(f"  Run log: {log_path}")
        print(f"{'='*60}\n")

        if status == "needs_human_review":
            print("[run_research] Evaluation gates require review. Run approve_report.py when ready.")
        elif status == "report_ready":
            print(f"[run_research] Pipeline complete. Run: python scripts/approve_report.py --run-id {self.run_id}")

        return run_log


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run full research pipeline for a VN pharma ticker.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--from-year", type=int, default=MVP_FROM_YEAR, dest="from_year")
    parser.add_argument("--to-year", type=int, default=MVP_TO_YEAR, dest="to_year")
    parser.add_argument("--report-type", default="full_report", dest="run_type")
    parser.add_argument("--skip-ingest", action="store_true", dest="skip_ingest",
                        help="Skip build_facts step and reuse existing snapshot.")
    parser.add_argument("--legacy-pipeline", action="store_true", dest="legacy_pipeline",
                        help="Use the pre-harness script pipeline instead of the LangGraph harness.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.legacy_pipeline:
        from backend.harness.runner import ResearchGraphRunner
        from backend.orchestrator import RunContext
        from backend.runtime_store import RuntimeStore
        from backend.settings import settings

        ticker = args.ticker.strip().upper()
        run_id = _run_id(ticker)
        flags = {
            "factsChanged": False,
            "catalystChanged": False,
            "valuationChanged": False,
            "thesisNeedsRefresh": False,
            "citationsNeedRefresh": False,
        }
        policy = {
            "budget_policy": settings.default_budget_policy,
            "soft_budget_usd": settings.soft_budget_usd,
            "hard_budget_usd": settings.hard_budget_usd,
            "fallback_model": settings.fallback_model,
        }
        store = RuntimeStore(dsn=settings.database_url)
        store.check_schema_version()
        store.create_run(
            run_id=run_id,
            ticker=ticker,
            run_type=args.run_type,
            objective=f"full_pipeline_{args.run_type}_{ticker}",
            flags=flags,
            config_snapshot_json=policy,
            requested_by="run_research_cli",
        )
        runner = ResearchGraphRunner(store=store)
        runner.execute(
            RunContext(
                run_id=run_id,
                ticker=ticker,
                run_type=args.run_type,
                objective=f"full_pipeline_{args.run_type}_{ticker}",
                policy=policy,
                flags=flags,
            )
        )
        print(f"[run_research] harness submitted run_id={run_id}")
        print("[run_research] graph pauses for HITL approvals when required")
        return

    runner = ResearchRunner(
        ticker=args.ticker,
        run_type=args.run_type,
        from_year=args.from_year,
        to_year=args.to_year,
        skip_ingest=args.skip_ingest,
    )
    result = runner.run()
    if result.get("status") == "failed":
        sys.exit(1)
    print("[run_research] done")


if __name__ == "__main__":
    main()
