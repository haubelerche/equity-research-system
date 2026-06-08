# ── ERR Equity Research System — CI Commands ──────────────────────────────────
# Usage:
#   make test                        — full deterministic unit test suite
#   make audit                       — static analysis: imports, schema, gate smoke
#   make generate-fixture-report TICKER=DBD  — end-to-end report from golden CSV
#   make check-gates TICKER=DBD      — run gate chain, print gate status
#   make clean-reports               — remove generated reports and artifacts
#
# All commands are non-interactive and return 0/non-0 for CI.

PYTHON := python
PYTEST := $(PYTHON) -m pytest
ROOT   := .
TICKER ?= DBD

.PHONY: test audit generate-fixture-report check-gates clean-reports help

# ── 1. Full test suite ────────────────────────────────────────────────────────
test:
	$(PYTEST) tests/unit/ -q --tb=short
	@echo "[make test] PASS"

# ── 2. Audit — static checks without running reports ─────────────────────────
audit:
	@echo "[make audit] Running schema and gate smoke checks..."
	$(PYTEST) tests/unit/test_phase7_reporting.py \
	          tests/unit/test_artifact_schema_snapshot.py \
	          tests/unit/test_debt_fcfe_gate.py \
	          tests/unit/test_net_debt_bridge.py \
	          -q --tb=short
	@echo "[make audit] Running import check..."
	$(PYTHON) -c "from backend.analytics.forecasting import run_forecast; \
	              from backend.analytics.fcff import compute_fcff; \
	              from backend.analytics.fcfe import compute_fcfe; \
	              from backend.analytics.blend import blend_dcf; \
	              from backend.analytics.sensitivity import build_fcff_sensitivity_table; \
	              from backend.reporting.export_gate import evaluate_export_gate; \
	              from backend.citations.claim_ledger import ClaimLedger; \
	              print('[make audit] All imports OK')"
	@echo "[make audit] PASS"

# ── 3. Generate fixture report from golden CSV ────────────────────────────────
generate-fixture-report:
	@echo "[make generate-fixture-report] Ticker=$(TICKER)"
	$(PYTHON) scripts/run_valuation.py --ticker $(TICKER) --use-golden-csv
	$(PYTHON) scripts/generate_report.py --ticker $(TICKER) --mode draft
	@echo "[make generate-fixture-report] Done — check reports/ and artifacts/reports/"

# ── 4. Check gate chain for a ticker ─────────────────────────────────────────
check-gates:
	@echo "[make check-gates] Ticker=$(TICKER)"
	$(PYTHON) -c "\
import json, glob, sys; \
files = sorted(glob.glob('artifacts/reports/*$(TICKER)*export_gate.json')); \
if not files: print('No export_gate artifact found for $(TICKER)'); sys.exit(1); \
d = json.loads(open(files[-1]).read()); \
print('render_mode:', d['render_mode']); \
print('is_final_exportable:', d['is_final_exportable']); \
[print(' ', g, '->', v) for g, v in d.get('gate_summary', {}).items()]; \
sys.exit(0 if d['is_final_exportable'] else 2) \
"

# ── 5. Clean generated outputs ─────────────────────────────────────────────
clean-reports:
	@echo "[make clean-reports] Removing generated reports and artifacts..."
	$(PYTHON) -c "\
import shutil, pathlib; \
for d in ['reports', 'artifacts/reports']: \
    p = pathlib.Path(d); \
    [f.unlink() for f in p.glob('*') if f.is_file()] if p.exists() else None; \
print('[make clean-reports] Done') \
"

# ── Help ──────────────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "ERR Equity Research — Available make targets:"
	@echo "  make test                          Full unit test suite (932+ tests)"
	@echo "  make audit                         Schema + gate smoke + import check"
	@echo "  make generate-fixture-report TICKER=DBD  End-to-end report from golden CSV"
	@echo "  make check-gates TICKER=DBD        Print gate status for latest artifact"
	@echo "  make clean-reports                 Remove generated reports/artifacts"
	@echo ""
