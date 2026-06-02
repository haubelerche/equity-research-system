 GOAL_OUTPUT.md � Chu?n d?u ra b�o c�o d?nh gi� c? phi?u

**Project:** Vietnam Pharma Multi-Agent Equity Research Agent  
**Document type:** Final report output specification + artifact contract + export gates  
**Primary output artifact:** Vietnamese professional equity research report, PDF-ready, t?i da kho?ng 8 trang A4  
**Primary audience:** analyst, reviewer, gi?ng vi�n, nh� d?u tu c� ki?n th?c co b?n  
**Report language:** Ti?ng Vi?t chuy�n nghi?p, trung l?p, c� ngu?n, kh�ng vi?t ki?u qu?ng c�o  
**Reference style:** B�o c�o equity research chuy�n nghi?p nhu m?u LLY, nhung du?c n�ng c?p b?ng citation, lineage, valuation reproducibility v� human review  
**Version:** v2.0  
**Status:** Revised after output-spec audit  

---

## 0. Executive Summary

T�i li?u n�y d?nh nghia chu?n d?u ra cu?i c�ng cho h? th?ng **Vietnam Pharma Multi-Agent Equity Research Agent** khi sinh b�o c�o ph�n t�ch v� d?nh gi� c? phi?u ng�nh du?c/y t? Vi?t Nam.

Chu?n n�y d�ng m?u equity research nhu LLY l�m tham chi?u v? **nh?p d?c, b? c?c, d? c� d?ng v� ki?u tr�nh b�y**, nhung kh�ng copy nguy�n m?u. B�o c�o c?a d? �n ph?i m?nh hon m?u tham chi?u ? c�c di?m sau:

1. M?i s? li?u quan tr?ng ph?i truy v?t du?c v? `canonical_fact`, `computed_metric` ho?c `valuation_result`.
2. M?i claim d?nh lu?ng ph?i c� citation ho?c artifact reference h?p l?.
3. Valuation ph?i ch?y b?ng deterministic Python engine, kh�ng d? LLM t? t�nh to�n trong van b?n.
4. Forecast ph?i d?a tr�n driver r� r�ng: business driver -> financial line item -> assumption -> valuation impact.
5. Report final ch? du?c export khi pass c�c gate b?t bu?c: source, numeric consistency, valuation reproducibility, citation, risk language v� human review.
6. PDF ph?i d? chuy�n nghi?p v? layout, b?ng, bi?u d?, ngu?n, disclaimer v� page budget.

T�i li?u n�y l� **single-file master spec** d? ti?n cho Claude/code agent tri?n khai. Tuy nhi�n, v? m?t ki?n tr�c, n?i dung du?c chia logic th�nh ba l?p:

```text
Layer A � Report Output Spec
  Quy d?nh n?i dung, c?u tr�c, page budget, chart, layout v� van phong c?a b�o c�o PDF/Markdown.

Layer B � Artifact Contracts
  Quy d?nh schema t?i thi?u cho claim_ledger, source_manifest, valuation_result, eval_result v� run_log.

Layer C � Generation Gates
  Quy d?nh c�c di?u ki?n ki?m d?nh tru?c khi report du?c export th�nh final.
```

---

## 1. M?c ti�u c?a t�i li?u

### 1.1. M?c ti�u s?n ph?m

�?u ra cu?i c�ng c?a h? th?ng l� m?t **b�o c�o equity research ti?ng Vi?t** cho c? phi?u ng�nh du?c/y t? Vi?t Nam, c� kh? nang:

- tr�nh b�y thesis d?u tu r� r�ng;
- gi?i th�ch doanh nghi?p ki?m ti?n t? d�u;
- ph�n t�ch xu hu?ng t�i ch�nh l?ch s?;
- d? ph�ng d?a tr�n driver;
- d?nh gi� b?ng FCFF DCF v� ki?m tra ch�o b?ng multiples;
- tr�nh b�y sensitivity, scenario, peer comparison;
- n�u catalyst v� r?i ro g?n v?i financial driver;
- c� citation, audit summary v� disclaimer;
- export du?c th�nh Markdown, HTML v� PDF.

### 1.2. M?c ti�u k? thu?t

B�o c�o kh�ng du?c l� k?t qu? vi?t t? do c?a LLM. B�o c�o ch? du?c sinh t? c�c artifact d� ki?m so�t:

```text
canonical financial facts
computed financial metrics
valuation_result.json
source_manifest.json
claim_ledger.json
evidence packs
approved assumptions
eval_result.json
run_log.json
```

LLM ch? d�ng vai tr�:

1. t?ng h?p v� di?n gi?i c�c artifact d� c�;
2. vi?t narrative theo c?u tr�c d� kh�a;
3. gi?i th�ch logic driver, r?i ro v� valuation b?ng ng�n ng? analyst;
4. kh�ng du?c t? t?o s? li?u ho?c t? s?a k?t qu? valuation.

### 1.3. M?c ti�u tr�nh b�y

B�o c�o final c?n d?t hai y�u c?u d?ng th?i:

| Y�u c?u | � nghia |
|---|---|
| Professional readability | �?c gi?ng m?t equity research report chuy�n nghi?p, kh�ng gi?ng log k? thu?t. |
| Machine-auditable output | M?i s?, claim, chart v� conclusion quan tr?ng c� th? truy v?t v? artifact. |

V� v?y, trong PDF client-facing ch? hi?n th? audit summary g?n. Chi ti?t k? thu?t nhu mismatch list, full claim ledger, full source manifest, trace v� gate failure ph?i n?m trong appendix artifact ho?c JSON, kh�ng l�m r?i th�n b�o c�o.

---

## 2. Ph?m vi d?u ra

### 2.1. In-scope

B�o c�o output chu?n �p d?ng cho:

- c? phi?u du?c/y t? Vi?t Nam tr�n HOSE, HNX, UPCOM;
- full equity research report;
- report b?ng ti?ng Vi?t;
- forecast t?i thi?u 3 nam, khuy?n ngh? 5 nam;
- valuation b?ng FCFF DCF l�m phuong ph�p ch�nh;
- P/E, P/B, EV/EBITDA l�m ki?m tra ch�o n?u d? li?u d?;
- sensitivity v� scenario analysis;
- catalyst/risk d?c th� ng�nh du?c Vi?t Nam;
- citation v� audit trail.

### 2.2. Out-of-scope

Report final kh�ng du?c th? hi?n nhu:

- h? th?ng t? d?ng khuy?n ngh? giao d?ch;
- t�n hi?u mua/b�n ng?n h?n;
- b�o c�o kh�ng ngu?n;
- b�o c�o ch? d?a tr�n d? li?u th? tru?ng t? API m� kh�ng c� ki?m ch?ng;
- b�o c�o d�ng LLM d? t? t�nh financial facts ho?c valuation;
- b�o c�o c� nh�n h�a cho m?t nh� d?u tu c? th?.

---

## 3. Nguy�n t?c b?t bu?c

### 3.1. Facts before narrative

Kh�ng du?c vi?t nh?n d?nh t�i ch�nh tru?c khi c� s? li?u, ngu?n v� ph�p t�nh. M?i s? nhu doanh thu, l?i nhu?n, EPS, WACC, FCFF, target price, upside/downside, market cap, P/E, P/B, ROE, ROA, bi�n l?i nhu?n ph?i truy v?t du?c v? m?t trong c�c artifact sau:

```text
canonical_fact
computed_metric
valuation_result
approved_assumption
```

N?u m?t s? kh�ng truy v?t du?c, s? d� kh�ng du?c xu?t hi?n trong b�o c�o final.

### 3.2. Code-first valuation

LLM kh�ng du?c t? t�nh DCF, FCFF, EPS, CAGR, P/E, P/B, EV/EBITDA, ROE, ROA, WACC ho?c target price b?ng van b?n. LLM ch? du?c di?n gi?i k?t qu? do deterministic Python engine tr? v?.

C�c ph�p t�nh b?t bu?c ph?i do code th?c hi?n:

```text
financial ratio calculation
historical growth calculation
CAGR
working capital metrics
FCFF
DCF discounting
terminal value
equity value
target price
upside/downside
sensitivity matrix
scenario table
weighted valuation summary
```

### 3.3. Citation-first reporting

M?i claim d?nh lu?ng v� m?i claim d?nh t�nh quan tr?ng ph?i c� ngu?n.

| Lo?i claim | V� d? | Citation b?t bu?c |
|---|---|---|
| S? li?u t�i ch�nh | Doanh thu 2024 d?t X t? d?ng | C� |
| D? ph�ng | Doanh thu 2026F tang X% | C�, tr? v? valuation artifact ho?c approved assumption |
| Th�ng tin doanh nghi?p | C�ng ty s? h?u nh� m�y GMP-WHO | C� |
| Catalyst | K?t qu? d?u th?u, BHYT, dang k� thu?c | C� |
| R?i ro | Ph? thu?c s?n ph?m ch�nh, �p l?c gi� th?u | C� |
| Peer comparison | P/E th?p hon trung v? ng�nh | C� |
| Nh?n d?nh chung | �v? th? t?t�, �tang tru?ng ?n d?nh� | C� evidence ho?c vi?t th?n tr?ng |

