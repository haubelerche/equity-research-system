"""Backfill draft-renderable reports from already-crawled canonical data.

This command does not crawl vnstock, OCR PDFs, or call the full agent graph.
It rebuilds the minimum run artifacts that the renderer needs:

    facts_snapshot.json + valuation.json + optional forecast.json + manifest.json

Then it renders and uploads the ticker-stable report/explanation PDFs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.harness.state import ArtifactRef, ServiceNodeResult, stable_hash
from backend.harness.tools import build_facts_tool, run_forecast_tool, run_valuation_tool
from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR
from backend.reporting.report_delivery import render_and_store
from backend.runtime_store import RuntimeStore
from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter, run_artifact_key
from backend.universe_registration import ensure_ticker_registered_from_universe


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
    digest = hashlib.sha256(f"draft_render_backfill:{ticker}:{ts}".encode()).hexdigest()[:10]
    return f"run_{ticker.lower()}_{ts}_{digest}"


def _universe_tickers() -> list[str]:
    path = ROOT / "config" / "dataset" / "universe" / "pharma_vn_universe.csv"
    with path.open(newline="", encoding="utf-8") as handle:
        return [
            str(row.get("ticker") or "").strip().upper()
            for row in csv.DictReader(handle)
            if str(row.get("ticker") or "").strip()
        ]


def _parse_tickers(raw: str | None, *, all_tickers: bool) -> list[str]:
    if all_tickers:
        return _universe_tickers()
    if not raw:
        raise SystemExit("Provide --tickers A,B,C or --all.")
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


def _ref_dict(ref: ArtifactRef | dict[str, Any]) -> dict[str, Any]:
    return ref.model_dump(mode="json") if isinstance(ref, ArtifactRef) else dict(ref)


def _save_result_refs(store: RuntimeStore, run_id: str, result: ServiceNodeResult) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for ref_obj in result.artifact_refs:
        ref = _ref_dict(ref_obj)
        if not ref.get("section_key"):
            continue
        refs.append(ref)
        store.save_artifact(
            artifact_id=str(ref.get("artifact_id") or f"{run_id}_{ref['section_key']}"),
            run_id=run_id,
            artifact_type=str(ref.get("artifact_type") or "run_log_json"),
            section_key=str(ref["section_key"]),
            version=int(ref.get("version") or 1),
            payload=result.summary,
            storage_bucket=ref.get("storage_bucket"),
            storage_path=ref.get("storage_path"),
            checksum=ref.get("checksum") or stable_hash(result.summary),
            created_by_agent=str(ref.get("producer") or result.node_name),
            is_locked=bool(ref.get("is_locked") or False),
        )
    return refs


def _write_manifest(run_id: str, ticker: str, refs: list[dict[str, Any]]) -> str:
    artifacts: dict[str, dict[str, Any]] = {}
    for ref in refs:
        path = str(ref.get("storage_path") or "")
        section_key = str(ref.get("section_key") or "")
        if not path or not section_key:
            continue
        artifacts[section_key] = {
            "path": path,
            "producer": str(ref.get("producer") or "draft_render_backfill"),
            "artifact_type": str(ref.get("artifact_type") or "run_log_json"),
            "version": int(ref.get("version") or 1),
            "checksum": ref.get("checksum"),
        }
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "ticker": ticker,
        "created_at": datetime.now(UTC).isoformat(),
        "artifacts": artifacts,
    }
    key = run_artifact_key(run_id, "manifest.json")
    SupabaseStorageAdapter().upload_json(RUNS_BUCKET, key, payload, upsert=True)
    return key


def _has_price(ticker: str) -> bool:
    from backend.database.config import connect_with_retry, require_database_url

    with connect_with_retry(require_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM fact.price_history WHERE ticker = %s LIMIT 1", (ticker,))
            return cur.fetchone() is not None


def backfill_ticker(
    ticker: str,
    *,
    from_year: int,
    to_year: int,
    render: bool,
    auto_approve_assumptions: bool,
) -> dict[str, Any]:
    ticker = ticker.upper()
    run_id = _run_id(ticker)
    store = RuntimeStore()
    ensure_ticker_registered_from_universe(store, ticker)
    store.create_run(
        run_id=run_id,
        ticker=ticker,
        run_type="full_report",
        objective=f"draft_render_backfill_{ticker}",
        flags={"draft_render_backfill": True},
        requested_by="backfill_renderable_reports",
        config_snapshot_json={
            "period_scope": {"period_type": "FY", "from_year": from_year, "to_year": to_year},
            "draft_mode": True,
            "auto_approve_assumptions": auto_approve_assumptions,
        },
    )
    store.update_run_state(run_id, "running", "BACKFILL")

    refs: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        facts_result = build_facts_tool(ticker, from_year=from_year, to_year=to_year, run_id=run_id)
        refs.extend(_save_result_refs(store, run_id, facts_result))
        snapshot_id = facts_result.summary.get("snapshot_id")
        if not snapshot_id:
            raise RuntimeError("facts_snapshot_missing")

        try:
            forecast_result = run_forecast_tool(
                ticker,
                snapshot_id=str(snapshot_id),
                from_year=from_year,
                to_year=to_year,
                run_id=run_id,
            )
            refs.extend(_save_result_refs(store, run_id, forecast_result))
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"forecast_backfill_failed:{type(exc).__name__}:{exc}")

        valuation_result = run_valuation_tool(
            ticker,
            from_year=from_year,
            to_year=to_year,
            run_id=run_id,
            auto_approve_assumptions=auto_approve_assumptions,
        )
        refs.extend(_save_result_refs(store, run_id, valuation_result))

        manifest_path = _write_manifest(run_id, ticker, refs)
        store.save_artifact(
            artifact_id=f"{run_id}_manifest",
            run_id=run_id,
            artifact_type="run_manifest_json",
            section_key="manifest",
            version=1,
            payload={"manifest_path": manifest_path, "artifacts": [r.get("section_key") for r in refs]},
            storage_bucket=RUNS_BUCKET,
            storage_path=manifest_path,
            checksum=stable_hash({"run_id": run_id, "refs": refs}),
            created_by_agent="draft_render_backfill",
            is_locked=False,
        )

        rendered = None
        if render:
            rendered_report = render_and_store(ticker, run_id, mode="analyst_draft")
            rendered = rendered_report.__dict__
        store.update_run_state(run_id, "auto_exported", "PUBLISH", finished=True)
        return {
            "ticker": ticker,
            "run_id": run_id,
            "status": "rendered" if render else "backfilled",
            "has_price_history": _has_price(ticker),
            "manifest_path": manifest_path,
            "warnings": warnings,
            "rendered": rendered,
        }
    except Exception as exc:  # noqa: BLE001
        store.update_run_state(run_id, "failed", "BACKFILL", finished=True)
        return {
            "ticker": ticker,
            "run_id": run_id,
            "status": "failed",
            "has_price_history": _has_price(ticker),
            "error_type": type(exc).__name__,
            "error": str(exc),
            "warnings": warnings,
        }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill renderer-ready draft artifacts without recrawling source data.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--tickers", help="Comma-separated tickers, for example DHG,IMP,DMC.")
    parser.add_argument("--all", action="store_true", help="Process the configured universe.")
    parser.add_argument("--from-year", type=int, default=DEFAULT_FROM_YEAR, dest="from_year")
    parser.add_argument("--to-year", type=int, default=DEFAULT_TO_YEAR, dest="to_year")
    parser.add_argument("--limit", type=int, default=0, help="Optional maximum tickers to process.")
    parser.add_argument("--no-render", action="store_true", help="Only write artifacts and manifest.")
    parser.add_argument(
        "--no-auto-approve-assumptions",
        action="store_true",
        help="Keep valuation assumptions unapproved; target may be draft-only.",
    )
    parser.add_argument("--write-json", default="output/backfill_renderable_reports.json")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _load_dotenv()
    args = parse_args(argv)
    tickers = _parse_tickers(args.tickers, all_tickers=bool(args.all))
    if args.limit and args.limit > 0:
        tickers = tickers[: args.limit]

    results = []
    for ticker in tickers:
        print(f"[backfill] {ticker}: start", flush=True)
        result = backfill_ticker(
            ticker,
            from_year=args.from_year,
            to_year=args.to_year,
            render=not args.no_render,
            auto_approve_assumptions=not args.no_auto_approve_assumptions,
        )
        results.append(result)
        print(f"[backfill] {ticker}: {result['status']} run_id={result['run_id']}", flush=True)

    summary = {
        "processed": len(results),
        "rendered": sum(1 for r in results if r["status"] == "rendered"),
        "backfilled": sum(1 for r in results if r["status"] == "backfilled"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "missing_price_history": [r["ticker"] for r in results if not r.get("has_price_history")],
    }
    output = {"summary": summary, "results": results}
    out_path = Path(args.write_json)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"[backfill] wrote {out_path}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
