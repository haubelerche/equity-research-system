# Problem Brief — Vietnam Pharma Multi-Agent Equity Research

*Tài liệu định nghĩa bài toán và nguyên tắc thiết kế cho backend của hệ `multi-agent equity research` tập trung vào cổ phiếu dược/y tế niêm yết tại Việt Nam.*

---

## 1. Mục tiêu tài liệu

- Làm rõ vì sao bài toán `equity research` ngành dược Việt Nam khó hơn một bài toán tóm tắt tài liệu hay chatbot tài chính thông thường.
- Chốt phạm vi kỹ thuật cốt lõi của hệ thống: `ingestion -> facts -> valuation -> grounded narrative -> HITL publish`.
- Thiết lập bộ nguyên tắc để đồng bộ [PRD.md](PRD.md), [BACKEND-PLAN.md](BACKEND-PLAN.md), và [SEQUENCE.md](SEQUENCE.md).

---

## 2. Bối cảnh và cơ hội

### 2.1 Bối cảnh thị trường

- Danh mục mục tiêu gồm khoảng `53` doanh nghiệp dược/y tế niêm yết trên `HOSE`, `HNX`, và `UPCOM`.
- Một báo cáo nghiên cứu chất lượng thường đòi hỏi `15-30 giờ` làm việc thủ công cho thu thập dữ liệu, chuẩn hóa số liệu, dựng luận điểm, và rà soát nguồn.
- Dòng tiền vào nhóm dược chịu ảnh hưởng mạnh bởi catalyst địa phương như `đấu thầu thuốc`, `BHYT`, `thay đổi đăng ký/lưu hành`, và tín hiệu từ `Cục Quản lý Dược`.

### 2.2 Khoảng trống công cụ hiện tại

- Công cụ quốc tế mạnh về dữ liệu toàn cầu nhưng yếu ở `văn bản tiếng Việt`, `đấu thầu`, `quy định địa phương`, và `bối cảnh pharma Việt Nam`.
- Nền tảng chứng khoán nội địa mạnh ở market data nhưng chưa có workflow `multi-agent`, `code-first valuation`, và `citation-first reporting`.
- LLM chat đơn lẻ có thể hỗ trợ viết nháp, nhưng không đáng tin cho `đúng số`, `đúng nguồn`, `đúng logic`, và `đúng kiểm soát quy trình`.

### 2.3 Cơ hội sản phẩm

- Chuẩn hóa research workflow cho toàn bộ `53` mã thay vì lệ thuộc vào excel và phân tích thủ công.
- Tạo `flash memo` và `full report draft` có nguồn, giúp analyst tập trung vào judgment thay vì dành phần lớn thời gian cho khâu dựng nền.
- Xây dựng lợi thế cạnh tranh bằng `local context first`: dữ liệu Việt Nam, taxonomy Việt Nam, catalyst Việt Nam, và review workflow phù hợp tổ chức tài chính.

---

## 3. Vì sao bài toán này khó

### 3.1 Dữ liệu phân mảnh và không đồng nhất

- Báo cáo tài chính tồn tại ở nhiều dạng `PDF`, `HTML`, file scan, và công bố rời rạc.
- Line item thay đổi theo doanh nghiệp, năm, và cách thuyết minh.
- Nguồn catalyst phi cấu trúc, thiếu schema thống nhất, và có chất lượng không đồng đều.

### 3.2 Domain reasoning mang tính địa phương

- Tác động của `đấu thầu`, `BHYT`, `GMP`, `gia hạn số đăng ký`, hoặc `thu hồi thuốc` không thể suy ra đúng chỉ bằng một prompt chung.
- Một catalyst nhỏ có thể ảnh hưởng doanh thu, biên, hoặc tốc độ mở rộng thị phần theo cách chỉ domain analyst mới hiểu.
- Peer comparison trong ngành dược Việt Nam cần taxonomy riêng để tránh so sánh sai nhóm doanh nghiệp.