Kh�ng du?c d�ng citation chung chung ki?u:

```text
Source: database
Source: vnstock
Source: market data
Source: company filings
```

Tr? khi source tag d� c� th? click ho?c truy ngu?c v? `source_manifest.source_id`, `fact_id`, document chunk, URL ho?c file path c? th?.

### 3.4. Driver-based forecast

Forecast kh�ng du?c ch? l� k�o d�i s? qu� kh?. Forecast ph?i th? hi?n logic:

```text
business driver -> affected financial line item -> assumption -> forecast output -> valuation impact
```

V� d?:

```text
�?u th?u thu?c -> doanh thu ETC / gross margin -> gi? d?nh gi� b�n gi?m x bps -> EBIT gi?m -> FCFF gi?m
T?n kho tang -> net working capital -> ?NWC tang -> FCFF gi?m
M? r?ng nh� m�y -> s?n lu?ng / CAPEX / depreciation -> revenue tang nhung FCFF ng?n h?n gi?m
```

### 3.5. Kh�ng dua l?i khuy�n c� nh�n h�a

B�o c�o c� th? c� rating c?p d? b�o c�o nhu `BUY`, `HOLD`, `SELL`, `UNDER REVIEW`, nhung ph?i di?n d?t l� **k?t lu?n d?nh gi� d?a tr�n m� h�nh, d? li?u v� gi? d?nh hi?n t?i**, kh�ng ph?i l?i khuy�n d?u tu c� nh�n h�a.

C�u chu?n b?t bu?c dua v�o disclaimer ho?c ph?n rating note:

```text
Rating trong b�o c�o l� k?t lu?n m� h�nh d?a tr�n d? li?u, gi? d?nh v� m?c sinh l?i k? v?ng t?i th?i di?m l?p b�o c�o; kh�ng ph?i khuy?n ngh? d?u tu c� nh�n h�a.
```

### 3.6. Human approval gate

B�o c�o ch? du?c chuy?n sang `final_exportable` khi pass to�n b? gate:

```text
source_gate = pass
numeric_consistency_gate = pass
valuation_reproducibility_gate = pass
citation_gate = pass
risk_language_gate = pass
human_assumption_approval = pass
human_final_review = pass
```

N?u m?t trong c�c gate fail, h? th?ng ph?i xu?t `NEEDS_REVIEW`, `PENDING_APPROVAL` ho?c `BLOCKED`, kh�ng du?c gi? v? ho�n ch?nh.

---

## 4. File d?u ra b?t bu?c

M?i research run ph?i t?o t?i thi?u c�c file sau:

```text
artifacts/
+-- reports/{run_id}_{ticker}_report.md
+-- reports_html/{run_id}_{ticker}_report.html
+-- reports_pdf/{run_id}_{ticker}_report.pdf
+-- charts/{run_id}_{ticker}_{chart_id}.png
+-- valuation_results/{run_id}_{ticker}_valuation_result.json
+-- claim_ledgers/{run_id}_{ticker}_claim_ledger.json
+-- source_manifests/{run_id}_{ticker}_source_manifest.json
+-- eval_results/{run_id}_{ticker}_eval_result.json
+-- run_logs/{run_id}_{ticker}_run_log.json
```

### 4.1. Report status

M?i report ph?i c� tr?ng th�i r� r�ng:

```yaml
report_status:
  - DRAFT
  - NEEDS_REVIEW
  - PENDING_APPROVAL
  - APPROVED
  - BLOCKED
  - FINAL_EXPORTABLE
```

Kh�ng du?c xu?t PDF final n?u status chua ph?i `FINAL_EXPORTABLE`.

### 4.2. Artifact immutability

C�c artifact d�ng d? sinh final report ph?i du?c version h�a. N?u s? li?u, source, assumption ho?c valuation thay d?i, report ph?i t?o version m?i thay v� ghi d� �m th?m.

```text
same_run_id + changed_artifact_hash = invalid final export
new_artifact_hash -> rerun affected stages -> regenerate report version
```

---

## 5. PDF-ready rendering specification

### 5.1. Page setup

| Thu?c t�nh | Chu?n |
|---|---|
| Kh? gi?y | A4 portrait |
| �? d�i | T?i da kho?ng 8 trang cho full report body |
| Margin | 16-20mm m?i c?nh |
| Header | Ticker, company name, report type, report date |
| Footer | Page number, short source/disclaimer note |
| Ng�n ng? | Ti?ng Vi?t |
| T�ng gi?ng | Chuy�n nghi?p, ph�n t�ch, trung l?p |
| Citation | Source tag ng?n trong th�n b�i; full source trong artifact |
| Disclaimer | B?t bu?c cu?i b�o c�o |
| Executive summary | B?t bu?c trang 1 |
| Valuation assumptions | B?t bu?c ? ph?n d?nh gi� |
| Sensitivity | B?t bu?c n?u c� target price |

### 5.2. Typography

| Element | Recommended size | Rule |
|---|---:|---|
| Report title | 18-22pt | Kh�ng qu� d�i, uu ti�n ticker + company |
| Section heading | 13-15pt | R� c?p b?c, kh�ng d�ng qu� nhi?u c?p |
| Body text | 8.5-10pt | D? d?c tr�n A4 |
| Table text | 7.5-9pt | Kh�ng nh?i qu� nhi?u c?t |
| Chart title | 9-11pt | Ph?i c� k? v� don v? |
| Source caption | 6.5-8pt | B?t bu?c du?i chart/table n?u c� ngu?n |

### 5.3. Layout grid

| Page type | Layout khuy?n ngh? |
|---|---|
| Page 1 | Snapshot layout: rating block + key metrics + thesis + 1 chart |
| Analytical pages | 55/45 ho?c 60/40 text-chart split |
| Valuation page | B?ng l?n full-width + commentary ng?n |
| Sensitivity page | Matrix/table full-width, narrative ng?n |
| Risk page | B?ng catalysts v� risks, �t prose |
| Final page | Key takeaways + client-facing quality summary + key sources + disclaimer |

### 5.4. Chart rendering rules

M?i chart ph?i c�:

```text
title
period
unit
source_caption
actual_or_forecast_marker
```

Kh�ng du?c d�ng chart n?u:

- d? li?u thi?u k?;
- d? li?u nh?m don v?;
- d? li?u chua pass numeric gate;
- chart kh�ng h? tr? decision-making;
- chart ch? du?c th�m d? l�m d?p.

### 5.5. Table rendering rules

| Rule | M� t? |
|---|---|
| Max columns | T?i da 10 c?t trong PDF, tr? sensitivity matrix |
| Unit clarity | Ph?i ghi r� t? VND, %, x, VND/share |
| Forecast marker | Actual d�ng `A`, forecast d�ng `F`, TTM ghi r� `TTM` |
| Negative values | Ph?i hi?n th? nh?t qu�n, kh�ng m?t d?u �m |
| Source | B?ng t�i ch�nh ph?i c� source tag ho?c artifact reference |

---

## 6. Quy t?c n�n n?i dung 8 trang

B�o c�o kh�ng du?c c? dua to�n b? b?ng d? ph�ng chi ti?t v�o th�n PDF. PDF ch? hi?n th? b?ng t�m t?t; chi ti?t n?m trong appendix ho?c JSON artifact.

| N?i dung | C�ch x? l� trong PDF 8 trang |
|---|---|
| B?ng KQKD 10 nam | Ch? hi?n th? 5-7 d�ng ch�nh: doanh thu thu?n, l?i nhu?n g?p, EBIT/EBITDA, LNST, EPS, bi�n g?p, bi�n r�ng |
| B?ng c�n d?i k? to�n | Ch? hi?n th? t�i s?n, n? vay, VCSH, ti?n, h�ng t?n kho, ph?i thu n?u li�n quan thesis |
| B?ng luu chuy?n ti?n t? | Ch? hi?n th? CFO, CAPEX, FCF/FCFF, working capital |
| Ratio table | Ch?n 10-14 ch? s? ch�nh |
| Industry overview | Kh�ng vi?t th�nh section ri�ng trong MVP; l?ng v�o catalyst/risk n?u c� evidence |
| News list | Kh�ng li?t k� qu� nhi?u; ch? ch?n catalyst material |
| Peer comparison | Ch? hi?n th? peer median v� 3-5 peer li�n quan |
| Audit detail | Client-facing summary trong PDF; full detail trong `eval_result.json` |

### 6.1. Page budget b?t bu?c

