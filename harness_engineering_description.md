# Harness Engineering cho AI Agents

> Tài liệu này chuyển hóa nội dung nguồn thành một bản mô tả có cấu trúc về **Harness Engineering**.  
> Mục tiêu là giúp người đọc hiểu bản chất, các thành phần kỹ thuật, bài học thiết kế, và checklist áp dụng khi xây dựng AI agents ở mức production.

---

## 1. Context

Trong giai đoạn đầu của làn sóng LLM, trọng tâm thường nằm ở **Prompt Engineering**: viết câu hỏi, instruction, hoặc prompt sao cho model trả lời tốt hơn.

Sau đó, trọng tâm dịch chuyển sang **Context Engineering**: đưa đúng dữ liệu, đúng định dạng, đúng thời điểm vào context window để model có đủ thông tin xử lý nhiệm vụ.

**Harness Engineering** mở rộng phạm vi hơn nữa. Nó không chỉ hỏi “prompt nên viết thế nào” hay “context nên đưa vào ra sao”, mà hỏi:

> Toàn bộ môi trường vận hành xung quanh AI model cần được thiết kế như thế nào để agent làm việc đúng, tin cậy, có kiểm soát, có khả năng tự phục hồi, và ít lặp lại lỗi?

Nói cách khác, Harness Engineering là tư duy thiết kế hệ thống cho AI agents.

---

## 2. Định nghĩa Harness Engineering

**Harness Engineering** là kỹ thuật xây dựng toàn bộ lớp môi trường bao quanh một AI model hoặc AI agent, bao gồm:

- Tooling và interface mà agent được phép sử dụng.
- Quyền truy cập, permission, và security boundary.
- Memory, state, và session handoff.
- Context management.
- Feedback loop sau lỗi.
- Guardrails và quality gates.
- Cơ chế kiểm định, testing, evaluation.
- Multi-agent coordination.
- Workflow orchestration.
- Cách agent tương tác với filesystem, database, API, browser, terminal, hoặc các công cụ chuyên dụng.

Một cách diễn đạt ngắn gọn:

> Model là thành phần suy luận. Harness là môi trường quyết định model được nhìn thấy gì, được làm gì, bị kiểm soát ra sao, và lỗi được phát hiện như thế nào.

---

## 3. Tiến hóa từ Prompt Engineering đến Harness Engineering

| Giai đoạn | Câu hỏi trung tâm | Phạm vi tối ưu |
|---|---|---|
| Prompt Engineering | Hỏi AI như thế nào cho đúng? | Câu lệnh, instruction, role, format đầu ra |
| Context Engineering | Đưa thông tin gì cho AI để nó trả lời tốt? | Context window, retrieval, tài liệu, memory, format dữ liệu |
| Harness Engineering | Toàn bộ hệ thống xung quanh AI vận hành ra sao? | Tools, state, permission, testing, feedback loop, workflow, multi-agent, guardrails |

Ví dụ so sánh:

- **Prompt Engineering** giống như viết một email tốt.
- **Context Engineering** giống như đính kèm đúng tài liệu vào email.
- **Harness Engineering** giống như thiết kế cả văn phòng: quy trình, công cụ, người kiểm duyệt, tiêu chuẩn chất lượng, phân quyền, lưu trữ, và cơ chế sửa lỗi.

---

## 4. Luận điểm cốt lõi

Harness Engineering dựa trên một nhận định quan trọng:

> Khi model đủ mạnh, bottleneck không còn chỉ là năng lực suy luận của model, mà là môi trường mà hệ thống cung cấp cho model.

Trong hệ thống agentic, cùng một model có thể cho kết quả rất khác nhau nếu:

- Tool interface khác nhau.
- Context được cắt/nén khác nhau.
- Search trả về quá nhiều hoặc quá ít kết quả.
- File viewer có hoặc không có số dòng.
- Editor có hoặc không có linter.
- Agent có hoặc không có trạng thái tiến độ bền vững qua nhiều session.
- Evaluation được thực thi bởi chính agent làm việc hay bởi một evaluator độc lập.
- Permission system chặn hoặc cho phép hành động nguy hiểm.

Vì vậy, harness không phải phần phụ. Trong production agent, harness thường là phần quyết định độ tin cậy cuối cùng.

