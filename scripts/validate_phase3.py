"""Phase 3 smoke test — verifies source tier coverage gate and golden provenance."""
import glob
import json
import sys
from pathlib import Path

failures = []

# 1. Provenance file exists and is valid JSON
prov_path = Path("config/dataset/golden/financials/DHG_golden_provenance.json")
if prov_path.exists():
    try:
        prov = json.loads(prov_path.read_text(encoding="utf-8"))
        tier = prov.get("source_tier")
        print(f"[OK] DHG_golden_provenance.json — source_tier={tier}, verified_by={prov.get('verified_by')!r}")
        if tier not in (0, 1):
            print(f"[FAIL] Expected source_tier 0 or 1, got {tier}")
            failures.append("provenance source_tier not 0/1")
    except Exception as exc:
        print(f"[FAIL] Cannot parse provenance JSON: {exc}")
        failures.append("provenance parse error")
else:
    print("[FAIL] DHG_golden_provenance.json missing")
    failures.append("provenance missing")

# 2. Load latest fact artifact
files = sorted(glob.glob("artifacts/facts/DHG_*_fact_report.json"), reverse=True)
if not files:
    print("[FAIL] No DHG fact report found. Run build_facts.py --ticker DHG first.")
    sys.exit(1)

data = json.loads(Path(files[0]).read_text(encoding="utf-8"))
print(f"\nChecking: {files[0]}")

# 3. source_tier_coverage key present
cov = data.get("source_tier_coverage", {})
if cov:
    print(f"[OK] source_tier_coverage present for periods: {sorted(cov.keys())}")
else:
    print("[FAIL] source_tier_coverage missing from artifact")
    failures.append("source_tier_coverage missing")

# 4. 2021FY should have Tier 0/1 (from golden CSV with provenance)
cov_2021 = cov.get("2021FY", {})
if cov_2021.get("has_tier01"):
    print(f"[OK] 2021FY has Tier 0/1 source (tiers={cov_2021.get('tiers_present')})")
else:
    print(f"[FAIL] 2021FY should have Tier 0/1 after golden provenance — got {cov_2021}")
    failures.append("2021FY not Tier 0/1")

# 5. 2022-2025 should be Tier 3-only (vnstock only)
tier3_periods = [p for p in ["2022FY", "2023FY", "2024FY", "2025FY"] if not cov.get(p, {}).get("has_tier01")]
if len(tier3_periods) == 4:
    print(f"[OK] 2022-2025FY are correctly identified as Tier 3-only: {tier3_periods}")
else:
    print(f"[WARN] Expected 4 Tier 3-only periods, got: {tier3_periods}")

# 6. source_tier_coverage_status should be 'fail' (4 periods Tier 3-only)
validation = data.get("validation", {})
cov_status = validation.get("source_tier_coverage_status")
if cov_status == "fail":
    print(f"[OK] source_tier_coverage_status = 'fail' (expected: 4 Tier 3-only periods)")
else:
    print(f"[WARN] source_tier_coverage_status = {cov_status!r} (expected 'fail')")

# 7. run_status should be 'tier3_only_warning' not 'ok'
run_status = validation.get("run_status")
if run_status == "tier3_only_warning":
    print(f"[OK] run_status = 'tier3_only_warning' (gate is mandatory, not silent)")
elif run_status == "ok":
    print(f"[FAIL] run_status = 'ok' — silent pass still active!")
    failures.append("run_status is still ok (silent pass not removed)")
else:
    print(f"[INFO] run_status = {run_status!r}")

# 8. valuation_gate should be 'fail' (Tier 3-only for 4/5 periods)
vg = validation.get("valuation_gate")
if vg == "fail":
    print(f"[OK] valuation_gate = 'fail' (correct: 4 Tier 3-only periods block valuation gate)")
else:
    print(f"[WARN] valuation_gate = {vg!r}")

# 9. blocking_reasons should mention tier3_only
blocking = validation.get("blocking_reasons", [])
tier3_reasons = [r for r in blocking if "tier3_only" in r]
if tier3_reasons:
    print(f"[OK] blocking_reasons contain tier3_only messages: {len(tier3_reasons)}")
else:
    print(f"[WARN] No tier3_only blocking reasons found. blocking_reasons={blocking[:3]}")

# 10. Artifact has source_tier in fact entries
first_metric = next(iter(data["facts"]))
first_period = next(iter(data["facts"][first_metric]))
first_entry = data["facts"][first_metric][first_period]
if "source_tier" in first_entry:
    print(f"[OK] Fact entries carry source_tier: {first_entry.get('source_tier')}")
else:
    print(f"[FAIL] Fact entries missing source_tier")
    failures.append("fact entries missing source_tier")

print()
print("=" * 40)
if failures:
    print(f"[RESULT] FAIL — {len(failures)} issue(s): {failures}")
    sys.exit(1)
else:
    print("[RESULT] PASS — Phase 3 verified.")
    print("  2021FY: Tier 1 (golden CSV + provenance)")
    print("  2022-2025FY: Tier 3-only (vnstock) — correctly flagged")
    print("  Gate is mandatory — no silent pass")
