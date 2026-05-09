This package implements a phased backend skeleton aligned to `specs/BACKEND-PLAN.md` and `specs/SEQUENCE.md` with the agent set:

- `Supervisor`
- `DataAgent`
- `QuantAgent`
- `ResearcherAgent`
- `AuditorAgent`

## Run

```bash
python -m backend.main
```

Server starts on `:8010`.

## Main Endpoints

- `POST /research/start`
- `GET /research/{run_id}/status`
- `GET /research/{run_id}/artifacts`
- `GET /reports/{run_id}`
- `POST /research/{run_id}/approve`
- `POST /research/{run_id}/recompute`
- `POST /research/{run_id}/evaluate`

## Phase Mapping

- Phase 1: contracts + runtime schema + API skeleton
- Phase 2: `DataAgent` ingestion + DQF + `QuantAgent` valuation
- Phase 3: retrieval indexing + grounding evidence refs
- Phase 4: stateful orchestration + HITL approvals
- Phase 5: offline evaluation + budget guardrails + ops playbook
- Phase 6: debate/critique loop + scale hooks

