# Kiểm định sequence và flow của hệ thống

Cập nhật theo mã nguồn hiện tại: 2026-06-13

## Context

Tài liệu này mô tả các luồng chính đang được triển khai trong dự án `multi-agent-equity-research`. Nội dung được đối chiếu với các điểm thực thi chính: `scripts/run_research.py`, `backend/api.py`, `backend/orchestrator.py`, `backend/harness/graph.py`, `backend/harness/runner.py`, `backend/harness/gates.py`, `backend/runtime_store.py`, `backend/storage/layout.py` và lớp xuất báo cáo.

Mục tiêu của tài liệu là cung cấp bộ sơ đồ đủ chi tiết để đưa vào đồ án, nhưng mỗi sơ đồ chỉ mô tả một lát cắt nghiệp vụ hoặc kỹ thuật rõ ràng. Cách chia này giúp người đọc hiểu hệ thống theo từng tầng: đầu vào, dữ liệu, kiểm định, định giá, báo cáo, xuất bản và hậu kiểm chuyên gia.

## Problem Statement

Luồng hiện tại không phải là một hệ thống trò chuyện đơn lẻ và cũng không phải một quy trình phê duyệt thủ công nhiều tầng. Hệ thống là một pipeline nghiên cứu tự động có điều phối trạng thái, công cụ tất định, agent chuyên trách, cổng kiểm định tự động, tệp kết quả theo `run_id`, gói bằng chứng và báo cáo HTML/PDF.

Pipeline sản xuất hiện có đúng chín chặng:

```text
PREFLIGHT
-> PLAN
-> INGEST_AND_VALIDATE
-> ANALYZE
-> FORECAST_AND_VALUE
-> WRITE_REPORT
-> REVIEW
-> EXPORT_GATES
-> PUBLISH
```

Khi một cổng kiểm định nghiêm trọng thất bại, bộ chạy nghiên cứu (`ResearchGraphRunner`) đặt trạng thái run thành `blocked`, ghi `blocking_reason`, lưu checkpoint và dừng trước chặng tiếp theo. Khi toàn bộ cổng kiểm định đạt yêu cầu, chặng `PUBLISH` tự xuất báo cáo, lưu `report.html` và `report.pdf` trong bucket `runs`, sau đó trạng thái cơ sở dữ liệu chuyển thành `auto_exported`; API ánh xạ trạng thái này thành `PUBLISHED_DRAFT`. Tên `auto_exported` thể hiện rõ đây là báo cáo tự xuất sau khi cổng tự động đạt, không phải chữ ký phê duyệt thủ công.

Đánh giá chuyên gia sau đầu ra là hoạt động hậu kiểm, không phải cổng chặn nằm giữa `EXPORT_GATES` và `PUBLISH`. Điều này cần được trình bày rõ trong đồ án để tránh nhầm giữa kiểm định tự động trong runtime và phản hồi chuyên gia sau khi báo cáo đã được tạo.

## Technical Deep-Dive

### 1. Bản đồ tổng quan hệ thống

Sơ đồ này mô tả các khối lớn của hệ thống, không đi sâu vào từng agent.

```mermaid
flowchart TD
    U["Người dùng hoặc hệ thống gọi"]
    CLI["Lệnh chạy nghiên cứu (CLI)"]
    API["Giao diện lập trình (API)"]
    O["Bộ điều phối báo cáo đầy đủ (FullReportOrchestrator)"]
    R["Bộ chạy nghiên cứu (ResearchGraphRunner)"]
    DB["Cơ sở dữ liệu PostgreSQL/Supabase"]
    ST["Kho tệp Supabase Storage"]
    LLM["Mô hình ngôn ngữ (LLM)"]
    T["Công cụ tất định"]
    G["Cổng kiểm định tự động"]
    P["Bộ xuất báo cáo khách hàng (ClientReportPublisher)"]
    E["Chuyên gia hậu kiểm"]

    U --> CLI
    U --> API
    CLI --> O
    API --> O
    O --> R
    R --> DB
    R --> ST
    R --> LLM
    R --> T
    R --> G
    G --> R
    R --> P
    P --> ST
    ST --> E
```

Ý nghĩa chính: orchestration chỉ là lớp điều phối, còn toàn bộ trình tự thực thi và dừng chặn nằm trong `ResearchGraphRunner`.

