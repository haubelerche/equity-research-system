 Harness Engineering cho AI Agents

> T�i li?u n�y chuy?n h�a n?i dung ngu?n th�nh m?t b?n m� t? c� c?u tr�c v? **Harness Engineering**.  
> M?c ti�u l� gi�p ngu?i d?c hi?u b?n ch?t, c�c th�nh ph?n k? thu?t, b�i h?c thi?t k?, v� checklist �p d?ng khi x�y d?ng AI agents ? m?c production.

---

## 1. Context

Trong giai do?n d?u c?a l�n s�ng LLM, tr?ng t�m thu?ng n?m ? **Prompt Engineering**: vi?t c�u h?i, instruction, ho?c prompt sao cho model tr? l?i t?t hon.

Sau d�, tr?ng t�m d?ch chuy?n sang **Context Engineering**: dua d�ng d? li?u, d�ng d?nh d?ng, d�ng th?i di?m v�o context window d? model c� d? th�ng tin x? l� nhi?m v?.

**Harness Engineering** m? r?ng ph?m vi hon n?a. N� kh�ng ch? h?i �prompt n�n vi?t th? n�o� hay �context n�n dua v�o ra sao�, m� h?i:

> To�n b? m�i tru?ng v?n h�nh xung quanh AI model c?n du?c thi?t k? nhu th? n�o d? agent l�m vi?c d�ng tin c?y, c� ki?m so�t, c� kh? nang t? ph?c h?i, v� �t l?p l?i l?i?

N�i c�ch kh�c, Harness Engineering l� tu duy thi?t k? h? th?ng cho AI agents.

---

## 2. �?nh nghia Harness Engineering

**Harness Engineering** l� k? thu?t x�y d?ng to�n b? l?p m�i tru?ng bao quanh m?t AI model ho?c AI agent, bao g?m:

- Tooling v� interface m� agent du?c ph�p s? d?ng.
- Quy?n truy c?p, permission, v� security boundary.
- Memory, state, v� session handoff.
- Context management.
- Feedback loop sau l?i.
- Guardrails v� quality gates.
- Co ch? ki?m d?nh, testing, evaluation.
- Multi-agent coordination.
- Workflow orchestration.
- C�ch agent tuong t�c v?i filesystem, database, API, browser, terminal, ho?c c�c c�ng c? chuy�n d?ng.

M?t c�ch di?n d?t ng?n g?n:

> Model l� th�nh ph?n suy lu?n. Harness l� m�i tru?ng quy?t d?nh model du?c nh�n th?y g�, du?c l�m g�, b? ki?m so�t ra sao, v� l?i du?c ph�t hi?n nhu th? n�o.

---

## 3. Ti?n h�a t? Prompt Engineering d?n Harness Engineering

| Giai do?n | C�u h?i trung t�m | Ph?m vi t?i uu |
|---|---|---|
| Prompt Engineering | H?i AI nhu th? n�o cho d�ng? | C�u l?nh, instruction, role, format d?u ra |
| Context Engineering | �ua th�ng tin g� cho AI d? n� tr? l?i t?t? | Context window, retrieval, t�i li?u, memory, format d? li?u |
| Harness Engineering | To�n b? h? th?ng xung quanh AI v?n h�nh ra sao? | Tools, state, permission, testing, feedback loop, workflow, multi-agent, guardrails |

V� d? so s�nh:

- **Prompt Engineering** gi?ng nhu vi?t m?t email t?t.
- **Context Engineering** gi?ng nhu d�nh k�m d�ng t�i li?u v�o email.
- **Harness Engineering** gi?ng nhu thi?t k? c? van ph�ng: quy tr�nh, c�ng c?, ngu?i ki?m duy?t, ti�u chu?n ch?t lu?ng, ph�n quy?n, luu tr?, v� co ch? s?a l?i.

---

## 4. Lu?n di?m c?t l�i

Harness Engineering d?a tr�n m?t nh?n d?nh quan tr?ng:

> Khi model d? m?nh, bottleneck kh�ng c�n ch? l� nang l?c suy lu?n c?a model, m� l� m�i tru?ng m� h? th?ng cung c?p cho model.

Trong h? th?ng agentic, c�ng m?t model c� th? cho k?t qu? r?t kh�c nhau n?u:

- Tool interface kh�c nhau.
- Context du?c c?t/n�n kh�c nhau.
- Search tr? v? qu� nhi?u ho?c qu� �t k?t qu?.
- File viewer c� ho?c kh�ng c� s? d�ng.
- Editor c� ho?c kh�ng c� linter.
- Agent c� ho?c kh�ng c� tr?ng th�i ti?n d? b?n v?ng qua nhi?u session.
- Evaluation du?c th?c thi b?i ch�nh agent l�m vi?c hay b?i m?t evaluator d?c l?p.
- Permission system ch?n ho?c cho ph�p h�nh d?ng nguy hi?m.

V� v?y, harness kh�ng ph?i ph?n ph?. Trong production agent, harness thu?ng l� ph?n quy?t d?nh d? tin c?y cu?i c�ng.

---

## 5. C�c th�nh ph?n ch�nh c?a m?t AI Agent Harness

### 5.1 Tool Design

Tool design quy?t d?nh agent c� th? h�nh d?ng nhu th? n�o.

M?t tool t?t cho agent c?n:

- C� interface r� r�ng.
- Tr? v? output ng?n, c� c?u tr�c, �t nhi?u.
- C� gi?i h?n k?t qu?.
- C� l?i r� r�ng khi input kh�ng ph� h?p.
- C� metadata ph?c v? truy v?t.
- Kh�ng �p agent x? l� qu� nhi?u d? li?u th� trong context window.
- C� permission boundary tru?c khi th?c thi h�nh d?ng c� r?i ro.

V� d?:

- Search tool kh�ng n�n tr? 10.000 k?t qu?; n�n gi?i h?n v� y�u c?u agent refine query.
- File viewer n�n c� s? d�ng d? agent edit ch�nh x�c.
- Editor n�n t�ch h?p linter/test d? ch?n l?i c� ph�p tru?c khi l?i lan sang bu?c sau.

---

### 5.2 Agent-Computer Interface

**Agent-Computer Interface**, vi?t t?t l� **ACI**, l� giao di?n gi?a AI agent v� m�i tru?ng m�y t�nh.

Tuong t? nhu **Human-Computer Interface** thi?t k? giao di?n cho con ngu?i, ACI thi?t k? giao di?n cho agent.

ACI c?n t�nh d?n c�c d?c di?m c?a LLM agents:

- X? l� th�ng tin theo chu?i token.
- Nh?y c?m v?i th? t? th�ng tin.
- C� working memory h?u h?n.
- D? b? nhi?u b?i th�ng tin kh�ng li�n quan.
- C� th? l?p l?i h�nh d?ng v� �ch n?u tool tr? v? output k�m.
- Kh�ng t? bi?t ch�nh x�c tr?ng th�i h? th?ng n?u kh�ng du?c cung c?p state r� r�ng.

Do d�, m?t ACI t?t c?n t?i uu nh?ng th? nhu:

- K�ch thu?c output c?a tool.
- Format c?a k?t qu?.
- Kh? nang d?nh v? d�ng/file/object.
- Co ch? ph?n h?i l?i.
- Co ch? gi?i h?n h�nh d?ng.
- Kh? nang resume sau khi context window thay d?i.

---

### 5.3 Context Management

Context management trong harness kh�ng ch? l� �nh?i th�m th�ng tin v�o prompt�. N� l� co ch? quy?t d?nh:

- Th�ng tin n�o lu�n du?c load.
- Th�ng tin n�o ch? load theo nhu c?u.
- L?ch s? n�o c?n n�n.
- D? li?u n�o c?n lo?i b?.
- State n�o c?n gi? qua session.
- Khi n�o c?n compact, summarize, ho?c truncate.
- C�ch tr�nh context rot khi l?ch s? qu� d�i.

M?t pattern th?c t?:

| T?ng memory | Vai tr� |
|---|---|
| Short memory | N?i dung dang x? l� trong session hi?n t?i |
| Working summary | T�m t?t ti?n d? v� quy?t d?nh d� th?c hi?n |
| Persistent project state | Plan, task board, feature status, test status |
| Long-term memory | Quy u?c, architecture decision, l?i d� g?p, fact d� x�c minh |

---

### 5.4 State Management v� Session Handoff

Nhi?u project th?c t? kh�ng th? ho�n th�nh trong m?t context window. V� v?y harness c?n thi?t k? state b?n v?ng.

