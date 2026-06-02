 Problem Brief � Vietnam Pharma Multi-Agent Equity Research

*T�i li?u d?nh nghia b�i to�n v� nguy�n t?c thi?t k? cho backend c?a h? `multi-agent equity research` t?p trung v�o c? phi?u du?c/y t? ni�m y?t t?i Vi?t Nam.*

---

## 1. M?c ti�u t�i li?u

- L�m r� v� sao b�i to�n `equity research` ng�nh du?c Vi?t Nam kh� hon m?t b�i to�n t�m t?t t�i li?u hay chatbot t�i ch�nh th�ng thu?ng.
- Ch?t ph?m vi k? thu?t c?t l�i c?a h? th?ng: `ingestion -> facts -> valuation -> grounded narrative -> HITL publish`.
- Thi?t l?p b? nguy�n t?c d? d?ng b? [PRD.md](PRD.md), [BACKEND-PLAN.md](BACKEND-PLAN.md), v� [SEQUENCE.md](SEQUENCE.md).

---

## 2. B?i c?nh v� co h?i

### 2.1 B?i c?nh th? tru?ng

- Danh m?c m?c ti�u g?m kho?ng `53` doanh nghi?p du?c/y t? ni�m y?t tr�n `HOSE`, `HNX`, v� `UPCOM`.
- M?t b�o c�o nghi�n c?u ch?t lu?ng thu?ng d�i h?i `15-30 gi?` l�m vi?c th? c�ng cho thu th?p d? li?u, chu?n h�a s? li?u, d?ng lu?n di?m, v� r� so�t ngu?n.
- D�ng ti?n v�o nh�m du?c ch?u ?nh hu?ng m?nh b?i catalyst d?a phuong nhu `d?u th?u thu?c`, `BHYT`, `thay d?i dang k�/luu h�nh`, v� t�n hi?u t? `C?c Qu?n l� Du?c`.

### 2.2 Kho?ng tr?ng c�ng c? hi?n t?i

- C�ng c? qu?c t? m?nh v? d? li?u to�n c?u nhung y?u ? `van b?n ti?ng Vi?t`, `d?u th?u`, `quy d?nh d?a phuong`, v� `b?i c?nh pharma Vi?t Nam`.
- N?n t?ng ch?ng kho�n n?i d?a m?nh ? market data nhung chua c� workflow `multi-agent`, `code-first valuation`, v� `citation-first reporting`.
- LLM chat don l? c� th? h? tr? vi?t nh�p, nhung kh�ng d�ng tin cho `d�ng s?`, `d�ng ngu?n`, `d�ng logic`, v� `d�ng ki?m so�t quy tr�nh`.

### 2.3 Co h?i s?n ph?m

- Chu?n h�a research workflow cho to�n b? `53` m� thay v� l? thu?c v�o excel v� ph�n t�ch th? c�ng.
- T?o `flash memo` v� `full report draft` c� ngu?n, gi�p analyst t?p trung v�o judgment thay v� d�nh ph?n l?n th?i gian cho kh�u d?ng n?n.
- X�y d?ng l?i th? c?nh tranh b?ng `local context first`: d? li?u Vi?t Nam, taxonomy Vi?t Nam, catalyst Vi?t Nam, v� review workflow ph� h?p t? ch?c t�i ch�nh.

---

## 3. V� sao b�i to�n n�y kh�

### 3.1 D? li?u ph�n m?nh v� kh�ng d?ng nh?t

- B�o c�o t�i ch�nh t?n t?i ? nhi?u d?ng `PDF`, `HTML`, file scan, v� c�ng b? r?i r?c.
- Line item thay d?i theo doanh nghi?p, nam, v� c�ch thuy?t minh.
- Ngu?n catalyst phi c?u tr�c, thi?u schema th?ng nh?t, v� c� ch?t lu?ng kh�ng d?ng d?u.

### 3.2 Domain reasoning mang t�nh d?a phuong

- T�c d?ng c?a `d?u th?u`, `BHYT`, `GMP`, `gia h?n s? dang k�`, ho?c `thu h?i thu?c` kh�ng th? suy ra d�ng ch? b?ng m?t prompt chung.
- M?t catalyst nh? c� th? ?nh hu?ng doanh thu, bi�n, ho?c t?c d? m? r?ng th? ph?n theo c�ch ch? domain analyst m?i hi?u.
- Peer comparison trong ng�nh du?c Vi?t Nam c?n taxonomy ri�ng d? tr�nh so s�nh sai nh�m doanh nghi?p.

### 3.3 B�i to�n kh�ng ch?p nh?n hallucination ? l?p d?nh lu?ng

