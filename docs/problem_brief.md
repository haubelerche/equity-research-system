### 1. Bối cảnh và Tầm nhìn

Trong lĩnh vực đầu tư chứng khoán, báo cáo nghiên cứu cổ phiếu (Equity Research Report) là nền tảng quan trọng nhất cho mọi quyết định đầu tư. Theo tiêu chuẩn CFA Institute, một báo cáo chất lượng cao phải thực hiện đầy đủ **9 bước phân tích chuẩn**: từ xác định phạm vi và investment thesis, thu thập tài liệu, phân tích mô hình kinh doanh, ngành & đối thủ, báo cáo tài chính, dự phóng, định giá, xây dựng khuyến nghị, đến đánh giá rủi ro.

Ngành Dược phẩm (Pharma) là một trong những ngành phức tạp nhất do:

- Dữ liệu đa dạng **và trộn lẫn**: kết hợp số liệu tài chính (10-K/10-Q, XBRL), dữ liệu phi cấu trúc (clinical trial results, patent expiry, FDA/EMA approvals), transcript họp cổ đông, tin tức quy định, và pipeline thuốc.
- Tính chất ngành đặc thù: doanh thu tương lai phụ thuộc rất lớn vào xác suất thành công của thử nghiệm lâm sàng (Probability of Success – PoS), patent cliff, thay đổi chính sách đấu thầu, và các sự kiện bất ngờ (M&A, thu hồi thuốc).
- Yêu cầu khắt khe: mọi con số, dự báo và nhận định phải minh bạch, trích nguồn rõ ràng, tuân thủ quy định tài chính nghiêm ngặt.

Tầm nhìn của dự án là xây dựng một **Financial-Document Intelligence Engine** – không phải LLM đơn thuần “viết văn”, mà là một hệ thống Multi-Agent tự động hóa toàn bộ pipeline equity research ngành dược, giảm thời gian lập báo cáo từ 3–7 ngày xuống dưới 60 phút (sau human review), đồng thời đảm bảo độ chính xác >95% và 100% grounded với citation.

### 2. Phân tích Điểm đau (Pain Points)

Dựa trên nguyên tắc “Hỏi trước, làm sau”, các vấn đề cốt lõi mà analyst đang gặp phải:

| Triệu chứng (Symptom) | Căn nguyên (Root Cause) | Tác động thực tế |
| --- | --- | --- |
| Quá tải dữ liệu (60–80% thời gian) | Thu thập & parse từ PDF, XBRL, transcript, tin tức FDA, bảng biểu phức tạp | Analyst mất hàng ngày chỉ để “lấy số” |
| Thiếu nhất quán & sai sót | Line items không đồng nhất giữa các công ty/năm, one-off items, footnotes | Sai lệch ratio, peer comparison, forecast |
| Độ trễ cập nhật | Dữ liệu thay đổi liên tục (tin thuốc giai đoạn 3, FDA reject) | Mất cơ hội đầu tư |
| Hallucination & thiếu grounding | LLM đơn lẻ không có cơ chế kiểm chứng nguồn | Rủi ro pháp lý, mất lòng tin |
| Không scale được | Thủ công + Excel + LLM cơ bản | Không theo dõi đồng thời 10–20 cổ phiếu |

### 3. Xác định Bài toán Cụ thể (Problem Definition)

Bài toán **không phải** là “AI viết báo cáo”.

Bài toán là xây dựng **hệ thống Multi-Agent AI** có khả năng:

- **Ingestion & Structuring**: Tự động parse và cấu trúc hóa dữ liệu đa nguồn (PDF tables, XBRL, transcript, news) thành database quan hệ (Text-to-SQL ready).
- **Semantic Normalization**: Ánh xạ line items tài chính về một taxonomy chuẩn (Revenue = Net Sales, phân biệt Adjusted EBITDA…).
- **Domain Reasoning**: Phân tích pipeline thuốc, patent cliff, regulatory risks, sentiment tin tức.
- **Quantitative Engine**: Tính toán ratio, forecasting (base/bull/bear), valuation (DCF, multiples, sensitivity) bằng code Python thay vì LLM thuần.
- **Structured Debate & Grounded Generation**: Tạo báo cáo CFA chuẩn với citation chính xác đến trang/số dòng, confidence score, và human-in-the-loop (HITL) tại assumptions & final approval.

### 4. Kiến trúc Hệ thống Multi-Agent

Hệ thống tuân thủ nguyên tắc “Đơn giản trước, phức tạp sau” → bắt đầu bằng workflow patterns, nâng cấp lên Multi-Agent khi cần autonomy cao. Kiến trúc Orchestrator-Workers + Evaluator-Optimizer + Structured Debate.

![image.png](attachment:c251e458-9fd6-4565-a40c-4064d6e0af72:image.png)