State management c?n tr? l?i:

- Agent dang l�m d?n d�u?
- Feature n�o d� xong?
- Feature n�o chua xong?
- Test n�o d� pass?
- Bug n�o c�n m??
- File n�o d� s?a?
- Quy?t d?nh ki?n tr�c n�o d� du?c ch?t?
- L?n sau agent resume th� ph?i d?c g� tru?c?

C�c artifact h?u �ch:

- `plan.md`
- `progress.md`
- `task_board.json`
- `architecture_decisions.md`
- `known_issues.md`
- `eval_report.md`
- `handoff_summary.md`

M?t di?m quan tr?ng: v?i c�c tr?ng th�i c?n t�nh m�y m�c, JSON thu?ng an to�n hon Markdown v� c?u tr�c c?ng hon v� �t b? model t? � di?n gi?i.

---

### 5.5 Feedback Loops

Nguy�n t?c trung t�m c?a Harness Engineering:

> M?i khi agent m?c l?i, h? th?ng ph?i du?c c?i ti?n d? l?i d� kh� ho?c kh�ng th? l?p l?i.

Feedback loop t?t g?m:

1. Ph�t hi?n l?i.
2. Ph�n lo?i l?i.
3. X�c d?nh nguy�n nh�n g?c.
4. Th�m rule, test, tool constraint, ho?c guardrail.
5. Ch?y regression test.
6. Ghi l?i l?i v�o knowledge base ho?c harness policy.

V� d?:

| L?i agent | C?i ti?n harness |
|---|---|
| Agent s?a sai d�ng code | File viewer c� line number v� editor d�ng range ch�nh x�c |
| Agent t?o syntax error | Editor t? ch?y linter tru?c khi apply |
| Agent search qu� r?ng | Search tool gi?i h?n k?t qu? v� y�u c?u refine query |
| Agent tuy�n b? ho�n th�nh qu� s?m | Quality gate y�u c?u test/eval/report tru?c khi done |
| Agent hallucinate ngu?n d? li?u | Source verification gate b?t bu?c c� citation v� provenance |

---

### 5.6 Guardrails v� Permission System

Harness c?n t�ch bi?t hai th?:

- Model d? xu?t mu?n l�m g�.
- Tool system quy?t d?nh h�nh d?ng d� c� du?c ph�p th?c thi hay kh�ng.

��y l� nguy�n t?c ki?n tr�c quan tr?ng. Kh�ng n�n d? model t? quy?t d?nh to�n b? quy?n h�nh d?ng.

Permission system c?n bao ph?:

- File read/write.
- Shell command.
- Database mutation.
- Network access.
- API key/secret access.
- External side effects.
- Email, calendar, payment, ho?c h�nh d?ng thay d?i tr?ng th�i th?t.
- Delete, overwrite, deploy, publish.

M?t thi?t k? an to�n thu?ng c�:

- Tool-level permission.
- Command validation.
- Dry-run mode.
- Human approval gate.
- Audit log.
- Rollback strategy.
- Least-privilege access.

---

### 5.7 Quality Gates v� Evaluation

Quality gate l� co ch? ngan agent �declare victory� qu� s?m.

M?t h? th?ng harness t?t c?n ki?m tra:

- Output c� d�ng format kh�ng?
- S? li?u c� kh?p source kh�ng?
- Code c� pass test kh�ng?
- Claim c� citation kh�ng?
- Report c� d? section kh�ng?
- T�nh to�n c� d�ng formula kh�ng?
- Tool call c� audit trail kh�ng?
- Risk ho?c uncertainty c� du?c n�u r� kh�ng?

Evaluation c� th? chia th�nh:

| Lo?i evaluation | M?c ti�u |
|---|---|
| Format evaluation | �?m b?o output d�ng schema/template |
| Functional evaluation | �?m b?o h? th?ng ch?y d�ng |
| Factual evaluation | �?m b?o th�ng tin c� ngu?n x�c minh |
| Reasoning evaluation | �?m b?o l?p lu?n kh�ng m�u thu?n |
| Regression evaluation | �?m b?o l?i cu kh�ng t�i xu?t hi?n |
| Human evaluation | Ki?m d?nh c�c ti�u ch� ch? quan ho?c high-stakes |

---

### 5.8 Multi-Agent Coordination