- M?t h? th?ng d�ng trong equity research kh�ng du?c ph�p d? LLM �t? nghi� ra s?.
- Sai s? ? `financial facts`, `valuation`, ho?c `citations` k�o theo r?i ro ph�p l�, r?i ro uy t�n, v� l�m s?p ni?m tin v?i ngu?i d�ng t? ch?c.

### 3.4 T�nh v?n h�nh d�i h?n

- H? th?ng ph?i x? l� song song nhi?u m�, nhi?u ngu?n, nhi?u k? c�ng b?, nhi?u lo?i run.
- Workflow c� bu?c d�i, c� th? l?i gi?a ch?ng, c?n `resume`, `retry`, `checkpoint`, v� `human approval`.
- Chi ph� token tang nhanh n?u kh�ng c� `usage tracking` v� `budget guardrails`.

---

## 4. B�i to�n c?n gi?i quy?t

��y kh�ng ph?i b�i to�n �AI vi?t b�o c�o�. ��y l� b�i to�n x�y d?ng m?t `research operating system` c� kh? nang:

1. Thu th?p v� chu?n h�a d? li?u da ngu?n th�nh `canonical facts`.
2. Ki?m tra ch?t lu?ng d? li?u tru?c khi dua v�o l?p ph�n t�ch.
3. T�nh to�n d?nh lu?ng b?ng `code-first engine` thay v� d? LLM t�nh nh?m.
4. D�ng LLM cho reasoning v� narrative tr�n c�c artifact d� du?c kh�a ngu?n v� ki?m d?nh.
5. T?o b�o c�o c� `citation`, `audit trail`, `confidence`, v� `HITL approval`.
6. H? tr? `incremental recompute` khi c� t�i li?u ho?c catalyst m?i.

---

## 5. V� sao single-agent ho?c chatbot l� chua d?

### 5.1 Kh�ng t�ch du?c tr�ch nhi?m

M?t agent don l? ph?i c�ng l�c:
- ingest t�i li?u,
- chu?n h�a line item,
- l�m domain reasoning,
- d?nh gi�,
- vi?t b�o c�o,
- ki?m citation.

M� h�nh n�y l�m m? ranh gi?i gi?a `facts`, `inference`, v� `presentation`, n�n r?t kh� ki?m so�t ch?t lu?ng.

### 5.2 Kh�ng h? tr? ki?m so�t workflow

Chatbot kh�ng c� kh�i ni?m r� r�ng v?:
- `run lifecycle`,
- `idempotency`,
- `retry and resume`,
- `approval checkpoints`,
- `partial recompute`.

### 5.3 Kh�ng ph� h?p m�i tru?ng production

T? ch?c t�i ch�nh c?n:
- lineage,
- audit,
- data quality gates,
- cost governance,
- observability,
- reproducibility.

��y l� y�u c?u c?a m?t backend workflow engine, kh�ng ph?i c?a m?t giao di?n chat thu?n.

---

## 6. T?m nh�n h? th?ng

H? th?ng m?c ti�u l� m?t n?n t?ng backend theo m� h�nh:

- `API/BFF`: nh?n y�u c?u nghi�n c?u, tr? tr?ng th�i, tr? artifact.
- `Orchestration`: di?u ph?i c�c bu?c theo state machine c� checkpoint v� HITL.
- `Async workers`: ingestion, parsing, normalization, indexing, valuation, synthesis, rendering.
- `Data plane`: object store, relational facts, vector index, audit records.
- `Connector plane`: ngu?n filings, tender, BHYT, regulatory, company news.

V? m?t logic nghi�n c?u, h? th?ng v?n b�m c?u tr�c `Data-CoT -> Concept-CoT -> Thesis-CoT`, nhung tri?n khai backend ph?i t�ch r�:

- `agent role`: vai tr� suy lu?n.
- `service/module`: nang l?c k? thu?t.
- `workflow node`: bu?c ch?y trong orchestration.

Kh�ng ph?i m?i vai tr� d?u c?n tr? th�nh m?t agent d?c l?p.

---

## 7. C�c nguy�n t?c thi?t k? c?t l�i

### 7.1 Facts before narrative

- S? li?u v� valuation artifact du?c sinh b?ng code v� schema c? d?nh.
- LLM ch? du?c di?n gi?i tr�n artifact d� qua ki?m so�t.

### 7.2 Local context first

- Uu ti�n ngu?n d? li?u v� logic th? tru?ng Vi?t Nam.
- D? li?u qu?c t? ch? d�ng vai tr� tham chi?u, kh�ng ph?i n?n c?a MVP.

### 7.3 Lineage by default

