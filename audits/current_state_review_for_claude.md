# Current State Review — Client Demo Equity Research Reports vs FPTS Target Report

## 1. Executive Summary

The current client demo outputs for **DBD** and **DHG** are not yet at the quality level expected from a professional sell-side equity research update such as the FPTS DBD valuation report.

The reports currently look like a **financial report generator with tables and lightly templated commentary**, rather than a true equity research product. The main issue is not only missing data. The deeper problem is that the reports do not yet perform real investment analysis: they list financial numbers, repeat broad statements, and provide generic risk commentary, but they do not build a clear investment thesis from business drivers, operating evidence, forecast assumptions, valuation bridge, and recommendation logic.

The current output gives the appearance of structure, but the underlying research logic is still weak. It does not yet connect:

```text
Company-specific business drivers
→ Segment and channel evidence
→ Forecast assumptions
→ FCFF / FCFE valuation bridge
→ Sensitivity analysis
→ Investment recommendation
```

The report format is also still fragmented. Several pages contain too much white space, only one table or chart, or charts that are not integrated into the narrative. Some tables have visible rendering errors. The final result does not yet feel like a polished professional equity report.

---

## 2. Benchmark: What the FPTS Target Report Does Well

The FPTS DBD update report is not simply a collection of financial tables. It is built around a clear thesis:

> DBD can sustain growth and improve long-term prospects through key ETC drug lines and EU-GMP production upgrades.

FPTS supports that thesis through detailed analysis of:

- ETC and OTC channel performance.
- Oncology drugs, antibiotics, and dialysis solution as separate product drivers.
- Tender value and tender market share.
- The limitation of DBD's current WHO-GMP status.
- The future upside from EU-GMP qualification and access to higher-value tender groups.
- The specific timeline of each production line upgrade.
- API cost pressure and its direct effect on gross margin.
- Forecasts by business driver rather than only by top-line CAGR.
- FCFF and FCFE valuation with explicit weights and assumptions.

This is the standard the current system should target. The report should not only show numbers. It must explain **why the numbers matter**, **what changed**, **what drives the forecast**, and **why the valuation conclusion is justified**.

---

## 3. Biggest Gap: The Current Output Is Not Thesis-Driven

The most important weakness is that the current reports do not yet have a strong company-specific investment thesis.

The DBD and DHG demo reports use nearly the same structure and reasoning pattern:

- Revenue growth.
- Gross margin.
- API cost pressure.
- ETC/OTC channel comments.
- SG&A control.
- WACC and terminal growth.
- Generic risks around tender pricing, API cost, FX, and generic competition.

This makes the reports look templated. Only the numbers and ticker names change.

For DBD, the report should be built around the specific DBD story:

- Oncology drugs as a core driver.
- Antibiotics and dialysis solution as supporting segments.
- ETC channel dominance.
- Tender group limitations under WHO-GMP.
- EU-GMP upgrades as a step-change catalyst.
- Tender group 1–2 access as a possible pricing and market-share driver.
- Delayed but important production-line approval timeline.
- API oncology cost pressure in 3Q2025.

For DHG, the report should not reuse the same DBD-style logic. DHG needs its own story around:

- Leading domestic pharma position.
- Product portfolio strength.
- OTC and distribution network quality.
- Margin resilience.
- Dividend profile.
- Valuation premium or discount versus peers.
- Why the recommendation is HOLD rather than BUY.

At the moment, the system is generating **generic pharma-sector commentary**, not company-specific equity research.

---

## 4. Format and Layout Problems

### 4.1 Too Much Empty Space

Several pages are poorly utilized. Some pages contain only one table or a small number of charts, leaving large blank areas. This makes the report look unfinished.

Observed examples:

- DBD page 2 contains a financial summary table near the top with most of the page left blank.
- DHG page 2 has a similar problem, with the financial summary table pushed into a narrow area and a large unused section below.
- Pages with charts often do not use the remaining space to provide chart interpretation or additional analysis.