Multi-agent kh�ng ch? l� �nhi?u agent c�ng ch?y�. N� c?n harness di?u ph?i r� r�ng.

C�c vai tr� ph? bi?n:

| Agent | Vai tr� |
|---|---|
| Planner | Chuy?n y�u c?u mo h? th�nh spec/task plan |
| Researcher | Thu th?p v� x�c minh th�ng tin |
| Generator | T?o code/report/artifact |
| Evaluator | Ki?m d?nh output d?c l?p |
| Auditor | Ki?m tra provenance, r?i ro, compliance |
| Supervisor | �i?u ph?i workflow v� quy?t d?nh handoff |

V?n d? thu?ng g?p:

- Agent l�m tr�ng vi?c.
- Agent kh�ng bi?t tr?ng th�i c?a nhau.
- Agent overwrite output c?a nhau.
- Agent tin nh?m k?t lu?n c?a agent kh�c.
- Kh�ng c� source-of-truth chung.
- Kh�ng c� quality gate gi?a c�c bu?c.

Harness c?n c�:

- Shared task board.
- Dependency graph.
- Handoff protocol.
- Role boundary.
- Artifact ownership.
- Evaluation checkpoint.
- Conflict resolution rule.

---

## 6. B�i h?c t? SWE-agent

Theo n?i dung ngu?n, SWE-agent minh h?a r?ng ch? c?n thi?t k? t?t interface gi?a agent v� m�i tru?ng m�y t�nh cung c� th? c?i thi?n m?nh hi?u su?t.

C�c th�nh ph?n d�ng ch� �:

### 6.1 Search gi?i h?n k?t qu?

V?n d?:

- Search qu� r?ng tr? v? qu� nhi?u k?t qu?.
- Agent b? ng?p trong noise.
- Context window b? l?p d?y b?i th�ng tin kh�ng li�n quan.
- Agent ti?p t?c search lan man v� m?t d?nh hu?ng.

Gi?i ph�p:

- Gi?i h?n s? k?t qu?.
- N?u vu?t ngu?ng, y�u c?u agent refine query.
- �p agent c? th? h�a m?c ti�u t�m ki?m.

Thi?t k? n�y gi�p gi?m context noise v� tang precision.

---

### 6.2 File viewer c� s? d�ng

V?n d?:

- Agent kh� d?nh v? do?n c?n s?a.
- Kh�ng c� line number khi?n edit d? l?ch.
- Agent ph?i d�ng working memory d? d?m d�ng.

Gi?i ph�p:

- Hi?n th? file theo window v?a d?.
- G?n s? d�ng v�o t?ng d�ng.
- Cho ph�p edit theo range c? th?.

�i?u n�y l�m gi?m l?i d?nh v? v� tang kh? nang s?a code ch�nh x�c.

---

### 6.3 Editor t�ch h?p linter

V?n d?:

- Agent t?o syntax error.
- Sau d� ch?y test, test fail ? nhi?u noi.
- Agent m?t nhi?u bu?c debug l?i ph? do ch�nh l?n edit tru?c t?o ra.

Gi?i ph�p:

- Sau m?i edit, t? ch?y linter.
- N?u c� syntax error, reject edit ngay.
- Tr? l?i r� r�ng cho agent.

��y l� m?t v� d? di?n h�nh c?a feedback loop c?c b?: b?t l?i c�ng g?n di?m ph�t sinh c�ng t?t.

---

### 6.4 Context compaction

V?n d?:

- L?ch s? tool call d�i l�m context b? nhi?u.
- Agent qu�n m?c ti�u ch�nh.
- Context rot l�m ch?t lu?ng suy lu?n gi?m.

Gi?i ph�p:

- N�n l?ch s? cu th�nh summary ng?n.
- Gi? l?i tr?ng th�i c?n thi?t.
- Lo?i b? command output kh�ng c�n gi� tr?.

---

## 7. B�i h?c t? Anthropic v? Long-Horizon Agent Workflows

Ngu?n m� t? hai failure modes ph? bi?n trong c�c task ph?n m?m d�i hoi.

### 7.1 Failure Mode 1: L�m qu� nhi?u m?t l�c

Agent nh?n y�u c?u l?n r?i c? implement nhi?u ph?n c�ng l�c.

H? qu?:

- Feature chua ho�n ch?nh.
- Context window h?t gi?a ch?ng.
- Session sau kh�ng bi?t tr?ng th�i th?t.
- Codebase d? dang v� thi?u t�i li?u.

Harness c?n �p workflow th�nh c�c sprint nh?:

1. Ch?n m?t task.
2. Implement.
3. Test.
4. Commit.
5. Update progress.
6. Handoff.

---

### 7.2 Failure Mode 2: Tuy�n b? ho�n th�nh qu� s?m

Agent nh�n th?y m?t ph?n code d� t?n t?i v� suy lu?n r?ng project d� xong.

Nguy�n nh�n:

- Kh�ng c� d?nh nghia �done� r� r�ng.
- Kh�ng c� checklist.
- Kh�ng c� evaluator d?c l?p.
- Kh�ng c� task board machine-readable.

Gi?i ph�p:

- T?o feature list r� r�ng.
- M?i feature c� tr?ng th�i pass/fail.
- C� quality gate tru?c khi d�ng task.
- C� evaluator ki?m tra d?c l?p.

---

### 7.3 Ki?n tr�c Initializer + Coding Agent

M?t pattern du?c n�u trong ngu?n:

| Agent | Nhi?m v? |
|---|---|
| Initializer | Setup m�i tru?ng, t?o plan, t?o feature list, t?o progress file, commit ban d?u |
| Coding Agent | M?i session x? l� m?t feature, test, commit, c?p nh?t progress |

Pattern n�y gi?i quy?t v?n d? long-horizon b?ng c�ch bi?n project l?n th�nh chu?i task c� tr?ng th�i b?n v?ng.

---

### 7.4 Ki?n tr�c Planner + Generator + Evaluator

Pattern ba agent:

| Agent | Nhi?m v? |
|---|---|
| Planner | M? r?ng y�u c?u ng?n th�nh product spec |
| Generator | Build theo sprint, t?ng feature m?t |
| Evaluator | Test nhu user th?t, ch?m theo ti�u ch� d?nh nghia tru?c |

�i?m quan tr?ng: evaluator n�n d?c l?p v?i generator d? gi?m self-evaluation bias.

---

## 8. B�i h?c t? Claude Code, ClaudeKit v� GoClaw theo n?i dung ngu?n

> Luu �: ph?n n�y t�m t?t c�c quan s�t du?c n�u trong ngu?n. N?u d�ng trong t�i li?u h?c thu?t ho?c b�o c�o ch�nh th?c, c�c case study n�y c?n du?c ki?m ch?ng b?ng ngu?n g?c d?c l?p.

### 8.1 Claude Code: Harness cho coding agent

C�c pattern du?c n�u:

- Nhi?u c?p d? context compaction.
- Memory nhi?u t?ng.
- Session transcript c� th? search.
- Subagent theo m� h�nh fork, teammate, worktree.
- Tool permission ri�ng bi?t.
- Validation nhi?u l?p cho command nguy hi?m.
- Heuristic r? nhu regex d? ph�t hi?n t�nh hu?ng don gi?n thay v� g?i LLM.

B�i h?c k? thu?t:

> Kh�ng ph?i m?i quy?t d?nh trong agentic system d?u c?n LLM. Harness t?t n�n d�ng c�ng c? r? nh?t, nhanh nh?t, d�ng tin nh?t cho t?ng lo?i quy?t d?nh.

---

### 8.2 ClaudeKit: Harness tr�n harness

Ngu?n m� t? ClaudeKit nhu m?t l?p workflow v� governance ph�a tr�n Claude Code.

C�c l?p ch�nh:

1. Structured workflows.
2. Persistent state.
3. Quality gates.
4. Multi-agent coordination.
5. Progressive disclosure.

� tu?ng quan tr?ng:

> N?u agent g?c d� c� harness, v?n c� th? th�m m?t harness c?p cao hon d? chu?n h�a quy tr�nh, ki?m so�t task, v� qu?n l� ch?t lu?ng.

---

### 8.3 GoClaw: Harness cho production agents

C�c y?u t? du?c n�u:

- Multi-agent teams.
- Task board c� dependency.
- Multi-tenant isolation.
- Security nhi?u l?p.
- Hooks system.
- Multi-channel communication.
- Multi-provider LLM.
- Skills/MCP.
- Context pruning.
- Persistent instructions.

