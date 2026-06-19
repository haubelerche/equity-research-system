"""Recompute valuations in place with the fixed forecast/valuation engine.

Bridges the gap between ``run_valuation.py`` (which only writes a local
valuation.json) and the renderer (which reads the per-run ``valuation.json`` from
the Supabase ``runs`` bucket). For each ticker it:

  1. finds the latest renderable run (valuation + facts present),
  2. recomputes the full valuation artifact with the current engine,
  3. overwrites the run's ``valuation.json`` in storage (upsert), so the existing
     manifest now resolves to the corrected artifact,
  4. reports the before/after raw target, headline target, upside, and adjustment.

It renders PDFs only when --render is explicitly supplied on a non-dry-run.

Usage:
    python scripts/recompute_valuation_inplace.py --tickers DHG
    python scripts/recompute_valuation_inplace.py --all
    python scripts/recompute_valuation_inplace.py --all --dry-run
    python scripts/recompute_valuation_inplace.py --all --dry-run --audit-output output/valuation_recompute_audit.csv
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv() -> None:
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _all_tickers_with_valuation() -> list[str]:
    from backend.database.config import connect_with_retry, require_database_url
    with connect_with_retry(require_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT r.ticker
                FROM research.runs r
                JOIN research.run_artifacts a ON a.run_id = r.run_id
                WHERE a.section_key = 'valuation' AND a.storage_path IS NOT NULL
                ORDER BY r.ticker
                """
            )
            return [t for (t,) in cur.fetchall()]


def _render_run_id(ticker: str) -> str | None:
    """The run generate_fast_report will render — first candidate with a readable
    manifest that resolves a valuation artifact (some runs lack a stored manifest)."""
    import scripts.generate_fast_report as g
    from backend.reporting.artifact_manifest import read_manifest
    for run_id in g._latest_report_run_ids(ticker, "standard"):
        man = read_manifest(run_id)
        if man is not None and man.resolve("valuation"):
            return run_id
    return None


def _valuation_snapshot(valuation: dict, ticker: str, run_id: str) -> dict[str, object]:
    from backend.valuation_method_policy import build_valuation_publishability_policy
    pol = build_valuation_publishability_policy(valuation, ticker=ticker, run_id=run_id)
    headline = pol.headline_target_governance or {}
    return {
        "publishable": pol.target_price_publishable,
        "policy_target": pol.target_price_vnd,
        "current_price": headline.get("current_price_vnd"),
        "raw_model_target": headline.get("raw_model_target_vnd"),
        "headline_target": headline.get("headline_target_vnd"),
        "headline_upside": headline.get("headline_upside"),
        "target_adjustment": headline.get("target_adjustment"),
        "target_band_low": headline.get("target_band_low_vnd"),
        "target_band_high": headline.get("target_band_high_vnd"),
    }


def _price_preflight_snapshot(ticker: str) -> dict[str, object]:
    from backend.valuation.market_price_resolver import resolve_market_price

    resolution = resolve_market_price(ticker, allow_live=False)
    missing: list[str] = []
    if resolution.current_price is None:
        missing.append("current_price")
    if resolution.high is None:
        missing.append("high")
    if resolution.low is None:
        missing.append("low")
    status = "market_price_ready" if not missing else f"missing_market_price:{','.join(missing)}"
    return {
        "status": status,
        "current_price": resolution.current_price,
        "high": resolution.high,
        "low": resolution.low,
        "high_52w": resolution.high_52w,
        "low_52w": resolution.low_52w,
        "price_as_of": resolution.price_as_of,
        "price_source": resolution.source,
        "price_staleness_days": resolution.staleness_days,
        "price_warnings": ";".join(resolution.warnings),
    }


def _fmt(value: object) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:,.0f}"
    return str(value) if value not in (None, "") else "—"