A professional sell-side layout should make each page useful. Each page should generally include:

```text
Section title
→ Key message
→ Supporting table/chart
→ Interpretation of the table/chart
→ Source note
```

The current report often shows the table or chart without enough surrounding analytical explanation.

### 4.2 Table Header Rendering Errors

There are serious table rendering issues, especially in the DHG report.

Examples:

- Year headers appear merged or corrupted, such as `2021F2Y022F2Y023F...`.
- Some growth values appear stuck together, such as `-26.1%9.8%` or `-25.9%9.5%`.
- Dense tables are squeezed horizontally and become hard to read.

These are not cosmetic issues. In an equity research report, table readability is directly linked to credibility. If the financial tables look broken, readers will not trust the analysis.

### 4.3 Stock Performance Section Is Empty

The first page includes a stock price performance block, but key fields such as YTD, 1M, 3M, and 12M performance are empty or shown as dashes.

This is a problem because the front page of an equity research report must quickly communicate:

- Recent price performance.
- Relative performance versus the market or sector.
- Current price context.
- Trading liquidity and valuation snapshot.

If the system does not have reliable data for this section, it should either:

1. Hide the section, or
2. Replace it with a clearly defined fallback, or
3. Block final export until required market data is available.

Rendering empty professional sections makes the report feel incomplete.

### 4.4 Charts Are Not Integrated Into the Story

Some charts are displayed, but they are not used as part of the reasoning flow. A chart should not be inserted merely to fill space. It should answer a specific analytical question.

For example:

- What trend does the chart prove?
- What changed versus last year?
- Which driver explains the change?
- Does the chart support or weaken the investment thesis?

The current charts often lack this role. Some charts also contain weak or missing data. The DCF value bridge chart is especially problematic because it displays no useful DCF bridge data.

---

## 5. Analytical Quality Problems

### 5.1 The Report Mostly Describes Numbers Instead of Explaining Them

The current narrative often follows this pattern:

```text
Revenue was X.
Gross margin was Y.
Cash conversion was Z.
API and ETC are important.
Investors should monitor tender results and API prices.
```

This is not enough for equity research.

A proper research note should explain:

- Why revenue grew or declined.
- Which channel or product group drove the change.
- Whether the growth is sustainable.
- Whether margin movement is structural or temporary.
- Which driver matters most for valuation.
- What evidence supports the forecast.
- What could make the thesis wrong.

Currently, the reports are closer to a **financial summary** than an **investment thesis**.

### 5.2 Missing Segment and Product-Level Analysis

The FPTS DBD report analyzes DBD by business channels and product lines:

- ETC channel.
- OTC channel.
- Oncology drugs.
- Antibiotics.
- Dialysis solution.
- Tender value.
- Tender market share.
- EU-GMP production line timeline.

The current demo does not adequately break down revenue and growth by these drivers. It mostly discusses revenue at the total-company level.

This is a major weakness because pharma equity research depends heavily on product mix, channel mix, tender status, production standards, and regulatory milestones.

The report needs to move from:

```text
Revenue grew by X%.
```

To:

```text
Revenue grew by X% because ETC demand increased, oncology drugs gained tender share, antibiotics were stable/weak due to price competition, and OTC remained pressured by modern pharmacy chain expansion.
```

### 5.3 Weak Industry and Competitive Positioning

The section titled “Sensitivity and peer comparison” does not actually contain meaningful peer comparison.

Missing items include:

- Peer valuation table.
- P/E comparison.
- EV/EBITDA comparison.
- Gross margin comparison.
- ROE / ROIC comparison.
- Market cap and liquidity comparison.
- Business model comparison among DBD, DHG, IMP, TRA, DMC, etc.
- Explanation of whether the company deserves a premium or discount.

Without peer context, the valuation recommendation is weak. A BUY or HOLD call should not rely only on DCF; it should also be checked against sector multiples and company positioning.

