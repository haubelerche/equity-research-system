# Catalog tài liệu sau tái thiết hệ thống

## Context

Catalog này là chỉ mục tài liệu nên dùng sau đợt tái thiết hệ thống ngày 2026-06-09 và audit ngày 2026-06-10. Mục tiêu là tránh dùng nhầm tài liệu cũ mô tả `LangGraph`, supervisor/five-agent workflow, schema `v2_*`, latest-file fallback, hoặc các luồng report legacy không còn là production contract.

Trục kiến trúc hiện hành cần được trình bày trong báo cáo tốt nghiệp là:

```text
PostgreSQL/Supabase canonical data layer
-> run-scoped storage and artifact manifest
-> deterministic analytics and valuation engine
-> fixed six-agent full_report harness
-> deterministic gates
-> human-in-the-loop approval
-> approved HTML/PDF export
```

## Problem Statement

Repo hiện có nhiều tài liệu sinh ra trong các giai đoạn thiết kế khác nhau. Một số tài liệu vẫn đúng về mặt ý tưởng nền tảng, nhưng không còn đúng như contract sản xuất sau tái thiết. Nếu đưa các tài liệu đó vào báo cáo học thuật, phần mô tả hệ thống sẽ bị mâu thuẫn ở ba điểm nghiêm trọng:

| Nhóm sai lệch | Mô tả sai | Contract hiện hành |
|---|---|---|
| Data schema | `v2_ref`, `v2_ingest`, `v2_fact`, `v2_research`, `v2_report` là production schema | Production schema là `ref`, `ingest`, `fact`, `research`, `valuation`, `report`, `audit` |
| Workflow | Supervisor/LangGraph/five-role hoặc dynamic graph | Fixed six-agent `full_report` harness, `ResearchGraphRunner` là executor nội bộ, không dùng compiled LangGraph |
| Artifact resolution | Lấy latest/glob artifact hoặc render từ script legacy | Production phải dùng `run_id`, manifest, explicit artifact refs, final approval trước export |

## Technical Deep-Dive

### Tài Liệu Active Nên Dùng

| Ưu tiên | Tài liệu | Vai trò trong báo cáo | Lý do chọn |
|---:|---|---|---|
| 1 | [README.md](README.md) | Tổng quan dự án, pipeline, công nghệ, lệnh chạy | Tài liệu mới nhất mô tả hệ thống evidence-grounded, code-first valuation và HITL |
| 2 | [docs/SEQUENCE.md](docs/SEQUENCE.md) | Mô tả workflow sáu tác tử | Đã cập nhật theo fixed six-agent full-report sequence |
| 3 | [docs/AI_PRODUCT_SPEC.md](docs/AI_PRODUCT_SPEC.md) | Product framing, người dùng mục tiêu, yêu cầu AI product | Phù hợp cho chương tổng quan, phạm vi, MVP, trust và guardrails |
| 4 | [docs/data_architecture/final_storage_and_db_contract.md](docs/data_architecture/final_storage_and_db_contract.md) | Contract dữ liệu và lưu trữ cuối cùng | Xác nhận schema canonical và storage path sau cutover |
| 5 | [docs/data_architecture/source_of_truth_matrix.md](docs/data_architecture/source_of_truth_matrix.md) | Source-of-truth matrix | Dùng để giải thích DB/file/object storage artifact nào là nguồn sự thật |
| 6 | [audits/final_data_architecture_verification.md](audits/final_data_architecture_verification.md) | Bằng chứng audit data architecture | Xác nhận không còn `v2_*` schema trong production và nêu blocker còn lại |
| 7 | [audits/data_warehouse_live_inventory.md](audits/data_warehouse_live_inventory.md) | Inventory database live | Bằng chứng thực nghiệm cho data layer |
| 8 | [audits/semantic_data_model_audit.md](audits/semantic_data_model_audit.md) | Kiểm toán semantic model | Dùng cho phần data quality, source classification và semantic consistency |
| 9 | [audits/filesystem_storage_cleanup_inventory.md](audits/filesystem_storage_cleanup_inventory.md) | Kiểm toán filesystem/storage | Dùng cho phần storage governance và archive policy |
| 10 | [audits/SIX_AGENT_FULL_REPORT_REBUILD_AUDIT.md](audits/SIX_AGENT_FULL_REPORT_REBUILD_AUDIT.md) | Audit hệ thống sau rebuild | Nên dùng để trình bày trạng thái thực tế: partial pass, điểm đã đạt và điểm chưa verify |
| 11 | [fin_plan/tai-thiet-he-thong.md](fin_plan/tai-thiet-he-thong.md) | Tài liệu thiết kế tái kiến trúc | Dùng như plan thiết kế, không dùng như bằng chứng implementation đã hoàn tất |
| 12 | [fin_plan/01_standards/01_valuation_60_fcff_40_fcfe.md](fin_plan/01_standards/01_valuation_60_fcff_40_fcfe.md) | Chuẩn định giá FCFF/FCFE | Dùng cho chương cơ sở tài chính và valuation methodology |
| 13 | [valuation_calculation_audit_checklist.md](valuation_calculation_audit_checklist.md) | Checklist kiểm toán định giá | Dùng cho phần evaluation và financial reproducibility |
| 14 | [docs/OCR_PIPELINE.md](docs/OCR_PIPELINE.md) | OCR concept và dependency | Dùng có điều kiện; cần ưu tiên storage contract mới nếu có mâu thuẫn path |
| 15 | [docs/DATA_PROMOTION_POLICY.md](docs/DATA_PROMOTION_POLICY.md) | Chính sách promotion dữ liệu OCR/facts | Dùng cho lý thuyết data quality, nhưng phải đối chiếu với schema/storage cuối cùng |