### 2. Luồng khởi tạo bằng CLI

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant CLI as Lệnh chạy nghiên cứu (run_research.py)
    participant S as Kho runtime (RuntimeStore)
    participant REG as Đăng ký mã cổ phiếu
    participant O as Bộ điều phối (FullReportOrchestrator)
    participant R as Bộ chạy nghiên cứu (ResearchGraphRunner)

    U->>CLI: Nhập mã cổ phiếu, năm bắt đầu, năm kết thúc, tùy chọn OCR
    CLI->>CLI: Tạo run_id và chính sách chạy
    CLI->>S: Kiểm tra phiên bản schema
    CLI->>REG: Đảm bảo mã cổ phiếu có trong universe
    CLI->>S: Tạo run với trạng thái initialized
    CLI->>O: Gửi RunContext
    O->>O: Chỉ chấp nhận run_type = full_report
    O->>R: Thực thi pipeline chín chặng
    R-->>CLI: Trả trạng thái cuối cùng của run
```

Đặc điểm của CLI là chạy đồng bộ: lệnh chờ pipeline hoàn thành hoặc dừng lỗi.

### 3. Luồng khởi tạo bằng API

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng hoặc frontend
    participant API as API FastAPI
    participant S as Kho runtime (RuntimeStore)
    participant EX as Bộ thực thi nền (RunExecutor)
    participant O as Bộ điều phối (FullReportOrchestrator)
    participant R as Bộ chạy nghiên cứu (ResearchGraphRunner)

    U->>API: POST /research/start
    API->>API: Chuẩn hóa ticker, objective và policy
    API->>S: Đăng ký ticker và tạo run
    API->>EX: Submit RunContext vào ThreadPoolExecutor
    API-->>U: Trả run_id và trạng thái INIT
    EX->>O: Gọi execute(context) trong nền
    O->>R: Chạy pipeline chín chặng
    U->>API: GET /research/{run_id}/status
    API->>S: Đọc trạng thái run
    API-->>U: Trả trạng thái công khai
```

Đặc điểm của API là trả `run_id` sớm; người dùng theo dõi tiến độ bằng endpoint trạng thái.

### 4. Bản đồ chín chặng runtime

```mermaid
flowchart TD
    A["PREFLIGHT<br/>Kiểm tra run_type, ticker, schema, agent, tool và môi trường mô hình"]
    B["PLAN<br/>Tạo kế hoạch nghiên cứu tất định từ template cố định (không gọi LLM)"]
    C["INGEST_AND_VALIDATE<br/>Tái dùng snapshot hoặc thu thập tài liệu, xây facts, xây chỉ mục bằng chứng"]
    D["ANALYZE<br/>Đọc snapshot, đọc tỷ số tài chính, tạo phân tích tài chính"]
    E["FORECAST_AND_VALUE<br/>Dự phóng tất định, diễn giải dự phóng, định giá tất định"]
    F["WRITE_REPORT<br/>Viết bản nháp có nguồn và lắp ráp mô hình báo cáo cuối"]
    G["REVIEW<br/>Kiểm tra độ đầy đủ, chất lượng, phản biện và trích dẫn"]
    H["EXPORT_GATES<br/>Kiểm định quyền tool, manifest, công thức, gói bằng chứng và khả năng xuất"]
    I["PUBLISH<br/>Xuất báo cáo HTML/PDF và chuyển run thành auto_exported"]
    X["BLOCKED<br/>Ghi blocking_reason, lưu checkpoint và dừng"]
    Y["FAILED<br/>Ghi lỗi khi có exception hoặc render lỗi"]

    A --> B --> C --> D --> E --> F --> G --> H --> I
    C -. "cổng nghiêm trọng thất bại" .-> X
    D -. "cổng nghiêm trọng thất bại" .-> X
    E -. "cổng nghiêm trọng thất bại" .-> X
    F -. "cổng nghiêm trọng thất bại" .-> X
    G -. "cổng nghiêm trọng thất bại" .-> X
    H -. "cổng nghiêm trọng thất bại" .-> X
    A -. "exception" .-> Y
    B -. "exception" .-> Y
    I -. "render lỗi" .-> Y
```

### 5. Luồng tiền kiểm và lập kế hoạch

