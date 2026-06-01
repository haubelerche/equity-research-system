---
name: observability-cost-governance
description: Use when working on run tracing, stage logging, cost ledger, token usage tracking, retry logic, latency monitoring, budget policy, or failure diagnostics for any long-running research pipeline run.
---

# Observability and Cost Governance

## When to use

- Modifying `backend/orchestrator.py`, `backend/runtime_store.py`, or `backend/jobs/scheduler.py`.
- Adding or changing logging for pipeline stages.
- Implementing or fixing retry/resume/checkpoint logic.
- Adding cost tracking, token usage, or model usage logging.
- Debugging a run that silently failed or produced no output.
- Implementing budget caps or quota enforcement.

---

## Minimum Context to Read

```
backend/orchestrator.py
backend/runtime_store.py
backend/jobs/scheduler.py
backend/schemas.py          # RunState, CostLedger schema
scripts/run_research.py
.claude/EXECUTION_STATE.md  # current pipeline level
```

---

## Run State Requirements

Every research run must persist the following fields (see `RunState` in `backend/schemas.py`):

```yaml
run_id:
run_type:          # full_report | flash_memo | catalyst_refresh
ticker:
status:            # pending | running | paused | failed | completed
current_stage:     # ingestion | facts | valuation | retrieval | report | eval | approval
checkpoints:       # list of completed stages with timestamps
errors:            # list of {stage, error_type, message, timestamp}
cost_ledger:       # {model, input_tokens, output_tokens, cost_usd, cached_tokens}
trace:             # ordered list of stage events
created_at:
updated_at:
```

A run must be resumable from the last successful checkpoint. Do not restart from scratch if ingestion completed but valuation failed.

---

## Logging Requirements

Each pipeline stage must log at minimum:

| Event | Required fields |
|---|---|
| Stage start | `run_id`, `stage`, `ticker`, `timestamp` |
| Stage complete | `run_id`, `stage`, `ticker`, `duration_ms`, `output_artifact_path` |
| Stage failed | `run_id`, `stage`, `ticker`, `error_type`, `error_message`, `traceback` |
| LLM call | `run_id`, `stage`, `model`, `input_tokens`, `output_tokens`, `cached_tokens`, `cost_usd`, `stop_reason` |
| Retry | `run_id`, `stage`, `attempt_number`, `reason` |

Log enough to diagnose failures in: connector, parser, DB write, retrieval, valuation, synthesis, citation, and export.

**Never log:**
- API keys, DB passwords, tokens, or secrets.
- Raw user-submitted text if it may contain PII.
- Full LLM prompts containing internal system instructions.

---

## Cost Governance Rules

| Rule | Detail |
|---|---|
| Track per run | Cost ledger is per `run_id`, not global. |
| Track per stage | Break down token usage by pipeline stage. |
| Cheaper model for extraction | Use cheaper models for connector parsing, routing, and simple checks. Reserve stronger models for synthesis and critique. |
| Cache reusable intermediates | Valuation artifacts and evidence packs must be reused across re-runs of the same period when safe. |
| Budget cap | Runs should check against a configurable `max_cost_usd` and `max_tokens` before starting an expensive synthesis stage. |
| Alert on abnormal cost | If a single run exceeds 2× the median cost for its run type, log a `HIGH_COST_ALERT` event. |

---

## Freshness and Failure Metrics

Track these to detect degradation:

```
data_freshness_days: age of the most recent canonical fact used
connector_failure_rate: failures / attempts per connector per week
ingestion_p95_latency_ms: 95th percentile ingestion time per ticker
eval_gate_fail_rate: proportion of eval runs with at least one FAIL gate
abnormal_cost_rate: proportion of runs that trigger HIGH_COST_ALERT
```

---

## Retry and Resume Policy

- Transient connector errors (HTTP 429, 503, timeout): retry up to 3× with exponential backoff.
- DB write errors: retry up to 2×; after that, fail the stage and persist error to run state.
- LLM timeout or overload: retry once; if still failing, mark stage `degraded` and continue with cached artifact if available.
- Do not retry indefinitely — set a hard max retry count per stage.
- On resume, skip already-checkpointed stages. Do not re-run completed ingestion or valuation unless explicitly requested with `--force`.

---

## Hard Constraints

- **Do not swallow exceptions silently** — every caught exception must be logged with full traceback.
- **Do not log secrets** — sanitize log payloads before writing.
- **Do not skip cost tracking** to make a run faster — token cost is a first-class engineering constraint.
- **Partial recompute is preferred** over full restart when only downstream stages changed.
- **Stage status must be persisted to DB** — do not rely only on in-memory state for long runs.
