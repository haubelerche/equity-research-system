# Tổng hợp kỹ thuật và công nghệ sử dụng trong dự án

## Context

Dự án `multi-agent-equity-research` là một hệ thống AI hỗ trợ nghiên cứu cổ phiếu ngành dược/y tế Việt Nam, tập trung vào báo cáo equity research có kiểm chứng nguồn, định giá bằng mã nguồn tất định, kiểm soát hallucination bằng evaluation gates, và phê duyệt con người trước khi xuất bản. Kiến trúc hiện tại không phải là chatbot RAG đơn giản; nó là một nền tảng nghiên cứu tài chính có quản trị dữ liệu, snapshot theo `run_id`, artifact manifest, bộ agent cố định, và pipeline định giá có khả năng tái lập.

Phạm vi kỹ thuật được xác nhận từ các thành phần sau: `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `Makefile`, `backend/`, `scripts/`, `config/`, `docs/DATA_ARCHITECTURE.md`, `docs/AI_PRODUCT_SPEC.md`, và bộ migration SQL trong `backend/database/migrations/`.

## Problem Statement

Hệ thống cần giải quyết đồng thời ba lớp rủi ro đặc thù của AI trong phân tích tài chính:

| Rủi ro | Biểu hiện kỹ thuật | Cơ chế kiểm soát trong dự án |
|---|---|---|
| Sai lệch dữ liệu tài chính | Nguồn API, OCR, PDF, hoặc dữ liệu thủ công có thể xung đột về kỳ, đơn vị, dòng chỉ tiêu | Canonical facts, source tier, reconciliation, validation gates, snapshot đóng băng |
| Hallucination của LLM | Agent có thể tạo claim không có nguồn hoặc diễn giải vượt bằng chứng | Citation gates, evidence packets, source provenance, prompt role constraints |
| Không tái lập được báo cáo | Báo cáo đọc live data hoặc artifact mới nhất theo timestamp sẽ thay đổi sau mỗi lần chạy | Run-scoped artifact manifest, Supabase Storage key contract, `research.run_artifacts` |

Do đó, các công nghệ trong dự án được tổ chức quanh nguyên tắc: dữ liệu tài chính và định giá phải do code tất định xử lý, còn LLM chỉ được dùng cho lập kế hoạch, tổng hợp luận điểm, diễn giải có nguồn, và kiểm định nội dung trong biên giới được kiểm soát.

## Technical Deep-Dive

### 1. Nền tảng runtime và backend

| Thành phần | Công nghệ | Vai trò | Bằng chứng mã nguồn |
|---|---|---|---|
| Ngôn ngữ chính | Python | Toàn bộ backend, pipeline dữ liệu, valuation, rendering, CLI scripts | `backend/`, `scripts/` |
| Runtime container | Python 3.11 slim | Môi trường production trong Docker | `Dockerfile` |
| API framework | FastAPI | Expose các endpoint điều phối research run | `backend/api.py` |
| ASGI server | Uvicorn | Chạy app FastAPI tại `0.0.0.0:8010` | `backend/main.py` |
| Data validation | Pydantic v2 | Request/response schema, state contracts, typed artifacts | `backend/schemas.py`, `requirements.txt` |
| Background execution | `ThreadPoolExecutor` | Chạy run bất đồng bộ theo `worker_pool_size` | `backend/executor.py` |
| CLI orchestration | Python scripts + Makefile | Entry point cho ingestion, valuation, report, migration, tests | `scripts/`, `Makefile` |
| Container orchestration local | Docker Compose | Build app, mount `storage`, truyền `.env`, chạy pipeline mặc định | `docker-compose.yml` |

API hiện tại cung cấp các endpoint chính: `/health`, `/research/start`, `/research/{run_id}/status`, `/research/{run_id}/artifacts`, `/reports/{run_id}`, và `/research/{run_id}/approve`. Endpoint `approve` hiện đọc trạng thái run nhưng logic phê duyệt đầy đủ nằm ở flow orchestration và script approval.

### 2. Multi-agent harness và lớp LLM

| Thành phần | Công nghệ/cấu hình | Vai trò |
|---|---|---|
| Kiểu orchestration | Fixed graph harness | Chạy workflow cố định thay vì agent tự do route không kiểm soát |
| Stage graph | `PREFLIGHT`, `PLAN`, `INGEST_AND_VALIDATE`, `ANALYZE`, `FORECAST_AND_VALUE`, `WRITE_REPORT`, `REVIEW`, `EXPORT_GATES`, `PUBLISH` | Chuỗi xử lý end-to-end từ kiểm tra đầu vào đến publish |
| Agent registry | YAML config | Khai báo 6 agent, prompt path, model, tools, schema, timeout |
| Agent roles | ResearchManager, DataEvidence, FinancialAnalysis, ForecastValuation, ThesisReport, SeniorCritic | Phân tách trách nhiệm để giảm context bottleneck và tăng auditability |
| LLM provider production | OpenAI Chat Completions | Adapter production hiện chỉ gọi OpenAI |
| Model chính | `gpt-5-mini` | Reasoning, synthesis, analysis, critique |
| Model rẻ/nhẹ | `gpt-5-nano` | Routing, classification, extraction JSON, normalization |
| Embedding | `text-embedding-3-small` mặc định | Tạo embedding cho document chunks và semantic retrieval |
| Cost control | BudgetGuard + `audit.cost_ledger` | Ghi nhận cost estimate, soft/hard budget, fallback policy |

Các file trung tâm gồm `backend/harness/runner.py`, `backend/harness/graph.py`, `backend/harness/model_adapter.py`, `backend/harness/agent_registry.py`, `backend/harness/tool_registry.py`, và `config/agents/agents.yml`.

Lưu ý kỹ thuật: `requirements.txt` vẫn khai báo `anthropic>=0.40`, nhưng kiểm tra mã nguồn cho thấy runtime production trong `backend/harness/model_adapter.py` chỉ dùng OpenAI. Đây có khả năng là dependency di sản hoặc dự phòng chưa được nối vào adapter production.

### 3. Cơ sở dữ liệu, schema và persistence

| Thành phần | Công nghệ | Vai trò | Ghi chú kỹ thuật |
|---|---|---|---|
| Database chính | Supabase PostgreSQL | Source of truth cho structured state, facts, run metadata, audit | `backend/database/config.py` cưỡng chế host Supabase |
| Driver DB | `psycopg2-binary` | Kết nối PostgreSQL, transaction, batch upsert | `backend/database/*`, `backend/runtime_store.py` |
| Migration runner | SQL files + custom Python runner | Áp dụng migration và ghi `public.schema_migrations` | `backend/database/migrate.py` |
| Schema version hiện tại | `034_runs_status_add_blocked` | Highest migration theo runner | `backend/database/migrate.py` |
| Runtime schema minimum | `030_supabase_storage_contract` | RuntimeStore kiểm tra mốc tối thiểu cho storage contract | `backend/runtime_store.py` |
| Vector extension | pgvector | Semantic search trên `ingest.document_chunks.embedding` | `031_pgvector_document_chunks.sql` |
| Full-text search | PostgreSQL `to_tsvector`/GIN | Fallback retrieval khi embedding thiếu | migrations `028`, `032`, `backend/retrieval.py` |

Các schema production được mô tả trong `docs/DATA_ARCHITECTURE.md` gồm:

| Schema | Trách nhiệm |
|---|---|
| `ref` | Company master, metric dictionaries, peer groups, formula references |
| `ingest` | Source documents, connector runs, raw observations, document chunks |
| `fact` | Canonical financial facts, price history, catalyst events |
| `research` | Runs, stages, snapshots, manifests, artifact metadata |
| `valuation` | Valuation run metadata, assumptions, summaries |
| `report` | Report records, claims, citations, gates, approvals |
| `audit` | Governance events, migration, deletion, cost ledger |

Điểm quan trọng: README còn nhắc "PostgreSQL local hoặc Supabase", nhưng mã runtime hiện tại từ chối `localhost`, `127.0.0.1`, `::1`, và `db`; do đó trạng thái thực thi hiện tại là Supabase PostgreSQL-only.

### 4. Object storage và artifact contract

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| Storage backend | Supabase Storage REST API | Lưu source binaries, run artifacts, approved exports, archive |
| Adapter | `backend/storage/supabase_adapter.py` | Upload/download JSON, bytes, checksum, signed URL |
| Path authority | `backend/storage/layout.py` | Kiểm soát bucket và object key hợp lệ |
| Buckets | `sources`, `runs`, `exports`, `archive` | Phân vùng storage theo source, runtime, client output, retention |
| Artifact manifest | `manifest.json` trong bucket `runs` | Ràng buộc artifact theo `run_id`, không dùng latest file glob |

Storage key contract chính:

| Bucket | Ví dụ object key | Ý nghĩa |
|---|---|---|
| `sources` | `official_documents/DHG/2024/{source_doc_id}.pdf` | PDF/source chính thức bất biến |
| `runs` | `{run_id}/valuation.json`, `{run_id}/report.html`, `{run_id}/quality_gate.json` | Artifact của một lần chạy |
| `exports` | `approved_reports/DHG/{run_id}/report.pdf` | Report đã qua phê duyệt |
| `archive` | `legacy/...`, `debug/...`, `failed_runs/...` | Lưu trữ debug/legacy |

### 5. Data ingestion và nguồn dữ liệu

| Nguồn/kênh | Công nghệ/kết nối | Vai trò | Source tier theo thiết kế |
|---|---|---|---|
| vnstock financial API | Local/vendored `vnstock` package, pandas | Lấy báo cáo tài chính, ratio, market data | Tier 3 aggregator |
| vnstock quote API | `vnstock.api.quote.Quote` | Giá lịch sử, benchmark market data | Tier 3 |
| CafeF structured data | `urllib.request` connector | Structured BCTC từ aggregator | Tier 2 |
| Official PDFs | Company IR, HOSE, HNX, SSC connectors | Nguồn chính thức, PDF/source documents | Tier 0/1 tùy kênh |
| Regulatory/catalyst feeds | DAV, BHYT, HOSE/HNX, tender connectors | Sự kiện ngành, đấu thầu, chính sách | Theo `config/source_registry.yaml` |
| Manual/golden fixtures | CSV/YAML trong `config/dataset` | Bootstrap MVP, kiểm thử golden facts | Nguồn kiểm soát nội bộ |

Các connector tiêu biểu nằm ở `scripts/connectors/`, `backend/documents/connectors/`, `backend/news/`, và `scripts/auto_ingest_official_documents.py`.

Rủi ro dependency: một số connector dùng `requests` và `bs4`, nhưng `requirements.txt` hiện không khai báo trực tiếp `requests` hoặc `beautifulsoup4`; nếu các gói này không đến từ dependency bắc cầu của `vnstock` hoặc môi trường local, Docker runtime có thể lỗi ở các crawler catalyst.

### 6. Document processing, OCR và retrieval

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| Text PDF extraction | `pdfplumber` | Trích bảng/text từ PDF có text layer |
| OCR | Tesseract OCR + Vietnamese language pack | Nhận diện PDF scan tiếng Việt |
| PDF to image | Poppler + `pdf2image` | Render trang PDF thành ảnh cho OCR |
| Image processing | Pillow | Hỗ trợ pipeline OCR |
| OCR Python binding | `pytesseract` | Gọi Tesseract từ Python |
| Metric mapping | YAML dictionary + regex | Map nhãn báo cáo tài chính Việt Nam vào metric canonical |
| Chunking/retrieval | `ingest.document_chunks`, pgvector, PostgreSQL full-text | Evidence retrieval có metadata và fallback |

OCR không được xem là source of truth trực tiếp. Output OCR phải đi qua validation, reconciliation, và promotion gate trước khi trở thành canonical fact.

### 7. Analytics, valuation và financial computation

| Module | Vai trò |
|---|---|
| `backend/analytics/ratios.py` | Tính financial ratios |
| `backend/analytics/forecasting.py` | Forecast 5 năm theo drivers |
| `backend/analytics/fcff.py` | FCFF DCF: EBIT sau thuế, D&A, CAPEX, NWC, WACC, EV-to-equity bridge |
| `backend/analytics/fcfe.py` | FCFE DCF: NI, D&A, CAPEX, NWC, net borrowing, cost of equity |
| `backend/analytics/blend.py` | Blend DCF 60% FCFF và 40% FCFE |
| `backend/analytics/multiples.py` | P/E, EV/EBITDA, relative valuation cross-check |
| `backend/analytics/sensitivity.py` | Sensitivity tables cho WACC/g, Re/g, multiples |
| `backend/analytics/approval_gate.py` | Kiểm soát giả định và readiness trước export |

Nguyên tắc kỹ thuật cốt lõi là LLM không tính toán số liệu tài chính chính. LLM có thể đề xuất narrative hoặc review output, nhưng target price, ratio, forecast, DCF, sensitivity và sanity checks phải được sinh bởi Python deterministic modules.

### 8. Reporting, charting và PDF export

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| HTML templating | Jinja2 | Render report HTML từ view model |
| CSS template | Static CSS | Layout báo cáo client-facing |
| Markdown support | `markdown` package | Hỗ trợ legacy/dev rendering |
| Charting | Matplotlib Agg | Sinh PNG charts deterministic, không cần GUI |
| Statistical visualization | Seaborn | Heatmap sensitivity và biểu đồ phân tích |
| Data frame handling | pandas, numpy | Transform dữ liệu tabular và chart inputs |
| PDF primary backend | WeasyPrint | HTML-to-PDF có Unicode/Vietnamese support tốt |
| PDF fallback | pdfkit/Chrome/xhtml2pdf | Các đường xuất PDF dự phòng |
| Font strategy | DejaVu/NotoSans fallback | Giảm lỗi mojibake và thiếu glyph tiếng Việt |

Các file chính gồm `backend/reporting/html_renderer.py`, `backend/reporting/pdf_renderer.py`, `backend/reporting/chart_generator.py`, `backend/reporting/final_report_renderer.py`, `backend/reporting/report_assembler.py`, và template `backend/reporting/templates/report.html.j2`.

### 9. Evaluation, gates và quality control

| Nhóm kiểm định | Công nghệ/cơ chế | Mục tiêu |
|---|---|---|
| Numeric consistency | Python validators | Số trong report khớp canonical facts/artifacts |
| Citation coverage | Citation map, claim ledger, source tier policy | Claim quan trọng phải có nguồn hợp lệ |
| Source provenance | Source tier gates | Chặn Tier 3-only khi cần official support |
| Valuation reproducibility | Formula traces, valuation artifacts | Tái lập target price và assumptions |
| Forecast quality | Balance sheet identity, driver support, cash-flow checks | Tránh forecast không cân hoặc thiếu drivers |
| Export gate | Harness deterministic gates | Chặn publish khi fail critical gate |
| Senior critic | LLM + deterministic quality gate | Review narrative và readiness |

Evaluation code nằm ở `backend/evaluation/`, `backend/harness/gates.py`, `backend/citations/`, `scripts/evaluate_report.py`, `scripts/evaluate_report_quality.py`, và các test tương ứng trong `tests/`.

### 10. Testing và kiểm chứng

| Thành phần | Công nghệ | Vai trò |
|---|---|---|
| Test framework | pytest | Unit, integration, source, citation, valuation, reporting tests |
| Test markers | `integration` | Phân loại test cần nguồn live hoặc DB |
| Make target | `make test`, `make audit` | Chạy test toàn bộ hoặc audit subset |
| Contract tests | Unit tests cho schema, gates, storage, model adapter | Bảo vệ behavior cốt lõi |

Bộ test hiện bao phủ nhiều lớp: analytics, OCR gates, source provenance, report assembler, Supabase storage contract, production models, migration runner, citation policy, và run research entrypoint. Một số target trong `Makefile` tham chiếu test file có thể đã bị đổi tên hoặc xóa trong working tree, cần kiểm tra lại trước khi dùng `make audit` làm CI canonical.

### 11. Hạ tầng cấu hình và domain taxonomy

| Loại cấu hình | File/thư mục | Vai trò |
|---|---|---|
| Agent config | `config/agents/agents.yml` | Agent role, model, prompt, tool permission |
| Agent prompts | `config/agents/prompts/` | Prompt riêng cho từng agent |
| Harness contracts | `config/harness/` | Task registry, schemas, export gate policy, tool contracts |
| Financial taxonomy | `config/dataset/taxonomy/financial_taxonomy_vn_pharma.yaml` | Metric canonical cho ngành dược |
| Metric dictionary | `config/financial_metric_dictionary.yaml` | Mapping label/CafeF/PDF/OCR vào metric IDs |
| Source registry | `config/source_registry.yaml` | Nguồn dữ liệu được phép và metadata tier |
| MVP universe | `config/dataset/universe/pharma_vn_universe.csv` | Danh mục ticker ngành dược/y tế |
| Golden fixtures | `config/dataset/golden/financials/` | Dữ liệu kiểm chứng cho ticker MVP |

### 12. Observability và governance

| Thành phần | Trạng thái | Nhận định |
|---|---|---|
| Run steps | Implemented trong `research.run_steps` | Ghi stage, agent, status, duration, retry, input/output hash |
| Audit events | Implemented trong `research.run_audit_events` | Ghi agent messages, tool calls, checkpoints |
| Cost ledger | Implemented trong `audit.cost_ledger` | Ghi model, tokens, estimated cost |
| Langfuse | Dependency và env docs tồn tại | Chưa thấy integration runtime trực tiếp trong `backend` hoặc `scripts` |
| Progress reporter | Implemented | Báo tiến trình run ở harness |

Langfuse nên được xem là optional/latent dependency ở trạng thái hiện tại, chưa phải observability backbone đã được nối trong runtime chính.

## Kết luận kỹ thuật

Dự án đang sử dụng một stack tương đối nhất quán cho bài toán AI tài chính có rủi ro cao: Python/FastAPI cho backend, Supabase PostgreSQL cho structured governance, Supabase Storage cho artifact bất biến, pgvector cho evidence retrieval, OpenAI cho agent reasoning/extraction, deterministic Python analytics cho định giá, OCR/PDF tooling cho dữ liệu báo cáo tài chính, và pytest cho contract verification.

Điểm mạnh cốt lõi không nằm ở việc có nhiều agent, mà ở cách hệ thống ràng buộc agent vào dữ liệu có provenance, artifact theo `run_id`, valuation có formula trace, và export gates. Điểm cần ưu tiên xử lý tiếp theo là giảm drift giữa tài liệu, dependency manifest, và runtime thực tế để hệ thống dễ triển khai, dễ kiểm thử, và ít phụ thuộc vào trạng thái local của máy phát triển.
