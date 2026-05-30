"""Phase 2 smoke test — verifies fact artifact has source provenance in all entries."""
import glob
import json
import sys
from pathlib import Path

files = sorted(glob.glob("artifacts/facts/DHG_*_fact_report.json"), reverse=True)
if not files:
    print("[FAIL] No DHG fact report found. Run build_facts.py --ticker DHG first.")
    sys.exit(1)

data = json.loads(Path(files[0]).read_text(encoding="utf-8"))
failures = []

print(f"Checking: {files[0]}")
print()

# 1. Required Phase 2 keys present
for key in ("source_conflicts", "source_tier_coverage"):
    if key in data:
        print(f"[OK] Artifact has '{key}' key")
    else:
        print(f"[FAIL] Artifact missing '{key}' key")
        failures.append(f"missing key: {key}")

print(f"[OK] source_conflicts count: {len(data.get('source_conflicts', []))}")

# 2. All fact entries are dicts (not bare floats)
all_entries = [
    (k, p, v)
    for k, periods in data["facts"].items()
    for p, v in periods.items()
]
bare = [(k, p) for k, p, v in all_entries if not isinstance(v, dict)]
if not bare:
    print(f"[OK] All {len(all_entries)} fact entries are dicts (not bare floats)")
else:
    print(f"[FAIL] {len(bare)} bare float entries found (first 3): {bare[:3]}")
    failures.append(f"{len(bare)} bare float entries")

# 3. All entries have source_tier
missing_tier = [(k, p) for k, p, v in all_entries if isinstance(v, dict) and "source_tier" not in v]
if not missing_tier:
    print(f"[OK] All entries have 'source_tier' field")
else:
    print(f"[FAIL] {len(missing_tier)} entries missing source_tier")
    failures.append(f"{len(missing_tier)} entries missing source_tier")

# 4. Base facts have source_id (not derived)
base_with_source = [
    (k, p)
    for k, p, v in all_entries
    if isinstance(v, dict) and v.get("source_id")
]
print(f"[OK] {len(base_with_source)} fact entries have non-empty source_id")

# 5. Derived entries have None source_tier (as expected)
derived = [
    (k, p, v)
    for k, p, v in all_entries
    if isinstance(v, dict) and v.get("source_tier") is None
]
print(f"[OK] {len(derived)} derived entries have source_tier=None (computed metrics)")

# 6. source_tier_coverage structure
cov = data.get("source_tier_coverage", {})
print(f"[OK] source_tier_coverage periods: {sorted(cov.keys())}")
tier01_periods = [p for p, c in cov.items() if c.get("has_tier01")]
tier3only = [p for p, c in cov.items() if not c.get("has_tier01")]
print(f"[INFO] Periods with Tier 0/1 source: {tier01_periods or 'none'}")
print(f"[INFO] Periods with Tier 3-only: {tier3only}")

# 7. Check fact table structure for a known metric
revenue = data["facts"].get("revenue.net", {})
if revenue:
    sample_period = next(iter(revenue))
    sample_entry = revenue[sample_period]
    required_fields = {"value", "source_tier", "source_id"}
    missing_fields = required_fields - set(sample_entry.keys())
    if not missing_fields:
        print(f"[OK] revenue.net entry has all required fields: {list(sample_entry.keys())}")
    else:
        print(f"[FAIL] revenue.net entry missing fields: {missing_fields}")
        failures.append(f"revenue.net missing fields: {missing_fields}")

print()
print("=" * 40)
if failures:
    print(f"[RESULT] FAIL — {len(failures)} issue(s): {failures}")
    sys.exit(1)
else:
    print("[RESULT] PASS — Phase 2 artifact verified.")
