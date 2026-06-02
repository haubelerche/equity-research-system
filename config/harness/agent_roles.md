# Harness Agent Roles

## Context

The project uses agents as bounded reviewers around deterministic tools, not as unrestricted calculators or data providers.

| Agent | Responsibility | Forbidden Responsibility |
|---|---|---|
| SupervisorAgent | Build execution plan, route approvals, and preserve run state. | Override export gates or silently skip failed stages. |
| DataRetrievalAgent | Review source coverage, provenance, and retrieval readiness. | Treat Tier-3-only material facts as verified. |
| FinancialAnalystAgent | Interpret deterministic tables and identify analytical risks. | Compute final ratios or valuation figures in prose. |
| ValuationAgent | Review deterministic FCFF/FCFE/DCF outputs and assumptions. | Patch missing debt, capex, or working-capital forecasts narratively. |
| ReportWriterCriticAgent | Check citation coverage, narrative grounding, and export readiness. | Publish a final report when deterministic gates fail. |

## Handoff Rule

Every session handoff must reference the current `run_id`, latest `manifest_path`, failed gate issue ids, and unresolved entries in `config/harness/known_failures.json`.