### 5.4 Generic Risk Section

The risk section is too generic and nearly identical across tickers.

The current risks include:

- Tender price pressure.
- API and FX volatility.
- Generic competition.
- Regulatory changes.

These are valid pharma-sector risks, but the report needs company-specific risk transmission.

For DBD, the risk section should explain:

- Which API categories are most exposed.
- Whether oncology API prices are the biggest margin risk.
- How delayed EU-GMP approval affects the forecast.
- How ETC tender group limitations cap pricing power.
- How OTC weakness affects diversification.

For DHG, the risks should be different and tied to DHG's own business model.

---

## 6. Forecasting Problems

### 6.1 Driver-Based Forecasting Is Not Real Yet

The report includes a table called “Key Forecast Drivers,” but it is mostly a list of high-level assumptions:

- Revenue growth.
- Gross margin.
- SG&A / revenue.
- Depreciation / revenue.
- Capex / revenue.
- Tax rate.
- Cash conversion.
- WACC.
- Terminal growth.

This is not enough to qualify as true driver-based modeling.

True driver-based modeling should start from operational drivers such as:

- ETC revenue by product group.
- OTC revenue by product group.
- Oncology tender volume and price.
- Antibiotic tender volume and price.
- Dialysis solution demand.
- EU-GMP approval year.
- Tender group migration from group 3–5 to group 1–2.
- Production capacity utilization.
- API cost inflation by category.
- Pharmacy chain penetration.
- Insurance coverage or BHYT-related demand effects.

The current model appears to extrapolate from historical CAGR and margin averages. It does not yet model the business mechanics that actually drive pharma revenue and margin.

### 6.2 DBD Forecast Conflicts With Its Own Thesis

The DBD demo says EU-GMP upgrades and ETC expansion are important. However, the forecast uses a flat 6.3% revenue growth assumption from 2026F to 2030F.

This is inconsistent.

If EU-GMP approval is a major catalyst, then the forecast should show a step-change or at least a clear acceleration around the expected approval and ramp-up period. The FPTS report forecasts a much stronger 2026–2030 growth phase driven by EU-GMP-related opportunities.

The current DBD model behaves like a stable mature company forecast, while the narrative claims a catalyst-driven growth story. This mismatch must be fixed.

### 6.3 Forecast Explanations Are Too Thin

The report should explain why each major forecast assumption is reasonable.

For example:

- Why is revenue growth 6.3% for DBD?
- Why is gross margin assumed at 48.3%?
- Why is SG&A / revenue 22.9%?
- Why is capex / revenue 8.3%?
- Why is terminal growth 3.0%?
- What would trigger an assumption revision?

Currently, the report gives the assumption but not enough evidence or reasoning behind it.

---

## 7. Valuation Problems

### 7.1 DBD Target Price Conflicts With Sensitivity Table

This is the most serious valuation issue found in the DBD report.

The DBD report states:

- Target price: 63,560 VND/share.
- Current price: 50,200 VND/share.
- Upside: +26.6%.
- Recommendation: BUY.

However, the sensitivity table shows a fair value range of only approximately:

```text
31,294 VND/share to 49,528 VND/share
```

This means the sensitivity table is entirely below the stated target price and mostly below the current price.

This creates a major logical contradiction:

- If the sensitivity table is the FCFF DCF valuation, the BUY recommendation is not supported.
- If the target price comes from another method, the report does not explain it.
- If the target price is blended from FCFF and FCFE, the report must show the bridge.
- If the sensitivity table is wrong, the valuation artifact must be blocked before export.

This should be treated as a **hard gate failure**.

### 7.2 Missing FCFF / FCFE Valuation Bridge

The FPTS target report clearly shows:

- FCFE value per share.
- FCFF value per share.
- Weighting between methods.
- Rounded target price.
- WACC.
- Cost of debt.
- Cost of equity.
- Risk-free rate.
- Risk premium.
- Levered beta.
- Terminal growth.
- Forecast period.
- Enterprise value to equity value bridge.