### Tài Liệu Nên Dùng Theo Chương Báo Cáo

| Chương báo cáo | Tài liệu nền | Ghi chú sử dụng |
|---|---|---|
| Chương 1: Tổng quan và vấn đề nghiên cứu | `README.md`, `docs/AI_PRODUCT_SPEC.md` | Nhấn mạnh augmentation-first, không phải autonomous stock picking |
| Chương 2: Cơ sở lý thuyết | `fin_plan/01_standards/*`, `docs/DATA_PROMOTION_POLICY.md`, `valuation_calculation_audit_checklist.md` | Tách rõ tài chính truyền thống, data lineage, OCR/RAG, multi-agent |
| Chương 3: Thiết kế hệ thống | `docs/SEQUENCE.md`, `docs/data_architecture/*`, `fin_plan/tai-thiet-he-thong.md` | Mô tả fixed six-agent harness và run-scoped artifacts |
| Chương 4: Triển khai | `README.md`, `docs/SEQUENCE.md`, `backend/harness/graph.py`, `backend/harness/contracts.py`, `config/agents/agents.yml` | Dùng code làm nguồn sự thật khi tài liệu cũ mâu thuẫn |
| Chương 5: Thực nghiệm và đánh giá | `audits/SIX_AGENT_FULL_REPORT_REBUILD_AUDIT.md`, `audits/final_data_architecture_verification.md`, `valuation_calculation_audit_checklist.md` | Trình bày trung thực PASS/PARTIAL/NOT VERIFIED |
| Chương 6: Kết luận và hướng phát triển | `audits/*`, `docs/AI_PRODUCT_SPEC.md` | Nêu các blocker còn lại: live full report, artifact inventory, Langfuse trace, final render verification |

### Công Nghệ Nên Mô Tả Trong Báo Cáo

