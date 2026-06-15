Mình đã đối chiếu cả **feedback cũ** và **bản hiện tại trong file Word + file text tiến độ**. Kết luận của mình: **nhóm đã cải thiện rất rõ về tư duy phương pháp, kỹ thuật dữ liệu, truy vết, định giá tất định và cơ sở ngành dược**; tuy nhiên **bản Word hiện tại chưa “ăn” hết các cải thiện đó**, và vẫn còn một số lỗi đủ nặng để giáo viên có thể tiếp tục bắt sửa.

Điểm nguy hiểm nhất: **file `.txt` có nhiều phần Chương 3 đã viết khá tốt, nhưng file Word `BÁO CÁO KLTN N78.docx` đang thiếu phần thân Chương 3, Chương 4 và Chương 5 gần như chỉ là đề mục**. Nếu nộp đúng file Word hiện tại, cô có thể không thấy phần cải thiện lớn nhất của nhóm. Trong Word, Chương 3 hiển thị nhiều mục như 3.1 đến 3.7 nhưng phần nội dung thực tế bị trống/thiếu, sau đó chuyển sang Chương 4 với các mục kết quả cũng chủ yếu là đề cương.  

## 1. Những điểm đã cải thiện rõ

**Thứ nhất, nhóm đã chuyển hướng đúng từ “AI viết báo cáo” sang “pipeline phân tích có kiểm soát”.** Trong bản text hiện tại, hệ thống được mô tả theo mô hình đầu vào – xử lý – đầu ra, có yêu cầu phân tích mã cổ phiếu, phạm vi thời gian, loại báo cáo, dữ liệu nền, kiểm tra, chuẩn hóa và lưu vết trước khi phân tích. Đây là cải thiện đúng với góp ý “đừng kể chuyện, hãy định nghĩa input/process/output”. 

**Thứ hai, phần dữ liệu và lưu trữ đã cụ thể hơn nhiều.** Bản Word hiện tại đã nêu các công cụ như `vnstock`, `pandas`, `numpy`, `pdfplumber`, `Tesseract`, `Poppler`, `pdf2image`, `Pillow`, `requests`, `BeautifulSoup`, đồng thời mô tả Supabase PostgreSQL, Supabase Storage, tìm kiếm toàn văn và `pgvector` cho truy xuất theo vector. Đây là cải thiện trực tiếp so với feedback cũ yêu cầu nói rõ lấy dữ liệu bằng API, scraping hay tự parse PDF.  

**Thứ ba, phần “research snapshot”/versioning đã được xử lý tốt hơn.** Bản text hiện tại đã giải thích mỗi lần phân tích cần gắn với mã lần chạy, lưu trạng thái dữ liệu, nguồn, giả định định giá, kết quả phân tích và báo cáo theo cùng một phiên bản. Điều này trả lời khá tốt góp ý cũ về “Research snapshot được hiện thực hóa bằng kỹ thuật gì”. 

**Thứ tư, phần công thức tài chính đã cải thiện đáng kể.** Bản hiện tại đã có FCFF, FCFE, WACC, CAPM, Terminal Value, Equity Value, Fair Value Per Share, định giá tương đối, phân tích độ nhạy. Đây là bước tiến lớn so với feedback cũ chê phần định giá chỉ viết văn xuôi, thiếu phương trình toán học.  

**Thứ năm, cơ sở ngành y tế – dược phẩm đã sâu hơn.** Bản Word hiện tại đã bổ sung Luật Dược, bảo hiểm y tế, Thông tư 37/2024/TT-BYT, Thông tư 28/2025/TT-BYT, GMP, đấu thầu thuốc, tác động đến doanh thu, biên lợi nhuận, CAPEX và rủi ro pháp lý. Đây là cải thiện đúng hướng so với feedback cũ nói phần ngành dược còn mỏng và thiếu văn bản pháp lý.  

**Thứ sáu, nhóm đã hiểu đúng vai trò của LLM.** Bản text hiện tại nói rõ LLM không tự tính toán, không tự tạo số liệu, mà chỉ diễn giải kết quả đã khóa; các phép tính như FCFF, FCFE, WACC, giá trị hiện tại, giá trị cuối kỳ và phân tích độ nhạy được thực hiện bằng Python tất định. Đây là một cải thiện rất quan trọng về mặt phương pháp luận FinTech. 