---

## 5. Các thành phần chính của một AI Agent Harness

### 5.1 Tool Design

Tool design quyết định agent có thể hành động như thế nào.

Một tool tốt cho agent cần:

- Có interface rõ ràng.
- Trả về output ngắn, có cấu trúc, ít nhiễu.
- Có giới hạn kết quả.
- Có lỗi rõ ràng khi input không phù hợp.
- Có metadata phục vụ truy vết.
- Không ép agent xử lý quá nhiều dữ liệu thô trong context window.
- Có permission boundary trước khi thực thi hành động có rủi ro.

Ví dụ:

- Search tool không nên trả 10.000 kết quả; nên giới hạn và yêu cầu agent refine query.
- File viewer nên có số dòng để agent edit chính xác.
- Editor nên tích hợp linter/test để chặn lỗi cú pháp trước khi lỗi lan sang bước sau.

---

### 5.2 Agent-Computer Interface

**Agent-Computer Interface**, viết tắt là **ACI**, là giao diện giữa AI agent và môi trường máy tính.

Tương tự như **Human-Computer Interface** thiết kế giao diện cho con người, ACI thiết kế giao diện cho agent.

ACI cần tính đến các đặc điểm của LLM agents:

- Xử lý thông tin theo chuỗi token.
- Nhạy cảm với thứ tự thông tin.
- Có working memory hữu hạn.
- Dễ bị nhiễu bởi thông tin không liên quan.
- Có thể lặp lại hành động vô ích nếu tool trả về output kém.
- Không tự biết chính xác trạng thái hệ thống nếu không được cung cấp state rõ ràng.

Do đó, một ACI tốt cần tối ưu những thứ như:

- Kích thước output của tool.
- Format của kết quả.
- Khả năng định vị dòng/file/object.
- Cơ chế phản hồi lỗi.
- Cơ chế giới hạn hành động.
- Khả năng resume sau khi context window thay đổi.

---

### 5.3 Context Management

Context management trong harness không chỉ là “nhồi thêm thông tin vào prompt”. Nó là cơ chế quyết định:

- Thông tin nào luôn được load.
- Thông tin nào chỉ load theo nhu cầu.
- Lịch sử nào cần nén.
- Dữ liệu nào cần loại bỏ.
- State nào cần giữ qua session.
- Khi nào cần compact, summarize, hoặc truncate.
- Cách tránh context rot khi lịch sử quá dài.

Một pattern thực tế:

| Tầng memory | Vai trò |
|---|---|
| Short memory | Nội dung đang xử lý trong session hiện tại |
| Working summary | Tóm tắt tiến độ và quyết định đã thực hiện |
| Persistent project state | Plan, task board, feature status, test status |
| Long-term memory | Quy ước, architecture decision, lỗi đã gặp, fact đã xác minh |

---

### 5.4 State Management và Session Handoff

Nhiều project thực tế không thể hoàn thành trong một context window. Vì vậy harness cần thiết kế state bền vững.

State management cần trả lời:

- Agent đang làm đến đâu?
- Feature nào đã xong?
- Feature nào chưa xong?
- Test nào đã pass?
- Bug nào còn mở?
- File nào đã sửa?
- Quyết định kiến trúc nào đã được chốt?
- Lần sau agent resume thì phải đọc gì trước?

Các artifact hữu ích:

- `plan.md`
- `progress.md`
- `task_board.json`
- `architecture_decisions.md`
- `known_issues.md`
- `eval_report.md`
- `handoff_summary.md`

Một điểm quan trọng: với các trạng thái cần tính máy móc, JSON thường an toàn hơn Markdown vì cấu trúc cứng hơn và ít bị model tự ý diễn giải.

---

### 5.5 Feedback Loops

Nguyên tắc trung tâm của Harness Engineering:

> Mỗi khi agent mắc lỗi, hệ thống phải được cải tiến để lỗi đó khó hoặc không thể lặp lại.

Feedback loop tốt gồm:

1. Phát hiện lỗi.
2. Phân loại lỗi.
3. Xác định nguyên nhân gốc.
4. Thêm rule, test, tool constraint, hoặc guardrail.
5. Chạy regression test.
6. Ghi lại lỗi vào knowledge base hoặc harness policy.