The current demo does not provide this level of transparency.

The current report is missing:

- FCFF present value breakdown.
- Terminal value breakdown.
- Net debt adjustment.
- Cash and short-term investment adjustment.
- Shares outstanding reconciliation.
- FCFE present value calculation.
- Weighting between FCFF and FCFE.
- Final target price bridge.

A professional report must show how the target price is derived, not only state the final value.

### 7.3 DCF Value Bridge Chart Is Empty

The DCF bridge chart currently displays a message similar to “No DCF bridge data available.”

This is not acceptable in a client demo.

The DCF bridge should show at minimum:

```text
PV of explicit FCFF
+ PV of terminal value
+ Cash and short-term investments
- Debt
- Minority interest / other adjustments if applicable
= Equity value
÷ Diluted shares outstanding
= Fair value per share
```

If the system cannot produce this bridge, the valuation section should fail the export gate.

### 7.4 Recommendation Logic Is Not Proven

The recommendation should be derived from:

```text
Target price
+ Dividend yield
= Total expected return
→ Recommendation band
```

The current report sometimes states dividend yield and total return, but the supporting tables do not consistently reconcile with those values.

For example, DBD shows a dividend per share of 2,000 VND but the dividend yield row is rendered as 0 across years. This is an internal consistency error.

---

## 8. Citation and Source Problems

### 8.1 Sources Are Too Generic

The report uses broad source notes such as:

- Company financial statements.
- Bloomberg.
- Internal calculation.
- vnstock VCI.
- DCF internal model.

This is not enough.

A professional evidence-grounded report must let the reviewer trace each important claim back to:

- Specific source document.
- Specific year or quarter.
- Specific table or page if possible.
- Source date.
- Whether the figure is actual, estimated, or forecast.
- Whether the figure came from structured data, company disclosure, market data, or analyst calculation.

### 8.2 Quantitative Claims Need Claim-Level Citations

The project PRD requires 100% citation coverage for quantitative claims in the approved report.

The current output does not meet that standard. It provides section-level or table-level source notes, but not robust claim-level grounding.

Examples of claims that need stronger citation:

- Revenue and net profit values.
- Gross margin and net margin.
- Market cap.
- Shares outstanding.
- Dividend per share.
- WACC.
- Terminal growth.
- API pressure claims.
- ETC / OTC channel claims.
- Tender-related claims.
- EU-GMP timeline claims.

### 8.3 No Clear Distinction Between Actuals, Forecasts, and Analyst Assumptions

The report should clearly separate:

```text
Reported actual data
Analyst forecasts
Model assumptions
Calculated ratios
Narrative interpretation
```

Currently, the report mixes these layers. This is risky because readers cannot easily tell which numbers are sourced facts and which are generated assumptions.

---

## 9. DBD-Specific Issues

The DBD report has several severe issues.

### 9.1 Valuation Contradiction

The stated target price of 63,560 VND/share conflicts with the sensitivity table range of 31,294–49,528 VND/share.

This is a hard valuation consistency failure.

### 9.2 Dividend Yield Inconsistency

The front page states a dividend yield of +4.0%, while the financial summary table shows dividend yield as 0 even though dividend per share is 2,000 VND.

This indicates a calculation or formatting bug.

### 9.3 Missing DBD-Specific Thesis

The DBD report does not properly discuss:

- Oncology drug leadership.
- Tender group 4–5 limitations.
- Opportunity to enter tender groups 1–2.
- EU-GMP production line details.
- Timeline of oncology, sterile injectable antibiotics, and non-betalactam lines.
- Tender value growth.
- 9M2025 performance.
- API oncology cost pressure.
- OTC weakness and traditional pharmacy channel pressure.

These are central to the FPTS DBD report but largely absent from the demo.

