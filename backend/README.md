This package implements the v1 fixed `full_report` backend.

## Production Path

The only production workflow is:

```text
FullReportOrchestrator
-> ResearchGraphRunner
-> six specialist agents
-> deterministic tools and gates
-> human approval checkpoints
-> render/publish after approval
```

Supported agents are configured in `config/agents/agents.yml`:

- `research_manager`
- `data_evidence`
- `financial_analysis`
- `forecast_valuation`
- `thesis_report`
- `senior_critic`

The runner uses `backend/harness/graph.py` as a fixed stage list. It does not use a compiled dynamic graph, a Supervisor facade, or partial recompute routes.

## Main Runtime Files

- `backend/orchestrator.py`: lifecycle wrapper for `full_report` only.
- `backend/harness/runner.py`: pause-aware execution, artifact persistence, tool calls, gates, and approvals.
- `backend/harness/contracts.py`: typed agent artifact validation.
- `backend/harness/tool_registry.py`: deterministic tool ownership and permissions.
- `backend/reporting/report_assembler.py`: deterministic final report model assembly from the Thesis & Report Agent artifact.

## API Endpoints

- `POST /research/start`
- `GET /research/{run_id}/status`
- `GET /research/{run_id}/artifacts`
- `GET /reports/{run_id}`
- `POST /research/{run_id}/approve`

## CLI

```bash
python scripts/run_research.py --ticker DHG --from-year 2021 --to-year 2025
python scripts/approve_report.py --run-id <run_id> --stage assumptions --decision approve --reviewer analyst
python scripts/approve_report.py --run-id <run_id> --stage final --decision approve --reviewer analyst
```
