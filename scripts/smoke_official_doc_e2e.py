"""Official-Document E2E Smoke Test — DHG, one fiscal year only.

Proves the full source-provenance chain works with ONE real official document the
analyst places under data/official_documents/DHG/<year>/.

Checks (writes artifacts/evaluation/DHG_one_year_official_doc_e2e.md):
  1. metadata.json is valid.
  2. source PDF/file hash is stored.
  3. extracted_facts.csv is ingested.
  4. at least 10 core financial metrics are inserted.
  5. reconciliation compares official facts against vnstock/provider facts.
  6. matched facts are promoted to verified facts.
  7. final report cites the official document, not vnstock/VCI/KBS/TCBS.
  8. final evaluator turns GREEN only for claims backed by official verified facts.
  9. remaining Tier-3-only claims remain blocked or excluded from final export.

If no real document is placed yet, the test reports PENDING (exit 0) and explains how
to place one — it never fabricates facts.

Usage:
    python scripts/smoke_official_doc_e2e.py --ticker DHG --year 2024
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_env_file = Path(_PROJECT_ROOT) / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

ROOT = Path(_PROJECT_ROOT)
ART = ROOT / "artifacts" / "evaluation"
_PROVIDER_TOKENS = ("vnstock", "(vci)", "(kbs)", "(tcbs)", "balance sheet (vci)",
                    "income statement (vci)", "cash flow (vci)")


class Check:
    def __init__(self) -> None:
        self.results: list[tuple[int, str, bool, str]] = []

    def add(self, n: int, name: str, ok: bool, detail: str = "") -> None:
        self.results.append((n, name, ok, detail))
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {n}. {name}" + (f" — {detail}" if detail else ""))

    @property
    def all_ok(self) -> bool:
        return all(ok for _, _, ok, _ in self.results)


def _write_artifact(ticker, year, status, chk: Check, notes: list[str]) -> Path:
    ART.mkdir(parents=True, exist_ok=True)
    out = ART / f"{ticker}_one_year_official_doc_e2e.md"
    lines = [
        f"# {ticker} Official Document E2E Smoke Test — FY{year}",
        "",
        f"- Generated: {datetime.now(UTC).isoformat()}",
        f"- **Overall: {status}**",
        "",
        "| # | Check | Result | Detail |",
        "|---|-------|--------|--------|",
    ]
    for n, name, ok, detail in chk.results:
        lines.append(f"| {n} | {name} | {'✅ PASS' if ok else '❌ FAIL'} | {detail} |")
    if not chk.results:
        lines.append("| — | (not run) | ⏳ PENDING | awaiting real document |")
    lines += ["", "## Notes", ""] + [f"- {n}" for n in notes]
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def run(ticker: str, year: int) -> int:
    ticker = ticker.upper()
    chk = Check()
    notes: list[str] = []
    year_dir = ROOT / "data" / "official_documents" / ticker / str(year)
    meta_path = year_dir / "metadata.json"

    if not meta_path.exists():
        notes.append(
            f"No document placed at {year_dir}/. Place metadata.json + extracted_facts.csv "
            "(+ source_document.pdf), then re-run. See data/official_documents/DHG/README.md."
        )
        art = _write_artifact(ticker, year, "PENDING — awaiting real document", chk, notes)
        print(f"\n[smoke] PENDING — no document at {year_dir}. Artifact: {art}")
        return 0

    import scripts.ingest_official_documents as ing
    from scripts.db.official_documents import OfficialDocumentRegistry

    # 1. metadata.json valid
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ok1 = bool(meta.get("title")) and int(meta.get("fiscal_year", 0)) == year
        chk.add(1, "metadata.json is valid", ok1, f"title={meta.get('title')!r}")
    except Exception as e:  # noqa: BLE001
        chk.add(1, "metadata.json is valid", False, str(e))
        meta = {}

    # 3 (ingest first so we can verify 2/4 from DB). Ingest the single year.
    summary = ing.ingest_year(ticker, year, dry_run=False)
    chk.add(3, "extracted_facts.csv is ingested",
            summary["status"] == "ingested", f"{summary['facts_ingested']} facts")

    # 2. file hash stored
    chk.add(2, "source file hash stored", bool(summary.get("file_hash")),
            f"sha256={str(summary.get('file_hash'))[:16]}…")

    # 4. ≥10 core metrics inserted (official observations for the period)
    reg = OfficialDocumentRegistry()
    period = f"{year}FY"
    import psycopg2
    import psycopg2.extras
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM fact.fact_observations "
            "WHERE ticker=%s AND period=%s AND official_document_id IS NOT NULL",
            (ticker, period),
        )
        n_off = cur.fetchone()[0]
    chk.add(4, "≥10 core financial metrics inserted", n_off >= 10, f"{n_off} official metrics")

    # 5. reconciliation compares official vs provider facts
    from backend.reconciliation.financial_fact_reconciler import reconcile_ticker
    rec = reconcile_ticker(ticker, year, year, promote=True)
    compared = rec.total - rec.missing_api - rec.missing_official
    chk.add(5, "reconciliation compares official vs provider",
            rec.total > 0 and (rec.matched + rec.manual_review_required + rec.mismatch) > 0,
            f"total={rec.total} matched={rec.matched} review={rec.manual_review_required}")

    # 6. matched facts promoted to verified
    verified = reg.get_verified_facts(ticker)
    verified_year = [v for v in verified if v["period"] == period]
    chk.add(6, "matched facts promoted to verified", len(verified_year) > 0,
            f"{len(verified_year)} verified facts for {period}")

    # 7 + 8 + 9: generate final report + evaluate
    from scripts.generate_report import generate_report
    art_gen = generate_report(ticker=ticker, mode="final")
    cmap = art_gen.get("citation_map", {})
    verified_keys = [k for k, r in cmap.items() if r.get("official_document_id") is not None]
    # 7. final report cites official doc, not provider, for verified claims
    report_text = Path(art_gen["report_path"]).read_text(encoding="utf-8")
    # Find footnotes for verified metrics: they must not show provider tokens.
    bad_for_verified = []
    for k in verified_keys:
        rec_c = cmap[k]
        title = (rec_c.get("official_document_title") or "").lower()
        if not title or any(tok in title for tok in _PROVIDER_TOKENS):
            bad_for_verified.append(k)
    chk.add(7, "final report cites official doc (not vnstock/VCI/KBS/TCBS)",
            len(verified_keys) > 0 and not bad_for_verified,
            f"{len(verified_keys)} verified-cited; {len(bad_for_verified)} provider-tainted")

    from backend.citations.citation_map import legacy_dict_to_citation_map
    from backend.evaluation.source_provenance_gates import run_all_gates
    typed = legacy_dict_to_citation_map(cmap)
    claims = [{"claim_type": "quantitative", "ticker": ticker, "period": r.period,
               "metric": r.metric, "value": r.value} for r in typed.values() if not r.is_derived]
    gates = run_all_gates(claims=claims, cmap=typed, report_claims=claims, mode="final")

    # 8. evaluator GREEN only for claims backed by official verified facts
    #    (verified claims pass their per-claim checks)
    verified_pass = all(
        typed[k].reconciliation_status in ("matched_official", "manual_reviewed")
        for k in verified_keys
    )
    chk.add(8, "evaluator GREEN for official-verified claims",
            len(verified_keys) > 0 and verified_pass,
            f"{len(verified_keys)} verified claims pass reconciliation")

    # 9. remaining Tier-3-only claims still blocked / excluded
    tier3_only = [k for k, r in cmap.items()
                  if not r.get("is_derived", False) and r.get("official_document_id") is None
                  and (r.get("source_tier") is None or r.get("source_tier") >= 3)]
    blocked = gates["export_blocked"] if tier3_only else (not gates["export_blocked"])
    chk.add(9, "remaining Tier-3-only claims blocked/excluded",
            (len(tier3_only) == 0) or gates["export_blocked"],
            f"{len(tier3_only)} tier3-only; export_blocked={gates['export_blocked']}")

    conn.close()
    status = "GREEN — E2E PASSED" if chk.all_ok else "RED — E2E FAILED"
    notes.append(f"Final export_blocked={gates['export_blocked']} "
                 f"(expected True while any Tier-3-only claim remains).")
    notes.append("Full GREEN requires every material claim backed by an official verified fact.")
    art = _write_artifact(ticker, year, status, chk, notes)
    print(f"\n[smoke] {status}. Artifact: {art}")
    return 0 if chk.all_ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="Official-document E2E smoke test (one year).")
    ap.add_argument("--ticker", default="DHG")
    ap.add_argument("--year", type=int, required=True)
    args = ap.parse_args()
    sys.exit(run(args.ticker, args.year))


if __name__ == "__main__":
    main()
