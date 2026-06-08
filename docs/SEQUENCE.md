# Vietnam Pharma Equity Research Agent — Sơ đồ tuần tự UML

> Tài liệu này tổng hợp 6 sơ đồ tuần tự mô tả các luồng nghiệp vụ chính của hệ thống.
> Mọi tính toán tài chính được thực hiện bởi code-first engine xác định, không phải LLM.

---

## 01 — Luồng tạo Full Report

**Tiêu đề:** `01_full_report_sequence`

**Mô tả:** Mô tả toàn bộ hành trình từ khi Analyst yêu cầu báo cáo đến khi báo cáo được phê duyệt và xuất bản. Bao gồm các bước từ ingestion → canonical facts → valuation → report → evaluation gate → HITL approval → export.

**Mô tả tuần tự cách hoạt động:** Hệ thống multi-agent bắt đầu khi Analyst gửi yêu cầu tạo `full_report` cho một mã cổ phiếu cụ thể. Supervisor Agent là tác tử điều phối trung tâm, tiếp nhận yêu cầu, xác định ticker, nhận diện loại báo cáo cần sinh và kiểm tra yêu cầu có nằm trong phạm vi chính sách của hệ thống hay không. Nếu yêu cầu hợp lệ, Supervisor Agent khởi động pipeline ingest và chuyển nhiệm vụ sang Data Agent; nếu yêu cầu không hợp lệ hoặc nằm ngoài phạm vi đề tài, hệ thống dừng sớm để tránh tiêu tốn tài nguyên tính toán và hạn chế rủi ro sinh báo cáo không phù hợp.

Ở bước dữ liệu, Data Agent kiểm tra dữ liệu sẵn có, thu thập báo cáo tài chính, dữ liệu giá thị trường, tin tức và các tài liệu hỗ trợ từ những nguồn được phép sử dụng. Data Agent đồng thời tạo danh mục nguồn, loại bỏ dữ liệu trùng lặp và chuẩn bị payload đầu vào cho lớp xử lý dữ liệu. Sau đó, dịch vụ xử lý dữ liệu nội bộ thực hiện trích xuất, chuẩn hóa và chuyển đổi dữ liệu thô thành `canonical facts`, tức tập dữ kiện có cấu trúc thống nhất để các bước phân tích phía sau có thể sử dụng nhất quán. Các dữ kiện này phải vượt qua data quality gate, bao gồm kiểm tra tính đầy đủ, tính hợp lệ, tính nhất quán định lượng và khả năng truy xuất nguồn; nếu dữ liệu chưa đủ, hệ thống có thể đánh dấu thiếu dữ liệu thay vì tiếp tục với giả định không được kiểm chứng.

Khi `canonical facts` đã sẵn sàng, Supervisor Agent giao nhiệm vụ cho Financial Analysis Agent. Tác tử này sử dụng các engine tính toán xác định để tính chỉ số tài chính, phân tích xu hướng theo thời gian và phát hiện các bất thường trong dữ liệu, chẳng hạn biến động biên lợi nhuận, đòn bẩy tài chính, dòng tiền hoặc hiệu quả sử dụng vốn. Điều kiện chuyển bước là kết quả phân tích phải nhất quán với dữ liệu nguồn và có thể đối chiếu lại với các fact đã được lưu; các phép tính trọng yếu không được sinh tự do bởi LLM mà phải dựa trên code-first engine để bảo đảm khả năng tái lập.

Sau khi phân tích tài chính hoàn tất, Supervisor Agent chuyển artifact phân tích sang Valuation Agent. Valuation Agent xây dựng mô hình định giá, bao gồm DCF, P/E, EV/EBITDA và phân tích độ nhạy theo các giả định chính như WACC, tốc độ tăng trưởng dài hạn hoặc bội số so sánh. Trước khi tạo valuation artifact chính thức, hệ thống trình bày các assumption quan trọng cho Analyst phê duyệt theo cơ chế human-in-the-loop. Điều kiện chuyển bước là giả định phải được hiển thị minh bạch, kết quả định giá phải có thể tái tính, và khoảng giá trị hợp lý phải gắn với các tham số đầu vào cụ thể thay vì chỉ là nhận định định tính.

