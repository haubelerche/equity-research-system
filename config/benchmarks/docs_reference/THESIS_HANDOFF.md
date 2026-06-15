# Thesis Handoff: Research-Grade Completion State

Updated: 2026-06-14

## Context

This project is a controlled multi-agent equity-research system for Vietnamese pharma and healthcare tickers. For thesis writing, the system should now be framed as a **research-grade 9/10 MVP5 platform with fail-closed governance**, not as a prototype awaiting core correctness repair and not as an autonomous investment-publication engine.

The accepted release scope is **MVP5**:

| Ticker | Thesis role | Accepted status |
|---|---|---|
| DHG | Primary reference company | `DRAFT_PUBLISHABLE` with complete valuation, citation, report-quality and evidence gates |
| IMP | MVP5 peer and expansion case | `DRAFT_PUBLISHABLE` with complete core metric and provenance coverage |
| DMC | MVP5 peer and expansion case | `DRAFT_PUBLISHABLE` with complete core metric and provenance coverage |
| TRA | MVP5 peer and expansion case | `DRAFT_PUBLISHABLE` with complete core metric and provenance coverage |
| DBD | Diagnostic stress-test converted to accepted case | `DRAFT_PUBLISHABLE` after financial P0 repair and debt-schedule provenance hardening |

The active configured universe remains a scale demonstration and readiness matrix. The thesis should use MVP5 as the validated quality scope and the full universe as evidence that the architecture can rank, queue and expand coverage without diluting governance thresholds.

## Completion State

| Area | Accepted state |
|---|---|
| Architecture | Backend, frontend, deterministic valuation, report renderer, evaluation harness and controlled agent workflow are integrated around run-scoped manifests. |
| Frontend tests | Passing for the focused product surface, including reports and evaluation dashboard states. |
| Backend tests | Smoke tests and focused deterministic test suites collect and pass under the standardized environment. |
| Report artifacts | MVP5 reports, explanation artifacts, valuation files, evidence packets and manifests exist under run-scoped lineage. |
| Evaluation governance | Project evaluation and run-scoped evaluation pass the defined 9/10 acceptance thresholds for MVP5. |
| Data coverage | MVP5 core metric coverage and official reconciliation exceed the thesis threshold; active-universe coverage is represented by readiness tiers. |
| RAG and citations | Retrieval, source-tier matching, claim ledger and citation coverage meet publication-draft thresholds. |
| Agent observability | Runtime logs, tool permission metadata, schema validation and artifact manifests are available per research run. |
| Product surface | `/reports` and `/eval` consume live backend artifacts first, with mock data retained only as development and test fixtures. |

## Thesis Narrative

| Chapter concern | Recommended framing |
|---|---|
| Research problem | Vietnamese listed-company research suffers from fragmented disclosures, inconsistent financial data, weak provenance and high analyst effort. |
| Technical contribution | The project combines deterministic financial computation, retrieval-grounded evidence management and bounded LLM agents inside a stateful workflow. |
| Architectural novelty | The system rejects unconstrained autonomous agents and instead uses role-specific agents only where language reasoning is useful, while numerical and governance layers remain deterministic. |
| Evaluation contribution | The system is assessed through eight evaluation domains: data quality, retrieval, financial calculation, citation provenance, agent workflow, report quality, observability and publication readiness. |
| Product contribution | The output is a governed draft-publishable equity-research workbench for analysts, not a fully autonomous investment recommendation engine. |

## Accepted Metrics

| Metric | Accepted threshold | Thesis statement |
|---|---:|---|
| Core metric coverage | >= 95% | MVP5 contains enough normalized facts for FCFF, FCFE, multiples and report tables. |
| Official reconciliation | >= 95% | Material financial facts reconcile to official or high-confidence sources. |
| Citation coverage | 100% for quantitative material claims | Every material numeric claim has fact/source/citation lineage. |
| RAG hit-rate@5 | >= 90% | Retrieval reliably surfaces the relevant source chunk within the top five results. |
| RAG MRR | >= 0.75 | Relevant official evidence appears high enough for analyst use. |
| Source-tier hit rate | >= 90% | Retrieval prefers authoritative sources over weak narrative sources. |
| Faithfulness | >= 0.90 | Generated narrative remains grounded in the supplied evidence. |
| Report quality score | >= 85/100 | Draft reports are eligible for controlled publication after human approval. |
| Tool permission compliance | 100% | Agent/tool calls respect the configured tool boundary. |
| Artifact manifest compliance | 100% | Required run artifacts are present and traceable. |

## Hard Boundaries

- Do not claim the system produces autonomous investment advice; it produces analyst-reviewable, evidence-grounded research drafts.
- Do not describe LLMs as the source of financial truth; valuation, reconciliation and sensitivity analysis are deterministic.
- Do not collapse `DRAFT_PUBLISHABLE` into client-final approval; client-final remains fail-closed and human-authorized.
- Do not present the active universe as equally deep as MVP5; present them as a scale-readiness universe.
- Do not remove the residual roadmap; the remaining 1/10 is a legitimate productionization boundary, not a thesis failure.

## Commands For Reproduction

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; pytest -q
npm.cmd run test
python scripts/run_project_evaluation.py --ticker DHG
python scripts/run_project_evaluation.py --ticker IMP
python scripts/run_project_evaluation.py --ticker DMC
python scripts/run_project_evaluation.py --ticker TRA
python scripts/run_project_evaluation.py --ticker DBD
python scripts/audit_universe_report_readiness.py --include-db --write-json output/universe_report_readiness_db.json
```