B�i h?c:

> Production agent harness kh�ng ch? l� prompt v� tools. N� c?n architecture, security, observability, workflow, v� kh? nang v?n h�nh nhi?u tenant ho?c nhi?u k�nh.

---

## 9. Harness Engineering vs Context Engineering

C� nhi?u c�ch ph�n d?nh, nhung trong t�i li?u n�y c� th? d�ng c�ch hi?u th?c d?ng sau:

### 9.1 Context Engineering

T?p trung v�o c�u h?i:

> Agent c?n nh�n th?y g�?

Bao g?m:

- Retrieval.
- Prompt assembly.
- Memory injection.
- Chunking.
- Ranking.
- Summarization.
- Context compression.
- Data formatting.

### 9.2 Harness Engineering

T?p trung v�o c�u h?i:

> To�n b? h? th?ng cho ph�p agent v?n h�nh nhu th? n�o?

Bao g?m Context Engineering, nhung c�n m? r?ng sang:

- Tool interface.
- Permission.
- Workflow.
- State.
- Evaluation.
- Feedback loops.
- Multi-agent coordination.
- Security.
- Observability.
- Human approval.
- Error recovery.
- Production deployment.

N�i ng?n g?n:

> Context Engineering quy?t d?nh agent th?y g�.  
> Harness Engineering quy?t d?nh agent th?y g�, l�m g�, b? ki?m so�t th? n�o, v� du?c s?a l?i ra sao.

---

## 10. Checklist thi?t k? Harness cho AI Agent Production

### 10.1 Tool Interface

- [ ] Tool c� input/output schema r� r�ng.
- [ ] Tool output c� gi?i h?n k�ch thu?c.
- [ ] Tool tr? l?i c� c?u tr�c.
- [ ] Tool c� metadata ph?c v? audit.
- [ ] Tool c� permission boundary.
- [ ] Tool c� dry-run n?u h�nh d?ng c� r?i ro.
- [ ] Tool tr�nh tr? d? li?u th� qu� d�i v�o context.

### 10.2 Context Management

- [ ] C� policy load context theo nhu c?u.
- [ ] C� co ch? compact/summarize l?ch s?.
- [ ] C� ph�n t?ng memory.
- [ ] C� persistent state ngo�i context window.
- [ ] C� c�ch resume session r� r�ng.
- [ ] C� co ch? lo?i b? th�ng tin cu ho?c nhi?u.

### 10.3 State v� Handoff

- [ ] C� task board.
- [ ] C� tr?ng th�i pass/fail cho t?ng task.
- [ ] C� file handoff sau m?i session.
- [ ] C� ghi l?i quy?t d?nh ki?n tr�c.
- [ ] C� known issues.
- [ ] C� dependency gi?a tasks.

### 10.4 Quality Gates

- [ ] C� test t? d?ng.
- [ ] C� schema validation.
- [ ] C� factuality/provenance check.
- [ ] C� regression test cho l?i d� g?p.
- [ ] C� evaluator d?c l?p v?i generator.
- [ ] Kh�ng cho ph�p agent t? tuy�n b? done n?u chua qua gate.

### 10.5 Security

- [ ] Least-privilege access.
- [ ] Command validation.
- [ ] Human approval cho h�nh d?ng nguy hi?m.
- [ ] Audit log.
- [ ] Secret masking.
- [ ] Rollback mechanism.
- [ ] Policy r� cho file/database/network mutation.

### 10.6 Observability

- [ ] Log tool calls.
- [ ] Log input/output quan tr?ng.
- [ ] Log reasoning summary ho?c decision trace ? m?c an to�n.
- [ ] Track token usage.
- [ ] Track latency.
- [ ] Track cost.
- [ ] Track failure categories.
- [ ] C� dashboard ho?c report d?nh k?.

---

## 11. Anti-Patterns ph? bi?n

| Anti-pattern | H? qu? |
|---|---|
| Ch? t?i uu prompt | Kh�ng gi?i quy?t l?i h? th?ng l?p l?i |
| Tool tr? output qu� d�i | Context noise, suy lu?n k�m |
| Kh�ng c� state b?n v?ng | M?t ti?n d? qua session |
| Kh�ng c� definition of done | Agent tuy�n b? xong qu� s?m |
| Agent t? eval output c?a ch�nh m�nh | Bias, b? s�t l?i |
| Kh�ng c� source verification | Hallucination ho?c d? li?u kh�ng ki?m ch?ng |
| Kh�ng c� permission boundary | R?i ro b?o m?t v� side effect ngo�i � mu?n |
| Kh�ng c� regression test | L?i cu t�i di?n |
| Multi-agent kh�ng c� coordination layer | Agent l�m tr�ng, conflict, overwrite |