Khi valuation artifact được tạo, Supervisor Agent giao nhiệm vụ tổng hợp cho Report Agent. Report Agent xây dựng context từ `canonical facts`, kết quả phân tích tài chính và valuation artifact, sau đó sử dụng LLM để sinh narrative tiếng Việt cho bản nháp báo cáo. Mỗi nhận định quan trọng, đặc biệt là nhận định định lượng, khuyến nghị đầu tư, luận điểm rủi ro và diễn giải định giá, phải được gắn citation hoặc ánh xạ về nguồn dữ liệu hỗ trợ. Trước khi trả bản nháp về Supervisor Agent, Report Agent thực hiện kiểm định logic đầu ra nhằm phát hiện mâu thuẫn nội bộ, thiếu nguồn hoặc diễn giải vượt quá bằng chứng.

Cuối cùng, Supervisor Agent gửi bản nháp sang Export Gate để chạy các evaluation gates trước khi cho phép xuất bản. Export Gate không phải một agent độc lập mà là lớp kiểm định và chặn xuất bản, chịu trách nhiệm đánh giá tính nhất quán số liệu, độ phủ citation, tính hợp lệ của nguồn, độ mới của dữ liệu, khả năng tái lập định giá, tính hợp lệ của khuyến nghị và các ràng buộc kế toán cơ bản. Nếu tất cả gates đạt trạng thái PASS, báo cáo được gửi cho Analyst phê duyệt cuối; nếu Analyst approve, hệ thống xuất bản báo cáo, còn nếu Analyst reject, bản nháp được trả về để chỉnh sửa. Nếu có gate ở mức CRITICAL FAIL, Supervisor Agent chặn export và thông báo lỗi cho Analyst, bảo đảm báo cáo không được công bố khi chưa đạt chuẩn kiểm định tối thiểu.

```mermaid
sequenceDiagram
    participant Analyst
    participant Supervisor as Supervisor Agent
    participant DataAgent as Data Agent
    participant FAAgent as Financial Analysis Agent
    participant ValAgent as Valuation Agent
    participant ReportAgent as Report Agent
    participant ExportGate as Export Gate

    Analyst->>Supervisor: Yêu cầu full_report cho ticker
    activate Supervisor
    Supervisor->>Supervisor: Xác định ticker, loại báo cáo, kiểm tra policy
    Supervisor->>DataAgent: Khởi động pipeline ingest
    activate DataAgent
    DataAgent->>DataAgent: Thu thập BCTC, giá thị trường, tin tức
    DataAgent->>DataAgent: Chuẩn hóa → canonical facts
    DataAgent->>DataAgent: Data quality gate
    DataAgent-->>Supervisor: canonical facts sẵn sàng
    deactivate DataAgent

    Supervisor->>FAAgent: Phân tích tài chính
    activate FAAgent
    FAAgent->>FAAgent: Tính ratio, xu hướng (code-first engine)
    FAAgent->>FAAgent: Phát hiện bất thường
    FAAgent-->>Supervisor: Kết quả phân tích tài chính
    deactivate FAAgent

    Supervisor->>ValAgent: Định giá
    activate ValAgent
    ValAgent->>ValAgent: Chạy DCF, P/E, EV/EBITDA (code-first engine)
    ValAgent->>ValAgent: Sensitivity analysis
    ValAgent->>Analyst: Trình bày assumptions để duyệt
    Analyst-->>ValAgent: Phê duyệt assumptions
    ValAgent->>ValAgent: Tạo valuation artifact
    ValAgent-->>Supervisor: valuation artifact sẵn sàng
    deactivate ValAgent

    Supervisor->>ReportAgent: Tổng hợp và viết báo cáo
    activate ReportAgent
    ReportAgent->>ReportAgent: Xây dựng context từ facts và artifact
    ReportAgent->>ReportAgent: Sinh narrative tiếng Việt (LLM)
    ReportAgent->>ReportAgent: Gắn citation cho mọi claim
    ReportAgent->>ReportAgent: Kiểm định logic đầu ra
    ReportAgent-->>Supervisor: Bản nháp báo cáo
    deactivate ReportAgent

    Supervisor->>ExportGate: Chạy evaluation gates (7 cổng)
    activate ExportGate
    ExportGate-->>Supervisor: PASS / FAIL
    deactivate ExportGate

    alt Tất cả gates PASS
        Supervisor->>Analyst: Gửi báo cáo để phê duyệt cuối (HITL)
        Analyst-->>Supervisor: approve / reject + ghi chú
        alt Analyst approve
            Supervisor->>ExportGate: Xuất bản báo cáo
            ExportGate-->>Analyst: Báo cáo đã publish
        else Analyst reject
            Supervisor-->>Analyst: Trả về bản nháp để chỉnh sửa
        end
    else Có gate CRITICAL FAIL
        Supervisor-->>Analyst: Báo lỗi, chặn export
    end
    deactivate Supervisor
```

