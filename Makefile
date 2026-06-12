# ERR Equity Research System - canonical commands

PYTHON := python
PYTEST := $(PYTHON) -m pytest
TICKER ?= DHG
FROM_YEAR ?= 2021
TO_YEAR ?= 2025
DEV_RUN_ID ?= manual_render
INPUT_MARKDOWN ?=

.PHONY: test audit run-research dev-render clean-dev help

test:
	$(PYTEST) -q tests

audit:
	$(PYTEST) -q tests/unit/test_six_agent_workflow.py \
		tests/unit/test_tool_registry.py \
		tests/unit/test_report_assembler.py \
		tests/unit/test_production_gates.py \
		tests/unit/test_model_adapter_diagnostics.py

run-research:
	$(PYTHON) scripts/run_research.py --ticker $(TICKER) --from-year $(FROM_YEAR) --to-year $(TO_YEAR)

dev-render:
	@if "$(INPUT_MARKDOWN)" == "" (echo INPUT_MARKDOWN is required && exit 2)
	$(PYTHON) scripts/render_report.py --input-markdown $(INPUT_MARKDOWN) --dev-run-id $(DEV_RUN_ID) --pdf

clean-dev:
	$(PYTHON) -c "import shutil, pathlib; p=pathlib.Path('storage/dev_report_runs'); shutil.rmtree(p, ignore_errors=True); print('removed', p)"

help:
	@echo "make test"
	@echo "make audit"
	@echo "make run-research TICKER=DHG FROM_YEAR=2021 TO_YEAR=2025"
	@echo "make dev-render INPUT_MARKDOWN=path/to/report.md DEV_RUN_ID=manual"
	@echo "make clean-dev"