| Page | N?i dung | Budget |
|---|---|---|
| 1 | Cover + Investment Snapshot | 1 chart ho?c chart mini; thesis 180-220 t? |
| 2 | Company Overview + Business Model | 450-650 t? ho?c 1 b?ng driver |
| 3 | Financial Performance | 1 b?ng summary + t?i da 3 chart |
| 4 | Forecast & Key Assumptions | 1 forecast table + 1 driver table + 1 chart |
| 5 | Valuation | 1 DCF table + 1 valuation summary + 1 assumptions table |
| 6 | Sensitivity, Scenario & Peer Check | 1 sensitivity matrix + 1 scenario table + 1 peer table |
| 7 | Catalysts & Risks | 2 b?ng ch�nh, narrative t?i da 250 t? |
| 8 | Conclusion, Quality Summary, Sources & Disclaimer | G?n, kh�ng bi?n th�nh technical log |

N?u n?i dung vu?t qu� budget, renderer ph?i uu ti�n:

```text
Correctness > Traceability > Valuation Reproducibility > Decision Utility > Visual Design > Completeness of prose
```

---

## 7. C?u tr�c b�o c�o 8 trang

## Page 1 � Cover + Investment Snapshot

### 7.1.1. M?c ti�u

Ngu?i d?c ph?i hi?u ngay:

- m� c? phi?u;
- rating;
- current price;
- target price;
- upside/downside;
- horizon;
- risk level;
- data confidence;
- thesis ch�nh;
- r?i ro ch�nh;
- d? li?u du?c c?p nh?t d?n ng�y n�o.

### 7.1.2. Input b?t bu?c

```text
ticker_metadata
market_data
valuation_result
computed_metrics
claim_ledger
source_manifest
price_history
benchmark_price_history
```

### 7.1.3. B? c?c b?t bu?c

1. Header:
   - `Equity Research Report`
   - Ticker
   - T�n doanh nghi?p
   - S�n giao d?ch
   - Ng�nh: Du?c/Y t?
   - Ng�y l?p b�o c�o
   - Data cutoff
   - K? d? li?u g?n nh?t

2. Rating block:
   - `Rating`: BUY / HOLD / SELL / UNDER REVIEW
   - `Current Price`
   - `Target Price`
   - `Upside/Downside`
   - `Investment Horizon`
   - `Risk Level`
   - `Data Confidence`

3. Key metrics snapshot:
   - Market Cap
   - Net Revenue FY g?n nh?t ho?c TTM
   - Revenue Growth YoY
   - Gross Margin
   - Net Margin
   - ROE
   - ROA
   - EPS
   - P/E
   - P/B
   - EV/EBITDA n?u c�
   - Dividend Yield n?u c�

4. Investment thesis:
   - 5-7 d�ng.
   - 180-220 t?.
   - Ph?i bao g?m: growth driver, profitability outlook, valuation view, key risk.
   - M?i claim ch�nh ph?i map v�o claim ledger.

5. Chart 1:
   - So s�nh di?n bi?n gi� c? phi?u v?i VNINDEX trong 1Y ho?c 3Y.
   - Chu?n h�a base 100 t?i ng�y d?u k?.
   - C� source caption.

### 7.1.4. Template

```markdown
# {TICKER} � {COMPANY_NAME}
## Equity Research Report | Ng�nh Du?c/Y t? Vi?t Nam

| Rating | Current Price | Target Price | Upside/Downside | Horizon | Risk | Data Confidence |
|---|---:|---:|---:|---|---|---|
| {BUY/HOLD/SELL/UNDER_REVIEW} | {current_price} VND | {target_price} VND | {upside_pct}% | 12M | {risk_level} | {data_confidence} |

### Key Metrics Snapshot

| Metric | Value |
|---|---:|
| Market Cap | {market_cap} t? VND |
| Revenue FY{year} | {revenue} t? VND |
| Revenue Growth | {revenue_growth}% |
| Net Profit | {net_profit} t? VND |
| EPS | {eps} VND |
| P/E | {pe}x |
| P/B | {pb}x |
| ROE | {roe}% |

### Investment Thesis

{5-7 d�ng ng?n, c� citation ho?c claim ledger reference.}

![Stock vs VNINDEX](charts/{ticker}_price_vs_vnindex.png)
```

### 7.1.5. Fallback

N?u kh�ng c� price history ho?c VNINDEX benchmark h?p l?:

```text
Kh�ng v? Chart 1.
Thay b?ng note: D? li?u di?n bi?n gi� chua d? di?u ki?n ki?m d?nh d? hi?n th? trong b�o c�o final.
Report status t?i thi?u l� NEEDS_REVIEW n?u current price cung kh�ng d�ng tin c?y.
```

---

## Page 2 � Company Overview + Business Model

### 7.2.1. M?c ti�u

Gi?i th�ch doanh nghi?p ki?m ti?n t? d�u, s?n ph?m ho?c k�nh n�o d�ng g�p ch�nh, v� c�c driver v?n h�nh n�o ?nh hu?ng d?n forecast.

### 7.2.2. N?i dung b?t bu?c

| Block | N?i dung |
|---|---|
| Company profile | T�n d?y d?, nam th�nh l?p, s�n, linh v?c ch�nh |
| Business model | S?n xu?t, ph�n ph?i, ETC/OTC, thi?t b? y t?, b?nh vi?n, d?ch v? y t? t�y doanh nghi?p |
| Product/revenue mix | S?n ph?m/nh�m s?n ph?m ch�nh n?u c� d? li?u |
| Competitive position | GMP, h? th?ng ph�n ph?i, thuong hi?u, danh m?c thu?c, nang l?c d?u th?u n?u c� evidence |
| Growth strategy | M? r?ng nh� m�y, s?n ph?m m?i, k�nh ETC/OTC, M&A, xu?t kh?u |
| Key operating drivers | Gi� b�n, s?n lu?ng, bi�n g?p, d?u th?u, BHYT, t?n kho, working capital |

### 7.2.3. Business driver table b?t bu?c n?u c� d? li?u

```markdown
| Driver | Business Meaning | Financial Line Item | Direction | Evidence |
|---|---|---|---|---|
| K�nh ETC | Doanh thu b?nh vi?n/d?u th?u | Revenue, gross margin | Positive/Negative | SRC-... |
| Gi� th?u thu?c | �p l?c gi� b�n | Revenue, gross margin | Negative | SRC-... |
| Nguy�n li?u nh?p kh?u | Chi ph� d?u v�o | COGS, gross margin | Negative/Neutral | SRC-... |
| T?n kho/ph?i thu | V?n luu d?ng | ?NWC, FCFF | Negative if rising | FACT-... |
```

### 7.2.4. Writing constraints

Kh�ng du?c:

- vi?t l?ch s? doanh nghi?p qu� d�i;
- tuy�n b? �d?n d?u ng�nh� n?u kh�ng c� ngu?n;
- copy nguy�n van b�o c�o thu?ng ni�n;
- dua nh?n d?nh tang tru?ng n?u chua g?n v?i driver v� evidence;
- vi?t generic nhu �c�ng ty c� v? th? t?t� m� kh�ng gi?i th�ch b?ng s? ho?c source.

�? d�i: 450-650 t?.

---

## Page 3 � Financial Performance

### 7.3.1. M?c ti�u

Cho th?y xu hu?ng t�i ch�nh l?ch s?, ch?t lu?ng tang tru?ng, bi�n l?i nhu?n, hi?u qu? s? d?ng v?n v� di?m b?t thu?ng.

### 7.3.2. N?i dung b?t bu?c

1. Revenue & profitability:
   - Doanh thu thu?n 3-5 nam.
   - L?i nhu?n g?p, EBIT/EBITDA, LNST.
   - Bi�n g?p, bi�n EBIT/EBITDA, bi�n r�ng.

2. Growth analysis:
   - CAGR doanh thu.
   - CAGR LNST.
   - Gi?i th�ch c�c nam b?t thu?ng.

3. Operating efficiency:
   - V�ng quay h�ng t?n kho, ph?i thu, ph?i tr? ho?c cash conversion cycle n?u d? li?u d?.
   - Ch? gi?i th�ch n?u c� bi?n d?ng d�ng k?.

4. Abnormal movement analysis:
   - Flag n?u bi?n d?ng YoY vu?t ngu?ng c?u h�nh.
   - M?i flag ph?i c� reason v� source.

### 7.3.3. B?ng financial summary

```markdown
| Ch? ti�u | 2021A | 2022A | 2023A | 2024A | 2025A/TTM |
|---|---:|---:|---:|---:|---:|
| Doanh thu thu?n | | | | | |
| L?i nhu?n g?p | | | | | |
| EBITDA/EBIT | | | | | |
| LNST C� m? | | | | | |
| EPS | | | | | |
| Bi�n g?p | | | | | |
| Bi�n r�ng | | | | | |
| ROE | | | | | |
```