---

## 02 — Luồng Data Pipeline

**Tiêu đề:** `02_data_pipeline_sequence`

**Mô tả:** Mô tả chi tiết quá trình thu thập dữ liệu từ vnstock, chuẩn hóa thành canonical facts, kiểm tra chất lượng dữ liệu, và xây dựng retrieval index cho evidence. Đây là foundation cho mọi luồng phân tích.

```mermaid
sequenceDiagram
    participant Script as ingest_ticker.py
    participant Connector as vnstock Connector
    participant Registry as Source Registry
    participant Normalizer as Fact Normalizer
    participant DQGate as Data Quality Gate
    participant FactStore as Fact Store (DB)
    participant Indexer as Evidence Indexer

    Script->>Connector: Yêu cầu BCTC, giá, profile (ticker, years)
    activate Connector
    Connector->>Connector: Gọi vnstock API
    Connector->>Registry: Đăng ký source version (checksum)
    activate Registry
    Registry-->>Connector: source_version_id (bỏ qua nếu trùng)
    deactivate Registry
    Connector-->>Script: Raw payload + source_version_id
    deactivate Connector

    Script->>Normalizer: Chuẩn hóa raw payload
    activate Normalizer
    Normalizer->>Normalizer: Alias matching với taxonomy
    Normalizer->>Normalizer: Tạo FinancialFact rows
    Normalizer-->>Script: Danh sách canonical facts
    deactivate Normalizer

    Script->>DQGate: Kiểm tra chất lượng dữ liệu
    activate DQGate
    DQGate->>DQGate: Kiểm tra completeness (3 tiers)
    DQGate->>DQGate: Kiểm tra giá trị ngoại lệ
    DQGate->>DQGate: Kiểm tra nguồn hợp lệ

    alt Fact hợp lệ
        DQGate-->>Script: accepted / accepted_with_warning
    else Fact lỗi
        DQGate-->>Script: needs_review / rejected
    end
    deactivate DQGate

    Script->>FactStore: Upsert canonical facts đã qua gate
    activate FactStore
    FactStore-->>Script: Xác nhận lưu thành công
    deactivate FactStore

    Script->>Indexer: Xây dựng evidence index
    activate Indexer
    Indexer->>Indexer: Chunk tài liệu nguồn
    Indexer->>Indexer: Tạo embedding và citation map
    Indexer->>Indexer: Lưu vào Milvus
    Indexer-->>Script: Index và citation map sẵn sàng
    deactivate Indexer
```

---

## 03 — Luồng phối hợp Multi-Agent

**Tiêu đề:** `03_multi_agent_orchestration_sequence`

**Mô tả:** Thể hiện cách 5 agent tương tác và phân công nhiệm vụ qua Supervisor Agent. Phân biệt rõ vai trò agent (LLM-assisted reasoning) với service xác định (code-first). Supervisor điều phối toàn bộ workflow và quản lý checkpoint.

