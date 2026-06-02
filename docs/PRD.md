 PRD � Vietnam Pharma Multi-Agent Equity Research

*T�i li?u y�u c?u s?n ph?m cho backend v� workflow nghi�n c?u c? phi?u du?c/y t? ni�m y?t Vi?t Nam.*

---

## 1. T�m t?t s?n ph?m

S?n ph?m l� m?t n?n t?ng `multi-agent equity research` cho ng�nh du?c/y t? Vi?t Nam, c� kh? nang:

- ingest v� chu?n h�a d? li?u t? ngu?n Vi?t Nam,
- t?o `canonical facts` cho ph�n t�ch,
- ch?y `code-first valuation`,
- t?o `grounded draft report` c� citation,
- y�u c?u `HITL approval` tru?c khi ph�t h�nh,
- h? tr? `flash memo` v� `catalyst refresh`.

S?n ph?m kh�ng c?nh tranh tr?c ti?p ? l?p terminal d? li?u to�n c?u; l?i th? n?m ? `Vietnam-local data`, `artifact-first reasoning`, `workflow c� ki?m so�t`, v� `reporting c� ngu?n`.

---

## 2. Ngu?i d�ng m?c ti�u

### 2.1 Personas ch�nh

- `Sell-side analyst`: c?n gi?m th?i gian l?y s?, gi? consistency, v� sinh b?n nh�p nhanh.
- `Portfolio manager / buy-side`: c?n t�m t?t ng?n, catalyst alert, v� nhanh ch�ng th?y t�c d?ng d?n valuation.
- `Research lead / reviewer`: c?n c�ng c? ki?m tra lu?n di?m, citation, assumptions, v� audit trail.

### 2.2 Personas v?n h�nh

- `Data ops`: qu?n l� connector, parser, data quality, freshness, v� l?i ngu?n.
- `Compliance / reviewer`: ph� duy?t n?i dung tru?c publish, ki?m tra disclaimer v� ngu?n.
- `Admin`: qu?n tr? ngu?i d�ng, quota, policy, v� c?u h�nh model.

---

## 3. M?c ti�u s?n ph?m

### 3.1 M?c ti�u kinh doanh

- R�t ng?n th?i gian t?o `full report draft` t? `15-30 gi?` xu?ng du?i `60 ph�t` ? di?u ki?n backend ?n d?nh.
- Cung c?p `flash memo` trong v�ng `5 ph�t` cho c�c trigger d� chu?n h�a.
- Chu?n h�a research workflow cho `23` m� trong danh m?c m?c ti�u.

### 3.2 M?c ti�u ch?t lu?ng

- `100%` claim d?nh lu?ng trong b?n d� duy?t ph?i c� citation h?p l?.
- Ch?t lu?ng reviewer cho `accuracy / logicality / storytelling` d?t t?i thi?u `8 / 8 / 7.5` ? giai do?n pilot.
- `EPS forecast accuracy > 90%` theo d?nh nghia trong m?c do lu?ng.

### 3.3 M?c ti�u v?n h�nh

- H? tr? `resume`, `retry`, `partial recompute`, v� `audit log`.
- C� `usage tracking` v� `cost governance` cho t?ng research run.
- C� `data quality gates` tru?c khi d? li?u tr? th�nh fact c� th? d�ng cho valuation.

---

## 4. Ph?m vi s?n ph?m

### 4.1 Trong ph?m vi giai do?n 1

- `23` m� du?c/y t? ni�m y?t Vi?t Nam.
- `Full report`, `flash memo`, `catalyst refresh`.
- `DCF`, `P/E`, `EV/EBITDA`, sensitivity analysis.
- D? li?u t? BCTC, ni�m y?t, d?u th?u, BHYT, regulatory notices, company news.
- Peer comparison theo taxonomy n?i b?.
- B�o c�o ti?ng Vi?t c� citation, approval workflow, v� audit trail.

### 4.2 Ngo�i ph?m vi giai do?n 1

- Auto-trading, auto-order routing, ho?c recommendation publish t? d?ng.
- Bao ph? c? phi?u ngo�i danh m?c du?c/y t? m?c ti�u.
- Global biotech/pharma l�m l�i d? li?u.
- L?y Bloomberg API l�m dependency b?t bu?c.

---

## 5. K?t qu? ngu?i d�ng mong d?i

### 5.1 Full report

Ngu?i d�ng g?i y�u c?u nghi�n c?u v� nh?n l?i:

- tr?ng th�i run theo t?ng bu?c,
- assumptions draft,
- valuation artifact,
- report draft c� citation map,
- b�o c�o xu?t b?n sau khi du?c duy?t.

### 5.2 Flash memo

Ngu?i d�ng nh?n:

- memo ng?n theo catalyst ho?c bi?n d?ng d�ng k?,
- t�c d?ng so b? l�n lu?n di?m ho?c d?nh gi�,
- ngu?n v� m?c confidence.

### 5.3 Catalyst monitoring

Ngu?i d�ng theo d�i m� v� nh?n:

- catalyst m?i,
- m?c d? nghi�m tr?ng,
- c� c?n recompute thesis hay valuation hay kh�ng.

---

## 6. Nang l?c h? th?ng b?t bu?c

### CAP-1 Ingestion and connectors

- H? th?ng ph?i k?t n?i du?c v?i ngu?n BCTC, c�ng b? ni�m y?t, d?u th?u thu?c, BHYT, regulatory notices, v� company news.
- M?i l?n ingest ph?i sinh `source metadata`, `ingestion run`, v� checksum ho?c version tuong duong.

### CAP-2 Data quality and reconciliation

- D? li?u ingest ph?i qua validation tru?c khi ghi v�o canonical store.
- C�c rule t?i thi?u g?m:
  - schema validation,
  - missing-field checks,
  - financial sanity rules,
  - reconciliation gi?a subtotal v� total n?u c�,
  - duplicate detection,
  - source confidence scoring.

### CAP-3 Canonical financial model

- H? th?ng ph?i chu?n h�a line item v�o taxonomy n?i b?.
- Facts ph?i du?c luu du?i schema ?n d?nh, c� `source_uri`, `effective_date`, `ingested_at`, `parser_version`, v� `confidence`.

### CAP-4 Research orchestration

- Workflow ph?i l� stateful run c� `idempotency`, `checkpoint`, `retry`, `resume`, `manual escalation`.
- H? tr? c�c run type: `full_report`, `flash_memo`, `catalyst_refresh`.

### CAP-5 Valuation engine

- Valuation ch?y b?ng code v?i input/output schema r� r�ng.
- LLM kh�ng du?c ph�p t?o ho?c s?a financial facts sau bu?c fact validation.
- K?t qu? valuation ph?i luu th�nh artifact ri�ng d? downstream ch? d?c, kh�ng t? di?n gi?i l?i s?.

### CAP-6 Grounded report generation

- Report draft ph?i du?c sinh t? artifact d� kh�a ngu?n.
- M?i claim d?nh lu?ng ph?i c� citation t?i document chunk ho?c fact record h?p l?.
- N?u kh�ng t�m du?c grounding ph� h?p, claim d� kh�ng du?c xu?t b?n t? d?ng.

### CAP-7 HITL, review, and audit

- C� �t nh?t hai approval gates:
  - assumptions and key drivers,
  - final recommendation and publish.
- H? th?ng ph?i luu l?i `who approved what`, `when`, v� `against which artifact version`.

### CAP-8 Observability and admin

- C� dashboard ho?c API d? xem tr?ng th�i run, l?i connector, l?i parser, latency, v� approval backlog.
- C� log v� metric cho t?ng stage c?a workflow.

### CAP-9 Usage tracking and cost control

- M?i run ph?i ghi nh?n token usage, model cost, retry count, v� stop reason.
- Ph?i c� budget policy d? ch?n downgrade model, skip low-value steps, ho?c escalation sang manual review khi chi ph� vu?t ngu?ng.

### CAP-10 Offline evaluation

- H? th?ng ph?i h? tr? d�nh gi� ch?t lu?ng tru?c production cho:
  - extraction quality,
  - citation grounding,
  - thesis quality,
  - report stability.
- C� regression baseline d? so s�nh gi?a model/prompt/parser version.

---

## 7. User stories tr?ng t�m

### US-1 Analyst t?o full report

L� m?t `analyst`, t�i mu?n g?i y�u c?u cho m?t m� v?i c�c k?ch b?n co s? d? h? th?ng t?o b?n nh�p b�o c�o c� citation, nh?m gi?m th?i gian d?ng n?n v� gi? du?c c?u tr�c ph�n t�ch ?n d?nh.

### US-2 Reviewer duy?t khuy?n ngh?

L� m?t `reviewer`, t�i mu?n xem assumptions, valuation artifact, citation map, v� thay d?i so v?i b?n g?n nh?t, nh?m quy?t d?nh approve, reject, ho?c y�u c?u ch?y l?i t?ng ph?n.

### US-3 PM nh?n flash memo

L� m?t `portfolio manager`, t�i mu?n nh?n flash memo sau m?t catalyst m?i, nh?m bi?t nhanh li?u lu?n di?m d?u tu c� thay d?i d? l?n d? c?n d?c l?i full report hay kh�ng.

### US-4 Data ops x? l� l?i ngu?n

