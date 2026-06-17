"""Verify each universe ticker's real issuer identity against vnstock.

The pharma_vn_universe.csv was hand-curated by guessing ticker symbols from
Vietnamese company names; several symbols collide with unrelated listed issuers
(banks, oil, rubber, construction). Those tickers silently ingest the WRONG
company's financials. This audit resolves the true issuer name per ticker and
flags non-pharma identities. Throttled to respect vnstock's 20 req/min guest cap.

Usage:
    python scripts/audit_universe_identity.py
"""
from __future__ import annotations

import io
import json
import re
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PHARMA = re.compile(
    r"dược|y tế|y dược|bệnh viện|pharma|medi|dược liệu|trang thiết bị y|nhà thuốc|"
    r"vắc|sinh phẩm|hóa.?dược|mekophar|imexpharm|traphaco|domesco|bidiphar",
    re.I,
)
SLEEP_S = 3.4  # ~17 req/min, under the 20/min guest cap


def main() -> int:
    from backend.dataset.config_io import load_universe_rows
    from vnstock import Vnstock

    rows = load_universe_rows()
    out = []
    for r in rows:
        t = str(r.get("ticker") or "").strip().upper()
        if not t:
            continue
        csv_name = r.get("company_name", "")
        real = "?"
        for attempt in range(4):
            try:
                ov = Vnstock().stock(symbol=t, source="VCI").company.overview()
                d = ov.iloc[0].to_dict() if hasattr(ov, "iloc") and len(ov) else {}
                real = d.get("organ_name") or d.get("company_name") or d.get("short_name") or "?"
                break
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if "Rate limit" in msg or "limit" in msg.lower():
                    time.sleep(22)
                    continue
                real = "ERR:%s" % msg[:60]
                break
        is_pharma = bool(PHARMA.search(str(real)))
        rec = {"ticker": t, "csv_name": csv_name, "real_name": real,
               "is_pharma": is_pharma,
               "verdict": "ok" if is_pharma else ("error" if str(real).startswith("ERR") else "WRONG")}
        out.append(rec)
        print("%-5s %-9s %s" % (t, rec["verdict"], real), flush=True)
        time.sleep(SLEEP_S)

    wrong = [o["ticker"] for o in out if o["verdict"] == "WRONG"]
    err = [o["ticker"] for o in out if o["verdict"] == "error"]
    ok = [o["ticker"] for o in out if o["verdict"] == "ok"]
    summary = {"total": len(out), "ok": ok, "wrong": wrong, "error": err}
    dest = ROOT / "output" / "universe_identity_audit.json"
    dest.write_text(json.dumps({"summary": summary, "records": out},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== OK pharma (%d): %s" % (len(ok), ",".join(ok)))
    print("=== WRONG/non-pharma (%d): %s" % (len(wrong), ",".join(wrong)))
    print("=== ERROR/unverified (%d): %s" % (len(err), ",".join(err)))
    print("wrote %s" % dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