Ví dụ:

| Lỗi agent | Cải tiến harness |
|---|---|
| Agent sửa sai dòng code | File viewer có line number và editor dùng range chính xác |
| Agent tạo syntax error | Editor tự chạy linter trước khi apply |
| Agent search quá rộng | Search tool giới hạn kết quả và yêu cầu refine query |
| Agent tuyên bố hoàn thành quá sớm | Quality gate yêu cầu test/eval/report trước khi done |
| Agent hallucinate nguồn dữ liệu | Source verification gate bắt buộc có citation và provenance |

---

### 5.6 Guardrails và Permission System

Harness cần tách biệt hai thứ:

- Model đề xuất muốn làm gì.
- Tool system quyết định hành động đó có được phép thực thi hay không.

Đây là nguyên tắc kiến trúc quan trọng. Không nên để model tự quyết định toàn bộ quyền hành động.

Permission system cần bao phủ:

- File read/write.
- Shell command.
- Database mutation.
- Network access.
- API key/secret access.
- External side effects.
- Email, calendar, payment, hoặc hành động thay đổi trạng thái thật.
- Delete, overwrite, deploy, publish.

Một thiết kế an toàn thường có:

- Tool-level permission.
- Command validation.
- Dry-run mode.
- Human approval gate.
- Audit log.
- Rollback strategy.
- Least-privilege access.

---

### 5.7 Quality Gates và Evaluation

Quality gate là cơ chế ngăn agent “declare victory” quá sớm.

Một hệ thống harness tốt cần kiểm tra:

- Output có đúng format không?
- Số liệu có khớp source không?
- Code có pass test không?
- Claim có citation không?
- Report có đủ section không?
- Tính toán có đúng formula không?
- Tool call có audit trail không?
- Risk hoặc uncertainty có được nêu rõ không?

Evaluation có thể chia thành:

| Loại evaluation | Mục tiêu |
|---|---|
| Format evaluation | Đảm bảo output đúng schema/template |
| Functional evaluation | Đảm bảo hệ thống chạy đúng |
| Factual evaluation | Đảm bảo thông tin có nguồn xác minh |
| Reasoning evaluation | Đảm bảo lập luận không mâu thuẫn |
| Regression evaluation | Đảm bảo lỗi cũ không tái xuất hiện |
| Human evaluation | Kiểm định các tiêu chí chủ quan hoặc high-stakes |

---

### 5.8 Multi-Agent Coordination

Multi-agent không chỉ là “nhiều agent cùng chạy”. Nó cần harness điều phối rõ ràng.

Các vai trò phổ biến:

| Agent | Vai trò |
|---|---|
| Planner | Chuyển yêu cầu mơ hồ thành spec/task plan |
| Researcher | Thu thập và xác minh thông tin |
| Generator | Tạo code/report/artifact |
| Evaluator | Kiểm định output độc lập |
| Auditor | Kiểm tra provenance, rủi ro, compliance |
| Supervisor | Điều phối workflow và quyết định handoff |

Vấn đề thường gặp:

- Agent làm trùng việc.
- Agent không biết trạng thái của nhau.
- Agent overwrite output của nhau.
- Agent tin nhầm kết luận của agent khác.
- Không có source-of-truth chung.
- Không có quality gate giữa các bước.

Harness cần có:

- Shared task board.
- Dependency graph.
- Handoff protocol.
- Role boundary.
- Artifact ownership.
- Evaluation checkpoint.
- Conflict resolution rule.

---

## 6. Bài học từ SWE-agent

Theo nội dung nguồn, SWE-agent minh họa rằng chỉ cần thiết kế tốt interface giữa agent và môi trường máy tính cũng có thể cải thiện mạnh hiệu suất.

Các thành phần đáng chú ý:

### 6.1 Search giới hạn kết quả

Vấn đề:

- Search quá rộng trả về quá nhiều kết quả.
- Agent bị ngập trong noise.
- Context window bị lấp đầy bởi thông tin không liên quan.
- Agent tiếp tục search lan man và mất định hướng.

Giải pháp:

- Giới hạn số kết quả.
- Nếu vượt ngưỡng, yêu cầu agent refine query.
- Ép agent cụ thể hóa mục tiêu tìm kiếm.

Thiết kế này giúp giảm context noise và tăng precision.

---

### 6.2 File viewer có số dòng

Vấn đề:

- Agent khó định vị đoạn cần sửa.
- Không có line number khiến edit dễ lệch.
- Agent phải dùng working memory để đếm dòng.

Giải pháp:

- Hiển thị file theo window vừa đủ.
- Gắn số dòng vào từng dòng.
- Cho phép edit theo range cụ thể.

Điều này làm giảm lỗi định vị và tăng khả năng sửa code chính xác.

---

### 6.3 Editor tích hợp linter

Vấn đề:

- Agent tạo syntax error.
- Sau đó chạy test, test fail ở nhiều nơi.
- Agent mất nhiều bước debug lỗi phụ do chính lần edit trước tạo ra.

Giải pháp:

- Sau mỗi edit, tự chạy linter.
- Nếu có syntax error, reject edit ngay.
- Trả lỗi rõ ràng cho agent.

Đây là một ví dụ điển hình của feedback loop cục bộ: bắt lỗi càng gần điểm phát sinh càng tốt.

---

### 6.4 Context compaction

Vấn đề:

- Lịch sử tool call dài làm context bị nhiễu.
- Agent quên mục tiêu chính.
- Context rot làm chất lượng suy luận giảm.

Giải pháp:

- Nén lịch sử cũ thành summary ngắn.
- Giữ lại trạng thái cần thiết.
- Loại bỏ command output không còn giá trị.

---

## 7. Bài học từ Anthropic về Long-Horizon Agent Workflows

Nguồn mô tả hai failure modes phổ biến trong các task phần mềm dài hơi.

### 7.1 Failure Mode 1: Làm quá nhiều một lúc

Agent nhận yêu cầu lớn rồi cố implement nhiều phần cùng lúc.

Hệ quả:

- Feature chưa hoàn chỉnh.
- Context window hết giữa chừng.
- Session sau không biết trạng thái thật.
- Codebase dở dang và thiếu tài liệu.

Harness cần ép workflow thành các sprint nhỏ:

1. Chọn một task.
2. Implement.
3. Test.
4. Commit.
5. Update progress.
6. Handoff.

---

### 7.2 Failure Mode 2: Tuyên bố hoàn thành quá sớm

Agent nhìn thấy một phần code đã tồn tại và suy luận rằng project đã xong.

Nguyên nhân:

- Không có định nghĩa “done” rõ ràng.
- Không có checklist.
- Không có evaluator độc lập.
- Không có task board machine-readable.

Giải pháp:

- Tạo feature list rõ ràng.
- Mỗi feature có trạng thái pass/fail.
- Có quality gate trước khi đóng task.
- Có evaluator kiểm tra độc lập.

---

### 7.3 Kiến trúc Initializer + Coding Agent

Một pattern được nêu trong nguồn:

| Agent | Nhiệm vụ |
|---|---|
| Initializer | Setup môi trường, tạo plan, tạo feature list, tạo progress file, commit ban đầu |
| Coding Agent | Mỗi session xử lý một feature, test, commit, cập nhật progress |

Pattern này giải quyết vấn đề long-horizon bằng cách biến project lớn thành chuỗi task có trạng thái bền vững.

---

### 7.4 Kiến trúc Planner + Generator + Evaluator

Pattern ba agent:

| Agent | Nhiệm vụ |
|---|---|
| Planner | Mở rộng yêu cầu ngắn thành product spec |
| Generator | Build theo sprint, từng feature một |
| Evaluator | Test như user thật, chấm theo tiêu chí định nghĩa trước |

Điểm quan trọng: evaluator nên độc lập với generator để giảm self-evaluation bias.

---

## 8. Bài học từ Claude Code, ClaudeKit và GoClaw theo nội dung nguồn

> Lưu ý: phần này tóm tắt các quan sát được nêu trong nguồn. Nếu dùng trong tài liệu học thuật hoặc báo cáo chính thức, các case study này cần được kiểm chứng bằng nguồn gốc độc lập.

### 8.1 Claude Code: Harness cho coding agent