```mermaid
sequenceDiagram
    participant Analyst
    participant Supervisor as Supervisor Agent
    participant TaskRouter as Task Router
    participant DataAgent as Data Agent
    participant FAAgent as Financial Analysis Agent
    participant ValAgent as Valuation Agent
    participant ReportAgent as Report Agent

    Analyst->>Supervisor: Yêu cầu nghiên cứu (ticker, loại báo cáo)
    activate Supervisor
    Supervisor->>TaskRouter: Phân tích yêu cầu
    activate TaskRouter
    TaskRouter->>TaskRouter: Xác định ticker, loại báo cáo
    TaskRouter->>TaskRouter: Kiểm tra policy
    TaskRouter-->>Supervisor: Kế hoạch thực thi
    deactivate TaskRouter

    Supervisor->>DataAgent: Giao nhiệm vụ thu thập dữ liệu
    activate DataAgent
    DataAgent->>DataAgent: Data retrieval (vnstock connectors)
    DataAgent->>DataAgent: Source ranking và dedup
    DataAgent-->>Supervisor: canonical facts + source versions
    deactivate DataAgent
    Supervisor->>Supervisor: Lưu checkpoint (sau Data Agent)

    Supervisor->>FAAgent: Giao nhiệm vụ phân tích tài chính
    activate FAAgent
    FAAgent->>FAAgent: Data cleaning, normalization (code)
    FAAgent->>FAAgent: Ratio engine: gross margin, ROE, ROA (code)
    FAAgent->>FAAgent: Phát hiện bất thường (code + LLM)
    FAAgent-->>Supervisor: Kết quả phân tích
    deactivate FAAgent
    Supervisor->>Supervisor: Lưu checkpoint (sau FA Agent)

    Supervisor->>ValAgent: Giao nhiệm vụ định giá
    activate ValAgent
    ValAgent->>ValAgent: DCF, FCFF, FCFE (code-first engine)
    ValAgent->>ValAgent: P/E, EV/EBITDA comparables (code)
    ValAgent->>ValAgent: Sensitivity analysis (code)
    ValAgent-->>Supervisor: valuation artifact
    deactivate ValAgent
    Supervisor->>Supervisor: Lưu checkpoint (sau Valuation Agent)

    Supervisor->>ReportAgent: Giao nhiệm vụ tổng hợp báo cáo
    activate ReportAgent
    ReportAgent->>ReportAgent: Report generation (LLM narrative)
    ReportAgent->>ReportAgent: Citation check (deterministic)
    ReportAgent->>ReportAgent: Validation checklist
    ReportAgent-->>Supervisor: Bản nháp báo cáo + citation map
    deactivate ReportAgent

    Supervisor-->>Analyst: Bản nháp sẵn sàng để review
    deactivate Supervisor
```

---

## 04 — Luồng Định giá và HITL Approval

**Tiêu đề:** `04_valuation_hitl_sequence`

**Mô tả:** Mô tả chi tiết quá trình Valuation Agent chạy các mô hình định giá xác định, đề xuất assumptions, và yêu cầu Analyst phê duyệt trước khi tạo valuation artifact chính thức. Toàn bộ tính toán là code-first, không dùng LLM.