## 2. Những điểm vẫn chưa đạt theo feedback cũ

**1. Metrics và RAGAS vẫn chưa đạt yêu cầu của cô.** Feedback cũ yêu cầu rất cụ thể: đưa Accuracy, F1, Recall, ROC; dùng RAGAS với Faithfulness và Answer Relevance; hệ thống chấm 0–1 và nếu điểm dưới 0.8 thì kích hoạt “CRITICAL FAIL”.  Bản hiện tại đã có precision, recall, F-measure, citation precision/citation recall và claim-level citation checking, nhưng mình chưa thấy phần RAGAS, chưa thấy ngưỡng 0.8, chưa thấy bảng metric định lượng đầy đủ cho từng cổng kiểm định. 

**Đánh giá:** cải thiện một phần, nhưng **chưa qua được góp ý này**. Cần thêm một bảng ở mục 3.7, ví dụ:

| Nhóm đánh giá         |                    Metric | Công thức/logic                                       | Ngưỡng đạt |
| --------------------- | ------------------------: | ----------------------------------------------------- | ---------: |
| Trích xuất bảng BCTC  |             Cell Accuracy | số ô đọc đúng / tổng số ô mẫu                         |     ≥ 0.95 |
| Ánh xạ chỉ tiêu       |                Mapping F1 | F1 giữa chỉ tiêu dự đoán và nhãn chuẩn                |     ≥ 0.90 |
| Truy xuất bằng chứng  |     Recall@k, Precision@k | đoạn đúng mã, đúng kỳ, đúng nguồn                     |     ≥ 0.85 |
| Sinh nội dung RAG     |        RAGAS Faithfulness | điểm 0–1                                              |     ≥ 0.80 |
| Sinh nội dung RAG     |    RAGAS Answer Relevance | điểm 0–1                                              |     ≥ 0.80 |
| Trích dẫn             | Citation Precision/Recall | claim có citation đúng / claim cần citation           |     ≥ 0.90 |
| Định giá              |           Reproducibility | cùng input tạo cùng output                            |       100% |
| Cổng lỗi nghiêm trọng |             Critical Fail | nếu Faithfulness < 0.8 hoặc claim trọng yếu sai nguồn |       Fail |

**2. Driver-based forecasting vẫn còn quá chung.** Feedback cũ yêu cầu hàm dự phóng ngành dược dưới dạng (Y=f(x_1,x_2,...,x_n)), không chỉ nói “dựa trên động lực kinh doanh”.  Bản hiện tại có công thức doanh thu (Doanh thu_t = Doanh thu_{t-1} \times (1+g_t)), nhưng (g_t) vẫn chủ yếu được mô tả bằng lời: tăng trưởng lịch sử, triển vọng ngành, năng lực sản xuất, danh mục sản phẩm, chính sách đấu thầu, tiêu thụ dược phẩm. 

**Đánh giá:** có công thức, nhưng **chưa thật sự là driver-based forecasting**. Nên bổ sung dạng:

[
Revenue_t = f(Revenue_{t-1}, g_{industry,t}, TenderWinRate_t, ETCShare_t, OTCShare_t, CapacityUtilization_t, ASP_t, Volume_t, ProductMix_t)
]

hoặc cụ thể hơn:

[
g_t = \alpha_1 g_{hist} + \alpha_2 g_{industry,t} + \alpha_3 TenderWinRate_t + \alpha_4 CapacityExpansion_t + \alpha_5 ProductMixShift_t - \alpha_6 PolicyRisk_t
]

Sau đó giải thích biến nào lấy từ dữ liệu tài chính, biến nào nhập thủ công, biến nào lấy từ báo cáo ngành/văn bản pháp lý.

**3. Ke, Rf và beta vẫn chưa đủ “code-level”.** Feedback cũ hỏi rất cụ thể: Ke tính bằng code như thế nào, Rf lấy từ trái phiếu chính phủ kỳ hạn bao nhiêu, beta lấy từ chuỗi thời gian nào.  Bản hiện tại đã có CAPM:

[
R_e = R_f + \beta (R_m - R_f)
]