Các pattern được nêu:

- Nhiều cấp độ context compaction.
- Memory nhiều tầng.
- Session transcript có thể search.
- Subagent theo mô hình fork, teammate, worktree.
- Tool permission riêng biệt.
- Validation nhiều lớp cho command nguy hiểm.
- Heuristic rẻ như regex để phát hiện tình huống đơn giản thay vì gọi LLM.

Bài học kỹ thuật:

> Không phải mọi quyết định trong agentic system đều cần LLM. Harness tốt nên dùng công cụ rẻ nhất, nhanh nhất, đúng tin nhất cho từng loại quyết định.

---

### 8.2 ClaudeKit: Harness trên harness

Nguồn mô tả ClaudeKit như một lớp workflow và governance phía trên Claude Code.

Các lớp chính:

1. Structured workflows.
2. Persistent state.
3. Quality gates.
4. Multi-agent coordination.
5. Progressive disclosure.

Ý tưởng quan trọng:

> Nếu agent gốc đã có harness, vẫn có thể thêm một harness cấp cao hơn để chuẩn hóa quy trình, kiểm soát task, và quản lý chất lượng.

---

### 8.3 GoClaw: Harness cho production agents

Các yếu tố được nêu:

- Multi-agent teams.
- Task board có dependency.
- Multi-tenant isolation.
- Security nhiều lớp.
- Hooks system.
- Multi-channel communication.
- Multi-provider LLM.
- Skills/MCP.
- Context pruning.
- Persistent instructions.

Bài học:

> Production agent harness không chỉ là prompt và tools. Nó cần architecture, security, observability, workflow, và khả năng vận hành nhiều tenant hoặc nhiều kênh.

---

## 9. Harness Engineering vs Context Engineering

Có nhiều cách phân định, nhưng trong tài liệu này có thể dùng cách hiểu thực dụng sau:

### 9.1 Context Engineering

Tập trung vào câu hỏi:

> Agent cần nhìn thấy gì?

Bao gồm:

- Retrieval.
- Prompt assembly.
- Memory injection.
- Chunking.
- Ranking.
- Summarization.
- Context compression.
- Data formatting.

### 9.2 Harness Engineering

Tập trung vào câu hỏi:

> Toàn bộ hệ thống cho phép agent vận hành như thế nào?

Bao gồm Context Engineering, nhưng còn mở rộng sang:

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

Nói ngắn gọn:

> Context Engineering quyết định agent thấy gì.  
> Harness Engineering quyết định agent thấy gì, làm gì, bị kiểm soát thế nào, và được sửa lỗi ra sao.

---

## 10. Checklist thiết kế Harness cho AI Agent Production

### 10.1 Tool Interface

- [ ] Tool có input/output schema rõ ràng.
- [ ] Tool output có giới hạn kích thước.
- [ ] Tool trả lời có cấu trúc.
- [ ] Tool có metadata phục vụ audit.
- [ ] Tool có permission boundary.
- [ ] Tool có dry-run nếu hành động có rủi ro.
- [ ] Tool tránh trả dữ liệu thô quá dài vào context.

### 10.2 Context Management

- [ ] Có policy load context theo nhu cầu.
- [ ] Có cơ chế compact/summarize lịch sử.
- [ ] Có phân tầng memory.
- [ ] Có persistent state ngoài context window.
- [ ] Có cách resume session rõ ràng.
- [ ] Có cơ chế loại bỏ thông tin cũ hoặc nhiễu.

### 10.3 State và Handoff

- [ ] Có task board.
- [ ] Có trạng thái pass/fail cho từng task.
- [ ] Có file handoff sau mỗi session.
- [ ] Có ghi lại quyết định kiến trúc.
- [ ] Có known issues.
- [ ] Có dependency giữa tasks.

### 10.4 Quality Gates

- [ ] Có test tự động.
- [ ] Có schema validation.
- [ ] Có factuality/provenance check.
- [ ] Có regression test cho lỗi đã gặp.
- [ ] Có evaluator độc lập với generator.
- [ ] Không cho phép agent tự tuyên bố done nếu chưa qua gate.

### 10.5 Security

