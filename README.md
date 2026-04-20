# Multi-Agent Equity Research System — Pharma

> **Financial-Document Intelligence Engine** cho ngành Dược phẩm Việt Nam.  
> Tự động hóa toàn bộ pipeline equity research chuẩn CFA — từ ingestion đến báo cáo hoàn chỉnh — trong dưới 60 phút.

---

## Mục lục

- [Tổng quan](#tổng-quan)
- [Kiến trúc 5 Agent](#kiến-trúc-5-agent)
- [Tech Stack](#tech-stack)
- [Cấu trúc Dự án](#cấu-trúc-dự-án)
- [Roadmap Triển khai](#roadmap-triển-khai)
- [KPIs](#kpis)

---

## Tổng quan

Dự án xây dựng hệ thống **Multi-Agent AI** tự động hóa 9 bước phân tích chuẩn CFA Institute cho cổ phiếu ngành Dược (Pharma). Mục tiêu:

| Tiêu chí | Hiện tại | Mục tiêu |
|---|---|---|
| Thời gian lập báo cáo | 3–7 ngày | < 60 phút (bản nháp) |
| Độ chính xác trích xuất số liệu | ~70–80% (thủ công) | > 98% |
| Citation coverage | Không có | 100% định lượng có nguồn |
| Số cổ phiếu theo dõi đồng thời | 2–3 | 10–20 |

Hệ thống **không** là "AI viết văn" — mà là pipeline có kiểm chứng, mọi con số đều traceable, human analyst duyệt cuối.

---

## Kiến trúc 5 Agent

```
┌─────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR                        │
│         Điều phối workflow · Routing · HITL              │
└────────────┬────────────────────────────────────────────┘
             │
    ┌────────▼─────────┐
    │  Data Foundation  │  Ingestion · Parsing · SQL · News
    │      Agent        │  PDF/XBRL/Transcript → DB + VectorStore
    └────────┬──────────┘
             │
    ┌────────▼─────────┐
    │   Core Analyst    │  Financial Ratios (code) · Pharma Pipeline
    │      Agent        │  PoS-adjusted Forecast · Peer Comparison
    └────────┬──────────┘
             │
    ┌────────▼─────────┐
    │  Valuation &      │  DCF · Multiples · Sensitivity
    │  Reasoning Agent  │  Structured Debate: Believer ↔ Skeptic
    └────────┬──────────┘
             │
    ┌────────▼─────────┐
    │ Synthesis &       │  CFA Report Writer · Citation Mapper
    │  Auditor Agent    │  Confidence Scorer · Final Quality Gate
    └───────────────────┘
```

### Workflow 9 Bước CFA

1. Xác định phạm vi & investment thesis
2. Ingestion & Structuring (Data Foundation Agent)
3. Business & Industry Analysis — Pipeline + Peer
4. Historical Financial Analysis — Code-first, không LLM thuần
5. Forecasting — PoS-adjusted (base / bull / bear)
6. Valuation — DCF + Multiples + Sensitivity
7. Structured Debate — Believer mode → Skeptic mode (internal dual-role)
8. Synthesis & Report Generation — Grounded, 100% citation
9. HITL Review & Final Publication

---

## Tech Stack

### Agent Framework & LLM

| Layer | Công nghệ | Lý do chọn |
|---|---|---|
| **Agent Framework** | [LangGraph](https://github.com/langchain-ai/langgraph) | Stateful graph workflow, kiểm soát loop/retry chặt, phù hợp production hơn CrewAI |
| **LLM chính** | Claude claude-sonnet-4-6 / claude-opus-4-6 (Anthropic) | Tool use mạnh, context window lớn cho PDF dài, grounding tốt |
| **LLM phụ** | Claude Haiku 4.5 | Routing, classification, summarize nhanh và rẻ |
| **LLM Tooling** | [LangChain](https://python.langchain.com/) | RAG pipeline, SQL chain, prompt management |
| **LLM Tracing** | [LangSmith](https://smith.langchain.com/) | Debug agent chains, đo latency từng bước |

### Data Ingestion & Parsing

| Task | Công nghệ |
|---|---|
| PDF tài chính (tables, figures) | **Nougat** (Meta) + **pdfplumber** + **camelot** |
| Layout & table understanding | **LayoutLMv3** (Microsoft) |
| XBRL / SEC filings | **python-xbrl** + **sec-edgar-downloader** |
| Earnings transcripts | **BeautifulSoup** + custom scraper |
| News & regulatory (FDA/EMA) | **newsapi-python** + RSS feeds |
| Semantic normalization | Custom taxonomy mapper (YAML config) |

### Database & Storage

| Layer | Công nghệ | Vai trò |
|---|---|---|
| **Relational DB** | **PostgreSQL 16** | Financial data chuẩn hóa, Text-to-SQL |
| **Vector Store** | **pgvector** (Postgres extension) | Cùng DB — giảm số service, SQL + vector trong 1 nơi |
| **Text-to-SQL** | **Vanna.ai** | Tự học schema tài chính, sinh SQL chính xác |
| **Task Queue** | **Celery + Redis** | Async agents, long-running jobs |
| **Object Storage** | **MinIO** (local) / S3 | Raw PDFs, XBRL, file gốc |

### Quantitative Engine (Code-first, không dùng LLM để tính)

```python
pandas + numpy + scipy        # Financial calculations, time series
quantlib-python               # DCF, bond pricing chuẩn
statsmodels                   # Regression, forecasting models
plotly + matplotlib           # Charts nhúng vào report
```

### External APIs

| API | Dữ liệu |
|---|---|
| [ClinicalTrials.gov API](https://clinicaltrials.gov/api/gui) | Drug pipeline, Phase I/II/III status |
| [OpenFDA API](https://open.fda.gov/apis/) | Drug approvals, recalls, adverse events |
| **yfinance** | Giá cổ phiếu quốc tế |
| **VNDIRECT / SSI / FiinGroup API** | Giá & BCTC cổ phiếu VN (DHG, TRA, VNP) |

### Backend, Report & Frontend

| Layer | Công nghệ |
|---|---|
| **REST API** | **FastAPI** (async) + **Pydantic v2** |
| **Report Template** | **Jinja2** (HTML → CFA layout) |
| **Export** | **WeasyPrint** (PDF) + **python-docx** (Word) |
| **HITL Dashboard** | **Streamlit** (MVP) → Next.js + shadcn/ui (production) |
| **Containerization** | **Docker + Docker Compose** |
| **CI/CD** | **GitHub Actions** |

---

## Cấu trúc Dự án

```
multi-agent-equity-research/
│
├── agents/                              # 5 core agents
│   ├── orchestrator/
│   │   ├── orchestrator.py              # Main orchestration logic
│   │   ├── router.py                    # Task routing & delegation
│   │   └── hitl.py                      # Human-in-the-loop checkpoints
│   │
│   ├── data_foundation/
│   │   ├── agent.py
│   │   ├── parsers/
│   │   │   ├── pdf_parser.py            # Nougat + pdfplumber
│   │   │   ├── xbrl_parser.py           # SEC XBRL
│   │   │   ├── transcript_parser.py     # Earnings transcripts
│   │   │   └── news_scraper.py          # FDA / EMA / Reuters
│   │   ├── normalizer.py                # Semantic taxonomy mapping
│   │   └── sql_structurer.py            # Text-to-SQL via Vanna.ai
│   │
│   ├── core_analyst/
│   │   ├── agent.py
│   │   ├── financial_analytics.py       # Ratios, trends (code-first)
│   │   ├── pharma_pipeline.py           # PoS analysis, patent cliff
│   │   └── peer_comparison.py           # Peer benchmarking
│   │
│   ├── valuation_reasoning/
│   │   ├── agent.py
│   │   ├── dcf_engine.py                # DCF Python calculator
│   │   ├── multiples_engine.py          # EV/EBITDA, P/E, EV/Sales
│   │   ├── sensitivity.py               # Sensitivity / scenario analysis
│   │   └── debate.py                    # Dual-role: Believer + Skeptic
│   │
│   └── synthesis_auditor/
│       ├── agent.py
│       ├── report_writer.py             # CFA-standard report composer
│       ├── citation_mapper.py           # Grounded citation (trang/dòng)
│       ├── confidence_scorer.py         # Per-claim confidence score
│       └── final_evaluator.py           # Quality gate trước HITL
│
├── workflows/
│   ├── graph.py                         # LangGraph state machine (entry point)
│   ├── states.py                        # Typed state definitions
│   ├── edges.py                         # Conditional routing logic
│   └── checkpoints.py                   # HITL pause / resume points
│
├── tools/                               # Shared tools dùng cho nhiều agents
│   ├── sql_tools.py                     # Query PostgreSQL
│   ├── vector_tools.py                  # pgvector semantic search
│   ├── calc_tools.py                    # Python interpreter wrapper
│   ├── citation_tools.py                # Source → page/line mapping
│   └── external_apis/
│       ├── clinical_trials.py           # ClinicalTrials.gov
│       ├── fda_api.py                   # OpenFDA
│       └── market_data.py              # yfinance / VNDIRECT
│
├── database/
│   ├── models/
│   │   ├── company.py                   # ORM: Company master
│   │   ├── financial_statements.py      # Income / Balance / Cashflow
│   │   ├── drug_pipeline.py             # Drug trials, PoS, patent dates
│   │   └── news_events.py               # Regulatory events, M&A
│   ├── migrations/                      # Alembic migration scripts
│   └── seeds/
│       └── golden_dataset/              # DHG, TRA, VNP — 3–5 năm
│
├── rag/
│   ├── embeddings.py                    # Embedding pipeline
│   ├── indexer.py                       # Document chunking & indexing
│   ├── retriever.py                     # Semantic search + reranking
│   └── citation_store.py               # Lưu source → chunk → page/line
│
├── reports/
│   ├── templates/
│   │   ├── cfa_report.html.jinja2       # CFA 7–10 trang chuẩn
│   │   └── executive_summary.html.jinja2
│   ├── exporter.py                      # PDF / Word export
│   └── outputs/                         # Báo cáo đã sinh (gitignored)
│
├── api/
│   ├── main.py                          # FastAPI application
│   ├── routes/
│   │   ├── research.py                  # POST /research/start
│   │   ├── status.py                    # GET  /research/{id}/status
│   │   ├── hitl.py                      # POST /research/{id}/approve
│   │   └── reports.py                   # GET  /reports/{id}
│   └── schemas/                         # Pydantic request/response models
│
├── ui/
│   ├── app.py                           # Streamlit HITL dashboard
│   └── pages/
│       ├── 01_new_research.py           # Nhập ticker, scope
│       ├── 02_review_assumptions.py     # HITL: duyệt assumptions
│       └── 03_final_report.py           # Xem & export báo cáo
│
├── config/
│   ├── settings.py                      # Pydantic BaseSettings (.env)
│   ├── agents_config.yaml               # Model, temperature, thresholds
│   ├── taxonomy.yaml                    # Financial line item mappings
│   └── prompts/                         # System prompts per agent
│       ├── orchestrator.md
│       ├── data_foundation.md
│       ├── core_analyst.md
│       ├── valuation_believer.md
│       ├── valuation_skeptic.md
│       └── synthesis_auditor.md
│
├── tests/
│   ├── unit/                            # Unit test từng tool/function
│   ├── integration/                     # Test agent-to-agent flow
│   ├── golden/                          # So sánh output vs golden dataset
│   └── evaluation/                      # KPI measurement scripts
│
├── notebooks/                           # EDA, prototyping
│   ├── 01_data_exploration.ipynb
│   ├── 02_dcf_prototype.ipynb
│   └── 03_rag_evaluation.ipynb
│
├── docker/
│   ├── Dockerfile
│   ├── docker-compose.yml               # Postgres + Redis + MinIO + App
│   └── docker-compose.dev.yml
│
├── .env.example
├── pyproject.toml                       # Poetry dependencies
├── problem_brief.md
└── README.md
```

---

## Roadmap Triển khai

### Phase 1 — Nền tảng dữ liệu (Tuần 1–3)
- [ ] Xây **Golden Dataset**: DHG, TRA, VNP — 3–5 năm BCTC
- [ ] **Data Foundation Agent**: PDF parser + XBRL + SQL schema + normalizer
- [ ] **LangGraph workflow skeleton**: states, edges, HITL checkpoints
- [ ] PostgreSQL schema + pgvector setup

### Phase 2 — Core Analytics (Tuần 4–6)
- [ ] **Core Analyst Agent**: financial ratios (code-first, pandas)
- [ ] **Pharma pipeline**: ClinicalTrials.gov API + PoS model
- [ ] **RAG pipeline**: embedding, indexing, citation mapping
- [ ] Peer comparison module

### Phase 3 — Valuation & Debate (Tuần 7–8)
- [ ] **DCF + Multiples engine** (Python, không LLM)
- [ ] **Sensitivity analysis** — base / bull / bear scenarios
- [ ] **Structured Debate**: dual-role prompt (Believer ↔ Skeptic)

### Phase 4 — Report & HITL (Tuần 9–10)
- [ ] **CFA report template** (Jinja2) + PDF/Word export
- [ ] **Streamlit HITL dashboard** — review assumptions & final approval
- [ ] **KPI evaluation** vs golden dataset
- [ ] End-to-end integration test

---

## KPIs

| KPI | Mục tiêu |
|---|---|
| Accuracy trích xuất số liệu | > 98% |
| Citation coverage | 100% nhận định định lượng có nguồn |
| Thời gian sinh bản nháp | < 60 phút |
| Consistency giữa agents | Sai lệch < ngưỡng tolerance |
| Human Satisfaction (NPS) | Analyst rating ≥ 4/5 |

---

## Nguyên tắc Thiết kế

- **Code-first quantitative**: DCF, ratios, sensitivity chạy bằng Python thuần — không dùng LLM để tính toán, triệt tiêu hallucination số.
- **100% Grounded**: mọi con số trong báo cáo đều có citation đến trang/dòng nguồn.
- **Dual-role Debate**: Believer + Skeptic trong cùng một agent — tinh gọn hơn 3 agent riêng, vẫn đảm bảo tranh luận.
- **AI làm nháp, người duyệt cuối**: HITL tại assumptions và final approval — giảm rủi ro pháp lý.
- **Đơn giản trước, phức tạp sau**: bắt đầu workflow tuyến tính → nâng autonomy dần khi đã validate.
