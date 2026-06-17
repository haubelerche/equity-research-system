"""Audit per-ticker readiness across the 5 inputs a valuation report consumes.

Unlike audit_universe_report_readiness.py (raw BCTC + local PDF + DB run) and
audit_universe_data_gaps.py (DB facts + market cache identity), this audit answers
the operator question "does every universe ticker have the *content* needed to
synthesise a valuation report?" across exactly these inputs:

  1. news          - whitelisted news collected for the ticker
  2. market        - current price + 52w movement (CafeF/vnstock overview + quotes)
  3. agm_drivers   - OCR'd shareholder-resolution detail used as internal forward
                     drivers (borrowing/investment/business-direction/targets 2026)
  4. peer          - relative-multiple peer comparison availability (derived)
  5. ocr_financials- LLM/OCR-extracted facts from the annual financial-report PDFs
     raw_financials- vnstock annual statements cached locally (peer/forecast base)

It is filesystem-only (no DB) so it runs anywhere; news/peer that live primarily
in the DB are reported as "fs_signal" with a note that the live pipeline is the
source of truth.

Usage:
    python scripts/audit_report_data_completeness.py
    python scripts/audit_report_data_completeness.py --write-json output/report_data_completeness.json
    python scripts/audit_report_data_completeness.py --strict   # exit 1 if any ticker not report-ready
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

RAW_BCTC_FILES = (
    "income_statement_year.json",
    "balance_sheet_year.json",
    "cash_flow_year.json",
    "ratio_year.json",
)
OFFICIAL_DIR = ROOT / "artifacts" / "official_sources"
MARKET_ROOT = ROOT / "data" / "raw" / "market"
RAW_BCTC_ROOT = ROOT / "data" / "raw" / "bctc"

# AGM driver buckets that actually feed the forward forecast (debt/vay, capex,
# business direction, 2026 targets). dividend alone is not enough to call it a
# usable internal driver pack.
FORWARD_DRIVER_KEYS = (
    "borrowing_plan",
    "investment_plan",
    "rnd_and_product_focus",
    "business_direction",
    "targets_2026",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _raw_bctc_status(ticker: str) -> dict[str, Any]:
    d = RAW_BCTC_ROOT / ticker
    populated = 0
    present = 0
    for name in RAW_BCTC_FILES:
        p = d / name
        if not p.is_file():
            continue
        present += 1
        try:
            payload = _read_json(p)
            if isinstance(payload, dict) and payload.get("data"):
                populated += 1
        except Exception:
            pass
    return {"raw_bctc_present": present, "raw_bctc_populated": populated,
            "raw_financials_ready": populated >= 3}


def _ocr_financials_status(ticker: str) -> dict[str, Any]:
    p = OFFICIAL_DIR / f"{ticker}_pdf_llm_result.json"
    if not p.is_file():
        return {"ocr_pdf_present": False, "ocr_facts_written": 0, "ocr_financials_ready": False}
    try:
        d = _read_json(p)
    except Exception:
        return {"ocr_pdf_present": True, "ocr_facts_written": 0, "ocr_financials_ready": False}
    written = int(d.get("total_written") or 0)
    return {"ocr_pdf_present": True, "ocr_facts_written": written,
            "ocr_years": d.get("years"), "ocr_financials_ready": written > 0}


def _agm_status(ticker: str) -> dict[str, Any]:
    p = OFFICIAL_DIR / f"{ticker}_agm_result.json"
    if not p.is_file():
        return {"agm_present": False, "agm_drivers_total": 0, "agm_forward_drivers": 0,
                "agm_has_borrowing": False, "agm_drivers_ready": False}
    try:
        outcome = _read_json(p).get("outcome", {}) or {}
    except Exception:
        return {"agm_present": True, "agm_drivers_total": 0, "agm_forward_drivers": 0,
                "agm_has_borrowing": False, "agm_drivers_ready": False}
    drivers = outcome.get("drivers", {}) or {}
    total = sum(v for v in drivers.values() if isinstance(v, int))
    forward = sum(int(drivers.get(k) or 0) for k in FORWARD_DRIVER_KEYS)
    has_borrowing = int(drivers.get("borrowing_plan") or 0) > 0
    return {
        "agm_present": True,
        "agm_meeting_year": outcome.get("meeting_year"),
        "agm_approved_resolutions": outcome.get("approved_resolutions"),
        "agm_drivers_total": total,
        "agm_forward_drivers": forward,
        "agm_has_borrowing": has_borrowing,
        # usable as internal driver pack: has forward-looking content beyond dividend
        "agm_drivers_ready": forward >= 2,
    }


def _market_status(ticker: str) -> dict[str, Any]:
    quotes = sorted(MARKET_ROOT.glob(f"**/{ticker}_quote_history.json"))
    overview = sorted(MARKET_ROOT.glob(f"**/{ticker}_overview.json"))
    news = sorted(MARKET_ROOT.glob(f"**/{ticker}_news.json"))
    quote_rows = 0
    for q in quotes:
        try:
            payload = _read_json(q)
            recs = payload.get("data") if isinstance(payload, dict) else payload
            quote_rows += len(recs) if isinstance(recs, list) else 0
        except Exception:
            pass
    overview_valid = False
    for o in overview:
        try:
            payload = _read_json(o)
            recs = payload if isinstance(payload, list) else [payload]
            if any(isinstance(r, dict) and (r.get("exchange") or r.get("listing_price")
                                            or r.get("listed_volume")) for r in recs):
                overview_valid = True
        except Exception:
            pass
    return {
        "market_quote_rows": quote_rows,
        "market_overview_valid": overview_valid,
        "market_ready": quote_rows > 0 and overview_valid,
        "news_fs_present": bool(news),
    }


def audit(tickers: list[dict[str, str]]) -> dict[str, Any]:
    records = []
    for row in tickers:
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        raw = _raw_bctc_status(ticker)
        ocr = _ocr_financials_status(ticker)
        agm = _agm_status(ticker)
        mkt = _market_status(ticker)
        # peer comparison is computed live (build_peer_pack_live) from price + facts.
        # FS proxy: ticker has a financial base (raw or ocr) AND a market quote.
        peer_ready = bool((raw["raw_financials_ready"] or ocr["ocr_financials_ready"])
                          and mkt["market_ready"])
        rec = {
            "ticker": ticker,
            "company_name": row.get("company_name", ""),
            "exchange": row.get("exchange", ""),
            "segment": row.get("segment", ""),
            **raw, **ocr, **agm, **mkt,
            "peer_ready": peer_ready,
        }
        # A ticker is report-ready when it has: a financial base, market data,
        # and at least raw financials. AGM + OCR + news enrich but the hard gate
        # for a valuation report is market + financial base.
        rec["report_ready"] = bool(
            (raw["raw_financials_ready"] or ocr["ocr_financials_ready"]) and mkt["market_ready"]
        )
        rec["fully_enriched"] = bool(
            rec["report_ready"] and ocr["ocr_financials_ready"]
            and agm["agm_drivers_ready"] and mkt["news_fs_present"]
        )
        records.append(rec)

    def _count(key: str) -> int:
        return sum(1 for r in records if r.get(key))

    summary = {
        "universe_count": len(records),
        "raw_financials_ready": _count("raw_financials_ready"),
        "ocr_financials_ready": _count("ocr_financials_ready"),
        "agm_drivers_ready": _count("agm_drivers_ready"),
        "agm_has_borrowing": _count("agm_has_borrowing"),
        "market_ready": _count("market_ready"),
        "news_fs_present": _count("news_fs_present"),
        "peer_ready": _count("peer_ready"),
        "report_ready": _count("report_ready"),
        "fully_enriched": _count("fully_enriched"),
        "missing_market": [r["ticker"] for r in records if not r["market_ready"]],
        "missing_raw_financials": [r["ticker"] for r in records if not r["raw_financials_ready"]],
        "missing_ocr_financials": [r["ticker"] for r in records if not r["ocr_financials_ready"]],
        "missing_agm_drivers": [r["ticker"] for r in records if not r["agm_drivers_ready"]],
        "missing_news_fs": [r["ticker"] for r in records if not r["news_fs_present"]],
        "not_report_ready": [r["ticker"] for r in records if not r["report_ready"]],
        "not_fully_enriched": [r["ticker"] for r in records if not r["fully_enriched"]],
    }
    return {"summary": summary, "records": records}


def _print_matrix(result: dict[str, Any]) -> None:
    records = sorted(result["records"], key=lambda r: r["ticker"])
    hdr = f"{'TICK':<6}{'mkt':>5}{'news':>6}{'rawFin':>8}{'ocrFin':>8}{'agmDrv':>8}{'borrow':>8}{'peer':>6}{'RPT':>5}{'FULL':>6}"
    print(hdr)
    print("-" * len(hdr))

    def m(b: bool) -> str:
        return " Y" if b else " ."

    for r in records:
        print(
            f"{r['ticker']:<6}{m(r['market_ready']):>5}{m(r['news_fs_present']):>6}"
            f"{m(r['raw_financials_ready']):>8}{m(r['ocr_financials_ready']):>8}"
            f"{m(r['agm_drivers_ready']):>8}{m(r['agm_has_borrowing']):>8}"
            f"{m(r['peer_ready']):>6}{m(r['report_ready']):>5}{m(r['fully_enriched']):>6}"
        )
    s = result["summary"]
    print("-" * len(hdr))
    print(
        f"[completeness] universe={s['universe_count']} market={s['market_ready']} "
        f"news_fs={s['news_fs_present']} raw_fin={s['raw_financials_ready']} "
        f"ocr_fin={s['ocr_financials_ready']} agm_drv={s['agm_drivers_ready']} "
        f"peer={s['peer_ready']} REPORT_READY={s['report_ready']} FULLY_ENRICHED={s['fully_enriched']}"
    )
    for key in ("not_report_ready", "missing_market", "missing_raw_financials",
                "missing_ocr_financials", "missing_agm_drivers", "missing_news_fs"):
        vals = s[key]
        if vals:
            print(f"[completeness] {key} ({len(vals)}): {','.join(vals)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write-json", default="")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    from backend.dataset.config_io import load_universe_rows
    result = audit(load_universe_rows())
    _print_matrix(result)

    if args.write_json:
        out = Path(args.write_json)
        if not out.is_absolute():
            out = ROOT / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str),
                       encoding="utf-8")
        print(f"[completeness] wrote {out}")

    if args.strict and result["summary"]["not_report_ready"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
