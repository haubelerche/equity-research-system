import os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_env = Path(__file__).resolve().parents[1] / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import psycopg2, psycopg2.extras
conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute(
    "SELECT metric, value, source_tier FROM fact.canonical_facts "
    "WHERE ticker=%s AND period=%s AND canonical_version=%s ORDER BY metric",
    ("DHG", "2021FY", "v_legacy"),
)
rows = cur.fetchall()
print(f"Canonical facts for DHG 2021FY (v_legacy): {len(rows)}")
for r in rows:
    print(f"  {r['metric']}: {r['value']}")

cur.execute(
    "SELECT metric, value FROM fact.fact_observations "
    "WHERE ticker=%s AND period=%s AND official_document_id IS NOT NULL ORDER BY metric",
    ("DHG", "2021FY"),
)
orows = cur.fetchall()
print(f"\nOfficial observations for DHG 2021FY: {len(orows)}")
for r in orows:
    print(f"  {r['metric']}: {r['value']}")

conn.close()