def _write_audit_csv(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ticker", "run_id", "status",
        "old_current_price", "old_raw_model_target", "old_headline_target",
        "old_headline_upside", "old_target_adjustment",
        "new_current_price", "new_raw_model_target", "new_headline_target",
        "new_headline_upside", "new_target_adjustment",
        "new_target_band_low", "new_target_band_high",
        "old_publishable", "new_publishable",
        "price_preflight_status", "price_source", "price_as_of",
        "price_high", "price_low", "price_high_52w", "price_low_52w",
        "price_staleness_days", "price_warnings",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*", default=None)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="recompute + report, do not overwrite storage")
    ap.add_argument(
        "--audit-output",
        default=str(ROOT / "output" / "valuation_recompute_audit.csv"),
        help="CSV path for before/after target governance rows.",
    )
    ap.add_argument(
        "--render",
        action="store_true",
        help="After a non-dry-run storage write, render the fast report for each successful ticker.",
    )
    ap.add_argument(
        "--with-live-peer",
        action="store_true",
        help="Allow run_valuation to fetch live peer and market-snapshot data during recompute.",
    )
    args = ap.parse_args()

    _load_dotenv()
    from backend.reporting.artifact_manifest import read_manifest
    from backend.storage import RUNS_BUCKET, SupabaseStorageAdapter
    from scripts.run_valuation import run_valuation

    if args.tickers:
        tickers = [t.upper() for t in args.tickers]
    elif args.all:
        tickers = _all_tickers_with_valuation()
    else:
        ap.error("pass --tickers T1 T2 ... or --all")

    if not args.with_live_peer:
        os.environ["SKIP_LIVE_PEER"] = "1"
        os.environ["SKIP_LIVE_MARKET_SNAPSHOT"] = "1"
        os.environ["ALLOW_LIVE_MARKET_PRICE"] = "0"

    audit_path = Path(args.audit_output)
    if not audit_path.is_absolute():
        audit_path = ROOT / audit_path

    adapter = SupabaseStorageAdapter()
    print(
        f"{'TKR':6}{'old_raw':>12}{'old_head':>12}{'new_raw':>12}"
        f"{'new_head':>12}{'adj':>18}  status"
    )
    ok = fail = 0
    audit_rows: list[dict[str, object]] = []

    def record(row: dict[str, object]) -> None:
        audit_rows.append(row)
        _write_audit_csv(audit_rows, audit_path)

    for ticker in tickers:
        try:
            run_id = _render_run_id(ticker)
            if run_id is None:
                print(f"{ticker:6}{'—':>12}{'—':>12}{'—':>9}{'—':>9}  no_render_run")
                record({"ticker": ticker, "run_id": "", "status": "no_render_run"})
                fail += 1
                continue
            manifest = read_manifest(run_id)
            if manifest is None or not manifest.resolve("valuation"):
                print(f"{ticker:6}{'—':>12}{'—':>12}{'—':>9}{'—':>9}  no_manifest")
                record({"ticker": ticker, "run_id": run_id, "status": "no_manifest"})
                fail += 1
                continue
            val_path = manifest.resolve("valuation")
            old_val = manifest.load_json("valuation")
            old_val = old_val.get("payload") or old_val
            old = _valuation_snapshot(old_val, ticker, run_id)
            price_preflight = _price_preflight_snapshot(ticker)
            if price_preflight["status"] != "market_price_ready":
                print(
                    f"{ticker:6}{_fmt(old.get('raw_model_target')):>12}"
                    f"{_fmt(old.get('headline_target')):>12}"
                    f"{'â€”':>12}{'â€”':>12}"
                    f"{_fmt(price_preflight['status'])[:18]:>18}  skipped"
                )
                record({
                    "ticker": ticker,
                    "run_id": run_id,
                    "status": "skipped_missing_market_price",
                    "old_current_price": old.get("current_price"),
                    "old_raw_model_target": old.get("raw_model_target"),
                    "old_headline_target": old.get("headline_target"),
                    "old_headline_upside": old.get("headline_upside"),
                    "old_target_adjustment": old.get("target_adjustment"),
                    "price_preflight_status": price_preflight["status"],
                    "price_source": price_preflight["price_source"],
                    "price_as_of": price_preflight["price_as_of"],
                    "price_high": price_preflight["high"],
                    "price_low": price_preflight["low"],
                    "price_high_52w": price_preflight["high_52w"],
                    "price_low_52w": price_preflight["low_52w"],
                    "price_staleness_days": price_preflight["price_staleness_days"],
                    "price_warnings": price_preflight["price_warnings"],
                })
                fail += 1
                continue

            buf = io.StringIO()
            with redirect_stdout(buf):
                new_val = run_valuation(ticker=ticker, allow_live_market_price=False)
            new = _valuation_snapshot(new_val, ticker, run_id)

            if not args.dry_run:
                adapter.upload_json(RUNS_BUCKET, val_path, new_val, upsert=True)
                if args.render:
                    from scripts.generate_fast_report import generate_fast_report

                    generate_fast_report(ticker, mode="standard")

            print(
                f"{ticker:6}{_fmt(old.get('raw_model_target')):>12}"
                f"{_fmt(old.get('headline_target')):>12}"
                f"{_fmt(new.get('raw_model_target')):>12}"
                f"{_fmt(new.get('headline_target')):>12}"
                f"{_fmt(new.get('target_adjustment')):>18}  "
                f"{'dry_run' if args.dry_run else 'written'}"
            )
            record({
                "ticker": ticker,
                "run_id": run_id,
                "status": "dry_run" if args.dry_run else "written",
                "old_current_price": old.get("current_price"),
                "old_raw_model_target": old.get("raw_model_target"),
                "old_headline_target": old.get("headline_target"),
                "old_headline_upside": old.get("headline_upside"),
                "old_target_adjustment": old.get("target_adjustment"),
                "new_current_price": new.get("current_price"),
                "new_raw_model_target": new.get("raw_model_target"),
                "new_headline_target": new.get("headline_target"),
                "new_headline_upside": new.get("headline_upside"),
                "new_target_adjustment": new.get("target_adjustment"),
                "new_target_band_low": new.get("target_band_low"),
                "new_target_band_high": new.get("target_band_high"),
                "old_publishable": old.get("publishable"),
                "new_publishable": new.get("publishable"),
                "price_preflight_status": price_preflight["status"],
                "price_source": price_preflight["price_source"],
                "price_as_of": price_preflight["price_as_of"],
                "price_high": price_preflight["high"],
                "price_low": price_preflight["low"],
                "price_high_52w": price_preflight["high_52w"],
                "price_low_52w": price_preflight["low_52w"],
                "price_staleness_days": price_preflight["price_staleness_days"],
                "price_warnings": price_preflight["price_warnings"],
            })
            ok += 1
        except SystemExit as exc:
            print(f"{ticker:6}{'—':>12}{'—':>12}{'—':>9}{'—':>9}  ERR SystemExit: {exc}")
            record({
                "ticker": ticker,
                "run_id": "",
                "status": f"ERR SystemExit: {exc}",
            })
            fail += 1
        except Exception as exc:  # noqa: BLE001 — isolate per ticker
            print(f"{ticker:6}{'—':>12}{'—':>12}{'—':>9}{'—':>9}  ERR {type(exc).__name__}: {str(exc)[:60]}")
            record({
                "ticker": ticker,
                "run_id": "",
                "status": f"ERR {type(exc).__name__}: {str(exc)[:120]}",
            })
            fail += 1
        # Throttle: keep any conditional vnstock shares fetch under the guest limit.
        time.sleep(1.0)
    _write_audit_csv(audit_rows, audit_path)
    print(f"--- audit_csv: {audit_path} ---")
    print(f"--- done: {ok} ok, {fail} failed ---")


if __name__ == "__main__":
    main()