### 9.4 Forecast Too Flat for a Catalyst-Based Story

The DBD report assumes steady 6.3% growth across the forecast period. This does not match the report’s own claim that EU-GMP and ETC expansion are major long-term catalysts.

---

## 10. DHG-Specific Issues

The DHG report is also not yet client-ready.

### 10.1 Excessive Template Reuse

The DHG report uses nearly the same analytical framing as DBD:

- ETC/OTC.
- API.
- Tender pressure.
- GMP-EU.
- Generic competition.

This may be partially relevant, but it does not create a DHG-specific investment thesis.

DHG should have its own research logic around:

- Its leading domestic pharma position.
- Product portfolio and brand strength.
- OTC distribution and pharmacy channel exposure.
- Margin resilience.
- Dividend policy.
- Operational efficiency.
- Valuation relative to peers.
- Why upside is limited enough to justify HOLD.

### 10.2 Table Rendering Errors

The DHG financial tables contain serious formatting issues:

- Year headers are merged and unreadable.
- Some percentage values are stuck together.
- Dense financial tables overflow or compress too aggressively.

These issues must be fixed before any client-facing demo.

### 10.3 HOLD Recommendation Is Not Fully Explained

The report states a HOLD recommendation with +8.4% upside, but it does not clearly explain:

- The recommendation threshold.
- Whether dividend yield is included.
- Why valuation upside is limited.
- Whether DHG is trading at a premium or discount to peers.
- What catalyst could change HOLD to BUY.

---

## 11. Current Output vs Expected Professional Report Standard

| Area | Current Demo State | Expected Standard |
|---|---|---|
| Investment thesis | Generic and template-like | Company-specific thesis with clear catalysts |
| Business driver analysis | Mostly top-line revenue and margin | Segment, product, channel, tender, and capacity drivers |
| Forecasting | High-level CAGR and margin assumptions | Operational driver-based model |
| Valuation | Target price stated but weak bridge | Transparent FCFF / FCFE bridge and weighting |
| Sensitivity analysis | Present but sometimes contradictory | Reconciled with target price and base case |
| Peer comparison | Mostly missing | Clear peer valuation and operating comparison |
| Citation | Broad source notes | Claim-level citation and source lineage |
| Layout | Fragmented, many blank areas | Dense but readable professional layout |
| Charts | Often decorative or weak | Charts tied to analytical message |
| Tables | Some rendering bugs | Clean, readable, auditable tables |
| Recommendation | Not fully justified | Linked to total return, valuation, and thesis |

---

## 12. Required Fix Priorities for Claude

### Priority 1 — Fix Hard Valuation Consistency Gates

Claude should implement strict validation before export:

- Target price must reconcile with valuation artifact.
- Sensitivity base case must reconcile with stated target price or clearly explain the difference.
- Dividend yield must reconcile with dividend per share and current price.
- Recommendation must reconcile with target return and recommendation thresholds.
- DCF bridge must not be empty.
- FCFF / FCFE values must be traceable to model outputs.

If any of these fail, the report should be blocked.

### Priority 2 — Build a Real Valuation Bridge Section

The valuation section must include:

- FCFF value per share.
- FCFE value per share.
- Weighting between methods.
- Target price calculation.
- Enterprise value to equity value bridge.
- PV of explicit forecast.
- PV of terminal value.
- Cash and short-term investments.
- Debt adjustment.
- Shares outstanding.
- WACC assumptions.
- Cost of equity assumptions.
- Cost of debt assumptions.
- Terminal growth.
- Sensitivity table.

### Priority 3 — Replace Generic Narrative With Thesis-Driven Templates

The report writer should not simply fill a generic pharma template.

It should create a report-specific thesis using:

```text
Company profile
→ Business model
→ Revenue driver map
→ Margin driver map
→ Key catalyst map
→ Forecast driver table
→ Valuation implications
→ Risks and monitoring indicators
```

