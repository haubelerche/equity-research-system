# Tổng hợp kỹ thuật và công nghệ sử dụng trong dự án

Cập nhật: 2026-06-17

## Context

Dự án `multi-agent-equity-research` là một hệ thống AI hỗ trợ nghiên cứu cổ phiếu ngành dược và thiết bị y tế Việt Nam, với trọng tâm không phải là chatbot RAG đơn giản mà là một pipeline research có kiểm soát: ingestion dữ liệu, chuẩn hóa fact tài chính, truy xuất evidence, định giá tất định, sinh báo cáo, kiểm định chất lượng, lưu artifact theo `run_id`, và xuất bản sau khi đi qua export gates.

Phạm vi rà soát được đối chiếu từ các nguồn bằng chứng chính sau:

| Nhóm bằng chứng | File/thư mục đã kiểm tra | Ý nghĩa kỹ thuật |
|---|---|---|
| Manifest runtime | `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `.env.example`, `Makefile`, `pytest.ini` | Xác định dependency khai báo, system packages, entrypoint, biến môi trường, và lệnh vận hành |
| Backend runtime | `backend/api.py`, `backend/main.py`, `backend/executor.py`, `backend/settings.py`, `backend/orchestrator.py` | Xác định API, executor bất đồng bộ, cấu hình runtime, và orchestration |
| Controlled agentic harness | `backend/harness/`, `config/agents/agents.yml`, `config/agents/prompts/`, `config/harness/` | Xác định graph, vai trò cấu hình, tác tử LLM thực sự, model adapter, tool registry, gates và typed contracts |
| Data platform | `backend/database/`, `backend/database/migrations/`, `backend/runtime_store.py`, `backend/storage/` | Xác định Supabase PostgreSQL, migrations, schema governance, và Supabase Storage contract |
| Data ingestion | `scripts/connectors/`, `backend/documents/connectors/`, `backend/news/`, `scripts/auto_ingest_official_documents.py` | Xác định nguồn dữ liệu tài chính, official documents, catalyst feeds, và news evidence |
| Document/OCR/Retrieval | `backend/documents/`, `backend/retrieval.py`, `scripts/build_index.py`, `docs/OCR_PIPELINE.md` | Xác định PDF parsing, OCR, pgvector, và PostgreSQL full-text fallback |
| Analytics/reporting/evaluation | `backend/analytics/`, `backend/reporting/`, `backend/evaluation/`, `backend/citations/`, `tests/` | Xác định định giá, forecast, charting, rendering, citation gates, và kiểm thử |

## Problem Statement

Tài liệu tech stack hiện mô tả trạng thái codebase mới nhất, trong đó dependency manifest đã được đồng bộ với các import chính, evaluation stack đã được khai báo, và frontend/backend surface đã đủ phục vụ live report inventory cùng evaluation dashboard. Với một hệ thống AI tài chính, tech stack không chỉ là danh sách thư viện; nó là một phần của bằng chứng reproducibility, latency envelope, cost-to-serve và governance của agentic workflow.

Các rủi ro chính được phát hiện:

| Rủi ro | Biểu hiện trong repo | Tác động vận hành |
|---|---|---|
| Dependency manifest đã đồng bộ | `requirements.txt` khai báo trực tiếp `requests`, `beautifulsoup4`, `vnstock`, `pdfkit`, `pypdf` và evaluation stack | Môi trường sạch có thể tái dựng crawler, PDF fallback, preflight và benchmark evaluation |
| Cấu hình LLM bị lệch pha | `.env.example` vẫn nhắc `ANTHROPIC_API_KEY`, `requirements.txt` có `anthropic`, nhưng `backend/harness/model_adapter.py` production chỉ gọi OpenAI | Người vận hành có thể cấp sai secret, hoặc hiểu sai provider production |
| Quan sát hệ thống | `langfuse>=4.0` đã nối qua drop-in `langfuse.openai` trong `model_adapter.py`; bật khi có credentials, no-op nếu thiếu | Observability optional, không phải backbone bắt buộc |
| PDF rendering đã đủ cho MVP5 | Code hỗ trợ WeasyPrint, pdfkit/wkhtmltopdf, Chrome headless, xhtml2pdf, pypdf preflight; manifest đã có PDF fallback packages | WeasyPrint là đường chính; hardening wkhtmltopdf/Chrome trong container SLA thuộc residual roadmap |
| Thiếu lockfile và packaging chuẩn | Không thấy `pyproject.toml`, `setup.cfg`, `requirements.lock`, hoặc CI config trong danh sách file | Reproducibility phụ thuộc vào version floating và trạng thái máy phát triển |

## Technical Deep-Dive

### 1. Ngôn ngữ, runtime và packaging

| Thành phần | Công nghệ | Trạng thái | Bằng chứng |
|---|---|---|---|
| Ngôn ngữ chính | Python | Runtime chính cho toàn bộ backend, scripts, analytics, ingestion, report generation | `backend/`, `scripts/`, `tests/` |
| Python runtime container | `python:3.11-slim` | Được dùng trong Docker image production/local | `Dockerfile` |
| Dependency manifest | `requirements.txt` | Manifest đã bao phủ runtime, crawler, PDF fallback, observability và evaluation stack | `requirements.txt`, quét import trong `backend/`, `scripts/`, `tests/` |
| Package manager | `pip` | Docker cài bằng `pip install -r requirements.txt`; lockfile vẫn là residual roadmap 1/10 | `Dockerfile` |
| Project packaging | Không phát hiện `pyproject.toml`/`setup.py` | Repo đang vận hành theo kiểu source tree trực tiếp, không phải package installable chuẩn | `rg --files` |
| Local vendored namespace | `vnstock/` | Có thư mục local; connector cố tình ưu tiên pip-installed `vnstock` trước local path | `vnstock/`, `scripts/connectors/vnstock_finance_connector.py` |

Nhận định theo Iron Triangle: stack Python phù hợp với latency không quá thấp của research workflow và tăng reliability nhờ ecosystem dữ liệu tài chính, nhưng scalability vận hành bị giới hạn nếu dependency không pin version và không có lockfile tái dựng.

### 2. Backend API và execution model

| Thành phần | Công nghệ/cơ chế | Vai trò | Bằng chứng |
|---|---|---|---|
| API framework | FastAPI | Expose API điều phối research run và artifact lookup | `backend/api.py` |
| ASGI server | Uvicorn | Chạy `backend.api:app` tại `0.0.0.0:8010` | `backend/main.py` |
| Typed API schema | Pydantic v2 | Request/response models, enum trạng thái, typed contracts | `backend/schemas.py`, `backend/harness/contracts.py` |
| Background execution | `ThreadPoolExecutor` | Chạy full-report runs bất đồng bộ theo `WORKER_POOL_SIZE` | `backend/executor.py` |
| Runtime settings | Dataclass + environment variables | DB URL, model, budget policy, worker pool, Supabase secrets | `backend/settings.py` |
| Local orchestration | Docker Compose | Build app, đọc `.env`, mount `./storage:/app/storage`, chạy pipeline | `docker-compose.yml` |

Các endpoint chính hiện có:

| Endpoint | Chức năng |
|---|---|
| `GET /health` | Health check tối giản |
| `POST /research/start` | Tạo run, ghi state ban đầu, submit executor |
| `GET /research/{run_id}/status` | Trả trạng thái run |
| `GET /research/{run_id}/artifacts` | Liệt kê artifact metadata |
| `GET /reports` | Trả report inventory cho universe, ưu tiên run manifest/artifact lineage và dùng local preview fallback |
| `GET /reports/{ticker}/file/{kind}` | Ưu tiên phục vụ report/explanation PDF từ Supabase `exports`, fallback local output cho dev |
| `GET /reports/{ticker}/preview/{page}` | Phục vụ preview PNG local |
| `POST /reports/{ticker}/generate` | Chọn `fast_render` nếu có snapshot và run renderable, nếu không chạy `full_pipeline` |
| `GET /reports/{run_id}` | Lọc artifact liên quan đến report/evaluation/log |
| `GET /eval/framework` | Trả evaluation packet và framework metadata mới nhất |
| `GET /eval/artifacts/{artifact_name}` | Trả artifact evaluation cụ thể |
| `GET /research/{run_id}/evaluation` | Trả evaluation packet theo run |

Backend expose evaluation API cho dashboard live; route frontend `/eval` đọc backend artifacts theo mặc định và chỉ dùng mock fixtures trong development/test. Khi có `frontend/dist/`, FastAPI mount assets và SPA fallback sau các API route.

### 3. Multi-agent harness và lớp LLM

| Thành phần | Công nghệ/cấu hình | Trạng thái | Bằng chứng |
|---|---|---|---|
| Workflow graph | Fixed stage graph | Dùng graph cố định thay vì agent tự route tự do | `backend/harness/graph.py` |
| Stage sequence | `PREFLIGHT`, `PLAN`, `INGEST_AND_VALIDATE`, `ANALYZE`, `FORECAST_AND_VALUE`, `WRITE_REPORT`, `REVIEW`, `EXPORT_GATES`, `PUBLISH` | Pipeline end-to-end có checkpoint và gate | `backend/harness/runner.py` |
| Role registry | YAML + Pydantic | Khai báo sáu khóa cấu hình cho role class, prompt path, model, timeout và allowed tools; không đồng nghĩa với sáu tác tử LLM | `config/agents/agents.yml`, `backend/harness/agent_registry.py` |
| LLM-capable roles | FinancialAnalysis, ForecastValuation narrative, ThesisReport, SeniorCritic | Chỉ các role có lời gọi LLM mới được mô tả là tác tử hoặc vai trò lai | `config/agents/agents.yml`, `docs/AGENTS_AND_TOOLS.md` |
| Production LLM provider | OpenAI Chat Completions | Adapter production gọi `openai.OpenAI(...).chat.completions.create(...)` | `backend/harness/model_adapter.py` |
| Production models | `gpt-5-mini`, `gpt-5-nano` | Allow-list cứng trong adapter; model nhẹ dùng cho route/classify/extract | `backend/harness/model_adapter.py` |
| Embedding model | `text-embedding-3-small` | Dùng cho chunk embedding và query embedding khi có `OPENAI_API_KEY` | `scripts/admin/chunk_pipeline.py`, `backend/retrieval.py` |
| Tool governance | Tool registry typed | Ràng buộc tool theo owner agent, timeout, permission level, blocking semantics | `backend/harness/tool_registry.py` |
| Budget control | BudgetGuard + cost estimate | Soft/hard budget và cost ledger theo model/tokens ước tính | `backend/services.py`, `backend/harness/model_adapter.py` |

Lưu ý quan trọng: `anthropic>=0.40` và `ANTHROPIC_API_KEY` đang tồn tại ở manifest/env template, nhưng production adapter hiện chỉ dùng OpenAI. Vì vậy Anthropic phải được xem là dependency di sản hoặc dự phòng chưa nối vào runtime, không phải provider production đang hoạt động.

### 4. Database, schema governance và persistence

| Thành phần | Công nghệ | Trạng thái | Bằng chứng |
|---|---|---|---|
| Database chính | Supabase PostgreSQL | Runtime hiện tại bắt buộc dùng host Supabase, từ chối localhost/db | `backend/database/config.py` |
| PostgreSQL driver | `psycopg2-binary` | Kết nối DB, retry transient disconnect, batch insert/upsert | `backend/database/`, `backend/runtime_store.py` |
| Migration model | SQL migrations + custom runner | Migrations `001` đến `045`, ghi `public.schema_migrations` | `backend/database/migrate.py`, `backend/database/migrations/` |
| Migration runner requirement | `043_cafef_financial_source_type` | `CURRENT_SCHEMA_VERSION` hiện kiểm version này | `backend/database/migrate.py` |
| Runtime schema floor | `035_runs_status_auto_exported` | `RuntimeStore` kiểm tra schema tối thiểu cho trạng thái `auto_exported` | `backend/runtime_store.py` |
| Highest migration detected | `045_agm_resolutions.sql` | Migration mới nhất trong repo, phục vụ AGM/DHCD driver | `backend/database/migrations/` |
| Vector search | pgvector | Cột `embedding vector(1536)` và HNSW index cho document chunks | `031_pgvector_document_chunks.sql` |
| Full-text search | PostgreSQL `to_tsvector`, `plainto_tsquery`, GIN | Fallback khi embedding hoặc OpenAI key không khả dụng | `backend/retrieval.py`, migrations `028`, `032` |

Các schema logic đang được sử dụng:

| Schema | Trách nhiệm |
|---|---|
| `ref` | Company master, metric dictionaries, peer groups, formula references |
| `ingest` | Source documents, connector runs, raw observations, document chunks |
| `fact` | Canonical facts, price history, catalyst events |
| `research` | Runs, steps, snapshots, artifact metadata, audit events |
| `valuation` | Valuation assumptions, run metadata, summaries |
| `report` | Reports, claims, citations, gates, approvals |
| `audit` | Governance events, migration/cost/deletion records |

### 5. Supabase Storage và artifact contract

| Thành phần | Công nghệ/cơ chế | Vai trò | Bằng chứng |
|---|---|---|---|
| Object storage | Supabase Storage REST API | Lưu official documents, run artifacts, approved exports, archive | `backend/storage/supabase_adapter.py` |
| Storage client | Adapter tự viết bằng `urllib.request` | Tránh dependency Supabase Python SDK; dùng service-role key | `backend/storage/supabase_adapter.py` |
| Bucket contract | `sources`, `runs`, `exports`, `archive` | Ràng buộc phân vùng storage theo lifecycle | `backend/storage/layout.py` |
| Key validation | Regex + allow-list artifact names | Ngăn path traversal và object key ngoài contract | `backend/storage/layout.py` |
| User-facing signed URL | Chỉ bucket `exports` | Giảm rủi ro lộ source/runtime artifacts | `backend/storage/supabase_adapter.py` |

Storage key chính:

| Bucket | Key mẫu | Ý nghĩa |
|---|---|---|
| `sources` | `official_documents/{TICKER}/{YEAR}/{source_doc_id}.pdf` | Official PDF/source binary bất biến |
| `runs` | `{run_id}/manifest.json`, `{run_id}/valuation.json`, `{run_id}/report.html`, `{run_id}/quality_gate.json` | Artifact theo một lần chạy cụ thể |
| `exports` | `approved_reports/{TICKER}/{run_id}/report.pdf` | Client-facing report đã được publish |
| `archive` | `legacy/...`, `debug/...`, `failed_runs/...` | Lưu trữ legacy/debug/failure artifacts |

### 6. Data ingestion và external sources

| Nhóm nguồn | Công nghệ/kết nối | Vai trò | Bằng chứng |
|---|---|---|---|
| Financial statements API | `vnstock.api.financial.Finance`, pandas | Lấy income statement, balance sheet, cash flow, ratios từ VCI/KBS | `scripts/connectors/vnstock_finance_connector.py` |
| Market price API | `vnstock.api.quote.Quote`, pandas | Lấy giá hiện tại/lịch sử, market snapshot, chart input | `scripts/connectors/vnstock_price_connector.py`, `backend/reporting/market_data_artifact.py` |
| Company metadata | `vnstock.api.company.Company` | Hồ sơ công ty, market snapshot bổ sung | `scripts/connectors/vnstock_company_connector.py`, `backend/reporting/market_snapshot.py` |
| Official document discovery | Company IR, HOSE, HNX, SSC connectors | Tìm và xếp hạng PDF/source chính thức | `backend/documents/connectors/` |
| Catalyst crawler | `requests`, `beautifulsoup4` | Crawl DAV, BHYT, HOSE, tender feeds | `scripts/connectors/catalyst_*.py` |
| News subsystem | stdlib `HTMLParser`, custom extractor/store/evidence builder | Thu thập và kiểm chứng narrative evidence, tránh phụ thuộc trafilatura/bs4 trong extractor chính | `backend/news/` |
| Manual/golden fixtures | CSV/YAML/JSON | Bootstrap MVP, kiểm thử golden facts, universe/taxonomy | `config/dataset/` |

Manifest đã khai báo trực tiếp `vnstock`, `requests` và `beautifulsoup4`, do đó crawler và connector tài chính không còn phụ thuộc vào dependency bắc cầu khi tái dựng môi trường sạch.

### 7. Document processing, OCR và retrieval

| Thành phần | Công nghệ | Trạng thái | Bằng chứng |
|---|---|---|---|
| PDF text extraction | `pdfplumber` | Trích text/table từ PDF có text layer | `backend/documents/`, `scripts/build_index.py` |
| OCR engine | Tesseract OCR + Vietnamese language pack | Xử lý PDF scan tiếng Việt | `Dockerfile`, `scripts/check_ocr_runtime.py`, `backend/documents/pdf_extractor.py` |
| PDF to image | Poppler + `pdf2image` | Render trang PDF thành ảnh trước OCR | `Dockerfile`, `docs/OCR_PIPELINE.md` |
| Image processing | Pillow/PIL | Dependency cho OCR/image pipeline | `requirements.txt`, `scripts/check_ocr_runtime.py` |
| OCR Python binding | `pytesseract` | Gọi Tesseract từ Python | `requirements.txt`, `scripts/database/ocr_official_document.py` |
| Semantic retrieval | OpenAI embeddings + pgvector | Vector query khi có embedding và `OPENAI_API_KEY` | `backend/retrieval.py`, `scripts/admin/chunk_pipeline.py` |
| Retrieval fallback | PostgreSQL full-text search | Tìm evidence khi embedding unavailable | `backend/retrieval.py` |
| Source-tier prioritization | SQL order by source tier | Ưu tiên official sources trước aggregator/API | `backend/retrieval.py` |

Nguyên tắc sản phẩm: OCR và embeddings chỉ hỗ trợ evidence discovery; chúng không phải source of truth tài chính. Fact tài chính phải đi qua normalization, reconciliation, source tier policy, và promotion gates trước khi được dùng trong valuation/report.

### 8. Analytics, forecast và valuation

| Module | Vai trò kỹ thuật |
|---|---|
| `backend/analytics/ratios.py` | Tính financial ratios từ fact/snapshot |
| `backend/analytics/forecasting.py` | Forecast driver-based theo giai đoạn FY |
| `backend/analytics/fcff.py` | FCFF DCF: EBIT sau thuế, D&A, CAPEX, NWC, WACC, EV-to-equity bridge |
| `backend/analytics/fcfe.py` | FCFE DCF: NI, D&A, CAPEX, NWC, net borrowing, cost of equity |
| `backend/analytics/blend.py` | Blend DCF 60% FCFF và 40% FCFE |
| `backend/analytics/multiples.py` | P/E, EV/EBITDA, relative valuation cross-check |
| `backend/analytics/sensitivity.py` | Sensitivity tables cho WACC/g, Re/g, multiples |
| `backend/analytics/approval_gate.py` | Kiểm soát assumption readiness trước export |
| `backend/analytics/cash_sweep.py`, `debt_schedule.py`, `dividend_schedule.py`, `working_capital_schedule.py`, `share_rollforward.py`, `tax_policy.py` | Các schedule hỗ trợ forecast và bridge định giá |

Quy tắc kiến trúc cốt lõi: LLM không được là máy tính định giá chính. Target price, DCF, ratios, sensitivity, formula trace, và sanity checks phải được sinh bằng Python deterministic modules; LLM chỉ nên tổng hợp narrative, giải thích, hoặc critic output trong biên giới evidence.

### 9. Reporting, charts và PDF export

| Thành phần | Công nghệ | Trạng thái | Bằng chứng |
|---|---|---|---|
| HTML templating | Jinja2 | Render report HTML từ view model | `backend/reporting/html_renderer.py`, `backend/reporting/templates/` |
| Markdown conversion | `markdown` | Hỗ trợ dev rendering và legacy sections | `backend/reporting/html_renderer.py`, `scripts/render_report.py` |
| Charting | Matplotlib Agg | Sinh chart PNG deterministic không cần GUI | `backend/reporting/chart_generator.py` |
| Statistical visualization | Seaborn | Heatmap sensitivity và biểu đồ phân tích | `backend/reporting/chart_generator.py` |
| Tabular processing | pandas, numpy | Xử lý dữ liệu market/fact/chart input | `backend/reporting/market_data_artifact.py`, `backend/reporting/chart_generator.py` |
| Primary PDF renderer | WeasyPrint | Backend ưu tiên cho Vietnamese Unicode PDF | `backend/reporting/pdf_renderer.py` |
| PDF fallback 1 | pdfkit + wkhtmltopdf | Fallback khi WeasyPrint lỗi | `backend/reporting/pdf_renderer.py` |
| PDF fallback 2 | Chrome/Edge headless | Fallback qua `--print-to-pdf` nếu có browser cài trên máy | `backend/reporting/pdf_renderer.py` |
| PDF fallback 3 | xhtml2pdf + Unicode font injection | Fallback cuối khi có font DejaVu/NotoSans | `backend/reporting/pdf_renderer.py` |
| PDF preflight | pypdf | Trích text để phát hiện mojibake/forbidden terms | `backend/reporting/pdf_renderer.py` |

PDF manifest đã khai báo `pdfkit` và `pypdf`; WeasyPrint vẫn là renderer chính, còn wkhtmltopdf hoặc Chrome/Edge là fallback phụ thuộc môi trường. Font Unicode cho PDF fallback cần được kiểm chứng trong image thật khi chuyển sang production SLA, nhưng không còn là blocker của nghiệm thu MVP5.

### 10. Evaluation, citations và governance gates

| Nhóm kiểm định | Công nghệ/cơ chế | Mục tiêu | Bằng chứng |
|---|---|---|---|
| Numeric consistency | Python validators | Số trong report khớp fact/artifact canonical | `backend/evaluation/numeric_consistency.py` |
| Citation coverage | Citation map, claim ledger, validator | Claim quan trọng phải có source refs hợp lệ | `backend/citations/`, `backend/evaluation/citation_coverage.py` |
| Source provenance | Source tier policy | Chặn claim thiếu official support hoặc dựa quá nhiều vào Tier 3 | `backend/citations/source_tier_policy.py`, `backend/evaluation/source_provenance_gates.py` |
| Formula trace | Harness deterministic gate | Đảm bảo valuation có trace tái lập | `backend/harness/gates.py` |
| Forecast quality | Gate riêng cho forecast | Kiểm tra driver support, forecast structure, cash-flow consistency | `backend/harness/gates.py` |
| Export gate | Workflow export gate | Chặn publish khi critical gates fail | `backend/harness/gates.py`, `config/harness/export_gate_policy.yml` |
| Senior critic | Tool + LLM critic | Review narrative và readiness | `scripts/evaluate_report_quality.py`, `config/agents/prompts/senior_critic.md` |

Đây là lớp reliability quan trọng nhất của dự án: agentic workflow được phép tạo narrative và phân tích, nhưng publish path bị ràng buộc bởi artifact manifest, formula trace, citation coverage, source provenance, và report completeness.

### 11. Scheduling, CLI và vận hành

| Thành phần | Công nghệ/cơ chế | Trạng thái | Bằng chứng |
|---|---|---|---|
| Canonical CLI commands | Makefile | `make test`, `make audit`, `make run-research`, `make run-once` | `Makefile` |
| Research entrypoint | Python scripts | `scripts/run_research.py`, `scripts/generate_fast_report.py`, `scripts/ingest_pdf_llm.py`, `scripts/ingest_agm.py` | `scripts/` |
| Benchmark entrypoints | Python scripts | `scripts/run_project_evaluation.py` cho tám plan, `scripts/run_benchmark_suite.py` cho cohort benchmark | `scripts/`, `backend/evaluation/` |
| Scheduler | Windows Task Scheduler | Job gọi CLI idempotent thu thập tin định kỳ; app runtime không phụ thuộc scheduler nào | `scripts/schedule_news_collection.ps1`, `scripts/collect_ticker_news.py` |
| Docker entrypoint | Shell CMD | `APP_MODE=api` chạy migrations rồi Uvicorn; `APP_MODE=worker` chạy migrations rồi `scripts/run_research.py` | `Dockerfile` |
| OCR smoke test | Python script | Kiểm tra Tesseract/Poppler/Python OCR packages | `scripts/check_ocr_runtime.py` |
| Storage migration scripts | Python scripts | Di chuyển local artifacts/documents lên Supabase Storage | `scripts/storage/` |

Scheduling được tách khỏi app runtime: news collection chạy qua Windows Task Scheduler gọi `scripts/collect_ticker_news.py` (đăng ký bằng `scripts/schedule_news_collection.ps1`); application requirements không chứa scheduler dependency. Astro/Airflow deploy kit đã được gỡ.

### 12. Testing và quality assurance

| Thành phần | Công nghệ | Trạng thái | Bằng chứng |
|---|---|---|---|
| Test framework | pytest | Unit, integration, database, evaluation, reporting, source/citation tests | `tests/`, `pytest.ini` |
| Test markers | `integration` | Phân loại live integration tests | `pytest.ini` |
| Contract tests | Python unit tests | Bảo vệ gates, storage layout, model adapter, migration runner, valuation formulas | `tests/` |
| Make targets | `make test`, `make audit`, `make run-research`, `make run-once` | Lệnh kiểm thử và vận hành chính; `run-once` bọc PDF LLM, AGM ingest, harness draft và render local | `Makefile` |

Trạng thái nghiệm thu: `make test`, focused gate tests, frontend tests và project evaluation tạo baseline đủ cho đồ án. CI/CD đa môi trường và lockfile reproducibility được giữ trong residual roadmap 1/10 vì chúng thuộc productionization hơn là chứng minh phương pháp nghiên cứu.

### 13. Configuration, taxonomy và domain contracts

| Loại cấu hình | File/thư mục | Vai trò |
|---|---|---|
| Agent config | `config/agents/agents.yml` | Agent role, model, prompt, allowed tools, schema, timeout |
| Agent prompts | `config/agents/prompts/` | Prompt chuyên biệt cho từng agent |
| Harness contracts | `config/harness/` | Tool contracts, task registry, run state schema, evidence packet schema, export gate policy |
| Financial taxonomy | `config/dataset/taxonomy/financial_taxonomy_vn_pharma.yaml` | Metric canonical ngành dược/y tế Việt Nam |
| Catalyst taxonomy | `config/dataset/taxonomy/catalyst_taxonomy_vn_pharma.yaml` | Event taxonomy cho catalyst ngành |
| Metric dictionary | `config/financial_metric_dictionary.yaml` | Mapping label Việt/English/API/OCR vào canonical metric IDs |
| Source registry | `config/source_registry.yaml`, `config/dataset/sources/source_catalog.yaml` | Nguồn dữ liệu được phép, source tier, metadata |
| Universe | `config/dataset/universe/pharma_vn_universe.csv` | Tập ticker MVP |
| Golden facts | `config/dataset/golden/financials/` | Fixture kiểm thử dữ liệu tài chính |
| JSON schema contracts | `config/dataset/contracts/` | Contracts cho document chunks, citations, catalyst events, financial facts, source versions |

### 14. Observability, auditability và state tracking

| Thành phần | Công nghệ/cơ chế | Trạng thái | Bằng chứng |
|---|---|---|---|
| Run state | PostgreSQL tables qua `RuntimeStore` | Lưu run, step, artifacts, status, checkpoints | `backend/runtime_store.py` |
| Step audit | `research.run_steps` và audit events | Ghi stage, agent, duration, status, hashes, tool calls | `backend/harness/runner.py`, migrations |
| Artifact manifest | JSON manifest theo `run_id` | Chống lookup kiểu latest/glob và tăng reproducibility | `backend/harness/runner.py`, `backend/storage/layout.py` |
| Cost ledger | Budget/cost estimate | Ước tính chi phí model call theo token | `backend/services.py`, `backend/harness/model_adapter.py` |
| Langfuse | OpenAI drop-in tracing (`langfuse.openai`) | Đã nối: mỗi LLM call tạo 1 trace, gom theo `langfuse_session_id=run_id`; bật khi có `LANGFUSE_PUBLIC_KEY`+`LANGFUSE_SECRET_KEY`, no-op nếu thiếu | `backend/harness/model_adapter.py` (`_resolve_openai_client`, `flush_traces`) |
| Logging | Python logging + stderr progress | Theo dõi harness stage, LLM call, tool trace | `backend/harness/runner.py`, `backend/harness/model_adapter.py` |

Langfuse là optional: khi credentials có mặt, adapter chuyển sang drop-in `langfuse.openai` và flush ở cuối run; khi vắng credentials, dùng `openai` trần không kèm tracing kwargs.

### 15. System dependencies ngoài Python

| Dependency hệ thống | Trạng thái trong Dockerfile | Vai trò |
|---|---|---|
| `build-essential`, `gcc`, `python3-dev` | Có | Build native Python wheels khi cần |
| `tesseract-ocr` | Có | OCR engine |
| `tesseract-ocr-vie` | Có | Vietnamese OCR language data |
| `poppler-utils` | Có | PDF-to-image conversion cho OCR |
| `libpq-dev` | Có | PostgreSQL native compilation/runtime support |
| `curl` | Có | Network diagnostics/download support |
| Unicode fonts | Chưa cài rõ trong Dockerfile | Cần cho PDF tiếng Việt ổn định |
| `wkhtmltopdf` | Chưa cài | Cần cho pdfkit fallback |
| Chrome/Edge/Chromium | Chưa cài | Cần cho headless browser PDF fallback |

### 16. Dependency inventory đối chiếu

| Nhóm | Package/công nghệ | Trạng thái hiện tại |
|---|---|---|
| Đã khai báo và đang dùng | `fastapi`, `uvicorn`, `pydantic`, `psycopg2-binary`, `pandas`, `numpy`, `pdfplumber`, `pyyaml`, `openai`, `pytest`, `pytesseract`, `pdf2image`, `Pillow`, `matplotlib`, `seaborn`, `jinja2`, `markdown`, `weasyprint`, `xhtml2pdf` | Hợp lệ về mặt manifest, cần pin version nếu muốn reproducibility |
| Đã bổ sung trực tiếp sau rà soát import | `vnstock`, `requests`, `beautifulsoup4`, `pdfkit`, `pypdf` | Không còn phải dựa vào dependency bắc cầu cho crawler, PDF fallback và preflight |
| Khai báo nhưng chưa thấy runtime integration chính | `anthropic` | Cần quyết định giữ làm optional hoặc loại khỏi production requirements (`langfuse` đã được tích hợp qua drop-in OpenAI) |
| System packages đã khai báo | Tesseract, Vietnamese Tesseract data, Poppler, libpq, compiler toolchain, curl | Đủ cho OCR cơ bản và DB build/runtime |
| System packages còn thiếu hoặc phụ thuộc môi trường | Unicode fonts, wkhtmltopdf, Chrome/Chromium, WeasyPrint native/font prerequisites | Cần chuẩn hóa nếu PDF là output bắt buộc |

## Strategic Recommendations

### 1. Duy trì dependency manifest sau nghiệm thu

| Ưu tiên | Hành động | Lý do |
|---|---|---|
| Done | `vnstock`, `requests`, `beautifulsoup4`, `pdfkit`, `pypdf` và evaluation stack đã có trong `requirements.txt` | Các import thực tế đã được khai báo trực tiếp cho môi trường sạch |
| P0 | Cập nhật `.env.example`: bỏ hoặc ghi rõ `ANTHROPIC_API_KEY` là legacy/unused nếu chưa có Anthropic adapter | Tránh cấu hình sai provider production |
| P1 | Pin version tối thiểu có kiểm chứng hoặc tạo `requirements.lock` | Giảm drift do dependency floating |
| P1 | Chuẩn hóa PDF dependencies: chọn WeasyPrint-only hoặc cài đủ fallback system packages | Giảm lỗi PDF tiếng Việt theo môi trường |
| Done | Langfuse: đã tích hợp tracing thật qua drop-in `langfuse.openai` (mỗi LLM call → 1 trace, gom theo run) | Observability nối thật, optional theo credentials |

### 2. Chuẩn hóa deployment contract

| Vấn đề | Khuyến nghị |
|---|---|
| Supabase-only runtime | Tài liệu vận hành phải nói rõ `DATABASE_URL` local bị từ chối; README nào còn nhắc local PostgreSQL cần cập nhật |
| Storage contract | Giữ Supabase Storage adapter tự viết nếu mục tiêu là giảm dependency, nhưng cần test integration cho bucket/key/signed URL |
| Docker reproducibility | Build image phải chạy được `python -m backend.database.migrate`, OCR smoke test, và một report render smoke test tối thiểu |
| Residual roadmap | Thêm workflow chạy import smoke, unit tests, storage layout tests, và một target kiểm tra `requirements.txt` khớp import thực tế |

### 3. Giữ nguyên ranh giới sản phẩm giữa LLM và deterministic finance

| Ranh giới | Quyết định nên giữ |
|---|---|
| LLM | Planning, synthesis, structured narrative, critique, evidence request |
| Python deterministic | Forecast, FCFF/FCFE, ratios, sensitivity, formula trace, report gates |
| Database | Canonical facts, source provenance, run state, artifact metadata |
| Storage | Immutable source binaries, run-scoped artifacts, approved exports |
| Gates | Publish blocker cho citation, source tier, numeric consistency, formula trace, completeness |

### 4. Kết luận kỹ thuật

Tech stack thực tế của dự án gồm Python 3.11, FastAPI/Uvicorn, Pydantic v2, Supabase PostgreSQL, psycopg2, OpenAI embeddings, pgvector, PostgreSQL full-text search, vnstock, pandas/numpy, OCR bằng Tesseract/Poppler/pdfplumber/pdf2image/Pillow, reporting bằng Jinja2/Markdown/Matplotlib/Seaborn, WeasyPrint/pdfkit/Chrome/xhtml2pdf/pypdf preflight, deterministic valuation modules, pytest, Windows Task Scheduler cho news cron, và optional Langfuse/Anthropic tùy trạng thái tích hợp.

Điểm mạnh kiến trúc là dự án đã đặt agent vào một workflow có graph cố định, typed contracts, source provenance, run-scoped artifacts, live evaluation dashboard và export gates. Phần còn lại của tech stack nằm ở productionization: lockfile, CI/CD đa môi trường, queue bền vững và hardening PDF fallback trong container SLA.
