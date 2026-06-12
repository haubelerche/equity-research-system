# Harness Tool Contracts

## Context

Production research tools must return compact, structured summaries and explicit artifact references. The report writer must consume verified artifacts and evidence packets rather than rediscovering files or inventing material figures.

## Required Contract

| Tool ID | Required Input | Required Output | Permission | Blocking Semantics |
|---|---|---|---|---|
| `auto_ingest` | ticker, FY range, OCR flag | source acquisition summary, warnings | read-write artifact | Non-blocking, but downstream gates must block Tier-3-only material facts. |
| `build_facts` | ticker, FY range | snapshot id, fact artifact path, validation gates | read-write artifact | Blocking when snapshot, FY scope, source validation, or reconciliation fails. |
| `build_index` | ticker, FY range | index summary artifact and evidence refs | read-write artifact | Blocking only if evidence index is required for final citation coverage. |
| `read_snapshot` | ticker, explicit snapshot id | metric ids, FY periods, source tiers, evidence refs | read-only | Blocks `FINANCIAL_ANALYSIS` when snapshot id or snapshot facts are unavailable. |
| `read_ratio_artifact` | ticker, explicit snapshot id | ratio artifact path, metric ids, FY periods | read-only | Blocks `FINANCIAL_ANALYSIS` when ratio artifact cannot be derived from the snapshot. |
| `run_valuation` | ticker, FY range | valuation artifact, formula traces, assumption gate | read-write artifact | Blocking when formula traces, assumptions, FCFF/FCFE, debt schedule, or sensitivity outputs are missing. |
| `read_valuation_artifact` | explicit valuation artifact path | valuation methods and formula trace summary | read-only | Blocks valuation review when the artifact path is missing or unreadable. |
| `evaluate_report_quality` | ticker, report path, valuation path | deterministic gate result with issue codes | read-only | Blocking on any critical false-pass scenario. |

The executable source of truth is `backend.harness.tool_registry.ToolRegistry`; this document mirrors the registry for design review, but preflight validation must use the registry implementation.

## Non-Negotiable Constraints

| Constraint | Rationale |
|---|---|
| Artifact discovery must use explicit `ArtifactRef.storage_path`. | Glob-based rediscovery can attach stale outputs to a new run. |
| Gate outputs must include `status`, `severity`, and `issues`. | Boolean pass/fail alone is insufficient for durable stage tracing and regression tests. |
| Final export must require deterministic evidence before human approval. | Human approval cannot repair missing provenance or formula trace. |
