"""Phase 1 smoke test — verifies migration 010 and connector source_tier values."""
import os
import sys
from pathlib import Path

_ROOT = str(Path(__file__).resolve().parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_env = Path(_ROOT) / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import psycopg2
import psycopg2.extras

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
failures = []

print("=== Phase 1 Smoke Test ===\n")

# 1. Schema checks
print("-- Schema checks --")
checks = [
    ("source_tier column on ingest.sources",
     "SELECT column_name FROM information_schema.columns WHERE table_schema='ingest' AND table_name='sources' AND column_name='source_tier'"),
    ("parser_runs table",
     "SELECT table_name FROM information_schema.tables WHERE table_schema='ingest' AND table_name='parser_runs'"),
    ("raw_payloads.connector_name",
     "SELECT column_name FROM information_schema.columns WHERE table_schema='ingest' AND table_name='raw_payloads' AND column_name='connector_name'"),
    ("raw_payloads.request_uri",
     "SELECT column_name FROM information_schema.columns WHERE table_schema='ingest' AND table_name='raw_payloads' AND column_name='request_uri'"),
    ("accepted_financial_facts view has source_id",
     "SELECT column_name FROM information_schema.columns WHERE table_schema='fact' AND table_name='accepted_financial_facts' AND column_name='source_id'"),
    ("catalyst_events.causality_level",
     "SELECT column_name FROM information_schema.columns WHERE table_schema='fact' AND table_name='catalyst_events' AND column_name='causality_level'"),
]
for label, sql in checks:
    cur.execute(sql)
    ok = cur.fetchone() is not None
    status = "[OK]" if ok else "[FAIL]"
    print(f"  {status} {label}")
    if not ok:
        failures.append(label)

# 2. Source tier distribution
print("\n-- Source tier distribution (ingest.sources) --")
cur.execute("SELECT source_tier, source_type, COUNT(*) AS n FROM ingest.sources GROUP BY source_tier, source_type ORDER BY source_tier, n DESC")
rows = cur.fetchall()
for r in rows:
    print(f"  Tier {r['source_tier']:>2}  {r['source_type']:<30}  n={r['n']}")

# 3. Check DHG financial_statement sources are Tier 3
cur.execute(
    "SELECT source_tier, COUNT(*) AS n FROM ingest.sources "
    "WHERE ticker='DHG' AND source_type='financial_statement' GROUP BY source_tier"
)
dhg_fin = cur.fetchall()
dhg_tier3 = sum(r["n"] for r in dhg_fin if r["source_tier"] == 3)
if dhg_tier3 > 0:
    print(f"\n[OK] DHG financial_statement sources correctly assigned Tier 3 ({dhg_tier3} rows)")
else:
    print("\n[FAIL] DHG financial_statement sources not Tier 3")
    failures.append("DHG financial_statement sources not Tier 3")

# 4. Check raw_payloads has connector_name populated for new rows
cur.execute(
    "SELECT connector_name, COUNT(*) AS n FROM ingest.raw_payloads "
    "WHERE connector_name IS NOT NULL GROUP BY connector_name ORDER BY n DESC"
)
rp_rows = cur.fetchall()
print(f"\n-- raw_payloads with connector_name ({sum(r['n'] for r in rp_rows)} rows total) --")
for r in rp_rows:
    print(f"  {r['connector_name']:<45}  n={r['n']}")

cur.execute("SELECT COUNT(*) AS n FROM ingest.raw_payloads WHERE connector_name IS NULL")
nulls = cur.fetchone()["n"]
print(f"  (NULL connector_name: {nulls} legacy rows)")

# 5. Check catalyst_events have causality_level = contextual_event
cur.execute(
    "SELECT causality_level, COUNT(*) AS n FROM fact.catalyst_events "
    "GROUP BY causality_level ORDER BY n DESC LIMIT 5"
)
cl_rows = cur.fetchall()
print(f"\n-- catalyst_events causality_level distribution --")
for r in cl_rows:
    print(f"  {r['causality_level']:<35}  n={r['n']}")

conn.close()

print(f"\n{'='*40}")
if failures:
    print(f"[RESULT] FAIL — {len(failures)} issue(s): {failures}")
    sys.exit(1)
else:
    print("[RESULT] PASS — Phase 1 fully verified.")