- M?i fact, chunk, citation, v� report section ph?i truy ngu?c du?c v? source v� version d� d�ng.

### 7.4 Quality before persistence

- D? li?u kh�ng du?c ghi th�nh `canonical fact` n?u chua qua validation, reconciliation, v� confidence gate.

### 7.5 AI drafts, humans approve

- C�c bu?c c� r?i ro cao nhu gi? d?nh v� khuy?n ngh? cu?i ph?i c� `HITL`.

### 7.6 Budgeted intelligence

- M?i run ph?i c� gi?i h?n chi ph�, model policy, v� fallback strategy.

### 7.7 Incremental over full recompute

- Khi ch? m?t ph?n d? li?u thay d?i, h? th?ng ph?i c? g?ng invalidation c� ch?n l?c thay v� ch?y l?i to�n b? pipeline.

### 7.8 Evaluate before promote

- M?i thay d?i parser, prompt, model, ho?c retrieval policy ph?i di qua offline evaluation tru?c khi dua v�o lu?ng publish production.
- �i?m d�nh gi� t?i thi?u c?n b�m c�c tr?c: `grounding`, `accuracy`, `logicality`, `storytelling`, v� regression stability.

---

## 8. C�c pain point m� backend ph?i x? l� tr?c ti?p

### 8.1 Data pain

- Parse BCTC kh�ng ?n d?nh.
- OCR kh�ng d?ng d?u.
- Catalyst t? ngu?n c�ng khai thi?u chu?n h�a.

### 8.2 Analysis pain

- Analyst kh� gi? consistency gi?a nhi?u m�.
- R?t d? tr?n l?n facts v?i assumptions ho?c narrative.

### 8.3 Governance pain

- Thi?u audit trail.
- Kh� x�c minh ngu?n c?a m?t k?t lu?n d?nh lu?ng.
- Kh�ng c� co ch? bu?c review tru?c publish.

### 8.4 Operations pain

- Run d�i d? fail gi?a ch?ng.
- Kh� bi?t bu?c n�o g�y l?i ho?c d?i chi ph�.
- Kh� ch?y l?i ch? m?t ph?n pipeline.

---

## 9. Ph?m vi giai do?n d?u

### Trong ph?m vi

- `53` m� du?c/y t? ni�m y?t Vi?t Nam.
- `full report`, `flash memo`, `catalyst refresh`.
- D? li?u BCTC, th�ng tin ni�m y?t, catalyst t? d?u th?u/BHYT/regulatory/company news.
- �?nh gi� `DCF`, `P/E`, `EV/EBITDA`.
- Citation map v� review workflow.

### Ngo�i ph?m vi

- Auto-trading ho?c signal execution.
- Autonomous publish kh�ng qua review.
- Ph? to�n b? biotech/global pharma.
- D�ng LLM l�m ngu?n s? th?t cho s? li?u.

---

## 10. Hu?ng tri?n khai uu ti�n

1. `Foundation and data contracts`
2. `Fact ingestion and code-first valuation`
3. `RAG and citation pipeline`
4. `Orchestration and HITL`
5. `Production hardening`
6. `Agentic reasoning and thesis generation`

Tr�nh t? n�y ph?n �nh dependency tri?n khai th?c t?: c?n kh�a data contract v� fact layer tru?c, sau d� m?i ho�n thi?n grounding, orchestration, hardening production, r?i m?i d?y m?nh autonomy ? l?p thesis generation.

---

## 11. Ti�u ch� th�nh c�ng c?a problem brief

Problem brief du?c coi l� ho�n th�nh khi to�n b? team th?ng nh?t r?ng:

- D? �n l� m?t `research operating system`, kh�ng ph?i chatbot.
- `Vietnam pharma` l� ph?m vi MVP b?t bu?c.
- `code-first valuation`, `citation-first reporting`, `HITL publish`, `data quality gates`, v� `cost governance` l� c�c nguy�n t?c kh�ng du?c ph� v?.
- Ki?n tr�c backend ph?i du?c thi?t k? cho `stateful runs`, `partial recompute`, v� `production observability`.

---

## 12. K?t lu?n

Equity research cho ng�nh du?c Vi?t Nam l� b�i to�n lai gi?a `financial analysis`, `policy interpretation`, `regulatory monitoring`, v� `report production`. V� v?y h? th?ng th�nh c�ng kh�ng th? l� m?t LLM bi?t vi?t hay, m� ph?i l� m?t backend c� kh? nang qu?n l� d? li?u, reasoning, chi ph�, ki?m so�t ch?t lu?ng, v� ph� duy?t con ngu?i trong c�ng m?t workflow.
