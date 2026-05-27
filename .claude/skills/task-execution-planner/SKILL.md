---
name: task-execution-planner
description: Use when converting a user request into an implementation plan before writing code. Enforces incremental change, impact analysis, and final report format. Prevents broad rewrites and unscoped changes.
---

# Task Execution Planner

## When to use

Invoke before writing any non-trivial code change (more than a 1-line fix). Not needed for pure documentation edits.

---

## Task Decomposition Template

Fill this in mentally or in a scratchpad before touching files:

```
Task: <one-sentence description>
Trigger: <user request or failing test>
Phase gate: <which CLAUDE.md phase does this belong to?>
Pipeline stage: <ingestion | facts | valuation | retrieval | report | eval | approval>

Files to read first:
  - <file> — <reason>

Files likely to change:
  - <file> — <what changes>

Tests that must not break:
  - <test file or test name>

New tests required:
  - <yes/no — if yes, describe>

Out-of-scope (do NOT touch):
  - <any file outside the blast radius>
```

---

## Pre-Change Checks

Before writing any code:

- [ ] Confirm the task is within current phase scope (`CLAUDE.md` section 20 + `.claude/EXECUTION_STATE.md`).
- [ ] Confirm the change does not violate pipeline dependency order.
- [ ] Confirm no existing behavior is silently removed.
- [ ] Confirm secrets are not hardcoded.
- [ ] If modifying DB schema: confirm a migration file will be created.
- [ ] If modifying a formula: confirm `tests/unit/test_ratios.py` or `test_dcf.py` will be updated.

---

## Implementation Boundaries

| Allowed | Not allowed without explicit request |
|---|---|
| Fix the failing behavior described | Refactor surrounding code |
| Add one new function/class | Rename existing modules |
| Add/update the directly relevant test | Reformat unrelated files |
| Update affected spec section | Rewrite entire pipeline stage |
| Add minimal migration | Delete working migrations |

---

## Post-Change Verification

After implementing:

- [ ] Run the directly relevant smoke command from `CLAUDE.md` section 12.
- [ ] Run directly relevant tests: `pytest tests/unit/test_<module>.py -v`
- [ ] Confirm output artifact is generated if applicable.
- [ ] Confirm no new secrets introduced.
- [ ] Confirm `.claude/EXECUTION_STATE.md` reflects the new state if a phase was completed.

---

## Final Report Format

Always end any completed task with:

```
## Summary
- What was done (1–3 bullets).

## Files Changed
- <path> — <what changed>

## How to Run
- <smoke command>

## Validation
- Tests run: <test file and result>
- Passed: <yes/no>
- Not run: <reason if any>

## Risks / Limitations
- <known gaps, edge cases, or follow-ups>

## Next Step
- <one recommended action>
```
