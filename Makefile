# ERR Equity Research System - canonical commands

PYTHON := python
PYTEST := $(PYTHON) -m pytest
TICKER ?= DHG
FROM_YEAR ?= 2021
TO_YEAR ?= 2025

.PHONY: test audit run-research help

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

help:
	@echo "make test"
	@echo "make audit"
	@echo "make run-research TICKER=DHG FROM_YEAR=2021 TO_YEAR=2025"