For DBD, the thesis must include oncology, antibiotics, dialysis solution, ETC tender groups, and EU-GMP timeline.

For DHG, the thesis must be rebuilt around DHG’s own business model and valuation rationale.

### Priority 4 — Implement Segment-Level Analysis

The system should support sections for:

- Revenue by channel.
- Revenue by product group.
- Margin by product/channel if available.
- Tender value and tender share if available.
- Production capacity and EU-GMP timeline.
- OTC distribution and pharmacy chain exposure.

If data is missing, the report should explicitly state that the segment is unavailable and avoid pretending to analyze it.

### Priority 5 — Improve Layout Engine

The PDF/HTML renderer should enforce layout quality rules:

- No page should contain only one small table unless it is an appendix.
- Avoid large blank spaces in core report sections.
- Use two-column layouts for chart + commentary where appropriate.
- Keep table headers readable.
- Do not allow year headers to merge.
- Split wide tables across pages or use landscape appendix if needed.
- Remove or hide empty sections.
- Do not render charts with missing data.

### Priority 6 — Strengthen Citation and Evidence Lineage

Claude should enforce:

- Every quantitative claim must map to a fact record or source chunk.
- Every forecast assumption must be labeled as an assumption.
- Every sourced figure must include source type, source date, fiscal period, and calculation method.
- Section-level source notes are not enough for final report approval.

### Priority 7 — Add Peer Comparison

The report should include a real peer comparison section:

- Peer companies.
- P/E.
- EV/EBITDA.
- P/B.
- ROE.
- ROIC.
- Gross margin.
- Revenue growth.
- Market cap.
- Explanation of premium or discount.

This section should help justify whether the DCF-implied value is reasonable.

---

## 13. Suggested Report Structure After Fixes

A better full report structure should be:

```text
1. Front Page
   - Recommendation
   - Target price
   - Current price
   - Total return
   - Key market data
   - 3–5 bullet investment thesis
   - Price performance table/chart

2. Investment Thesis
   - What changed
   - Why it matters
   - Key catalysts
   - Key risks

3. Company and Business Model
   - Revenue by channel
   - Revenue by product group
   - Competitive position
   - Market share / tender position

4. Recent Results
   - Latest quarter / 9M / FY update
   - Revenue drivers
   - Margin drivers
   - Cash flow and working capital

5. Forecast Drivers
   - Segment-level forecast
   - Margin assumptions
   - Capex and working capital assumptions
   - Catalyst timeline

6. Valuation
   - FCFF bridge
   - FCFE bridge
   - Blended target price
   - Assumptions table
   - Sensitivity table
   - Peer cross-check

7. Risks and Monitoring Indicators
   - Downside risks
   - Upside catalysts
   - Early indicators to track

8. Financial Summary and Appendix
   - Income statement
   - Balance sheet
   - Cash flow
   - Key ratios
   - Source and citation appendix
```

---

## 14. Final Assessment

The current output is not yet ready as a professional client demo if the target is an FPTS-style valuation update report.

The system has made progress in generating a structured report with financial tables, forecast assumptions, valuation snippets, and risk sections. However, it still fails on the most important dimensions of equity research quality:

- It does not yet produce company-specific investment insight.
- It does not yet perform true driver-based forecasting.
- It does not yet provide a reliable valuation bridge.
- It has serious valuation consistency errors.
- It has weak citation and source lineage.
- It has visible layout and rendering problems.
- It uses too much generic template language.

The immediate engineering focus should not be adding more charts or more sections. The priority should be:

```text
1. Fix valuation consistency and hard export gates.
2. Build transparent FCFF / FCFE valuation bridge.
3. Replace generic narrative with thesis-driven company-specific analysis.
4. Add segment-level driver analysis.
5. Fix layout density and table rendering.
6. Enforce claim-level citation and source lineage.
```

Only after these are fixed should the system be considered close to a credible equity research report generator.