### 7.3.4. Charts b?t bu?c n?u d? li?u d?

| Chart | Lo?i | N?i dung |
|---|---|---|
| C2 | Bar + line | Revenue + EBITDA/EBIT margin |
| C3 | Line/bar | EPS + P/E ho?c LNST + bi�n r�ng |
| C4 | Multi-line | Gross margin, net margin, ROE |

### 7.3.5. Narrative chu?n

Th? t? vi?t b?t bu?c:

```text
1. N�u xu hu?ng ch�nh.
2. N�u driver ho?c nguy�n nh�n c� evidence.
3. Ch? ra di?m b?t thu?ng n?u c�.
4. Gi?i th�ch t�c d?ng t?i forecast ho?c valuation.
```

Kh�ng du?c n�i �t?t/x?u� chung chung. Ph?i n�i bi?n d?ng ?nh hu?ng th? n�o d?n revenue, margin, working capital, WACC, multiple ho?c FCFF.

---

## Page 4 � Forecast & Key Assumptions

### 7.4.1. M?c ti�u

Tr�nh b�y forecast m?t c�ch c� logic, c� driver, c� assumption, c� source v� c� tr?ng th�i approval.

### 7.4.2. Forecast horizon

Khuy?n ngh?:

```text
Base actual year: FY g?n nh?t d� ki?m d?nh ho?c TTM n?u d? tin c?y
Forecast horizon: 2026F-2030F ho?c 5 nam t�nh t? nam base
Minimum horizon: 3 nam
Preferred horizon: 5 nam
```

### 7.4.3. Forecast logic b?t bu?c

Forecast ph?i bao g?m t?i thi?u:

- Revenue growth driver.
- Gross margin assumption.
- SG&A/sales assumption.
- Tax rate.
- Working capital assumption.
- CAPEX/depreciation assumption.
- Terminal growth ho?c exit multiple n?u d�ng.

### 7.4.4. Driver-based planning table

B?ng n�y l� b?t bu?c, v� d�y l� c?u n?i gi?a business analysis v� valuation.

```markdown
| Driver | Linked Line Item | Direction | Base Assumption | Evidence | Valuation Impact | Approval Status |
|---|---|---|---:|---|---|---|
| S?n lu?ng/k�nh ETC | Revenue | Positive | +x% | SRC-... | Tang FCFF | approved/pending_review |
| Gi� th?u thu?c | Gross margin | Negative | -x bps | SRC-... | Gi?m EBIT, gi?m FCFF | approved/pending_review |
| Chi ph� nguy�n li?u | COGS | Negative | +x bps | SRC-... | Gi?m gross margin | approved/pending_review |
| T?n kho/ph?i thu | ?NWC | Negative | +x ng�y | FACT-... | Gi?m FCFF | approved/pending_review |
```

### 7.4.5. Forecast table

```markdown
| Ch? ti�u | 2025A/TTM | 2026F | 2027F | 2028F | 2029F | 2030F |
|---|---:|---:|---:|---:|---:|---:|
| Doanh thu thu?n | | | | | | |
| Tang tru?ng DT | | | | | | |
| L?i nhu?n g?p | | | | | | |
| Bi�n g?p | | | | | | |
| EBIT/EBITDA | | | | | | |
| Bi�n EBIT/EBITDA | | | | | | |
| LNST C� m? | | | | | | |
| EPS | | | | | | |
| FCFF | | | | | | |
```

### 7.4.6. Assumptions table

```markdown
| Assumption | Base Case | Rationale | Source/Artifact | Approval Status |
|---|---:|---|---|---|
| Revenue CAGR 2026F-2030F | {x}% | {rationale} | {source_id/artifact_id} | approved/pending_review |
| Gross margin | {x}% | {rationale} | {source_id/artifact_id} | approved/pending_review |
| SG&A / Revenue | {x}% | {rationale} | {source_id/artifact_id} | approved/pending_review |
| Tax rate | {x}% | {rationale} | {source_id/artifact_id} | approved/pending_review |
| WACC | {x}% | {rationale} | valuation_result | approved/pending_review |
| Terminal growth | {x}% | {rationale} | valuation_result | approved/pending_review |
```

### 7.4.7. Chart b?t bu?c n?u d? li?u d?

| Chart | Lo?i | N?i dung |
|---|---|---|
| C5 | Bar + line | Forecast revenue and profit ho?c revenue and FCFF |

### 7.4.8. Forecast writing rules

Agent ph?i gi?i th�ch �t nh?t 3 driver l?n nh?t l�m thay d?i forecast:

```yaml
driver_name:
affected_line_item:
direction: positive | negative | neutral
magnitude_estimate:
evidence:
assumption_status: approved | pending_review
valuation_impact:
```

Kh�ng du?c vi?t:

```text
Doanh thu du?c d? ph�ng tang ?n d?nh do tri?n v?ng ng�nh t�ch c?c.
```

N?u kh�ng c� driver v� source, ph?i vi?t:

```text
Chua d? b?ng ch?ng d? g�n nguy�n nh�n c? th? cho gi? d?nh tang tru?ng; assumption c?n reviewer ph� duy?t tru?c khi export final.
```

---

## Page 5 � Valuation: FCFF DCF + Relative Multiples

### 7.5.1. M?c ti�u

Ch?t gi� m?c ti�u b?ng m� h�nh d?nh gi� c� th? t�i l?p, minh b?ch assumption v� c� ki?m tra ch�o b?ng multiples.

### 7.5.2. Phuong ph�p b?t bu?c

1. FCFF DCF l� phuong ph�p ch�nh.
2. P/E, P/B, EV/EBITDA l� phuong ph�p ki?m tra ch�o n?u d? li?u d?.
3. EV/Sales ch? d�ng n?u doanh nghi?p d?c th� v� c� gi?i th�ch.
4. Kh�ng d�ng multiples n?u peer kh�ng d? tuong d?ng ho?c d? li?u kh�ng d�ng tin c?y.

### 7.5.3. C�ng th?c chu?n

```text
FCFF = EBIT � (1 - Tax Rate) + Depreciation - CAPEX - ?NWC

EV = S PV(FCFF_t) + PV(Terminal Value)

Equity Value = EV + Cash & Equivalents - Debt - Minority Interest

Target Price = Equity Value / Diluted Shares Outstanding

Upside/Downside = (Target Price / Current Price) - 1
```

C�c c�ng th?c ph?i du?c implement trong Python engine. Markdown report ch? di?n gi?i k?t qu?.

### 7.5.4. B?ng DCF summary

```markdown
| Valuation Item | 2026F | 2027F | 2028F | 2029F | 2030F |
|---|---:|---:|---:|---:|---:|
| EBIT | | | | | |
| Tax Rate | | | | | |
| EBIT(1-T) | | | | | |
| Depreciation | | | | | |
| CAPEX | | | | | |
| ?NWC | | | | | |
| FCFF | | | | | |
| Discount Factor | | | | | |
| PV of FCFF | | | | | |
```

### 7.5.5. Valuation summary table

```markdown
| Method | Implied Equity Value | Implied Price | Weight | Weighted Price | Status |
|---|---:|---:|---:|---:|---|
| DCF - FCFF | | | | | valid/limited |
| P/E | | | | | valid/limited |
| P/B | | | | | valid/limited |
| EV/EBITDA | | | | | valid/limited |
| Final Target Price | | | 100% | | |
```

### 7.5.6. Valuation assumptions table

```markdown
| Parameter | Value | Source/Method |
|---|---:|---|
| Risk-free rate | | valuation_result |
| Beta | | valuation_result/source |
| Equity risk premium | | valuation_result/source |
| Cost of equity | | valuation_result |
| Cost of debt | | valuation_result |
| Tax rate | | valuation_result/computed_metric |
| WACC | | valuation_result |
| Terminal growth | | valuation_result |
| Net debt / cash | | canonical_fact/computed_metric |
| Shares outstanding | | canonical_fact/source |
```

### 7.5.7. DCF value bridge

Khuy?n ngh? c� chart C6 n?u d? li?u d?:

| Chart | Lo?i | N?i dung |
|---|---|---|
| C6 | Waterfall | Enterprise value -> net debt/cash -> equity value -> target price |

### 7.5.8. Narrative chu?n

Th? t? vi?t b?t bu?c:

```text
1. N�u phuong ph�p ch�nh v� l� do ph� h?p.
2. Gi?i th�ch target price d?n t? d�u.
3. So s�nh target price v?i current price.
4. N�u assumption nh?y nh?t.
5. N�u di?u ki?n khi?n rating thay d?i.
```

Kh�ng du?c k?t lu?n ch?c ch?n. Ph?i vi?t theo di?u ki?n assumptions.

V� d? d�ng:

```text
Trong base case d� du?c ph� duy?t, FCFF DCF cho ra gi� tr? h?p l� X VND/cp. K?t qu? n�y nh?y nh?t v?i WACC v� terminal growth; khi WACC tang 100 bps, target price gi?m v? Y VND/cp. Do d�, rating hi?n t?i ph? thu?c d�ng k? v�o kh? nang duy tr� bi�n EBIT v� ki?m so�t v?n luu d?ng.
```

---

## Page 6 � Sensitivity, Scenario & Peer Check

### 7.6.1. M?c ti�u

Cho reviewer th?y m� h�nh c� b?n kh�ng khi gi? d?nh thay d?i.

### 7.6.2. Sensitivity b?t bu?c

Ph?i c� �t nh?t m?t trong hai d?ng:

1. Sensitivity target price theo `WACC` v� `terminal growth`.
2. Sensitivity theo `revenue CAGR` v� `EBIT/EBITDA margin` n?u terminal assumptions kh�ng ph� h?p.

### 7.6.3. Sensitivity matrix

```markdown
| Target Price Sensitivity | WACC -1.0% | WACC -0.5% | Base WACC | WACC +0.5% | WACC +1.0% |
|---|---:|---:|---:|---:|---:|
| g -0.5% | | | | | |
| Base g | | | | | |
| g +0.5% | | | | | |
```

### 7.6.4. Scenario table

```markdown
| Scenario | Revenue CAGR | Margin Assumption | WACC | Target Price | Upside/Downside | Rating Implication |
|---|---:|---:|---:|---:|---:|---|
| Bear | | | | | | |
| Base | | | | | | |
| Bull | | | | | | |
```

### 7.6.5. Peer comparison table

```markdown
| Ticker | Business Type | Market Cap | P/E | P/B | EV/EBITDA | ROE | Net Margin |
|---|---|---:|---:|---:|---:|---:|---:|
| {ticker} | | | | | | | |
| Peer Median | | | | | | | |
```

### 7.6.6. Peer rules

- Peer ph?i thu?c ng�nh du?c/y t? Vi?t Nam ho?c c� l� do tuong d?ng r�.
- N?u kh�ng c� peer d? tuong d?ng, ghi `peer comparison limited` thay v� �p so s�nh.
- Kh�ng d�ng peer global n?u kh�ng di?u ch?nh kh�c bi?t th? tru?ng, quy m� v� m� h�nh kinh doanh.
- Peer comparison kh�ng du?c t? d?ng k�o rating n?u DCF v� data confidence kh�ng d?.

### 7.6.7. Sensitivity risk flag

Report ph?i flag `valuation_extreme_sensitivity` n?u m?t trong c�c di?u ki?n x?y ra:

```text
WACC +1.0% l�m target price d?i rating t? BUY sang SELL ho?c t? SELL sang BUY
terminal growth +/-0.5% l�m target price thay d?i qu� ngu?ng c?u h�nh
base case target price n?m ngo�i v�ng h?p l� c?a peer check m� kh�ng c� gi?i th�ch
```

N?u flag n�y b?t, rating t?i da l� `UNDER REVIEW` cho d?n khi reviewer approve.

---

## Page 7 � Catalysts & Investment Risks

### 7.7.1. M?c ti�u

Tr�nh b�y di?u g� c� th? l�m thesis d�ng ho?c sai trong 6-12 th�ng t?i.

### 7.7.2. Positive catalysts table

```markdown
| Catalyst | Expected Timing | Affected Driver | Impact | Probability | Evidence |
|---|---|---|---|---|---|
| | | Revenue/margin/WACC/multiple | Low/Medium/High | Low/Medium/High | SRC-... |
```

### 7.7.3. Downside risks table

```markdown
| Risk | Affected Driver | Financial Impact | Mitigation/Monitor | Evidence |
|---|---|---|---|---|
| �p l?c gi?m gi� th?u | Gross margin/revenue | High | Theo d�i k?t qu? d?u th?u | SRC-... |
| Ph? thu?c s?n ph?m ch�nh | Revenue stability | Medium | Theo d�i product mix | SRC-... |
| T?n kho/ph?i thu tang | Working capital/FCFF | Medium | Theo d�i CCC | FACT-... |
```

### 7.7.4. R?i ro d?c th� ng�nh du?c/y t? Vi?t Nam c?n ki?m tra

- R?i ro d?u th?u thu?c.
- BHYT/reimbursement.
- Thay d?i quy d?nh dang k�/luu h�nh thu?c.
- GMP/nh� m�y/ch?t lu?ng s?n xu?t.
- C?nh tranh generic.
- Ph? thu?c k�nh ETC ho?c OTC.
- Bi?n d?ng nguy�n li?u nh?p kh?u.
- H�ng t?n kho, ph?i thu b?nh vi?n/nh� thu?c.
- T? gi� n?u nh?p nguy�n li?u.
- C? t?c, thanh kho?n, free float.
- R?i ro t?p trung s?n ph?m.
- R?i ro thu h?i thu?c ho?c ch?t lu?ng s?n ph?m.

### 7.7.5. Quy t?c vi?t risk

M?i r?i ro ph?i g?n v?i m?t financial driver.

Kh�ng vi?t:

```text
Th? tru?ng bi?n d?ng c� th? ?nh hu?ng d?n gi� c? phi?u.
```

Ph?i vi?t:

```text
N?u gi� tr�ng th?u gi?m m?nh hon gi? d?nh base case, gross margin c� th? gi?m x bps, l�m EBIT v� FCFF th?p hon m� h�nh hi?n t?i.
```

---

## Page 8 � Conclusion, Quality Summary, Sources & Disclaimer

### 7.8.1. M?c ti�u

Ch?t l?i b�o c�o, hi?n th? k?t lu?n d?nh gi�, m?c tin c?y, tr?ng th�i ki?m d?nh v� disclaimer.

### 7.8.2. N?i dung b?t bu?c

1. Key takeaways:
   - 3-5 bullet.
   - M?i bullet ph?i l� k?t lu?n c� can c?.

2. Final valuation conclusion:
   - Rating.
   - Target price.
   - Upside/downside.
   - �i?u ki?n d? rating thay d?i.

3. Client-facing quality summary:
   - Data confidence.
   - Source coverage.
   - Numeric consistency.
   - Valuation reproducibility.
   - Data cutoff.
   - Human review status.

4. Key sources:
   - Kh�ng li?t k� to�n b? source n?u qu� d�i.
   - Hi?n th? 5-10 ngu?n quan tr?ng nh?t.
   - To�n b? ngu?n n?m trong `source_manifest.json`.

5. Disclaimer.

### 7.8.3. Client-facing quality summary table

```markdown
| Quality Item | Status | Notes |
|---|---|---|
| Data Confidence | High/Medium/Low | |
| Source Coverage | {x}% | |
| Numeric Consistency | PASS/FAIL | |
| Valuation Reproducibility | PASS/FAIL | |
| Data Cutoff | {date} | |
| Human Review | PASS/PENDING | |
```

### 7.8.4. Internal gate summary

B?ng gate chi ti?t kh�ng b?t bu?c hi?n th? d?y d? trong PDF client-facing. Full detail ph?i n?m trong `eval_result.json`.

```markdown
| Gate | Status | Notes |
|---|---|---|
| Source Gate | PASS/FAIL | |
| Numeric Consistency | PASS/FAIL | |
| Valuation Reproducibility | PASS/FAIL | |
| Citation Coverage | {x}% | |
| Data Freshness | PASS/STALE | |
| Human Assumption Approval | PASS/PENDING | |
| Final Review | PASS/PENDING | |
```

### 7.8.5. Disclaimer chu?n

```text
B�o c�o n�y ch? nh?m m?c d�ch nghi�n c?u v� tham kh?o h?c thu?t/s?n ph?m. N?i dung kh�ng ph?i l� khuy?n ngh? d?u tu c� nh�n h�a, kh�ng ph?i l?i m?i mua/b�n ch?ng kho�n, v� kh�ng thay th? tu v?n t? chuy�n gia du?c c?p ph�p. Rating trong b�o c�o l� k?t lu?n m� h�nh d?a tr�n d? li?u, gi? d?nh v� m?c sinh l?i k? v?ng t?i th?i di?m l?p b�o c�o; kh�ng ph?i khuy?n ngh? d?u tu c� nh�n h�a. K?t qu? d?nh gi� ph? thu?c v�o d? li?u d?u v�o, gi? d?nh m� h�nh v� di?u ki?n th? tru?ng t?i th?i di?m l?p b�o c�o. Hi?u su?t qu� kh? kh�ng d?m b?o k?t qu? tuong lai. Ngu?i d?c ch?u tr�ch nhi?m d?c l?p khi s? d?ng th�ng tin.
```

---

## 8. Rating policy

### 8.1. Rating labels

