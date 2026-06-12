# Harness Agent Roles

## Context

The production harness uses a fixed six-agent `full_report` workflow. Agents are bounded decision and review components around deterministic tools; they are not unrestricted calculators, data providers, filesystem browsers, or side-effect executors. Runtime permissions are enforced by `backend.harness.tool_registry.ToolRegistry`; prompt instructions are policy documentation, not the primary control surface.

| Agent | Responsibility | Forbidden Responsibility |
|---|---|---|
| ResearchManagerAgent | Validate the objective, determine the run scope, and record the execution plan. | Override deterministic gates or publish a report directly. |
| DataEvidenceAgent | Acquire approved source material, build facts, build the evidence index, and summarize provenance coverage. | Treat Tier-3-only material facts as verified. |
| FinancialAnalysisAgent | Interpret deterministic fact and ratio artifacts, identify analytical risks, and produce grounded financial narrative. | Compute final ratios or valuation figures in prose. |
| ForecastValuationAgent | Execute deterministic forecast and valuation tools, review assumptions, and expose reproducible valuation artifacts. | Patch missing debt, capex, share-count, or working-capital forecasts narratively. |
| ThesisReportAgent | Synthesize the investment thesis and report draft from explicit artifact references. | Invent unsupported claims or bypass source-tier gates. |
| SeniorCriticAgent | Review citation coverage, numeric consistency, valuation reproducibility, narrative grounding, and export readiness. | Approve final publication when deterministic gates fail. |

## Runtime Contract

Each agent receives an `AgentExecutionContext`, not the raw graph state. The context must include only the current `run_id`, ticker, stage, task, allowed tools, input artifact references, relevant gate results, known limitations, and evidence packet path.

Each stage must append a structured trace entry and publish explicit output artifact references into the run state or run manifest. The trace entry must include input refs, output refs, review status, blocking issue ids, unresolved questions, next-stage recommendation, and a deterministic hash of the stage payload.

Tool execution is deterministic and stage-dispatched. An agent may only be associated with tools listed in `config/agents/agents.yml` and implemented in `ToolRegistry`. LLM agents do not receive arbitrary function-calling access in the production harness.

## Session Continuity Rule

Every session continuity note must reference the current `run_id`, latest `manifest_path`, failed gate issue ids, and unresolved entries in `config/harness/known_failures.json`.
