from __future__ import annotations
import os
import sys
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if s and not s.startswith("#") and "=" in s:
        k, v = s.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from backend.settings import settings  # noqa: E402
import psycopg2  # noqa: E402

run_id = sys.argv[1]
agent = sys.argv[2] if len(sys.argv) > 2 else "financial_analysis"
conn = psycopg2.connect(settings.database_url)
cur = conn.cursor()
cur.execute(
    "SELECT payload_json FROM research.run_audit_events "
    "WHERE run_id=%s AND actor=%s AND action LIKE 'Create%%' ORDER BY id DESC LIMIT 1",
    (run_id, agent),
)
row = cur.fetchone()
if not row:
    cur.execute(
        "SELECT payload_json FROM research.run_audit_events "
        "WHERE run_id=%s AND actor=%s ORDER BY id DESC LIMIT 1",
        (run_id, agent),
    )
    row = cur.fetchone()
p = row[0]
d = p if isinstance(p, dict) else json.loads(p)
print("STATUS:", d.get("status"))
print("WARNINGS:")
for w in d.get("warnings", []):
    print("  -", str(w)[:1500])
payload = d.get("payload", {})
if isinstance(payload, dict) and "raw_response" in payload:
    rr = payload["raw_response"]
    print("\nRAW_RESPONSE len:", len(rr))
    print("RAW_RESPONSE head:\n", rr[:800])
    print("\nRAW_RESPONSE tail:\n", rr[-800:])
else:
    print("\nPAYLOAD keys:", list(payload.keys()) if isinstance(payload, dict) else type(payload))
cur.close()
conn.close()