### 3.3 Bài toán không chấp nhận hallucination ở lớp định lượng

- Một hệ thống dùng trong equity research không được phép để LLM “tự nghĩ” ra số.
- Sai số ở `financial facts`, `valuation`, hoặc `citations` kéo theo rủi ro pháp lý, rủi ro uy tín, và làm sụp niềm tin với người dùng tổ chức.

### 3.4 Tính vận hành dài hạn

- Hệ thống phải xử lý song song nhiều mã, nhiều nguồn, nhiều kỳ công bố, nhiều loại run.
- Workflow có bước dài, có thể lỗi giữa chừng, cần `resume`, `retry`, `checkpoint`, và `human approval`.
- Chi phí token tăng nhanh nếu không có `usage tracking` và `budget guardrails`.

---

## 4. Bài toán cần giải quyết

Đây không phải bài toán “AI viết báo cáo”. Đây là bài toán xây dựng một `research operating system` có khả năng:

1. Thu thập và chuẩn hóa dữ liệu đa nguồn thành `canonical facts`.
2. Kiểm tra chất lượng dữ liệu trước khi đưa vào lớp phân tích.
3. Tính toán định lượng bằng `code-first engine` thay vì để LLM tính nhẩm.
4. Dùng LLM cho reasoning và narrative trên các artifact đã được khóa nguồn và kiểm định.
5. Tạo báo cáo có `citation`, `audit trail`, `confidence`, và `HITL approval`.
6. Hỗ trợ `incremental recompute` khi có tài liệu hoặc catalyst mới.

---

## 5. Vì sao single-agent hoặc chatbot là chưa đủ

### 5.1 Không tách được trách nhiệm

Một agent đơn lẻ phải cùng lúc:
- ingest tài liệu,
- chuẩn hóa line item,
- làm domain reasoning,
- định giá,
- viết báo cáo,
- kiểm citation.

Mô hình này làm mờ ranh giới giữa `facts`, `inference`, và `presentation`, nên rất khó kiểm soát chất lượng.

### 5.2 Không hỗ trợ kiểm soát workflow

Chatbot không có khái niệm rõ ràng về:
- `run lifecycle`,
- `idempotency`,
- `retry and resume`,
- `approval checkpoints`,
- `partial recompute`.

### 5.3 Không phù hợp môi trường production

Tổ chức tài chính cần:
- lineage,
- audit,
- data quality gates,
- cost governance,
- observability,
- reproducibility.

Đây là yêu cầu của một backend workflow engine, không phải của một giao diện chat thuần.

---

## 6. Tầm nhìn hệ thống

Hệ thống mục tiêu là một nền tảng backend theo mô hình:

- `API/BFF`: nhận yêu cầu nghiên cứu, trả trạng thái, trả artifact.
- `Orchestration`: điều phối các bước theo state machine có checkpoint và HITL.
- `Async workers`: ingestion, parsing, normalization, indexing, valuation, synthesis, rendering.
- `Data plane`: object store, relational facts, vector index, audit records.
- `Connector plane`: nguồn filings, tender, BHYT, regulatory, company news.

Về mặt logic nghiên cứu, hệ thống vẫn bám cấu trúc `Data-CoT -> Concept-CoT -> Thesis-CoT`, nhưng triển khai backend phải tách rõ:

- `agent role`: vai trò suy luận.
- `service/module`: năng lực kỹ thuật.
- `workflow node`: bước chạy trong orchestration.

Không phải mọi vai trò đều cần trở thành một agent độc lập.

---

## 7. Các nguyên tắc thiết kế cốt lõi

### 7.1 Facts before narrative

- Số liệu và valuation artifact được sinh bằng code và schema cố định.
- LLM chỉ được diễn giải trên artifact đã qua kiểm soát.

### 7.2 Local context first

- Ưu tiên nguồn dữ liệu và logic thị trường Việt Nam.
- Dữ liệu quốc tế chỉ đóng vai trò tham chiếu, không phải nền của MVP.

### 7.3 Lineage by default

