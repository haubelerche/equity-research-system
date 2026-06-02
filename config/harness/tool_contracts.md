# Harness Tool Contracts

## Context

Production research tools must return compact, structured summaries and explicit artifact references. The report writer must consume verified artifacts and evidence packets rather than rediscovering files or inventing material figures.

## Required Contract

| Tool | Required Input | Required Output | Blocking Semantics |
|---|---|---|---|
| `AUTO_INGEST` | ticker, FY range, OCR flag | source acquisition summary, warnings | Non-blocking, but downstream gates must block Tier-3-only material facts. |
| `BUILD_FACTS` | ticker, FY range | snapshot id, fact artifact path, validation gates | Blocking when snapshot, FY scope, source validation, or reconciliation fails. |
| `BUILD_INDEX` | ticker, FY range | index summary artifact and evidence refs | Blocking only if evidence index is required for final citation coverage. |
| `VALUATION_DRAFT` | ticker, FY range | valuation artifact, formula metadata, assumption gate | Blocking when formula traces, assumptions, FCFF/FCFE, debt schedule, or sensitivity outputs are missing. |
| `REPORT_GENERATION` | ticker, snapshot id, FY range, mode | report path, citation map path, claim counts, source-tier gate | Blocking for final export when material claims lack traceable citations. |
| `QUALITY_EVALUATION` | ticker, report path, valuation path | deterministic gate result with issue codes | Blocking on any critical false-pass scenario. |

## Non-Negotiable Constraints

| Constraint | Rationale |
|---|---|
| Artifact discovery must use explicit `ArtifactRef.storage_path`. | Glob-based rediscovery can attach stale outputs to a new run. |
| Gate outputs must include `status`, `severity`, and `issues`. | Boolean pass/fail alone is insufficient for durable handoff and regression tests. |
| Final export must require deterministic evidence before human approval. | Human approval cannot repair missing provenance or formula trace. |