```mermaid
sequenceDiagram
    autonumber
    participant R as Bộ chạy nghiên cứu (ResearchGraphRunner)
    participant S as Kho runtime (RuntimeStore)
    participant AR as Sổ đăng ký agent (AgentRegistry)
    participant TR as Sổ đăng ký công cụ (ToolRegistry)
    participant M as Bộ gọi mô hình (ModelAdapter)
    participant A as Quản lý nghiên cứu (ResearchManagerAgent)

    R->>S: Kiểm tra schema bắt buộc
    R->>AR: Nạp cấu hình 6 agent
    R->>TR: Kiểm tra quyền công cụ theo từng agent
    R->>M: Kiểm tra biến môi trường và thư viện mô hình
    R->>R: Dựng kế hoạch nghiên cứu tất định từ template (không gọi LLM)
    R->>S: Lưu research_plan, artifact và checkpoint
```

Chặng `PLAN` dựng kế hoạch nghiên cứu tất định từ template cố định (`_deterministic_research_plan`), không gọi LLM. Vai trò `research_manager` vẫn được cấu hình trong registry nhưng không được gọi ở chặng này. Kế hoạch vẫn tuân theo hợp đồng `ResearchManagerArtifact`.

### 6. Luồng dữ liệu có tái dùng snapshot

```mermaid
sequenceDiagram
    autonumber
    participant R as Bộ chạy nghiên cứu
    participant F as Kiểm tra độ mới snapshot
    participant T as Công cụ dữ liệu tất định
    participant G as Cổng chất lượng dữ liệu
    participant S as Kho runtime

    R->>F: Tìm snapshot mới nhất đã sẵn sàng theo ticker
    alt Có snapshot còn mới và không ép ingest lại
        R->>T: build_facts từ dữ liệu đã có
        T-->>R: Trả snapshot_id và tóm tắt facts
        R->>R: Đánh dấu chỉ mục bằng chứng được tái dùng
    else Không có snapshot phù hợp
        R->>T: auto_ingest tài liệu chính thức
        T-->>R: Trả metadata tài liệu và nguồn
        par Xây dữ liệu tài chính
            R->>T: build_facts
            T-->>R: Trả facts chuẩn hóa và snapshot
        and Xây chỉ mục bằng chứng
            R->>T: build_index
            T-->>R: Trả chỉ mục truy xuất bằng chứng
        end
    end
    R->>G: DATA_QUALITY_GATE
    G-->>R: pass hoặc fail
    R->>S: Lưu tool trace, artifact refs, gate result và checkpoint
```

Trong runtime hiện tại, `DataEvidenceAgent` là vai trò sở hữu công cụ, nhưng runner gọi trực tiếp các công cụ tất định; không có lời gọi LLM riêng cho `DataEvidenceAgent` ở chặng này.

### 7. Luồng OCR và thăng cấp facts

Sơ đồ này mô tả nhánh dữ liệu tài liệu khi gặp PDF quét hoặc PDF không có lớp chữ đáng tin cậy.

```mermaid
flowchart TD
    A["Tài liệu chính thức dạng PDF"]
    B{"PDF có lớp chữ đáng tin cậy?"}
    C["Trích xuất trực tiếp bằng pdfplumber"]
    D["OCR bằng Tesseract và Poppler"]
    E["Ứng viên dữ liệu tài chính"]
    F["Kiểm tra đơn vị, kỳ, ticker và nguồn"]
    G{"Đối chiếu được với nguồn hoặc quy tắc?"}
    H["Thăng cấp thành fact chuẩn (canonical fact)"]
    I["Giữ ở vùng staging và ghi lý do chặn"]
    J["Snapshot nghiên cứu theo run"]

    A --> B
    B -- "Có" --> C
    B -- "Không" --> D
    C --> E
    D --> E
    E --> F
    F --> G
    G -- "Đạt" --> H
    G -- "Không đạt" --> I
    H --> J
```

OCR chỉ tạo dữ liệu ứng viên. Số liệu chỉ được dùng cho báo cáo sau khi vượt qua kiểm tra và được thăng cấp thành fact chuẩn.

### 8. Luồng fact, snapshot và bằng chứng

```mermaid
flowchart LR
    A["Nguồn chính thức và dữ liệu thị trường"]
    B["Tài liệu nguồn (source_documents)"]
    C["Quan sát thô (observations)"]
    D["Fact chuẩn (canonical_facts)"]
    E["Snapshot nghiên cứu"]
    F["Tệp phân tích và định giá"]
    G["Gói bằng chứng (evidence_pack.json)"]
    H["Báo cáo có trích dẫn"]

    A --> B
    B --> C
    C --> D
    D --> E
    E --> F
    F --> G
    G --> H
```