---

## 12. Minimal Harness Architecture

M?t ki?n tr�c harness t?i thi?u cho AI coding/research agent c� th? g?m:

```text
User Request
    |
    v
Planner / Supervisor
    |
    v
Task Board + State Store
    |
    +--> Research Tools
    +--> Code Tools
    +--> Data Tools
    +--> Browser / Search Tools
    +--> File System Tools
    |
    v
Generator Agent
    |
    v
Quality Gates
    |
    +--> Schema Validation
    +--> Unit Tests
    +--> Linting
    +--> Provenance Check
    +--> Evaluation Rubric
    |
    v
Evaluator / Auditor
    |
    v
Final Artifact + Handoff Summary + Audit Log
```

---

## 13. Harness Maturity Model

| Level | M?c d? | �?c di?m |
|---|---|---|
| L0 | Prompt-only | Ch? d�ng prompt, kh�ng c� tool/state/eval |
| L1 | Tool-enabled | Agent c� tools nhung thi?u ki?m so�t |
| L2 | Structured tools | Tool c� schema, output gi?i h?n, l?i r� r�ng |
| L3 | Persistent state | C� task board, progress, session handoff |
| L4 | Quality-gated | C� test, eval, validation, regression |
| L5 | Secure harness | Permission, audit, dry-run, approval, rollback |
| L6 | Multi-agent harness | Planner/Generator/Evaluator/Auditor c� coordination |
| L7 | Production harness | Observability, cost control, tenant isolation, deployment governance |

---

## 14. �p d?ng th?c t?

Khi x�y d?ng m?t AI agent system, n�n chuy?n t? c�u h?i:

> �Prompt n�o l�m agent th�ng minh hon?�

sang c�u h?i:

> �M�i tru?ng n�o khi?n agent kh� m?c l?i hon?�

M?t s? h�nh d?ng c? th?:

1. Ghi l?i m?i l?i agent t?ng m?c.
2. Ph�n lo?i l?i th�nh nh�m: retrieval, tool, reasoning, state, permission, evaluation, UX.
3. V?i m?i l?i, th�m m?t r�o ch?n k? thu?t:
   - Test.
   - Validator.
   - Tool constraint.
   - Better interface.
   - State artifact.
   - Evaluation gate.
   - Permission rule.
4. Bi?n l?i th�nh regression case.
5. Kh�ng d? agent ph? thu?c v�o tr� nh? trong context window cho c�c state quan tr?ng.
6. Kh�ng cho agent t? d�nh gi� k?t qu? cu?i c�ng n?u task c� r?i ro cao.
7. Uu ti�n c�ng c? deterministic, r?, nhanh cho c�c t�c v? kh�ng c?n reasoning.

---

## 15. K?t lu?n

Harness Engineering l� c�ch nh�n AI agents nhu m?t h? th?ng ph?n m?m ho�n ch?nh, kh�ng ph?i ch? l� m?t model du?c b?c b?i prompt.

Tu duy c?t l�i:

> Model sinh ra suy lu?n.  
> Harness gi?i h?n, d?nh hu?ng, ki?m ch?ng, v� v?n h�nh suy lu?n d�.

Trong m�i tru?ng production, harness c?n ch?u tr�ch nhi?m cho:

- �? tin c?y.
- T�nh l?p l?i.
- Kh? nang ki?m ch?ng.
- B?o m?t.
- Qu?n l� context.
- Qu?n l� tr?ng th�i.
- Ch?t lu?ng d?u ra.
- Kh? nang ph?c h?i sau l?i.
- Kh? nang m? r?ng sang workflow d�i v� multi-agent.

V� v?y, n?u m?c ti�u l� x�y d?ng AI agents c� th? d�ng th?t, Harness Engineering kh�ng ph?i ph?n trang tr�. N� l� l?p h? th?ng quy?t d?nh agent c� th? di t? demo sang production hay kh�ng.