nhưng chưa thấy quy tắc vận hành rõ như: Rf = lợi suất trái phiếu Chính phủ Việt Nam 10 năm tại ngày định giá; beta = hồi quy lợi suất tuần của cổ phiếu với VN-Index trong 2 hoặc 3 năm; có loại bỏ outlier hay không; có dùng beta điều chỉnh hay unlever/relever beta hay không. 

**Đánh giá:** phần lý thuyết có, nhưng **phần thuật toán triển khai vẫn thiếu**. Đây là chỗ cô rất dễ bắt lại.

**4. Phần agent framework đã có hướng giải thích, nhưng vẫn thiếu pseudo-code/JSON/state machine.** Feedback cũ yêu cầu nhóm nói rõ dùng LangChain, AutoGen, CrewAI hay framework nào; supervisor ra quyết định theo logic nào; agent giao tiếp bằng JSON không; cần pseudo-code hoặc prompt cốt lõi.  Bản text hiện tại nói nhóm không dùng LangChain/LangGraph làm lõi, mà xây bộ điều phối riêng bằng Python để kiểm soát vòng đời phân tích. Đây là lựa chọn có thể bảo vệ được.  Tuy nhiên, nếu đã không dùng framework agent phổ biến, nhóm càng phải mô tả rõ hơn: state machine gồm những trạng thái nào, điều kiện chuyển trạng thái ra sao, message schema giữa các tác tử là gì.

**Đánh giá:** ý tưởng tốt, nhưng **chưa đủ hình thức kỹ thuật**. Cần thêm một bảng hoặc pseudo-code như:

```text
State: INIT -> DATA_READY -> VALUATION_READY -> DRAFT_READY -> REVIEW_READY -> APPROVED / BLOCKED

if missing_required_financial_fact:
    state = BLOCKED
elif valuation_assumption_invalid:
    state = BLOCKED
elif citation_score < 0.8:
    state = BLOCKED
else:
    state = APPROVED
```

Và một JSON schema mẫu:

```json
{
  "run_id": "string",
  "ticker": "DHG",
  "task": "valuation_review",
  "allowed_tools": ["read_fact_store", "read_valuation_result"],
  "inputs": {
    "financial_facts_version": "v1",
    "valuation_artifact_id": "..."
  },
  "outputs": {
    "claims": [],
    "warnings": [],
    "next_state": "REVIEW_READY"
  }
}
```

**5. Sơ đồ vẫn là điểm yếu.** Feedback cũ yêu cầu BPMN/flowchart Input → Process → Output, UML/Sequence Diagram, và RAG flowchart gồm Document Loader → Text Splitter → Embedding → Vector Store → Retriever → LLM.   Trong bản Word hiện tại mình chỉ thấy Hình 1.1 ở phần bối cảnh; chưa thấy hệ thống sơ đồ kỹ thuật tương xứng cho RAG, pipeline dữ liệu, sequence tác tử hoặc state machine. 

**Đánh giá:** phần văn bản đã khá hơn, nhưng **thiếu hình sẽ làm Chương 3 khó thuyết phục**. Ít nhất cần thêm 4 hình: pipeline tổng thể, kiến trúc dữ liệu, RAG flow, sequence/state machine tác tử.

## 3. Lỗi mới hoặc lỗi còn sót rất nguy hiểm trong file Word

**1. Bản Word chưa tích hợp nội dung Chương 3 từ file text.** Đây là lỗi lớn nhất. File text có phần 3.1–3.7 viết khá dài, nhưng Word lại gần như chỉ có heading của Chương 3 rồi nhảy sang Chương 4.  Nếu giáo viên mở file Word, cô sẽ kết luận nhóm chưa viết Chương 3, dù trong file text đã có nội dung.

**2. Chương 4 và Chương 5 hiện đang giống đề cương hơn là kết quả nghiên cứu.** Word có các mục 4.1 đến 4.7, 5.1 đến 5.5, nhưng phần hiển thị chủ yếu là tiêu đề, chưa có kết quả thực nghiệm, bảng kết quả, số liệu, đánh giá metric, case study cổ phiếu mẫu.   Với đề tài “xây dựng hệ thống”, Chương 4 phải có bằng chứng hệ thống đã chạy: mã cổ phiếu mẫu, dữ liệu đầu vào, kết quả định giá, bảng độ nhạy, RAG/citation score, thời gian xử lý, lỗi phát hiện.