```yaml
rating_labels:
  - BUY
  - HOLD
  - SELL
  - UNDER_REVIEW
```

### 8.2. Default upside/downside threshold

```yaml
rating_thresholds:
  buy:
    min_upside: 0.15
    required_confidence: 0.70
  hold:
    min_downside: -0.10
    max_upside: 0.15
    required_confidence: 0.60
  sell:
    max_upside: -0.10
    required_confidence: 0.70
  under_review:
    trigger:
      - insufficient_sources
      - failed_numeric_gate
      - missing_human_approval
      - valuation_extreme_sensitivity
      - source_conflict
      - unreliable_current_price
      - invalid_shares_outstanding
```

### 8.3. Enhanced rating rule

Rating kh�ng ch? d?a v�o upside/downside. Rating ph?i l� h�m c?a:

```text
rating = function(
  upside_downside,
  data_confidence,
  sensitivity_risk,
  liquidity_risk,
  business_risk,
  valuation_reproducibility,
  citation_coverage,
  reviewer_approval
)
```

### 8.4. Kh�ng du?c dua BUY/SELL/HOLD n?u

- Kh�ng c� current price d�ng tin c?y.
- Kh�ng c� shares outstanding h?p l?.
- Valuation kh�ng t�i l?p du?c.
- Target price thay d?i qu� m?nh theo sensitivity.
- D? li?u t�i ch�nh stale ho?c chua d? k?.
- Claim d?nh lu?ng ch�nh thi?u citation.
- Reviewer chua approve assumptions.
- Source m�u thu?n ? financial facts tr?ng y?u.
- Thanh kho?n qu� th?p nhung chua du?c flag trong risk.
- Data confidence th?p hon ngu?ng c?u h�nh.

Trong c�c tru?ng h?p tr�n, rating ph?i l� `UNDER REVIEW`.

---

## 9. Chart registry

B�o c�o 8 trang n�n c� t?i da 5-7 bi?u d?.

| Chart ID | T�n | Lo?i | Trang | B?t bu?c n?u d? li?u d? |
|---|---|---|---|---|
| C1 | Stock vs VNINDEX | Line, base 100 | Page 1 | C� |
| C2 | Revenue & EBITDA/EBIT Trend | Bar + line | Page 3 | C� |
| C3 | EPS & P/E Trend | Dual-axis line/bar | Page 3 | C� |
| C4 | Margin & ROE Trend | Multi-line | Page 3 | C� |
| C5 | Forecast Revenue/Profit | Bar + line | Page 4 | C� |
| C6 | DCF Value Bridge | Waterfall | Page 5 | Khuy?n ngh? |
| C7 | Sensitivity Heatmap | Heatmap/table | Page 6 | C� |

### 9.1. Chart generation contract

```json
{
  "chart_id": "C2",
  "title": "Revenue & EBITDA Margin Trend",
  "ticker": "DHG",
  "periods": ["2021A", "2022A", "2023A", "2024A", "2025A"],
  "metrics": ["net_revenue", "ebitda_margin"],
  "unit": "ty_vnd_and_percent",
  "data_refs": ["FACT-...", "METRIC-..."],
  "source_refs": ["SRC-..."],
  "status": "valid"
}
```

### 9.2. Chart fallback

N?u chart b?t bu?c kh�ng d? d? li?u:

```yaml
chart_status: omitted_due_to_missing_data
required_action:
  - explain_missing_data
  - do_not_fabricate_chart
  - flag_in_eval_result
```

---

## 10. Financial metric checklist

### 10.1. Metrics b?t bu?c

| Nh�m | Ch? s? |
|---|---|
| Growth | Revenue growth, net profit growth, revenue CAGR, net profit CAGR |
| Profitability | Gross margin, EBIT/EBITDA margin, net margin, ROE, ROA |
| Valuation | EPS, BVPS, P/E, P/B, EV/EBITDA, dividend yield n?u c� |
| Balance sheet | Debt/equity, net debt/cash, current ratio n?u c� |
| Working capital | Inventory days, receivable days, payable days, cash conversion cycle n?u d? d? li?u |
| Cash flow | CFO, CAPEX, FCFF, FCF conversion n?u d? d? li?u |

### 10.2. Formula registry requirement

Formula IDs trong code ph?i d?ng b? ch�nh x�c v?i `FORMULA_FINANCE.md` n?u file d� t?n t?i trong repository. M?c ti�u l� d? agent/tool calling g?i d�ng deterministic Python function, kh�ng t? t�nh b?ng ng�n ng? t? nhi�n.

```yaml
formulas:
  revenue_growth:
    formula: "(revenue_t / revenue_t_minus_1) - 1"
    unit: "%"
  gross_margin:
    formula: "gross_profit / net_revenue"
    unit: "%"
  net_margin:
    formula: "net_profit_after_tax / net_revenue"
    unit: "%"
  roe:
    formula: "net_profit_after_tax / average_equity"
    unit: "%"
  roa:
    formula: "net_profit_after_tax / average_assets"
    unit: "%"
  eps:
    formula: "net_profit_attributable_to_parent / weighted_average_shares"
    unit: "VND/share"
  pe:
    formula: "market_price / eps"
    unit: "x"
  pb:
    formula: "market_price / bvps"
    unit: "x"
  ev_ebitda:
    formula: "enterprise_value / ebitda"
    unit: "x"
  fcff:
    formula: "ebit * (1 - tax_rate) + depreciation - capex - change_in_nwc"
    unit: "VND"
```

### 10.3. Unit rules

| Data type | Internal storage | PDF display |
|---|---|---|
| VND amount | raw VND or normalized numeric with unit metadata | t? VND |
| Per-share | VND/share | VND/cp |
| Percent | decimal internally | % in PDF |
| Multiple | numeric | x |
| Date | ISO date | dd/mm/yyyy ho?c yyyy |

Kh�ng du?c tr?n `tri?u VND`, `t? VND`, `ngh�n VND` n?u kh�ng c� unit conversion r�.

---

## 11. Claim ledger contract

M?i claim trong report ph?i du?c ghi v�o `claim_ledger.json`.

### 11.1. Minimal schema

```json
{
  "claim_id": "CLM-001",
  "run_id": "RUN-...",
  "section": "investment_thesis",
  "page": 1,
  "claim_text": "Doanh thu thu?n 2024 tang 12.3% so v?i c�ng k?.",
  "claim_type": "quantitative",
  "ticker": "DHG",
  "period": "2024A",
  "metric": "net_revenue_growth",
  "value": 0.123,
  "unit": "%",
  "source_refs": ["SRC-001", "FACT-2024-DHG-IS-001"],
  "artifact_refs": ["valuation_result:base_case"],
  "support_status": "supported",
  "confidence": 0.92,
  "review_status": "approved"
}
```

### 11.2. Claim types

```yaml
claim_types:
  - quantitative
  - qualitative_business
  - valuation
  - forecast
  - risk
  - catalyst
  - peer_comparison
  - conclusion
  - disclaimer
```

### 11.3. Support status

```yaml
support_status:
  supported: "C� d? ngu?n ho?c artifact"
  partially_supported: "C� ngu?n nhung thi?u m?t ph?n logic"
  unsupported: "Kh�ng du?c ph�p xu?t hi?n trong final report"
  conflicting: "Ngu?n m�u thu?n, c?n review"
```

### 11.4. Final report rule

```text
unsupported claims allowed in final report = 0
conflicting claims allowed in final report = 0 unless explicitly labeled as conflict and approved by reviewer
```

---

## 12. Source manifest contract

### 12.1. Minimal schema

```json
{
  "source_id": "SRC-001",
  "run_id": "RUN-...",
  "ticker": "DHG",
  "source_type": "annual_report",
  "source_name": "B�o c�o thu?ng ni�n 2024",
  "publisher": "Company",
  "published_date": "2025-03-30",
  "retrieval_timestamp": "2026-05-07T10:00:00+07:00",
  "period": "2024A",
  "url_or_path": "sources/DHG/annual_report_2024.pdf",
  "reliability_tier": "official",
  "checksum": "sha256:...",
  "parser_version": "v1.0",
  "used_sections": ["financial_statements", "business_overview", "management_discussion"]
}
```

### 12.2. Reliability tiers

```yaml
reliability_tier:
  official: "Company filing, exchange disclosure, audited financial statement"
  regulated_public: "Government/regulatory/tender/BHYT source"
  reputable_media: "Recognized business/financial media"
  third_party_data: "Market data/data API/vendor"
  unknown: "Not allowed for final claims unless reviewer approves with note"
```

### 12.3. Source usage rule

| Source type | Allowed usage |
|---|---|
| Official filing | Financial facts, business overview, management discussion |
| Audited financial statement | Canonical financial facts |
| Exchange disclosure | Events, corporate actions, listing data |
| Regulatory/tender/BHYT | Catalysts and policy risk |
| Reputable media | Context, catalyst, market interpretation |
| Third-party API | Market data or provisional data; must be reconciled for critical financial facts |
| Unknown source | Not allowed in final report |