```mermaid
sequenceDiagram
    participant Supervisor as Supervisor Agent
    participant ValAgent as Valuation Agent
    participant FCFFEngine as FCFF Engine (code)
    participant FCFEEngine as FCFE Engine (code)
    participant BlendEngine as Blend 60/40 Engine (code)
    participant SensEngine as Sensitivity Engine (code)
    participant Analyst

    Supervisor->>ValAgent: Chạy định giá cho ticker
    activate ValAgent
    ValAgent->>ValAgent: Tải canonical facts từ DB
    ValAgent->>ValAgent: Tải tax policy, debt schedule

    ValAgent->>Analyst: Đề xuất assumptions (WACC, g, target P/E)
    activate Analyst
    Analyst-->>ValAgent: Phê duyệt / điều chỉnh assumptions
    deactivate Analyst

    ValAgent->>FCFFEngine: Chạy FCFF DCF (WACC, terminal growth)
    activate FCFFEngine
    FCFFEngine->>FCFFEngine: EBIT(1-T) + D&A - CAPEX - delta_NWC
    FCFFEngine->>FCFFEngine: Chiết khấu WACC, bridge EV -> Equity
    FCFFEngine-->>ValAgent: FCFF target price (60% trọng số)
    deactivate FCFFEngine

    ValAgent->>FCFEEngine: Chạy FCFE DCF (cost of equity)
    activate FCFEEngine
    FCFEEngine->>FCFEEngine: NI + D&A - CAPEX - delta_NWC + Net Borrowing
    FCFEEngine->>FCFEEngine: Chiết khấu Re, Equity Value trực tiếp
    FCFEEngine-->>ValAgent: FCFE target price (40% trọng số)
    deactivate FCFEEngine

    ValAgent->>BlendEngine: Tổng hợp Blend 60% FCFF + 40% FCFE
    activate BlendEngine
    BlendEngine->>BlendEngine: Kiểm tra TV weight < 70%
    BlendEngine->>BlendEngine: Kiểm tra FCFF/FCFE gap < 25%
    BlendEngine-->>ValAgent: Blend target price
    deactivate BlendEngine

    ValAgent->>SensEngine: Chạy sensitivity analysis
    activate SensEngine
    SensEngine->>SensEngine: Grid WACC x terminal growth (FCFF)
    SensEngine->>SensEngine: Grid Re x g (FCFE)
    SensEngine->>SensEngine: P/E matrix, EV/EBITDA matrix
    SensEngine-->>ValAgent: Sensitivity tables
    deactivate SensEngine

    ValAgent->>ValAgent: Đóng gói valuation artifact (JSON)
    ValAgent->>ValAgent: Ghi valuation confidence (high/medium/low)

    opt Assumption Gate chưa được duyệt
        ValAgent->>Analyst: Yêu cầu xác nhận lại assumptions
        Analyst-->>ValAgent: Xác nhận
    end

    ValAgent-->>Supervisor: valuation artifact hoàn chỉnh
    deactivate ValAgent
```

---

## 05 — Luồng Sinh báo cáo, Citation và Evaluation Gate

**Tiêu đề:** `05_report_citation_evaluation_sequence`

**Mô tả:** Mô tả chi tiết quá trình Report Agent sinh narrative, gắn citation cho từng claim, và hệ thống chạy 7 evaluation gates xác định trước khi mở Export Gate. Phân biệt rõ bước LLM (narrative) và bước deterministic (citation, numeric check).

```mermaid
sequenceDiagram
    participant Supervisor as Supervisor Agent
    participant ReportAgent as Report Agent
    participant CtxBuilder as Context Builder (service)
    participant LLMWriter as LLM Narrative Writer
    participant CitationSvc as Citation Service (service)
    participant EvalGate as Evaluation Gate (service)
    participant Analyst

    Supervisor->>ReportAgent: Tạo full_report
    activate ReportAgent

    ReportAgent->>CtxBuilder: Xây dựng context cho báo cáo
    activate CtxBuilder
    CtxBuilder->>CtxBuilder: Nạp canonical facts đã được duyệt
    CtxBuilder->>CtxBuilder: Nạp valuation artifact
    CtxBuilder->>CtxBuilder: Truy vấn evidence index (Milvus)
    CtxBuilder-->>ReportAgent: Structured context (facts + evidence)
    deactivate CtxBuilder

    ReportAgent->>LLMWriter: Sinh narrative tiếng Việt
    activate LLMWriter
    LLMWriter->>LLMWriter: Viết 8 sections (LLM, grounded context)
    LLMWriter->>LLMWriter: Sinh tóm tắt rủi ro, luận điểm đầu tư
    LLMWriter-->>ReportAgent: Bản nháp narrative
    deactivate LLMWriter

    ReportAgent->>CitationSvc: Gắn citation cho mọi claim định lượng
    activate CitationSvc
    CitationSvc->>CitationSvc: Trích xuất claim theo pattern
    CitationSvc->>CitationSvc: Map claim -> fact row / document chunk
    CitationSvc->>CitationSvc: Đánh dấu grounding_status
    CitationSvc-->>ReportAgent: Báo cáo + citation map đầy đủ
    deactivate CitationSvc

    ReportAgent-->>Supervisor: Bản nháp báo cáo có citation
    deactivate ReportAgent

    Supervisor->>EvalGate: Chạy 7 evaluation gates
    activate EvalGate
    EvalGate->>EvalGate: Gate 1: Numeric consistency (deterministic)
    EvalGate->>EvalGate: Gate 2: Citation coverage >= 90% (deterministic)
    EvalGate->>EvalGate: Gate 3: Citation validity (deterministic + LLM)
    EvalGate->>EvalGate: Gate 4: Stale data < 18 tháng (deterministic)
    EvalGate->>EvalGate: Gate 5: Valuation reproducibility (deterministic)
    EvalGate->>EvalGate: Gate 6: Unsupported recommendation (regex + LLM)
    EvalGate->>EvalGate: Gate 7: Balance sheet identity (deterministic)

    alt Tất cả gates PASS
        EvalGate-->>Supervisor: PASS - cho phép tiến tới HITL
    else Có CRITICAL FAIL
        EvalGate-->>Supervisor: FAIL - chặn export, liệt kê lỗi
        Supervisor-->>Analyst: Báo lỗi evaluation, yêu cầu xử lý
    end
    deactivate EvalGate
```

