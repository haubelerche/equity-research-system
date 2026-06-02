--
name: report-generation-rendering
description: Use when working on report generation, Markdown/HTML/PDF rendering, report sections, charts, tables, appendix, or the export pipeline. Enforces artifact-locked content, HITL approval before publish, and citation appendix inclusion.
---

# Report Generation and Rendering

## When to use

- Modifying `scripts/generate_report.py`.
- Modifying `scripts/approve_report.py`.
- Changing report section structure, template, or output format.
- Adding charts, tables, or visual elements to reports.
- Modifying export (Markdown ? HTML or PDF).
- Debugging missing citations, wrong numbers in reports, or formatting failures.

---

## Minimum Context to Read

```
scripts/generate_report.py
scripts/approve_report.py
backend/orchestrator.py
backend/harness/runner.py
backend/reporting/
config/agents/
backend/schemas.py
.claude/plan/PLAN_REPORT_BUILD.md
GOAL_OUTPUT.md
```

---

## Pipeline Dependency Check

Before generating a report for ticker `X`, confirm all upstream artifacts exist:

```
[ ] Canonical facts: coverage_gate=PASS, valuation_gate=PASS
[ ] Valuation artifacts: artifacts/valuation/X_dcf_*.json
[ ] Valuation artifacts: artifacts/valuation/X_ratios_*.json
[ ] Evidence index built (scripts/build_index.py passed for X)
[ ] Retrieval gates 4/4 pass (scripts/test_retrieval.py --ticker X)
```

If any upstream artifact is missing or has a `FAIL` gate, **do not generate the report** � fix upstream first.

---

## Report Section Contract

A full report must contain these sections in order:

```
1. T�m t?t d?u tu (Executive Summary)
2. T?ng quan doanh nghi?p (Company Overview)
3. B?i c?nh ng�nh v� th? tru?ng (Industry and Market Context)
4. Ph�n t�ch t�i ch�nh (Financial Performance) � from canonical facts only
5. �?nh gi� (Valuation) � from valuation artifacts only
6. Lu?n di?m d?u tu (Investment Thesis)
7. R?i ro ch�nh (Key Risks)
8. K?t lu?n (Conclusion)
9. Ph? l?c (Appendix)
   9a. Gi? d?nh (Assumptions)
   9b. B?ng d?nh gi� (Valuation tables)
   9c. B?ng ngu?n tr�ch d?n (Evidence / citation table)
   9d. T�m t?t d�nh gi� ch?t lu?ng (Evaluation summary)
```

---

## Non-Negotiable Rules

| Rule | Detail |
|---|---|
| **Locked artifacts only** | Report reads from valuation artifacts, fact records, and evidence packs � never recomputes or re-fetches live data. |
| **Report writer is read-only** | `generate_report.py` must not write back to the fact store or valuation artifacts. |
| **Citation appendix required** | Every exported report must include section 9c with the evidence/citation table. |
| **Evaluation summary required** | Section 9d must include gate pass/fail results from `evaluate_report.py`. |
| **No HITL bypass** | `approve_report.py` must be called explicitly to mark a report as approved. Automated export without approval record is forbidden. |
| **Language: Vietnamese** | All user-facing report sections are in Vietnamese. Internal artifact files may be English. |
| **Uncertainty must be explicit** | Use `"u?c t�nh"`, `"d? ph�ng"`, `"c� th?"` for forward-looking claims. Never state investment returns as guaranteed. |
| **Disclaimer required** | Every exported report must include the standard disclaimer section before publishing. |

---

## Execution Procedure

```bash
# 1. Generate report
python scripts/generate_report.py --ticker DHG --report-type full_report

# 2. Evaluate before export
python scripts/evaluate_report.py --report reports/DHG_full_report.md

# 3. Approve and export (requires explicit human action)
python scripts/approve_report.py --report-id <REPORT_ID>
```

Output locations:
```
reports/DHG_full_report.md
artifacts/evaluation/<report_id>_eval.json
artifacts/runs/<run_id>_approval.json
```

---

## Chart and Table Selection

Charts must be chosen for **analytical relevance**, not visual decoration.

Required tables for a full report:
- Revenue + gross margin trend (5-year)
- EBIT / net income margin trend (5-year)
- Valuation sensitivity table (WACC � terminal growth)
- Peer comparison table (P/E, EV/EBITDA, ROE)
- Ratio table (PE, PB, BVPS, CCC � per `GOAL_OUTPUT.md`)
- KQKD forecast with all line items
- Balance sheet forecast
- Structured risk table

Do not add charts that have no corresponding data in the locked artifacts.

---

## Hard Constraints

- **Never hardcode financial numbers** in the template � always read from artifact.
- **Never call an LLM to recompute** a valuation figure inside the report writer.
- **Never publish** by writing to output path directly � always go through `approve_report.py`.
- **Never remove the disclaimer section** from any exported report.
- **Never mutate** the valuation artifact or fact store from report generation code.