| Lớp | Công nghệ hiện hành | Vai trò |
|---|---|---|
| Backend/API | FastAPI, Uvicorn | API start/status/artifacts/approval |
| Workflow | `FullReportOrchestrator`, `ResearchGraphRunner`, fixed `GRAPH_STAGES` | Điều phối run-scoped `full_report` |
| Agent config | `config/agents/agents.yml` | Sáu agent active: research manager, data evidence, financial analysis, forecast valuation, thesis report, senior critic |
| Contract | Pydantic v2 | Typed artifact contracts và schema validation |
| Database | PostgreSQL/Supabase | Source-of-truth cho metadata, facts, runs, valuation, claims, approvals, audit |
| Storage | Supabase Storage contract: `sources`, `runs`, `exports`, `archive` | Lưu official documents, run artifacts, approved reports, archive |
| Retrieval | PostgreSQL full-text + pgvector | Evidence chunks và semantic retrieval |
| OCR/document | Tesseract, `pytesseract`, `pdf2image`, `Pillow`, `pdfplumber` | Xử lý BCTC/BCTN PDF và tài liệu scan tiếng Việt |
| Analytics | Python, pandas, numpy, `backend/analytics` | Ratios, forecast, FCFF, FCFE, blend, multiples, sensitivity |
| Reporting | Markdown, Jinja2, WeasyPrint, xhtml2pdf, Matplotlib, Seaborn | Sinh report HTML/PDF và biểu đồ |
| Observability/testing | Langfuse, pytest, Docker | Trace, cost, kiểm thử, reproducibility |

## Strategic Recommendations

### Nguồn Sự Thật Khi Tài Liệu Mâu Thuẫn

Thứ tự ưu tiên nên dùng khi viết báo cáo:

```text
1. Code runtime hiện hành
2. README.md cập nhật sau rebuild
3. docs/SEQUENCE.md và docs/data_architecture/*
4. audits ngày 2026-06-09/10
5. fin_plan/tai-thiet-he-thong.md như design intent
6. tài liệu cũ chỉ dùng nếu không mâu thuẫn với 1-4
```

### Tài Liệu Đã Loại Khỏi Active Catalog

Các tài liệu sau không nên dùng làm căn cứ học thuật hoặc kiến trúc hiện hành vì sai lệch logic sau cutover:

| Tài liệu/nhóm tài liệu | Lý do loại |
|---|---|
| `docs/data_warehouse_v2/*` | Mô tả `v2_*` schema là target/production trong khi audit cuối cùng xác nhận production không có `v2_*` |
| `docs/data_warehouse/final_schema_decision.md` | Quyết định giữ `v2_*` là final production đã bị trạng thái thực tế bác bỏ |
| `docs/data_warehouse/final_data_contracts.md` | Contract bảng `v2_*` không còn khớp schema canonical hiện hành |
| `docs/data_warehouse/destructive_cleanup_migrations.md` | Kế hoạch drop legacy theo hướng `v2_*` đã lỗi thời so với canonical cutover |
| `docs/DATA_ARCHITECTURE.md` bản cũ | Có nội dung LangGraph/Data Foundation Agent và path dữ liệu cũ; đã được thay bằng bản architecture hiện hành |

### Cách Diễn Đạt Trong Báo Cáo

Không viết:

```text
Hệ thống sử dụng LangGraph/Supervisor để điều phối nhiều loại run như full_report, flash_memo, catalyst_refresh.
```

Nên viết:

```text
Phiên bản tái thiết hiện hành chỉ mở production path cho full_report. Hệ thống sử dụng FullReportOrchestrator và ResearchGraphRunner nội bộ để chạy một stage list cố định, gồm sáu agent chuyên trách và các deterministic gates trước khi yêu cầu phê duyệt con người.
```

Không viết:

```text
Production database dùng v2_ref, v2_ingest, v2_fact, v2_research, v2_report.
```

Nên viết:

```text
Sau cutover, production database dùng các schema canonical gồm ref, ingest, fact, research, valuation, report và audit; archive_legacy chỉ là rollback boundary, không phải runtime source.
```

Không viết:

```text
LLM tính toán định giá và tạo khuyến nghị đầu tư tự động.
```

Nên viết:

```text
LLM chỉ hỗ trợ lập luận, diễn giải và soạn thảo dựa trên artifact đã khóa; mọi phép tính ratios, forecast, FCFF, FCFE, valuation bridge và sensitivity đều do Python deterministic engine thực hiện.
```