| STT | Tên Agent | Vai trò chính (gộp từ 8 agent cũ) | Lý do gộp | Công cụ chính cần dùng |
| --- | --- | --- | --- | --- |
| 1 | **Orchestrator** | Điều phối workflow, routing, quản lý state, HITL | Là “não trung tâm” – không thay đổi | LangGraph / CrewAI / AutoGen |
| 2 | **Data Foundation Agent** | Ingestion + Parsing + SQL Structuring + News & Sentiment | Gộp agent cũ 1 + 2 | LayoutLMv3/Nougat + Text-to-SQL + RAG |
| 3 | **Core Analyst Agent** | Financial Analytics (Code-first) + Pharma Pipeline Specialist | Gộp agent cũ 3 + 4 → một “Domain Expert” duy nhất | Python Interpreter + ClinicalTrials API |
| 4 | **Valuation & Reasoning Agent** | Valuation Engine + Structured Debate (Skeptic + Believer) | Gộp 3 agent cũ (5+6+7) thành **một agent có internal dual-role** | Python (DCF, multiples) + Dual Prompt |
| 5 | **Synthesis & Auditor Agent** | Report Writer + Final Evaluator + Grounded Generation | Gộp agent cũ 8 → làm “thẩm phán cuối cùng” | RAG + Citation Mapping + Post-processing |

### Cách hoạt động của 5 tác tử (Workflow tinh gọn)

1. **Orchestrator** nhận yêu cầu → phân công và theo dõi tiến độ.
2. **Data Foundation Agent** xử lý toàn bộ dữ liệu thô → xuất ra **SQL Database + Vector Store** (một lần duy nhất).
3. **Core Analyst Agent** truy vấn SQL + phân tích pipeline pharma → trả về historical ratios + PoS-adjusted forecast.
4. **Valuation & Reasoning Agent**:
    - Chạy Python tính DCF / Multiples / Sensitivity.
    - Sử dụng **internal structured debate** (dual-role prompt trong cùng một agent):
        - Phần 1: Believer mode (củng cố thesis).
        - Phần 2: Skeptic mode (tìm rủi ro).
        → Tránh phải tạo 3 agent riêng mà vẫn có tranh luận.

### 5. Quy trình 9 Bước CFA Tích hợp AI (Workflow)

1. Xác định phạm vi & investment thesis
2. Ingestion & Structuring
3. Business & Industry Analysis (Pipeline + Peer)
4. Historical Financial Analysis (Code)
5. Forecasting (PoS-adjusted)
6. Valuation (DCF + Multiples + Sensitivity)
7. Structured Debate (Skeptic vs Believer)
8. Synthesis & Report Generation (Grounded)
9. HITL Review & Final Publication

### 6. Bảng So sánh Hai Hướng Tiếp cận

| Tiêu chí | AI Agent Equity Research (Dự án đề xuất) | AI Khuyến nghị Đầu tư (Investment Advice) |
| --- | --- | --- |
| Mục tiêu | Hỗ trợ analyst, cung cấp báo cáo grounded | Đưa ra tín hiệu Mua/Bán trực tiếp |
| Output | Báo cáo 7–10 trang CFA + citation + confidence | Signal + probability |
| Rủi ro pháp lý | Thấp (AI làm nháp, người duyệt cuối) | Cao |
| Độ chính xác & explainability | Cao (traceable, debate) | Thấp |
| Tính sẵn sàng | Rất cao (tích hợp workflow hiện tại) | Thấp |
| Giá trị lâu dài | Cao (tri thức, scale research) | Ngắn hạn, dễ sai lệch |

**Khuyến nghị:** Tập trung vào **Equity Research** – phù hợp nguyên tắc “AI làm nháp, người duyệt cuối”.

### 7. KPIs Đo lường Hiệu quả (Measurable)

- **Accuracy**: >98% trích xuất số liệu & tính toán
- **Citation Coverage**: 100% nhận định định lượng có nguồn
- **Efficiency**: Giảm thời gian từ 3–7 ngày → <60 phút (bản nháp)
- **Consistency**: Sai lệch giữa các agent < ngưỡng tolerance
- **Human Satisfaction**: Analyst đánh giá chất lượng report (Net Promoter Score)

### 8. Giá trị Mang lại & Tác động Kinh doanh

- Tiết kiệm 70–90% thời gian analyst → tập trung judgment cao cấp.
- Scale theo dõi hàng chục cổ phiếu pharma cùng lúc, real-time update.
- Tạo “research edge” bền vững cho công ty chứng khoán/quỹ đầu tư.
- Giảm chi phí nhân sự research, tăng số lượng & chất lượng output.
- Tuân thủ chuẩn CFA, giảm rủi ro pháp lý & reputational.

### 9. Chiến lược Triển khai & Roadmap Ban đầu (PoC)

1. Xây dựng Golden Dataset (5 công ty dược Việt Nam: DHG, TRA, VNP… – 3–5 năm dữ liệu).
2. Triển khai Agent 1 & 3 (Data Foundation + Financial Analytics) – nền tảng cốt lõi.
3. Thử nghiệm Structured Debate (Skeptic vs Believer).
4. Human-in-the-loop iteration → nâng cấp dần autonomy.