- [ ] Least-privilege access.
- [ ] Command validation.
- [ ] Human approval cho hành động nguy hiểm.
- [ ] Audit log.
- [ ] Secret masking.
- [ ] Rollback mechanism.
- [ ] Policy rõ cho file/database/network mutation.

### 10.6 Observability

- [ ] Log tool calls.
- [ ] Log input/output quan trọng.
- [ ] Log reasoning summary hoặc decision trace ở mức an toàn.
- [ ] Track token usage.
- [ ] Track latency.
- [ ] Track cost.
- [ ] Track failure categories.
- [ ] Có dashboard hoặc report định kỳ.

---

## 11. Anti-Patterns phổ biến

| Anti-pattern | Hệ quả |
|---|---|
| Chỉ tối ưu prompt | Không giải quyết lỗi hệ thống lặp lại |
| Tool trả output quá dài | Context noise, suy luận kém |
| Không có state bền vững | Mất tiến độ qua session |
| Không có definition of done | Agent tuyên bố xong quá sớm |
| Agent tự eval output của chính mình | Bias, bỏ sót lỗi |
| Không có source verification | Hallucination hoặc dữ liệu không kiểm chứng |
| Không có permission boundary | Rủi ro bảo mật và side effect ngoài ý muốn |
| Không có regression test | Lỗi cũ tái diễn |
| Multi-agent không có coordination layer | Agent làm trùng, conflict, overwrite |

---

## 12. Minimal Harness Architecture

Một kiến trúc harness tối thiểu cho AI coding/research agent có thể gồm:

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

| Level | Mức độ | Đặc điểm |
|---|---|---|
| L0 | Prompt-only | Chỉ dùng prompt, không có tool/state/eval |
| L1 | Tool-enabled | Agent có tools nhưng thiếu kiểm soát |
| L2 | Structured tools | Tool có schema, output giới hạn, lỗi rõ ràng |
| L3 | Persistent state | Có task board, progress, session handoff |
| L4 | Quality-gated | Có test, eval, validation, regression |
| L5 | Secure harness | Permission, audit, dry-run, approval, rollback |
| L6 | Multi-agent harness | Planner/Generator/Evaluator/Auditor có coordination |
| L7 | Production harness | Observability, cost control, tenant isolation, deployment governance |

---

## 14. Áp dụng thực tế

Khi xây dựng một AI agent system, nên chuyển từ câu hỏi:

> “Prompt nào làm agent thông minh hơn?”

sang câu hỏi:

> “Môi trường nào khiến agent khó mắc lỗi hơn?”

Một số hành động cụ thể:

1. Ghi lại mỗi lỗi agent từng mắc.
2. Phân loại lỗi thành nhóm: retrieval, tool, reasoning, state, permission, evaluation, UX.
3. Với mỗi lỗi, thêm một rào chắn kỹ thuật:
   - Test.
   - Validator.
   - Tool constraint.
   - Better interface.
   - State artifact.
   - Evaluation gate.
   - Permission rule.
4. Biến lỗi thành regression case.
5. Không để agent phụ thuộc vào trí nhớ trong context window cho các state quan trọng.
6. Không cho agent tự đánh giá kết quả cuối cùng nếu task có rủi ro cao.
7. Ưu tiên công cụ deterministic, rẻ, nhanh cho các tác vụ không cần reasoning.

---

## 15. Kết luận

Harness Engineering là cách nhìn AI agents như một hệ thống phần mềm hoàn chỉnh, không phải chỉ là một model được bọc bởi prompt.

Tư duy cốt lõi:

> Model sinh ra suy luận.  
> Harness giới hạn, định hướng, kiểm chứng, và vận hành suy luận đó.

Trong môi trường production, harness cần chịu trách nhiệm cho:

- Độ tin cậy.
- Tính lặp lại.
- Khả năng kiểm chứng.
- Bảo mật.
- Quản lý context.
- Quản lý trạng thái.
- Chất lượng đầu ra.
- Khả năng phục hồi sau lỗi.
- Khả năng mở rộng sang workflow dài và multi-agent.

Vì vậy, nếu mục tiêu là xây dựng AI agents có thể dùng thật, Harness Engineering không phải phần trang trí. Nó là lớp hệ thống quyết định agent có thể đi từ demo sang production hay không.