---

## 13. Valuation result contract

`valuation_result.json` l� ngu?n duy nh?t cho target price, upside/downside, DCF output, multiples output, sensitivity v� scenario.

### 13.1. Minimal schema

```json
{
  "run_id": "RUN-...",
  "ticker": "DHG",
  "valuation_date": "2026-05-31",
  "currency": "VND",
  "base_year": "2025A",
  "forecast_years": ["2026F", "2027F", "2028F", "2029F", "2030F"],
  "current_price": 0,
  "target_price": 0,
  "upside_downside": 0,
  "rating_model_output": "UNDER_REVIEW",
  "fcff_dcf": {
    "wacc": 0,
    "terminal_growth": 0,
    "pv_fcff": 0,
    "terminal_value": 0,
    "pv_terminal_value": 0,
    "enterprise_value": 0,
    "cash_and_equivalents": 0,
    "debt": 0,
    "minority_interest": 0,
    "equity_value": 0,
    "shares_outstanding": 0,
    "implied_price": 0
  },
  "multiples": {
    "pe": {"implied_price": 0, "weight": 0, "status": "valid"},
    "pb": {"implied_price": 0, "weight": 0, "status": "valid"},
    "ev_ebitda": {"implied_price": 0, "weight": 0, "status": "valid"}
  },
  "sensitivity": {},
  "scenarios": {},
  "assumptions": [],
  "reproducibility_hash": "sha256:..."
}
```

### 13.2. Valuation reproducibility

Report final ph?i c� kh? nang recompute target price t? `valuation_result.json`.

```text
recomputed_target_price == reported_target_price within configured tolerance
```

N?u kh�ng pass, export ph?i b? block.

---

## 14. Evaluation gates

### 14.1. Gate thresholds

```yaml
evaluation_thresholds:
  quantitative_claim_citation_coverage: 1.00
  numeric_consistency_min: 0.99
  valuation_reproducibility: 1.00
  unsupported_claims_allowed: 0
  conflicting_claims_allowed_without_label: 0
  stale_financial_data_allowed: false
  fake_citation_allowed: false
  final_confidence_min: 0.70
```

### 14.2. Source gate

Pass khi:

- t?t c? financial facts ch�nh c� source;
- source t?n t?i trong source manifest;
- source kh�ng thu?c tier `unknown` cho claim quan tr?ng;
- financial facts ch�nh uu ti�n official ho?c reconciled source;
- kh�ng c� source conflict chua x? l�.

### 14.3. Numeric consistency gate

Agent ph?i ki?m tra:

- s? trong report kh?p v?i `canonical facts` ho?c `valuation_result`;
- don v? kh�ng b? sai: VND, t? VND, tri?u VND, %, x;
- nam/k? kh�ng b? nh?m;
- forecast v� actual du?c k� hi?u d�ng;
- t?ng t�i s?n = t?ng ngu?n v?n n?u hi?n th? b?ng c�n d?i k? to�n;
- FCFF c� th? recompute t? c�c th�nh ph?n;
- target price c� th? recompute t? equity value v� shares outstanding;
- chart data kh?p v?i data trong b?ng.

### 14.4. Citation gate

Pass khi:

```text
100% quantitative claims have valid citation or artifact reference
0 fake citation
0 dangling citation
0 citation pointing to wrong ticker
0 citation pointing to wrong period
```

### 14.5. Valuation reproducibility gate

Pass khi:

```text
DCF output recompute du?c t? valuation_result
final target price recompute du?c t? weighted valuation summary
upside/downside recompute du?c t? target price v� current price
sensitivity matrix recompute du?c t? assumptions
```

### 14.6. Risk language gate

Pass khi:

- kh�ng c� �ch?c ch?n�, �d?m b?o�, �n�n mua ngay�;
- rating du?c gi?i th�ch l� model conclusion;
- risks g?n v?i financial driver;
- disclaimer d?y d?;
- report kh�ng dua l?i khuy�n c� nh�n h�a.

### 14.7. Human review gate

Pass khi:

```json
{
  "human_assumption_approval": "pass",
  "human_final_review": "pass",
  "approved_by": "reviewer_id",
  "approved_at": "timestamp",
  "approved_artifact_hashes": ["sha256:..."]
}
```

---

## 15. Report quality rubric

| Dimension | Score 1 | Score 3 | Score 5 |
|---|---|---|---|
| Accuracy | Nhi?u l?i s?/ngu?n | C� l?i nh? | S? v� ngu?n nh?t qu�n |
| Logicality | Lu?n di?m r?i r?c | C� logic nhung thi?u driver | Driver -> forecast -> valuation -> risk r� |
| Storytelling | D�i, kh� d?c | �?c du?c | Ng?n g?n, chuy�n nghi?p, c� insight |
| Grounding | Thi?u citation | Citation chua d?u | Claim quan tr?ng d?u c� source |
| Valuation transparency | Assumption mo h? | C� b?ng assumption | Reproducible, c� sensitivity |
| Risk balance | Thi�n l?ch | C� r?i ro nhung chung | R?i ro c? th?, g?n financial driver |
| Visual design | R?i, kh� d?c | �?t m?c co b?n | PDF g?n, chuy�n nghi?p, d�ng page budget |

### 15.1. Minimum target

```yaml
quality_targets:
  accuracy: 5
  logicality: 4
  storytelling: 4
  grounding: 5
  valuation_transparency: 5
  risk_balance: 4
  visual_design: 4
```

---

## 16. Markdown skeleton cho report final

Agent c� th? d�ng skeleton sau d? sinh `report.md`.

```markdown
---
report_type: equity_research
ticker: "{TICKER}"
company_name: "{COMPANY_NAME}"
exchange: "{EXCHANGE}"
sector: "Du?c/Y t?"
report_date: "{REPORT_DATE}"
data_cutoff: "{DATA_CUTOFF}"
rating: "{RATING}"
current_price: "{CURRENT_PRICE}"
target_price: "{TARGET_PRICE}"
upside_downside: "{UPSIDE_DOWNSIDE}"
risk_level: "{RISK_LEVEL}"
data_confidence: "{DATA_CONFIDENCE}"
status: "{DRAFT|NEEDS_REVIEW|PENDING_APPROVAL|APPROVED|BLOCKED|FINAL_EXPORTABLE}"
---

# {TICKER} � {COMPANY_NAME}
## Equity Research Report | {REPORT_DATE}

### Investment Snapshot

| Rating | Current Price | Target Price | Upside/Downside | Horizon | Risk Level | Data Confidence |
|---|---:|---:|---:|---|---|---|
| {RATING} | {CURRENT_PRICE} | {TARGET_PRICE} | {UPSIDE_DOWNSIDE} | {HORIZON} | {RISK_LEVEL} | {DATA_CONFIDENCE} |

### Key Metrics Snapshot

{KEY_METRICS_TABLE}

### Investment Thesis

{INVESTMENT_THESIS}

![Stock vs VNINDEX](charts/{TICKER}_price_vs_vnindex.png)

\pagebreak

## Company Overview & Business Model

{COMPANY_OVERVIEW}

{BUSINESS_DRIVER_TABLE_OR_REVENUE_MIX_CHART}

\pagebreak

## Financial Performance

{FINANCIAL_PERFORMANCE_NARRATIVE}

{FINANCIAL_SUMMARY_TABLE}

![Revenue & EBITDA Trend](charts/{TICKER}_revenue_ebitda.png)

![EPS & P/E Trend](charts/{TICKER}_eps_pe.png)

![Margin & ROE Trend](charts/{TICKER}_margin_roe.png)

\pagebreak

## Forecast & Key Assumptions

{FORECAST_NARRATIVE}

{DRIVER_BASED_FORECAST_TABLE}

{FORECAST_TABLE}

{ASSUMPTIONS_TABLE}

![Forecast Revenue and Profit](charts/{TICKER}_forecast.png)

\pagebreak

## Valuation

{VALUATION_NARRATIVE}

{DCF_TABLE}

{VALUATION_SUMMARY_TABLE}

{VALUATION_ASSUMPTIONS_TABLE}

![DCF Value Bridge](charts/{TICKER}_dcf_bridge.png)

\pagebreak

## Sensitivity, Scenario & Peer Check

{SENSITIVITY_NARRATIVE}

{SENSITIVITY_MATRIX}

{SCENARIO_TABLE}

{PEER_COMPARISON_TABLE}

\pagebreak

## Catalysts & Risks

{CATALYSTS_TABLE}

{RISKS_TABLE}

{RISK_NARRATIVE}

\pagebreak

## Conclusion, Quality Summary & Disclaimer

### Key Takeaways

{KEY_TAKEAWAYS}

### Final Valuation Conclusion

{FINAL_CONCLUSION}

### Quality Summary

{CLIENT_FACING_QUALITY_SUMMARY}

### Key Sources

{KEY_SOURCES_TABLE}

### Disclaimer

{DISCLAIMER}
```

