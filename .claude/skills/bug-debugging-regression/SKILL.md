---
name: bug-debugging-regression
description: Use when a test fails, a pipeline script errors, or a runtime failure occurs. Forces reproduce-first root-cause analysis before patching. Prevents trial-and-error guessing and ensures a regression test is added for every fix.
---

# Bug Debugging and Regression

## When to use

- Any failing `pytest` test.
- Any `scripts/*.py` that errors mid-run.
- Any connector, parser, DB, or retrieval failure.
- Any silent wrong output (wrong value, missing artifact, stale data promoted as fresh).

---

## Debugging Procedure

### Step 1 — Reproduce

Run the failing command exactly. Do not modify code first.

```bash
# For a script failure:
python scripts/<failing_script>.py --ticker DHG

# For a test failure:
pytest tests/unit/test_<module>.py::test_<name> -v --tb=short

# For integration failure:
pytest tests/integration/ -v --tb=long
```

Capture the full traceback. Do not skip stack frames.

### Step 2 — State expected vs actual

Write explicitly:
```
Expected: <what should have happened>
Actual: <what actually happened>
Error: <exact exception class and message>
```

### Step 3 — Inspect logs and traceback

- Identify the **exact line** that raises the error.
- Identify the **calling chain** up to the entry point.
- Read only the files in the traceback — do not load unrelated modules.

### Step 4 — Isolate the smallest failing unit

- Can this be reproduced in a single function call with a minimal fixture?
- If the bug is in `backend/analytics/`, try calling the function directly in a Python shell first.
- If the bug is in a connector, check if the raw data fixture is valid before blaming parsing logic.

### Step 5 — Identify root cause

Classify before patching:

| Class | Description |
|---|---|
| `data` | Input data is malformed, missing, or has unexpected unit/period |
| `schema` | DB column missing, type mismatch, migration not applied |
| `logic` | Formula error, wrong condition, off-by-one |
| `contract` | Caller passes wrong type or wrong unit to a function |
| `env` | Missing env var, missing dependency, wrong DB URL |
| `race` | Ordering dependency in pipeline not enforced |

### Step 6 — Apply minimal patch

- Change **only the code responsible for the root cause**.
- Do not refactor surrounding code while fixing a bug.
- Do not rename functions while fixing a bug.
- If the fix requires a schema change, create a migration in `scripts/db/migrations/`.

### Step 7 — Add or update regression test

**Every bug fix must include a test that would have caught it.**

Test location by module:

| Module | Test file |
|---|---|
| `backend/facts/normalizer.py` | `tests/unit/test_normalizer.py` |
| `backend/analytics/ratios.py` | `tests/unit/test_ratios.py` |
| `backend/analytics/dcf.py` | `tests/unit/test_dcf.py` |
| `backend/dataops/quality_report.py` | `tests/unit/test_data_quality.py` |
| `scripts/db/migrate.py` | `tests/unit/test_migrate_runner.py` |
| `scripts/db/` (integration) | `tests/integration/test_db_integrity.py` |
| Any new module | Create `tests/unit/test_<module>.py` |

### Step 8 — Run the full relevant test suite

```bash
pytest tests/unit/ -v --tb=short
```

---

## Hard Constraints

- **Never patch a symptom** while leaving the root cause unfixed.
- **Never suppress an exception** with a bare `except: pass` to make a test pass.
- **Never adjust test assertions** to match wrong behavior — fix the behavior.
- **Never delete a test** because it is inconvenient.
- If a failing test reveals a deeper architectural problem, document it in a new GitHub issue or `.claude/EXECUTION_STATE.md` note and fix incrementally.

---

## Expected output from this skill

```
Root cause: <class — data|schema|logic|contract|env|race>
Explanation: <why it failed>
Fix: <what was changed and where>
Regression test: <test name and file>
Test result: <pass/fail count>
```