**3. Comment, highlight và ghi chú nội bộ vẫn còn trong Word.** Mình thấy các đoạn như “Comment by Dũng Nguyễn”, “Comment by Thanh Hau Luong”, ghi chú tài liệu tham khảo tạm và các vùng highlight ở các phần sau. Ví dụ file Word vẫn hiện comment yêu cầu viết lại mục 1.7.  Trước khi gửi cho cô, phải xóa toàn bộ comments, highlights, placeholder và ghi chú nội bộ.

**4. Danh mục ký hiệu, bảng, hình còn trống.** Word hiện có các mục “DANH MỤC CÁC KÝ HIỆU VÀ CHỮ VIẾT TẮT”, “DANH MỤC CÁC BẢNG”, “DANH MỤC CÁC HÌNH VẼ”, nhưng nội dung chưa được tạo.  Feedback cũ đã nhắc đưa DCF, P/E, EBITDA, WACC vào danh mục từ viết tắt; nếu danh mục còn trống thì cô sẽ bắt lỗi lại.

**5. Tên bảng vẫn chưa chuẩn.** Feedback cũ nhắc “Tên bảng ở trên”, “đánh số bảng theo chương”, ví dụ Bảng 2.1.  Nhưng trong Word vẫn còn “Bảng . Nhóm chỉ tiêu và ý nghĩa phân tích”, chưa đánh số.  Đây là lỗi hình thức nhưng rất dễ bị chấm vì cô đã nhắc cụ thể.

**6. Trích dẫn đã có nhưng còn placeholder và reference chưa sạch.** Chương 2 đã có nhiều citation hơn trước, nhưng vẫn còn dạng placeholder như `[CIT-PENMAN-FSA]`, `[CIT-DAMODARAN-VALUATION]`, `[CIT-WANG-STRONG-DQ]`.  Phần danh mục tài liệu tham khảo cũng còn định dạng chưa chuẩn, có nguồn ghi URL dài trong trường không phù hợp.  Đây là lỗi học thuật cần xử lý trước khi nộp.

**7. Thuật ngữ cô từng yêu cầu bỏ vẫn còn xuất hiện.** Feedback cũ yêu cầu bỏ các cụm như “human-in-the-loop”, “evaluation gates”, “valuation artifact”, “Valuation Agent”, “artifact”, và hạn chế nhắc lại DCF/P/E dài dòng.  Bản hiện tại vẫn có “human-in-the-loop” trong phần mục tiêu và vẫn dùng “artifact” ở nhiều đoạn.  Nên đổi hết sang tiếng Việt học thuật hơn: “cơ chế phê duyệt của con người”, “cổng kiểm định”, “sản phẩm trung gian”, “kết quả định giá”, “tệp bằng chứng”.

## 4. Đánh giá theo từng nhóm feedback cũ

| Nhóm feedback cũ                           | Tình trạng hiện tại                                                                               | Đánh giá                                 |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------- | ---------------------------------------- |
| Bổ sung trích dẫn Chương 2                 | Đã thêm nhiều trích dẫn và tài liệu nền, nhưng còn placeholder CIT và danh mục chưa sạch          | **Cải thiện nhưng chưa xong**            |
| Làm sâu ngành dược                         | Đã thêm Luật Dược, bảo hiểm y tế, thông tư, GMP, đấu thầu, tác động tài chính                     | **Cải thiện tốt**                        |
| Công thức FCFF/FCFE/WACC/CAPM              | Đã có công thức, nhưng cần format bằng Equation, đánh số chuẩn và làm rõ Ke/Rf/beta               | **Cải thiện nhưng còn thiếu triển khai** |
| Driver-based forecasting                   | Có công thức doanh thu cơ bản, nhưng chưa có hàm driver ngành dược đúng nghĩa                     | **Chưa đạt**                             |
| Nguồn dữ liệu/API/scraping/PDF             | Đã nêu vnstock, PDF, OCR, scraping, Supabase, pgvector                                            | **Cải thiện rõ**                         |
| Dedup/missing data                         | Có logic null, không tự bù, quản lý nguồn, nhưng cần trình bày thuật toán/bảng rõ hơn trong Word  | **Cải thiện một phần**                   |
| Kiến trúc database/vector store/versioning | Đã có PostgreSQL, Supabase Storage, pgvector, versioning/run_id                                   | **Cải thiện tốt**                        |
| Agent framework/state machine/JSON         | Có nói custom Python orchestrator, nhưng thiếu pseudo-code, JSON schema, state machine diagram    | **Chưa đạt đủ**                          |
| RAG flowchart/UML/Sequence                 | Chưa thấy đủ trong Word                                                                           | **Chưa đạt**                             |
| Metrics/RAGAS/CRITICAL FAIL                | Có precision/recall/citation checks, nhưng thiếu RAGAS Faithfulness, Answer Relevance, ngưỡng 0.8 | **Chưa đạt**                             |
| Bảng/hình/công thức format                 | Vẫn còn bảng chưa đánh số, danh mục trống, công thức chưa chuẩn Word Equation                     | **Chưa đạt**                             |
| Xóa thuật ngữ rối mắt                      | Vẫn còn artifact/human-in-the-loop và lặp thuật ngữ                                               | **Chưa đạt**                             |
| Tích hợp bản hoàn chỉnh                    | File text tốt hơn Word; Word thiếu Chương 3–5                                                     | **Lỗi mới rất nghiêm trọng**             |

