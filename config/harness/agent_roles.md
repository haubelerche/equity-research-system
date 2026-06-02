# Harness Agent Roles

## Context

The project uses agents as bounded decision/review components around deterministic tools, not as unrestricted calculators, data providers, or side-effect executors. Runtime permissions are enforced by `backend.harness.tool_registry.ToolRegistry`; prompt instructions are policy documentation, not the primary control surface.

| Agent | Responsibility | Forbidden Responsibility |
|---|---|---|
| SupervisorAgent | Build execution plan, route approvals, and preserve run state. | Override export gates or silently skip failed stages. |
| DataRetrievalAgent | Review source coverage, provenance, and retrieval readiness. | Treat Tier-3-only material facts as verified. |
| FinancialAnalystAgent | Interpret deterministic tables and identify analytical risks. | Compute final ratios or valuation figures in prose. |
| ValuationAgent | Review deterministic FCFF/FCFE/DCF outputs and assumptions. | Patch missing debt, capex, or working-capital forecasts narratively. |
| ReportWriterCriticAgent | Check citation coverage, narrative grounding, and export readiness. | Publish a final report when deterministic gates fail. |

## Runtime Contract

Each agent receives an `AgentExecutionContext`, not the raw graph state. The context must include only the current `run_id`, ticker, stage, task, allowed tools, input artifact references, relevant gate results, known limitations, and evidence packet path.

Each agent stage must produce an `AgentHandoff` artifact with input refs, output refs, review status, blocking issue ids, unresolved questions, recommended next stage, and a `handoff_hash`. The run manifest must include these handoffs.

Tool execution is deterministic and stage-dispatched. An agent may only be associated with tools listed in `config/agents/agents.yml` and implemented in `ToolRegistry`. LLM agents do not receive arbitrary function-calling access in harness v1.

## Handoff Rule

Every session handoff must reference the current `run_id`, latest `manifest_path`, failed gate issue ids, and unresolved entries in `config/harness/known_failures.json`.
