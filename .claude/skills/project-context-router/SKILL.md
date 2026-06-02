---
name: project-context-router
description: Use at the start of any task to decide which files to read and in what order. Prevents reading the entire repo, avoids context bloat, and ensures the correct source-of-truth layer is consulted before touching code.
---

# Project Context Router

## When to use

Invoke this skill **before any implementation, debugging, or planning task** when you need to decide which files are relevant. Skip it only if the task is a single-file edit with an already-known path.

---

## Source Priority Order

Consult sources in this order. Stop as soon as the question is answered.

| Priority | Layer | What it answers |
|---|---|---|
| 1 | `CLAUDE.md` | Project identity, engineering principles, phase constraints |
| 2 | `docs/PRD.md`, `docs/PROBLEM-BRIEF.md` | Product scope, out-of-scope boundaries, success criteria |
| 3 | `docs/AI_PRODUCT_SPEC.md`, `docs/DATA_ARCHITECTURE.md` | Agent roles, data flow, module responsibilities |
| 4 | `.claude/EXECUTION_STATE.md` | Current build level, completed phases, known gaps |
| 5 | `.claude/plan/*.md` | Formula contracts, DB schema decisions, migration handoffs |
| 6 | `specs/` | Data contracts, evaluation rubric, canonical schema |
| 7 | `backend/`, `scripts/` | Actual implementation truth |
| 8 | `tests/` | Confirmed behavior contracts |

---

## Token Budget Strategy

- Read **summaries and headers first** (first 30–60 lines of large files).
- Read **full file only if the first pass identifies it as directly relevant**.
- Do **not** load `FinRobot/` or `vnstock/` unless explicitly investigating connector/library internals.
- Do **not** load all connector files when debugging one connector.
- Do **not** read all `scripts/*.py` when the task concerns only one pipeline stage.
- Prefer `Grep` over `Read` for locating a symbol, function name, or config key.

---

## File Selection Heuristic

| Task type | Minimum read set |
|---|---|
| Ingestion / connector bug | `scripts/connectors/<connector>.py` + `scripts/ingest_ticker.py` + relevant test |
| Canonical facts bug | `backend/facts/normalizer.py` + `scripts/build_facts.py` + `tests/unit/test_normalizer.py` |
| Valuation calculation | `backend/analytics/<module>.py` + `.claude/plan/FORMULA_FINANCE.md` + relevant test |
| Report generation | `scripts/generate_report.py` + `backend/orchestrator.py` + `backend/harness/` + `config/agents/` |
| Evaluation gate | `scripts/evaluate_report.py` + `backend/dataops/quality_report.py` |
| DB / migration change | `backend/database/migrate.py` + `backend/database/migrations/` + `tests/integration/` |
| New feature | Start from `docs/PRD.md` section → `specs/` → `backend/` module plan |
| Ambiguous task | Read `docs/PRD.md` + `docs/PROBLEM-BRIEF.md` before asking user |

---

## Rules

- **Do not modify code before identifying:**
  1. The affected module(s).
  2. Any tests that cover the affected behavior.
  3. Whether the change conflicts with `CLAUDE.md` phase constraints or PRD out-of-scope list.

- **When a task is ambiguous**, infer intent from `docs/PRD.md` and `docs/PROBLEM-BRIEF.md` before asking the user.

- **Never invent architecture**. If a module described in `CLAUDE.md` section 6 does not exist yet as a file, note the gap and implement minimally — do not rename existing modules to match the spec blindly.

- **Pipeline dependency order is non-negotiable:**
  ```
  ingestion → canonical facts → data quality gates → valuation → evidence retrieval → report generation → evaluation → HITL approval → export
  ```
  Do not implement a downstream stage until its upstream dependency exists and produces valid output.

---

## Expected output from this skill

Before proceeding with the task, state:
- Which files you read.
- Which layer answered the question.
- Which files you deliberately skipped and why.
- The affected module(s).
- Whether any relevant tests exist.
