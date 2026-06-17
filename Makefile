# ERR Equity Research System - canonical commands

PYTHON := python
PYTEST := $(PYTHON) -m pytest
TICKER ?= DHG
FROM_YEAR ?= 2021
TO_YEAR ?= 2025
REPORT_MODE ?= standard

.PHONY: test audit run-research run-once help

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

run-once:
	$(PYTHON) scripts/ingest_pdf_llm.py --ticker $(TICKER) --from-year $(FROM_YEAR) --to-year $(TO_YEAR)
	$(PYTHON) scripts/ingest_agm.py --ticker $(TICKER)
	$(PYTHON) scripts/run_research.py --ticker $(TICKER) --from-year $(FROM_YEAR) --to-year $(TO_YEAR) --ocr --draft
	$(PYTHON) scripts/generate_fast_report.py --ticker $(TICKER) --mode $(REPORT_MODE)

help:
	@echo "make test"
	@echo "make audit"
	@echo "make run-research TICKER=DHG FROM_YEAR=2021 TO_YEAR=2025"
	@echo "make run-once TICKER=DHG FROM_YEAR=2021 TO_YEAR=2025 REPORT_MODE=standard"