Quy tắc quan trọng: báo cáo không đọc dữ liệu sống trực tiếp. Báo cáo dùng snapshot đã đóng băng và artifact theo `run_id`.

### 9. Luồng phân tích tài chính

```mermaid
sequenceDiagram
    autonumber
    participant R as Bộ chạy nghiên cứu
    participant T as Công cụ tất định
    participant A as Phân tích tài chính (FinancialAnalysisAgent)
    participant G as Cổng kiểm định
    participant S as Kho runtime

    R->>T: read_snapshot(ticker, snapshot_id)
    T-->>R: Snapshot tài chính đã đóng băng
    R->>T: read_ratio_artifact(ticker, snapshot_id)
    T-->>R: Tỷ số và bảng phân tích định lượng
    R->>A: Tạo phân tích tài chính có dẫn chiếu metric và kỳ
    A-->>R: FinancialAnalysis
    R->>G: FINANCIAL_ANALYST_GATE
    G-->>R: pass hoặc fail
    R->>S: Lưu phân tích, trace, gate result và checkpoint
```

Agent được dùng để diễn giải và cấu trúc nhận định; phép tính số liệu chính vẫn do công cụ Python thực hiện.

### 10. Luồng dự phóng và định giá

```mermaid
sequenceDiagram
    autonumber
    participant R as Bộ chạy nghiên cứu
    participant T as Công cụ định lượng
    participant A as Dự phóng và định giá (ForecastValuationAgent)
    participant G as Cổng kiểm định
    participant S as Kho runtime

    R->>T: run_forecast(ticker, snapshot_id, from_year, to_year)
    T-->>R: Mô hình dự phóng tất định
    alt Chế độ bình thường
        R->>A: Tạo diễn giải dự phóng có cấu trúc
        A-->>R: ForecastValuationArtifact
    else Chế độ nháp nhanh
        R->>R: Tạo diễn giải dự phóng tất định
    end
    R->>G: FORECAST_QUALITY_GATE
    G-->>R: pass hoặc block
    R->>T: run_valuation(auto_approve_assumptions=True)
    T-->>R: Valuation artifact, assumptions, công thức và sensitivity
    R->>T: read_valuation_artifact(storage_path)
    T-->>R: Valuation artifact đã đọc lại
    R->>G: VALUATION_GATE
    R->>G: VALUATION_RECONCILIATION_GATE
    R->>R: Tạo research_lock
    R->>S: Lưu valuation, formula trace, gates và checkpoint
```

Runtime hiện tại không dừng để chờ chuyên gia phê duyệt giả định định giá. Cờ `auto_approve_assumptions` trong CLI policy được ghi vào policy, nhưng lời gọi valuation trong runner đang truyền `auto_approve_assumptions=True`.

### 11. Luồng viết báo cáo

```mermaid
sequenceDiagram
    autonumber
    participant R as Bộ chạy nghiên cứu
    participant W as Người viết luận điểm (ThesisReportAgent)
    participant A as Bộ lắp ráp báo cáo (ReportAssembler)
    participant G as Cổng lắp ráp báo cáo
    participant S as Kho runtime

    R->>W: Viết bản nháp từ plan, facts, phân tích, dự phóng và định giá
    W-->>R: ReportDraft có claims và citation map
    R->>A: Validate cấu trúc bản nháp và artifact đầu vào
    alt Bản nháp hợp lệ
        A-->>R: final_report_model
        R->>G: REPORT_ASSEMBLY_GATE pass
        R->>S: Lưu final_report_model
    else Bản nháp không hợp lệ
        A-->>R: Danh sách lỗi
        R->>G: REPORT_ASSEMBLY_GATE fail
        R->>S: Chuyển run thành blocked
    end
```

`ReportAssembler` không tự sáng tạo nội dung mới; nhiệm vụ của nó là kiểm tra và sắp xếp các đầu vào đã có thành mô hình báo cáo cuối.

### 12. Luồng review (phản biện, không tự sửa)

```mermaid
sequenceDiagram
    autonumber
    participant R as Bộ chạy nghiên cứu
    participant Q as Công cụ đánh giá chất lượng
    participant C as Phản biện cấp cao (SeniorCriticAgent)
    participant G as Cổng review và trích dẫn
    participant S as Kho runtime

    R->>G: REPORT_COMPLETENESS_GATE
    R->>Q: evaluate_report_quality(ticker, report_path, valuation_path)
    Q-->>R: Quality summary
    R->>C: Tạo scorecard và findings
    C-->>R: CriticReview
    R->>G: SENIOR_CRITIC_GATE
    R->>G: CITATION_GATE
    R->>S: Lưu gate results và checkpoint
```