L� m?t `data ops`, t�i mu?n bi?t connector n�o l?i, record n�o fail validation, v� t�i li?u n�o g�y parse mismatch, nh?m x? l� nhanh m� kh�ng ?nh hu?ng to�n b? pipeline.

---

## 8. Acceptance criteria

### 8.1 MVP 5 m�

Ph?m vi: `DHG`, `IMP`, `DMC`, `TRA`, `DBD`.

- C� th? ingest t?i thi?u `3-5 nam` d? li?u BCTC cho m?i m�.
- C� golden dataset cho facts v� EPS actuals c?a 5 m�.
- `Full report p95 < 60 ph�t` trong m�i tru?ng m?c ti�u.
- `Flash memo p95 < 5 ph�t`.
- `Citation coverage = 100%` cho claim d?nh lu?ng trong b?n d� duy?t.
- `>= 90%` observation trong t?p v�ng d?t sai s? EPS trong ngu?ng d� d?nh.
- H? th?ng h? tr? `retry/resume` n?u l?i ? bu?c sau ingestion.
- C� approval workflow cho assumptions v� final recommendation.
- M?i run c� cost ledger v� stop reason.

### 8.2 Scale-up 23 m�

- C� taxonomy v� peer grouping ?n d?nh cho to�n b? 23 m�.
- C� catalyst ingestion t?i thi?u theo l?ch d?nh s?n v� trigger th? c�ng.
- H? tr? t?i d?ng th?i nhi?u run v?i queue isolation.
- C� incremental recompute khi document ho?c catalyst m?i xu?t hi?n.
- C� monitoring v� alert cho freshness, failure rate, v� abnormal cost per run.

---

## 9. �?nh nghia ch? s?

### 9.1 EPS forecast accuracy > 90%

�? xu?t m?c d?nh:

- T?p d�nh gi� g?m `N` qu� g?n nh?t c?a c�c m� trong MVP.
- Sai s? theo qu�:

```text
abs(EPS_forecast - EPS_actual) / max(abs(EPS_actual), epsilon)
```

- M?t quan s�t du?c t�nh l� th�nh c�ng khi sai s? `<= 15%`.
- KPI d?t khi `>= 90%` t?ng s? quan s�t th�nh c�ng.

### 9.2 Citation coverage

- T? l? claim d?nh lu?ng trong report final c� �t nh?t m?t citation h?p l? tr? v? source ho?c fact record d� du?c ch?p nh?n.

### 9.3 Cost per run

- T?ng chi ph� LLM v� compute c?a m?t run, du?c theo d�i theo t?ng stage d? ki?m so�t budget.

---

## 10. Y�u c?u phi ch?c nang

- `Reliability`: run ph?i c� kh? nang resume v� partial recompute.
- `Security`: RBAC theo vai tr� `analyst`, `reviewer`, `data_ops`, `admin`.
- `Compliance`: m?i publish ph?i c� approval record.
- `Scalability`: queue v� worker scale ngang cho ingestion, indexing, valuation, synthesis.
- `Observability`: trace, metrics, logs, lineage, v� run history.
- `Data rights`: tu�n th? gi?y ph�p v� di?u kho?n ngu?n.
- `Cost control`: budget policy, fallback model, v� usage reporting.

---

## 11. R?i ro v� ph? thu?c

- Ch?t lu?ng `OCR/PDF parsing` c?a BCTC v� t�i li?u ph�p l�.
- T�nh ?n d?nh v� quy?n truy c?p c?a ngu?n d?u th?u/BHYT/regulatory.
- Ch?t lu?ng taxonomy n?i b? v� peer grouping.
- R?i ro LLM di?n gi?i vu?t ra ngo�i artifact ho?c m?t grounding.
- Chi ph� model tang nhanh n?u kh�ng kh�a scope v� cache h?p l�.

---

## 12. L? tr�nh ph�t h�nh

1. `Foundation and data contracts`
2. `Fact ingestion and code-first valuation`
3. `RAG and citation pipeline`
4. `Orchestration and HITL`
5. `Production hardening`
6. `Agentic reasoning and thesis generation`

M?c m?c ti�u:

- `Q3/2026`: beta cho 5 m� MVP.
- `Q1/2027`: m? r?ng 23 m� v?i catalyst monitoring ?n d?nh.

---

## 13. C�u h?i s?n ph?m c�n m?

- �?nh nghia ch�nh th?c c?a `500 users`: seat t? ch?c hay MAU.
- M?c chi ti?t catalyst d?u th?u trong MVP: to�n qu?c, theo t?nh, hay theo b?nh vi?n.
- Ch�nh s�ch luu tr? van b?n regulatory: cache n?i b? hay luu metadata + link.
- Ngu?ng cost/run n�o s? k�ch ho?t fallback ho?c chuy?n sang manual review.