## 5. Việc nên sửa ngay trước khi gửi lại cô

Ưu tiên 1: **hợp nhất nội dung file text vào Word**. Đưa toàn bộ phần 3.1–3.7 đã viết trong file `ĐÁNH GIÁ TIẾN ĐỘ...txt` vào đúng Chương 3 của Word, sau đó cập nhật mục lục. Nếu không làm bước này thì các cải thiện lớn gần như không có giá trị khi cô đọc bản Word.

Ưu tiên 2: **hoàn thiện mục 3.7 bằng bảng metric định lượng**. Phải có Accuracy/F1/Recall/Precision cho trích xuất dữ liệu, citation precision/recall cho trích dẫn, RAGAS Faithfulness và Answer Relevance cho sinh nội dung, ngưỡng 0.8 và điều kiện “Critical Fail”. Đây là feedback cô nhấn rất mạnh. 

Ưu tiên 3: **bổ sung thuật toán tài chính ở mức triển khai**. Đặc biệt là Rf, beta, market risk premium, Ke, WACC, điều kiện (WACC > g), quy tắc lấy dữ liệu giá, tần suất lợi suất, khoảng thời gian hồi quy và cách xử lý cổ phiếu thanh khoản thấp. Phần công thức hiện có là nền tốt, nhưng chưa trả lời hết câu “hệ thống bằng code tính như thế nào”.

Ưu tiên 4: **viết lại driver-based forecasting thành hàm ngành dược**. Không chỉ dùng (Revenue_t = Revenue_{t-1}(1+g_t)); cần định nghĩa (g_t) phụ thuộc vào tăng trưởng ngành, kênh ETC/OTC, kết quả đấu thầu, công suất, danh mục sản phẩm, giá bán, sản lượng, chính sách BHYT và rủi ro pháp lý.

Ưu tiên 5: **thêm sơ đồ kỹ thuật**. Tối thiểu cần: sơ đồ pipeline tổng thể, RAG flowchart, sequence diagram giữa các tác tử, state machine của pipeline và sơ đồ lưu trữ PostgreSQL/pgvector/Supabase Storage.

Ưu tiên 6: **dọn Word sạch tuyệt đối**. Xóa comments, highlights, placeholder CIT, sửa “Bảng .” thành “Bảng 2.1”, “Bảng 2.2”, cập nhật danh mục bảng/hình/từ viết tắt, chuẩn hóa tiêu đề “AI Agent” hay “Multi-Agent”, bỏ thuật ngữ cô đã yêu cầu xóa.

Mức đánh giá của mình: **nội dung tư duy đã đi từ khoảng 45–50% lên 70–75%**, nhưng **bản Word nộp được hiện tại chỉ khoảng 55–60%** vì chưa tích hợp Chương 3 đầy đủ, Chương 4–5 còn rỗng và còn nhiều lỗi trình bày/học thuật. Nếu nhóm hợp nhất nội dung text vào Word, thêm metric RAGAS, làm rõ Ke/Rf/beta và dọn format, bản này có thể lên mức khá chắc để gửi lại cô.