---

## 06 — Luồng Catalyst Refresh

**Tiêu đề:** `06_catalyst_refresh_sequence`

**Mô tả:** Mô tả luồng xử lý khi có sự kiện catalyst mới (tin tức, chính sách, kết quả đấu thầu). Hệ thống thực hiện partial recompute chỉ những phần bị ảnh hưởng thay vì chạy lại toàn bộ pipeline, sau đó sinh catalyst_refresh memo.

```mermaid
sequenceDiagram
    participant Scheduler as APScheduler
    participant Supervisor as Supervisor Agent
    participant DataAgent as Data Agent
    participant FAAgent as Financial Analysis Agent
    participant ValAgent as Valuation Agent
    participant ReportAgent as Report Agent
    participant Analyst

    Scheduler->>Supervisor: Phát hiện catalyst mới (ticker, event_type)
    activate Supervisor
    Supervisor->>Supervisor: Đánh giá materiality_hint (high/medium/low)
    Supervisor->>Supervisor: Xác định phạm vi recompute cần thiết

    Supervisor->>DataAgent: Ingest catalyst event mới
    activate DataAgent
    DataAgent->>DataAgent: Gọi connector phù hợp (HOSE/BHYT/DAV/tender)
    DataAgent->>DataAgent: Đăng ký source version mới
    DataAgent->>DataAgent: Cập nhật catalyst_events trong DB
    DataAgent-->>Supervisor: Catalyst event đã được lưu
    deactivate DataAgent

    alt materiality_hint = high (cần recompute tài chính)
        Supervisor->>FAAgent: Recompute phân tích bị ảnh hưởng
        activate FAAgent
        FAAgent->>FAAgent: Cập nhật facts liên quan
        FAAgent->>FAAgent: Tính lại ratio bị ảnh hưởng (code)
        FAAgent-->>Supervisor: Facts và ratio đã cập nhật
        deactivate FAAgent

        Supervisor->>ValAgent: Partial recompute định giá
        activate ValAgent
        ValAgent->>ValAgent: Cập nhật assumptions nếu cần
        ValAgent->>ValAgent: Chạy lại DCF / Blend (code-first)
        ValAgent->>ValAgent: Cập nhật valuation artifact
        ValAgent-->>Supervisor: valuation artifact mới
        deactivate ValAgent
    end

    Supervisor->>ReportAgent: Sinh catalyst_refresh memo
    activate ReportAgent
    ReportAgent->>ReportAgent: Tóm tắt catalyst và tác động (LLM)
    ReportAgent->>ReportAgent: So sánh target price trước/sau nếu có recompute
    ReportAgent->>ReportAgent: Gắn citation cho catalyst event
    ReportAgent-->>Supervisor: Bản nháp catalyst_refresh
    deactivate ReportAgent

    Supervisor->>Analyst: Gửi catalyst_refresh để xem xét
    activate Analyst
    Analyst-->>Supervisor: approve / reject
    deactivate Analyst

    alt Analyst approve
        Supervisor->>Supervisor: Publish catalyst_refresh memo
        Supervisor-->>Analyst: Memo đã được xuất bản
    else Analyst reject
        Supervisor-->>Analyst: Trả về để chỉnh sửa
    end
    deactivate Supervisor
```