Chặng REVIEW không tự sửa báo cáo. Phản biện cấp cao chỉ tạo `findings`; nếu có phát hiện nghiêm trọng thì `SENIOR_CRITIC_GATE` chặn run. Nhánh tự sửa một lần (auto-repair) đã được loại bỏ vì bản sửa trước đây không được chạy lại qua assembler và các cổng nên không bao giờ tới khâu render.

### 13. Luồng kiểm định xuất bản

```mermaid
sequenceDiagram
    autonumber
    participant R as Bộ chạy nghiên cứu
    participant ST as Kho tệp Supabase Storage
    participant G as Cổng kiểm định tất định
    participant S as Kho runtime

    R->>ST: Ghi evidence_pack.json
    R->>G: PACKAGE_VALIDATION_GATE
    Note over G: Gộp nội bộ tool permission, manifest, formula trace,<br/>evidence packet và tổng hợp xuất bản trong một cổng
    alt Có cổng nghiêm trọng thất bại
        G-->>R: fail với blocking_reasons
        R->>S: Cập nhật status = blocked
    else Tất cả cổng đạt
        G-->>R: pass
        R->>S: Lưu quality_gate và checkpoint
    end
```

`PACKAGE_VALIDATION_GATE` không hỏi phê duyệt con người. Cổng này chạy nội bộ các kiểm tra tool permission, manifest, formula trace và evidence packet, rồi tổng hợp lỗi từ kết quả đánh giá chất lượng, liên kết snapshot, trạng thái formula trace và các điều kiện xuất bản định lượng — tất cả gói trong một kết quả cổng duy nhất.

### 14. Luồng xuất báo cáo

```mermaid
sequenceDiagram
    autonumber
    participant R as Bộ chạy nghiên cứu
    participant S as Kho runtime
    participant ST as Kho tệp Supabase Storage
    participant P as Bộ xuất báo cáo khách hàng (ClientReportPublisher)

    R->>R: Kiểm tra final_report_model có tồn tại
    alt Thiếu final_report_model
        R->>S: status = blocked, blocking_reason = final_report_model_missing_for_render
    else Có final_report_model
        R->>ST: Ghi manifest.json trước render nếu cần
        R->>P: publish(run_id, ticker, mode = client_final)
        P->>ST: Đọc artifact theo manifest và run_id
        P->>P: Dựng view model, section và chart
        P->>ST: Upload report.html vào bucket runs
        P->>ST: Upload report.pdf vào bucket runs
        R->>S: Lưu artifact refs đã xuất
        R->>S: status = auto_exported, current_stage = PUBLISH
    end
```

Đường xuất báo cáo hiện tại ghi HTML/PDF vào bucket `runs` theo khóa `{run_id}/report.html` và `{run_id}/report.pdf`. Bucket `exports` vẫn tồn tại trong storage contract, nhưng publish path hiện tại của runner không ghi bản sao vào bucket này.

### 15. Luồng artifact theo run_id

```mermaid
flowchart TD
    A["run_id"]
    B["facts_snapshot.json"]
    C["forecast.json"]
    D["valuation.json"]
    E["evidence_pack.json"]
    F["quality_gate.json"]
    G["manifest.json"]
    H["report.html"]
    I["report.pdf"]
    J["research.run_artifacts"]

    A --> B
    A --> C
    A --> D
    A --> E
    A --> F
    A --> G
    A --> H
    A --> I
    B --> J
    C --> J
    D --> J
    E --> J
    F --> J
    H --> J
    I --> J
```

Quy tắc trình bày trong đồ án: mọi artifact sản xuất phải được truy theo `run_id` và manifest. Không dùng cách tìm tệp mới nhất theo timestamp để dựng báo cáo.

### 16. Luồng trạng thái runtime