- Mỗi fact, chunk, citation, và report section phải truy ngược được về source và version đã dùng.

### 7.4 Quality before persistence

- Dữ liệu không được ghi thành `canonical fact` nếu chưa qua validation, reconciliation, và confidence gate.

### 7.5 AI drafts, humans approve

- Các bước có rủi ro cao như giả định và khuyến nghị cuối phải có `HITL`.

### 7.6 Budgeted intelligence

- Mỗi run phải có giới hạn chi phí, model policy, và fallback strategy.

### 7.7 Incremental over full recompute

- Khi chỉ một phần dữ liệu thay đổi, hệ thống phải cố gắng invalidation có chọn lọc thay vì chạy lại toàn bộ pipeline.

### 7.8 Evaluate before promote

- Mọi thay đổi parser, prompt, model, hoặc retrieval policy phải đi qua offline evaluation trước khi đưa vào luồng publish production.
- Điểm đánh giá tối thiểu cần bám các trục: `grounding`, `accuracy`, `logicality`, `storytelling`, và regression stability.

---

## 8. Các pain point mà backend phải xử lý trực tiếp

### 8.1 Data pain

- Parse BCTC không ổn định.
- OCR không đồng đều.
- Catalyst từ nguồn công khai thiếu chuẩn hóa.

### 8.2 Analysis pain

- Analyst khó giữ consistency giữa nhiều mã.
- Rất dễ trộn lẫn facts với assumptions hoặc narrative.

### 8.3 Governance pain

- Thiếu audit trail.
- Khó xác minh nguồn của một kết luận định lượng.
- Không có cơ chế buộc review trước publish.

### 8.4 Operations pain

- Run dài dễ fail giữa chừng.
- Khó biết bước nào gây lỗi hoặc đội chi phí.
- Khó chạy lại chỉ một phần pipeline.

---

## 9. Phạm vi giai đoạn đầu

### Trong phạm vi

- `53` mã dược/y tế niêm yết Việt Nam.
- `full report`, `flash memo`, `catalyst refresh`.
- Dữ liệu BCTC, thông tin niêm yết, catalyst từ đấu thầu/BHYT/regulatory/company news.
- Định giá `DCF`, `P/E`, `EV/EBITDA`.
- Citation map và review workflow.

### Ngoài phạm vi

- Auto-trading hoặc signal execution.
- Autonomous publish không qua review.
- Phủ toàn bộ biotech/global pharma.
- Dùng LLM làm nguồn sự thật cho số liệu.

---

## 10. Hướng triển khai ưu tiên

1. `Foundation and data contracts`
2. `Fact ingestion and code-first valuation`
3. `RAG and citation pipeline`
4. `Orchestration and HITL`
5. `Production hardening`
6. `Agentic reasoning and thesis generation`

Trình tự này phản ánh dependency triển khai thực tế: cần khóa data contract và fact layer trước, sau đó mới hoàn thiện grounding, orchestration, hardening production, rồi mới đẩy mạnh autonomy ở lớp thesis generation.

---

## 11. Tiêu chí thành công của problem brief

Problem brief được coi là hoàn thành khi toàn bộ team thống nhất rằng:

- Dự án là một `research operating system`, không phải chatbot.
- `Vietnam pharma` là phạm vi MVP bắt buộc.
- `code-first valuation`, `citation-first reporting`, `HITL publish`, `data quality gates`, và `cost governance` là các nguyên tắc không được phá vỡ.
- Kiến trúc backend phải được thiết kế cho `stateful runs`, `partial recompute`, và `production observability`.

---

## 12. Kết luận

Equity research cho ngành dược Việt Nam là bài toán lai giữa `financial analysis`, `policy interpretation`, `regulatory monitoring`, và `report production`. Vì vậy hệ thống thành công không thể là một LLM biết viết hay, mà phải là một backend có khả năng quản lý dữ liệu, reasoning, chi phí, kiểm soát chất lượng, và phê duyệt con người trong cùng một workflow.