---

## 17. Agent execution instruction

Khi du?c y�u c?u sinh b�o c�o, agent ph?i tu�n th? th? t? sau:

```text
1. Load run state and ticker metadata.
2. Validate source_manifest and data freshness.
3. Load canonical facts.
4. Run deterministic financial metric computation.
5. Run deterministic valuation engine.
6. Generate chart data from computed artifacts.
7. Build or verify driver-based forecast table.
8. Ask/verify human approval for assumptions if required.
9. Draft section-by-section report narrative.
10. Build claim_ledger.
11. Run citation audit.
12. Run numeric consistency audit.
13. Run valuation reproducibility audit.
14. Run risk language audit.
15. Run visual/page-budget check.
16. If all gates pass, export report.md/html/pdf.
17. If any gate fails, mark report as NEEDS_REVIEW/BLOCKED/PENDING_APPROVAL and explain failure.
```

### 17.1. Section writing constraints

| Section | Allowed source | Prohibited |
|---|---|---|
| Investment Thesis | facts + valuation_result + claim ledger | Unsupported growth story |
| Company Overview | official filings + company source + verified news | Generic company praise |
| Financial Performance | canonical facts + computed metrics | LLM-calculated ratios |
| Forecast | approved assumptions + valuation artifact + driver table | Invented assumptions |
| Valuation | valuation_result only | Manual target price in text |
| Sensitivity | valuation_result only | Manually invented matrix |
| Risks | evidence + domain risk taxonomy | Generic risk list |
| Conclusion | passed gates + valuation summary | Personalized investment advice |

### 17.2. LLM prompt boundary

LLM prompt ph?i nh?n artifact d� chu?n h�a, kh�ng nh?n raw unverified data d? t? suy do�n.

```text
LLM input allowed:
- cleaned evidence snippets
- source metadata
- canonical facts summary
- computed metrics table
- valuation_result summary
- approved assumptions
- gate status summary

LLM input not allowed:
- unverified raw financial data as source of truth
- ambiguous API output without unit metadata
- unsupported news snippets without source metadata
- user instruction to alter rating without valuation evidence
```

---

## 18. Failure handling

N?u thi?u d? li?u ho?c ki?m d?nh kh�ng pass, b�o c�o kh�ng du?c gi? v? ho�n ch?nh.

### 18.1. Failure messages

| Failure | Report Status | Required Message |
|---|---|---|
| Missing financial facts | `NEEDS_REVIEW` | Thi?u d? li?u t�i ch�nh cho k? X; kh�ng th? ho�n t?t valuation |
| Source conflict | `NEEDS_REVIEW` | Ngu?n A v� B m�u thu?n t?i ch? ti�u X |
| Failed numeric audit | `BLOCKED` | S? trong report kh�ng kh?p artifact |
| Failed citation audit | `BLOCKED` | C� claim quan tr?ng thi?u ngu?n |
| Failed valuation reproducibility | `BLOCKED` | Target price kh�ng t�i l?p du?c t? valuation_result |
| Extreme sensitivity | `NEEDS_REVIEW` | Target price qu� nh?y v?i WACC/growth |
| Missing human approval | `PENDING_APPROVAL` | Assumptions/final report chua du?c duy?t |
| Missing chart data | `NEEDS_REVIEW` ho?c `DRAFT` | Chart X b? b? v� thi?u d? li?u d� ki?m d?nh |
| Layout overflow | `NEEDS_REVIEW` | Report vu?t page budget; c?n n�n n?i dung ho?c chuy?n appendix |

### 18.2. Kh�ng du?c d�ng c�c c�u sau

- �C� th? c�ng ty s? tang tru?ng m?nh� n?u kh�ng c� driver v� ngu?n.
- �C? phi?u ch?c ch?n h?p d?n�.
- �N�n mua ngay�.
- �Theo d? li?u th? tru?ng� nhung kh�ng n�u ngu?n c? th?.
- �Target price du?c t�nh to�n� nhung kh�ng c� valuation artifact.
- �R?i ro th?p� n?u chua c� risk scoring.
- �Ngu?n: database� m� kh�ng c� source id/fact id.

---

## 19. Definition of Done

M?t b�o c�o du?c coi l� d?t chu?n n?u th?a to�n b? ti�u ch�:

| Category | Requirement |
|---|---|
| Structure | �? 8 section ch�nh, PDF kho?ng 8 trang |
| Visual | Layout chuy�n nghi?p, chart/table r�, kh�ng tr�n page budget |
| Data | C� source manifest v� data cutoff |
| Financials | C� b?ng financial summary v� forecast summary |
| Forecast | C� driver-based forecast table |
| Valuation | C� FCFF DCF, assumptions, target price, sensitivity |
| Rating | BUY/HOLD/SELL/UNDER_REVIEW theo threshold, data confidence v� review |
| Charts | C� t?i thi?u 5 chart ch�nh n?u d? li?u d? |
| Citation | 100% claim d?nh lu?ng c� citation ho?c artifact reference |
| Numeric | >=99% numeric consistency |
| Reproducibility | Target price recompute du?c t? valuation_result |
| Risk | R?i ro c? th?, g?n financial driver |
| Disclaimer | C� disclaimer chu?n |
| Audit | C� eval_result, claim_ledger, source_manifest, run_log |
| Human Review | C� approval record tru?c final export |

---

## 20. Minimal viable report cho demo 6 tu?n

N?u kh�ng d? th?i gian l�m b?n full 8 trang, demo t?i thi?u ph?i c�:

1. Page 1: Investment snapshot + thesis + price chart.
2. Page 2: Company overview + business model.
3. Page 3: Financial performance + 2 charts.
4. Page 4: Driver-based forecast assumptions + forecast table.
5. Page 5: FCFF DCF + target price.
6. Page 6: Sensitivity + risks.
7. Appendix artifacts: `claim_ledger`, `source_manifest`, `valuation_result`, `eval_result`.

Kh�ng du?c c?t b? valuation audit, citation audit ho?c numeric audit, v� d�y l� l�i tin c?y c?a d? �n.

### 20.1. MVP minimum gates

```yaml
mvp_minimum_gates:
  source_gate: required
  numeric_consistency_gate: required
  valuation_reproducibility_gate: required
  citation_gate: required
  risk_language_gate: required
  human_final_review: required
```

---

## 21. Implementation notes for Claude/code agent

### 21.1. Recommended module split

D� t�i li?u n�y l� single-file spec, implementation n�n t�ch code theo module:

```text
report_renderer/
  markdown_builder.py
  html_renderer.py
  pdf_renderer.py
  layout_rules.py

report_contracts/
  claim_ledger_schema.py
  source_manifest_schema.py
  valuation_result_schema.py
  eval_result_schema.py

report_gates/
  source_gate.py
  citation_gate.py
  numeric_consistency_gate.py
  valuation_reproducibility_gate.py
  risk_language_gate.py
  visual_budget_gate.py

report_sections/
  page_1_snapshot.py
  page_2_company.py
  page_3_financials.py
  page_4_forecast.py
  page_5_valuation.py
  page_6_sensitivity_peer.py
  page_7_catalyst_risk.py
  page_8_conclusion.py
```

### 21.2. Rendering strategy

Khuy?n ngh? pipeline:

```text
Markdown section builder
  -> HTML renderer with CSS layout
  -> PDF renderer
  -> visual/page-budget validation
  -> final export
```

Kh�ng n�n render PDF tr?c ti?p t? raw LLM text n?u chua qua structured section builder.

### 21.3. Test requirements

C?n c� test cho:

- missing citation blocks export;
- fake citation blocks export;
- numeric mismatch blocks export;
- target price mismatch blocks export;
- unsupported claim removed from final;
- failed human approval prevents final_exportable;
- chart with missing data omitted safely;
- report exceeding page budget flagged;
- driver-based forecast table required for Page 4;
- rating downgraded to UNDER_REVIEW when gate fails.

---

## 22. Final instruction for report-generating agent

Sinh b�o c�o nhu m?t analyst chuy�n nghi?p, nhung v?n h�nh nhu m?t h? th?ng ki?m d?nh d? li?u nghi�m ng?t.

Uu ti�n theo th? t?:

```text
Correctness > Traceability > Valuation Reproducibility > Risk Balance > Readability > Visual Design
```

Kh�ng du?c d�nh d?i d? d�ng s? li?u d? l?y van phong hay. M?t b�o c�o ng?n nhung d�ng ngu?n, d�ng s?, d�ng valuation t?t hon m?t b�o c�o d�i, d?p nhung kh�ng th? ki?m ch?ng.