```mermaid
stateDiagram-v2
    [*] --> initialized
    initialized --> running: PREFLIGHT / PLAN / INGEST_AND_VALIDATE
    running --> analysis_ready: ANALYZE
    analysis_ready --> valuation_ready: FORECAST_AND_VALUE
    valuation_ready --> report_ready: WRITE_REPORT
    report_ready --> report_ready: REVIEW / EXPORT_GATES
    report_ready --> auto_exported: PUBLISH thành công
    running --> blocked: cổng nghiêm trọng fail
    analysis_ready --> blocked: cổng nghiêm trọng fail
    valuation_ready --> blocked: cổng nghiêm trọng fail
    report_ready --> blocked: cổng nghiêm trọng fail
    initialized --> failed: exception
    running --> failed: exception
    analysis_ready --> failed: exception
    valuation_ready --> failed: exception
    report_ready --> failed: render hoặc exception
    auto_exported --> [*]
    blocked --> [*]
    failed --> [*]
```

`needs_human_review` không phải trạng thái runtime hiện tại của `ResearchGraphState`. Trạng thái bị chặn hiện tại là `blocked`.

### 17. Luồng ánh xạ trạng thái API

```mermaid
flowchart LR
    A["initialized"] --> A1["INIT"]
    B["running"] --> B1["ANALYZING"]
    C["analysis_ready"] --> C1["ANALYZING"]
    D["valuation_ready"] --> D1["VALUATING"]
    E["report_ready"] --> E1["SYNTHESIZING"]
    F["blocked"] --> F1["BLOCKED"]
    G["auto_exported"] --> G1["PUBLISHED_DRAFT"]
    H["failed"] --> H1["FAILED"]
    I["cancelled"] --> I1["FAILED"]
```

Trong giao diện công khai, `auto_exported` của cơ sở dữ liệu được hiển thị là `PUBLISHED_DRAFT`. Tên này nên được hiểu là run đã vượt qua cổng tự động và đã xuất báo cáo, không phải chữ ký phê duyệt thủ công của chuyên gia. Các run cũ trước migration 035 còn trạng thái `approved` vẫn ánh xạ về `PUBLISHED`.

### 18. Luồng tham gia của agent và công cụ

```mermaid
flowchart TD
    RM["Quản lý nghiên cứu (ResearchManagerAgent)"]
    DE["Bằng chứng dữ liệu (DataEvidenceAgent)"]
    FA["Phân tích tài chính (FinancialAnalysisAgent)"]
    FV["Dự phóng định giá (ForecastValuationAgent)"]
    TR["Viết luận điểm (ThesisReportAgent)"]
    SC["Phản biện cấp cao (SeniorCriticAgent)"]

    T1["auto_ingest"]
    T2["build_facts"]
    T3["build_index"]
    T4["read_snapshot"]
    T5["read_ratio_artifact"]
    T6["run_forecast"]
    T7["run_valuation"]
    T8["read_valuation_artifact"]
    T9["evaluate_report_quality"]

    RM -->|"kế hoạch tất định, không gọi LLM"| RM
    DE -->|"sở hữu tool, runner gọi trực tiếp"| T1
    DE -->|"sở hữu tool, runner gọi trực tiếp"| T2
    DE -->|"sở hữu tool, runner gọi trực tiếp"| T3
    FA -->|"tool"| T4
    FA -->|"tool"| T5
    FA -->|"LLM call"| FA
    FV -->|"tool"| T6
    FV -->|"tool"| T7
    FV -->|"tool"| T8
    FV -->|"LLM call ở normal mode"| FV
    TR -->|"LLM call"| TR
    SC -->|"tool"| T9
    SC -->|"LLM call"| SC
```

Tên “six-agent workflow” phản ánh sáu vai trò được cấu hình và kiểm soát quyền. Điều này không có nghĩa cả sáu agent đều được gọi qua LLM trong mọi chặng.

### 19. Luồng cổng kiểm định theo chặng

```mermaid
flowchart TD
    A["INGEST_AND_VALIDATE"] --> A1["DATA_QUALITY_GATE"]
    B["ANALYZE"] --> B1["FINANCIAL_ANALYST_GATE"]
    C["FORECAST_AND_VALUE"] --> C1["FORECAST_QUALITY_GATE"]
    C --> C2["VALUATION_GATE"]
    C --> C3["VALUATION_RECONCILIATION_GATE"]
    D["WRITE_REPORT"] --> D1["REPORT_ASSEMBLY_GATE"]
    E["REVIEW"] --> E1["REPORT_COMPLETENESS_GATE"]
    E --> E2["SENIOR_CRITIC_GATE"]
    E --> E3["CITATION_GATE"]
    F["EXPORT_GATES"] --> F1["PACKAGE_VALIDATION_GATE"]
    F1 --> X["BLOCKED nếu có fail nghiêm trọng"]
```

