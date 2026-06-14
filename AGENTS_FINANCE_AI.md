# AGENTS.md for Finance / AI / Multi-Agent Reporting Repositories

## Purpose

Use this file for repositories that generate financial analysis, valuation reports, RAG outputs, multi-agent research workflows, or evidence-grounded documents.

## Highest-priority requirements

1. Numerical correctness.
2. Source traceability.
3. Reproducibility.
4. Clear separation between data acquisition, computation, and narrative generation.
5. No unsupported financial claims.
6. No hidden changes to valuation assumptions.
7. No internal debug/policy text in user-facing reports.

## Architecture expectations

Preserve separation among these layers:

- Data ingestion and normalization.
- Evidence/source metadata.
- Financial computation and modeling.
- Agent orchestration.
- Audit/validation gates.
- Report rendering/export.

Do not mix narrative generation with canonical financial calculations.
Do not hard-code ticker-specific logic unless the task explicitly asks for a fixture or one-off diagnostic.

## Financial data rules

When touching financial data logic:

- Preserve fiscal period semantics: FY, quarter, TTM, forecast, actual.
- Do not mix quarterly and annual values silently.
- Preserve units: VND, thousand VND, million VND, billion VND, shares, percentages.
- Make unit conversion explicit and testable.
- Avoid implicit sign flips for debt, cash, tax, depreciation, working capital, or capex.
- Distinguish historical actuals from forecasts.
- Distinguish market data, financial statement data, and manually entered assumptions.

## Citation and provenance rules

Every quantitative claim in a final report must be traceable to a source or computed from traceable inputs.
Do not cite only an internal database if the system has access to source metadata.
Do not present API data as official filing data unless verified.
Do not invent source titles, dates, URLs, document names, or filing periods.

## Valuation and model rules

When changing valuation code, validate:

- Revenue growth drivers.
- Gross margin, EBIT margin, tax rate, reinvestment, capex, depreciation, working capital.
- WACC, cost of equity, cost of debt, beta, risk-free rate, ERP, terminal growth.
- FCFF/FCFE definitions.
- Terminal value weight.
- Net debt treatment.
- Share count consistency.
- Sensitivity table formulas.

Do not change model assumptions without surfacing the change in tests, docs, or final summary.

## Multi-agent workflow rules

For agentic pipelines:

- Supervisor should coordinate and enforce policy gates.
- Data agent should acquire, normalize, and validate input data.
- Quant agent should perform deterministic calculations.
- Research agent should generate evidence-grounded interpretation.
- Auditor agent should verify citations, numerical consistency, and report-readiness.

Do not allow narrative agents to overwrite validated numerical outputs.
Do not allow final export if data-quality or citation gates fail, unless the task explicitly asks for an internal draft.

## Report generation rules

User-facing reports must not contain:

- Internal debug warnings.
- Policy-tier labels.
- Raw exception traces.
- Prompt text.
- Agent names unless intentionally part of the report methodology.
- Unsupported caveats that are not actionable.

Report tables must preserve units, labels, periods, and rounding rules.
Markdown/PDF parity is required when both outputs are generated.

## Tests required for finance changes

For computation changes, add or update tests for:

- Unit conversion.
- Period selection.
- Missing data behavior.
- Forecast formulas.
- Sensitivity matrix formulas.
- Net debt/share count treatment.
- Citation availability for numerical claims.

For document extraction changes, add or update tests for:

- Vietnamese label matching.
- OCR/text-based PDF differences.
- Duplicate row handling.
- False positives and false negatives.
- Source metadata propagation.

## Final response format

End every implementation task with:

```text
Changed files:
- <file>: <change>

Financial/numerical impact:
- <changed formula/data path/none>

Validation:
- <command>: <pass/fail/not run>

Evidence/provenance impact:
- <citation/source behavior change/none>

Residual risks:
- <specific risk or none identified>
```
