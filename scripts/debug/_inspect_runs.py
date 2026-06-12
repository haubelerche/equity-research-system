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

conn = psycopg2.connect(settings.database_url)
cur = conn.cursor()

cur.execute(
    "SELECT column_name FROM information_schema.columns "
    "WHERE table_schema='research' AND table_name='run_steps' ORDER BY ordinal_position"
)
print("STEP COLS:", [r[0] for r in cur.fetchall()])

run_id = sys.argv[1] if len(sys.argv) > 1 else None
if run_id is None:
    cur.execute("SELECT run_id FROM research.runs ORDER BY created_at DESC LIMIT 1")
    run_id = cur.fetchone()[0]
print("RUN:", run_id)

cur.execute(
    "SELECT step_name, agent_name, status, policy_reason, error_message, metadata_json "
    "FROM research.run_steps WHERE run_id=%s ORDER BY started_at",
    (run_id,),
)
for step, agent, status, policy_reason, err, detail in cur.fetchall():
    print(f"\n=== {step} ({agent}) [{status}] ===")
    if policy_reason:
        print(f"  policy_reason: {policy_reason}")
    if err:
        print(f"  error_message: {str(err)[:1200]}")
    if detail:
        d = detail if isinstance(detail, dict) else json.loads(detail)
        for key in ("blocking_reason", "error", "review_reason", "warnings", "failure_stage", "message"):
            if key in d:
                print(f"  {key}: {str(d[key])[:600]}")

cur.close()
conn.close()