| Stage | Cổng kiểm định chính | Khi fail nghiêm trọng |
|---|---|---|
| `INGEST_AND_VALIDATE` | `DATA_QUALITY_GATE` | `blocked` |
| `ANALYZE` | `FINANCIAL_ANALYST_GATE` | `blocked` |
| `FORECAST_AND_VALUE` | `FORECAST_QUALITY_GATE`, `VALUATION_GATE`, `VALUATION_RECONCILIATION_GATE` | `blocked`, trừ cảnh báo không nghiêm trọng |
| `WRITE_REPORT` | `REPORT_ASSEMBLY_GATE` | `blocked` |
| `REVIEW` | `REPORT_COMPLETENESS_GATE`, `SENIOR_CRITIC_GATE`, `CITATION_GATE` | `blocked` |
| `EXPORT_GATES` | `PACKAGE_VALIDATION_GATE` (gộp tool permission, manifest, formula trace, evidence packet và tổng hợp xuất bản) | `blocked` |
| `PUBLISH` | Không có cổng phê duyệt thủ công | Render thành công thì `auto_exported`; render lỗi thì `failed` |

### 20. Luồng hậu kiểm chuyên gia sau báo cáo

```mermaid
sequenceDiagram
    autonumber
    participant R as Pipeline tự động
    participant P as Bộ xuất báo cáo
    participant ST as Kho artifact theo run_id
    actor E as Chuyên gia đánh giá
    participant N as Lần chạy hoặc cải tiến tiếp theo

    R->>P: Publish sau khi cổng tự động đạt
    P->>ST: Lưu report.html, report.pdf, manifest và evidence_pack
    ST-->>E: Cung cấp báo cáo và bằng chứng hỗ trợ
    E->>E: Đánh giá luận điểm, số liệu, rủi ro và khả năng sử dụng
    E-->>N: Gửi phản hồi để sửa dữ liệu, quy tắc, prompt hoặc cấu trúc báo cáo
    Note over E,N: Phản hồi không thay đổi artifact và trạng thái của run đã hoàn thành
```

Hậu kiểm chuyên gia là vòng phản hồi cho chất lượng sản phẩm, không phải một chặng runtime bắt buộc trước khi xuất báo cáo.

### 21. Luồng xử lý khi bị chặn

```mermaid
sequenceDiagram
    autonumber
    participant G as Cổng kiểm định
    participant R as Bộ chạy nghiên cứu
    participant S as Kho runtime
    participant ST as Kho artifact
    actor A as Người vận hành

    G-->>R: fail, severity = critical, blocking_reasons
    R->>R: Đặt state.status = blocked
    R->>R: Ghi state.blocking_reason
    R->>S: update_run_state(run_id, blocked, current_stage)
    R->>ST: Ghi graph_state_snapshot và evidence_pack nếu có thể
    A->>S: Xem trạng thái và blocking_reason
    A->>ST: Xem artifact liên quan để xác định nguyên nhân
```

Thiết kế này ưu tiên khả năng truy vết. Khi bị chặn, hệ thống giữ lại trạng thái, lý do và artifact để người vận hành biết cần sửa nguồn dữ liệu, công thức, prompt hay cấu hình nào.

### 22. Luồng lỗi ngoài cổng kiểm định

```mermaid
flowchart TD
    A["Stage đang chạy"]
    B{"Có exception?"}
    C["Tiếp tục stage tiếp theo"]
    D["state.status = failed"]
    E["blocking_reason = stage + lỗi"]
    F["Đóng step với status failed"]
    G["update_run_state failed"]
    H["Lưu checkpoint"]

    A --> B
    B -- "Không" --> C
    B -- "Có" --> D
    D --> E
    E --> F
    F --> G
    G --> H
```

Khác biệt chính: fail do cổng kiểm định thường là `blocked`; fail do exception hoặc render lỗi là `failed`.

### 23. Luồng dữ liệu lưu trữ theo bucket

```mermaid
flowchart TD
    A["sources"]
    B["official_documents/{ticker}/{year}/{source_doc_id}.pdf"]
    C["runs"]
    D["{run_id}/manifest.json"]
    E["{run_id}/valuation.json"]
    F["{run_id}/evidence_pack.json"]
    G["{run_id}/report.html"]
    H["{run_id}/report.pdf"]
    I["exports"]
    J["approved_reports/{ticker}/{run_id}/report.pdf"]
    K["archive"]
    L["legacy, debug, failed_runs"]

    A --> B
    C --> D
    C --> E
    C --> F
    C --> G
    C --> H
    I --> J
    K --> L
```

Bucket `exports` là một phần của storage contract, nhưng luồng publish hiện tại của `ResearchGraphRunner` dùng `ClientReportPublisher` và ghi báo cáo vào bucket `runs`.

### 24. Luồng IPO cho đồ án

```mermaid
flowchart LR
    A["Đầu vào<br/>Ticker, khoảng năm, objective, OCR flag, policy, nguồn dữ liệu"]
    B["Xử lý<br/>CLI/API, orchestrator, runner chín chặng, agent, tool, gates, checkpoint"]
    C["Đầu ra<br/>Snapshot, facts, forecast, valuation, evidence pack, manifest, HTML/PDF hoặc blocking_reason"]
    D["Hậu kiểm<br/>Chuyên gia đánh giá báo cáo đã xuất và tạo phản hồi cải tiến"]

    A --> B --> C --> D
```

Đây là sơ đồ ngắn nhất nên dùng khi cần giải thích hệ thống trong một slide tổng quan.

### 25. Các khẳng định đã kiểm định

| Nội dung | Trạng thái hiện tại |
|---|---|
| Có hai cửa vào chính: CLI và API | Đúng |
| Orchestrator là lớp điều phối mỏng | Đúng |
| Runtime có 9 stage trong `GRAPH_STAGES` | Đúng |
| Cổng nghiêm trọng fail thì trạng thái là `blocked` | Đúng |
| `needs_human_review` là trạng thái runtime hiện tại | Sai |
| Có cổng phê duyệt con người trước `PUBLISH` | Sai |
| `PUBLISH` dùng `ClientReportPublisher` trong đường chạy hiện tại | Đúng |
| Báo cáo HTML/PDF được ghi vào bucket `runs` | Đúng |
| Hậu kiểm chuyên gia diễn ra sau khi báo cáo đã xuất | Đúng theo ranh giới runtime hiện tại |

## Strategic Recommendations

### 1. Cách chọn sơ đồ đưa vào đồ án

Nên dùng bộ sơ đồ theo ba tầng:

| Tầng trình bày | Sơ đồ nên dùng | Mục tiêu |
|---|---|---|
| Tổng quan sản phẩm | Bản đồ tổng quan, IPO, trạng thái runtime | Giúp hội đồng hiểu hệ thống làm gì và dừng ở đâu |
| Kỹ thuật pipeline | CLI/API, chín chặng, dữ liệu, phân tích, định giá, báo cáo, export gates, publish | Chứng minh luồng thực thi có cấu trúc và kiểm soát |
| Kiểm soát rủi ro | OCR, fact promotion, artifact theo run_id, gate inventory, blocked flow, hậu kiểm chuyên gia | Chứng minh hệ thống có truy vết, chống sai số và có vòng phản hồi |

### 2. Cách diễn đạt đúng về HITL

Trong đồ án, nên mô tả HITL là “đánh giá chuyên gia sau đầu ra”. Không nên mô tả chuyên gia như một cổng bắt buộc giữa định giá và viết báo cáo, hoặc giữa `EXPORT_GATES` và `PUBLISH`, vì runner hiện tại không thực thi các cổng đó.

### 3. Các sơ đồ không nên dùng

Không nên dùng các sơ đồ mô tả:

- `VALUATION_PROPOSAL` và `ASSUMPTION_APPROVAL` như stage sản xuất.
- Phê duyệt con người trước publish như một bước runtime.
- `needs_human_review` như trạng thái runtime hiện tại.
- DataEvidenceAgent như một LLM agent được gọi trong chặng ingest.
- Xuất báo cáo production trực tiếp vào bucket `exports`.

### 4. Kết luận kiến trúc

Luồng cốt lõi của hệ thống là pipeline chín chặng tự động, kết hợp agent chuyên trách, công cụ tất định, cổng kiểm định, artifact lineage, manifest, evidence packet và xuất báo cáo theo `run_id`. Thiết kế này ưu tiên khả năng tái lập, khả năng truy vết và kiểm soát sai số tài chính hơn là tốc độ thời gian thực. Vai trò chuyên gia được đặt ở vòng hậu kiểm để đánh giá chất lượng báo cáo đã xuất và tạo tín hiệu cải tiến cho các lần chạy tiếp theo.
