# Vietnam Pharma Equity Research Agent

Hệ thống nghiên cứu cổ phiếu dược phẩm Việt Nam theo quy trình **evidence-grounded**, **code-first valuation**, và **human-in-the-loop approval**. Sinh báo cáo phân tích cổ phiếu có nguồn trích dẫn kiểm toán, không dùng LLM để tính toán số liệu tài chính.

> **CẢNH BÁO:** Hệ thống này dùng cho nghiên cứu nội bộ và học thuật. Không phải phần mềm tư vấn đầu tư. Tất cả báo cáo phải qua phê duyệt của chuyên gia trước khi sử dụng.

---

## Kiến trúc tổng quan

```
Dữ liệu thị trường (vnstock)
        │
        ▼
[Ingestion] ingest_ticker.py
  → Lưu raw payload + source metadata
        │
        ▼
[Canonical Facts] build_facts.py
  → Chuẩn hóa, validate, lưu DB (PostgreSQL)
        │
        ▼
[Valuation] run_valuation.py
  → Ratios, DCF 3 kịch bản, FCFF (60%), FCFE (40%),
    Blend 60/40, Multiples, Sensitivity tables
  → Artifact JSON → Supabase Storage `runs/{run_id}/valuation.json`
        │
        ▼
[Evidence Index] build_index.py
  → Chunking tài liệu, citation map
        │
        ▼
[Six-Agent Report Assembly] run_research.py
  -> ResearchManager, DataEvidence, FinancialAnalysis,
     ForecastValuation, ThesisReport, SeniorCritic
  -> run-scoped report artifacts through the harness manifest
        │
        ▼
[Evaluation Gates] evaluate_report.py
  → 7 cổng kiểm tra (numeric consistency, citation coverage,
    valuation reproducibility, stale data, unsupported claims,
    citation quality, balance sheet identity)
  → PASS / WARN / CRITICAL FAIL
        │
        ▼
[Human Approval] approve_report.py
  -> Reviewer xem xét + approve/reject
  -> FullReportOrchestrator.handle_approval -> RENDER_AND_PUBLISH
  -> report.html/report.pdf sau final approval
```

---

## Yêu cầu môi trường

### Python

```
Python >= 3.10
```

Cài dependencies:

```bash
pip install -r requirements.txt
```

### PostgreSQL

Cần một PostgreSQL instance (local hoặc Supabase). Áp dụng toàn bộ migrations bằng
migration runner (tự động theo thứ tự, idempotent — không chạy psql thủ công từng file):

```bash
python -m backend.database.migrate --check     # liệt kê migration đang pending
python -m backend.database.migrate             # áp dụng tất cả migration còn thiếu
python -m backend.database.migrate --version    # in version schema cao nhất đã áp dụng
```

Runner đọc `DATABASE_URL` từ `.env`. `CURRENT_SCHEMA_VERSION` trong
`backend/database/migrate.py` phải khớp file migration mới nhất.

### OCR Runtime Requirements

For processing scanned Vietnamese BCTC PDFs, the following dependencies are required:

#### System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-vie poppler-utils
```

#### Python Packages

```bash
pip install pytesseract pdf2image Pillow
```

These are included in `requirements.txt` and the `Dockerfile`. For local development without Docker, ensure the system packages are installed before running OCR-dependent scripts.

#### Verify Runtime

```bash
python scripts/check_ocr_runtime.py
```

### Biến môi trường

Tạo file `.env` ở root:

```env
# Dùng Supabase SESSION pooler cổng 5432 — KHÔNG dùng transaction pooler 6543
# (6543 không giữ session/prepared statements → ingestion & migration lỗi).
DATABASE_URL=postgresql://postgres.your-project:your-password@aws-0-your-region.pooler.supabase.com:5432/postgres
OPENAI_API_KEY=sk-...   # production models: gpt-5.4-mini + gpt-5.4-nano
LOG_LEVEL=INFO
```

Các biến tùy chọn (Supabase, Langfuse):

```env
SUPABASE_PROJECT_ID=...
SUPABASE_PUBLIC_KEY=...
SUPABASE_SECRET_KEY=...
LANGFUSE_SECRET_KEY=...
LANGFUSE_PUBLIC_KEY=...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

---

## Tạo báo cáo lần đầu

Chỉ cần chạy theo đúng thứ tự dưới đây. Ví dụ tạo báo cáo cho mã `DHG`.

### 1. Cài đặt ban đầu

Chỉ chạy bước này một lần:

```powershell
pip install -r requirements.txt
python -m backend.database.migrate
$env:PYTHONUTF8 = "1"
```

Đảm bảo file `.env` đã có `DATABASE_URL`, `OPENAI_API_KEY` và cấu hình Supabase.

### 2. Chạy nghiên cứu

```powershell
python scripts/run_research.py --ticker DHG --from-year 2021 --to-year 2025 --draft
```

Lệnh này tự chạy toàn bộ quy trình thu thập dữ liệu, chuẩn hóa, định giá, xây dựng
báo cáo và kiểm tra chất lượng. Không cần chạy riêng từng script trung gian.

### 3. Xuất báo cáo ra máy

Sau khi `run_research.py` hoàn tất:

```powershell
python scripts/generate_fast_report.py --ticker DHG
```

Báo cáo được tạo tại:

```text
output/DHG_fast_report.pdf
output/DHG_fast_report.html
```

Để tạo báo cáo cho công ty khác, thay `DHG` bằng mã cổ phiếu cần nghiên cứu.
Khi cần cập nhật số liệu hoặc nội dung báo cáo, chạy lại bước 2 rồi bước 3.

---
![alt text](image.png)

## Cấu trúc thư mục

```
.
├── backend/
│   ├── analytics/          # Valuation engines (FCFF, FCFE, blend, sensitivity, ...)
│   │   ├── fcff.py         # FCFF: EBIT(1-T)+D&A-CAPEX-ΔNWC; WACC; EV→Equity bridge
│   │   ├── fcfe.py         # FCFE: NI+D&A-CAPEX-ΔNWC+NetBorr; Re; Equity trực tiếp
│   │   ├── blend.py        # 60% FCFF + 40% FCFE; gap check; TV weight check
│   │   ├── sensitivity.py  # WACC×g, Re×g, blend grid, P/E, EV/EBITDA matrices
│   │   ├── forecasting.py  # 5-year forecast engine
│   │   ├── dcf.py          # DCF 3-scenario (simplified OCF-CAPEX)
│   │   ├── ratios.py       # Financial ratios
│   │   └── multiples.py    # P/E, EV/EBITDA cross-check
│   ├── facts/              # Fact normalization, taxonomy
│   ├── database/           # DB repositories and SQL migrations
│   ├── dataset/            # Dataset contract/taxonomy helper code
│   ├── harness/            # Fixed six-agent full_report harness, gates, checkpoints
│
├── scripts/
│   ├── ingest_ticker.py    # Phase 2: Data ingestion
│   ├── build_facts.py      # Phase 3: Canonical facts
│   ├── run_valuation.py    # Phase 4: Valuation
│   ├── build_index.py      # Phase 5: Evidence index
│   ├── generate_report.py  # DEV-ONLY legacy Markdown/citation helper
│   ├── evaluate_report.py  # Phase 7: Evaluation gates
│   ├── run_research.py     # Phase 8: End-to-end pipeline
│   ├── approve_report.py   # Phase 9: run-scoped harness approval
│   └── connectors/         # vnstock connector layer
│
├── reports/
│   ├── *.md                # Draft reports
│   └── approved/           # Approved & exported reports
│
├── storage/
│   ├── runs/               # Local cache/temp only; production artifacts live in Supabase Storage `runs`
│   ├── exports/            # Local cache/temp only; approved exports live in Supabase Storage `exports`
│   └── archive/            # Local staging for archived debug outputs
│
├── config/
│   ├── agents/             # Six-agent YAML config and prompt library
│   ├── dataset/            # Dataset contracts, taxonomy, universe, and golden fixtures
│   └── harness/            # Harness policies, schemas, registries, and contracts
│
├── specs/                  # Architecture & data contract docs
├── tests/                  # Unit + integration tests
├── CLAUDE.md               # Project rules & implementation protocol
└── .env                    # Secrets (không commit)
```

---

## Danh sách 53 mã cổ phiếu dược phẩm và y tế Việt Nam

Universe nghiên cứu đầy đủ được quản lý tại
`config/dataset/universe/pharma_vn_universe.csv`.

| Mã | Công ty | Sàn |
|----|---------|-----|
| DHG | Công ty Cổ phần Dược Hậu Giang | HOSE |
| IMP | Công ty Cổ phần Dược phẩm Imexpharm | HOSE |
| DMC | Công ty Cổ phần Xuất nhập khẩu Y tế Domesco | HOSE |
| TRA | Công ty Cổ phần Traphaco | HOSE |
| DBD | Công ty Cổ phần Dược - Trang thiết bị Y tế Bình Định | HOSE |
| OPC | Công ty Cổ phần Dược phẩm OPC | HOSE |
| PME | Công ty Cổ phần Pymepharco | HOSE |
| MKP | Công ty Cổ phần Hóa - Dược phẩm Mekophar | HOSE |
| TNH | Công ty Cổ phần Bệnh viện Quốc tế Thái Nguyên | HOSE |
| JVC | Công ty Cổ phần Thiết bị Y tế Việt Nhật | HOSE |
| DVN | Tổng Công ty Dược Việt Nam - CTCP | UPCOM |
| DHT | Công ty Cổ phần Dược phẩm Hà Tây | HNX |
| LDP | Công ty Cổ phần Dược Lâm Đồng - Ladophar | HNX |
| PPP | Công ty Cổ phần Dược phẩm Phong Phú | HNX |
| DP3 | Công ty Cổ phần Dược phẩm Trung ương 3 | UPCOM |
| DP1 | Công ty Cổ phần Dược phẩm Trung ương CPC1 | UPCOM |
| TW3 | Công ty Cổ phần Dược - Trang thiết bị Y tế Đà Nẵng | UPCOM |
| MED | Công ty Cổ phần Dược Trung ương Mediplantex | UPCOM |
| PMC | Công ty Cổ phần Dược phẩm Dược liệu Pharmedic | UPCOM |
| AMV | Công ty Cổ phần Sản xuất Kinh doanh Dược và Trang thiết bị Y tế Việt Mỹ | HNX |
| YTC | Công ty Cổ phần Xuất nhập khẩu Y tế Thành phố Hồ Chí Minh | UPCOM |
| VHE | Công ty Cổ phần Dược liệu Việt Nam | UPCOM |
| VDP | Công ty Cổ phần Dược phẩm Trung ương Vidipha | UPCOM |
| DCL | Công ty Cổ phần Dược phẩm Cửu Long | HOSE |
| SPM | Công ty Cổ phần S.P.M | HOSE |
| VMD | Công ty Cổ phần Y Dược phẩm Vimedimex | HNX |
| BVP | Công ty Cổ phần Dược phẩm Bình Việt | HNX |
| HBH | Công ty Cổ phần Chuỗi Nhà thuốc An Khang | HOSE |
| DNM | Công ty Cổ phần Điều dưỡng Minh Hải | UPCOM |
| DBT | Công ty Cổ phần Dược phẩm Trung Việt | UPCOM |
| DPP | Công ty Cổ phần Dược phẩm Phúc Thành | UPCOM |
| DRP | Công ty Cổ phần Dược Rarapharm | UPCOM |
| T32 | Công ty Cổ phần Y tế Hà Tây | UPCOM |
| DTP | Công ty Cổ phần Dược Tây Ninh | UPCOM |
| VMC | Công ty Cổ phần Y Dược Việt Nam | UPCOM |
| NDT | Công ty Cổ phần Bệnh viện Đa khoa tỉnh Ninh Bình | UPCOM |
| P29 | Công ty Cổ phần Dược phẩm Trung ương 29 | UPCOM |
| DDS | Công ty Cổ phần Diagnostics | UPCOM |
| BID | Công ty Cổ phần Dược Bình Dương | UPCOM |
| PDT | Công ty Cổ phần Dược phẩm Đồng Tháp | UPCOM |
| BCR | Công ty Cổ phần Bio-Pharmachemie | UPCOM |
| VNP | Công ty Cổ phần Dược Việt Nhơn | UPCOM |
| YT1 | Công ty Cổ phần Dược phẩm Y tế 1 | UPCOM |
| CPC | Công ty Cổ phần Dược phẩm CPC1 Hà Nội | UPCOM |
| HDA | Công ty Cổ phần Dược Hà Đông | UPCOM |
| TMP | Công ty Cổ phần Dược phẩm Tâm Phúc | UPCOM |
| DRG | Công ty Cổ phần Dược Rế Giang | UPCOM |
| LNT | Công ty Cổ phần Dược Liên | UPCOM |
| HGP | Công ty Cổ phần Dược phẩm Hưng Gia | UPCOM |
| PVD | Công ty Cổ phần Dược phẩm Việt Đức | UPCOM |
| DGW | Công ty Cổ phần Thế Giới Số | HOSE |
| CON | Công ty Cổ phần Dược phẩm Con Khỉ | UPCOM |
| TNT | Công ty Cổ phần Dược phẩm Tân Nhơn Tây | UPCOM |

---

## Nguyên tắc không thay đổi

1. **LLM không được tính toán số liệu tài chính** — tất cả valuation là Python thuần, tất định.
2. **Mọi claim phải có citation** — không có trích dẫn = không được export.
3. **Human approval bắt buộc** — hệ thống không tự publish báo cáo cuối.
4. **Không hardcode secrets** — dùng biến môi trường.
5. **Evaluation gates chặn export** nếu critical fail — không bypass.

---

## Chạy tests

```bash
# Unit tests
python -m pytest tests/unit/ -v

# Integration tests (cần DB)
python -m pytest tests/integration/ -v
```

---

## Cau truc va logic hien tai

### Context

He thong hien tai gom ba lop van hanh chinh:

1. **Research pipeline** trong `backend/`, `scripts/` va `tests/`: thu thap du lieu, tao canonical
   facts, tinh valuation deterministic, lap bao cao va ap dung cac governance gate.
2. **Project evaluation harness** trong `backend/evaluation/project_evaluator.py`: chay lan luot
   8 evaluation plan trong `eval/`, tong hop ket qua test va kiem tra runtime evidence theo nguyen
   tac fail-closed.
3. **Evaluation dashboard** trong `frontend/`: Vite + React + TypeScript doc evaluation packet
   truc tiep tu FastAPI va hien thi trang thai tung lop.
4. **Run-scoped evaluation writer** trong `backend/evaluation/run_evaluation.py`: moi research run
   sinh cac evaluation artifact fail-closed, upload vao Supabase Storage va dang ky trong manifest.

### Evaluation flow

```text
eval/01_data_reliability_plan.md
  -> eval/02_rag_and_ragas_plan.md
  -> eval/03_financial_calculation_plan.md
  -> eval/04_citation_and_source_provenance_plan.md
  -> eval/05_agent_workflow_and_llm_judge_plan.md
  -> eval/06_report_quality_plan.md
  -> eval/07_observability_cost_latency_plan.md
  -> eval/08_rollout_and_ci_plan.md
  -> output/evaluation/eval_result/evaluation_packet.json
  -> GET /eval/framework
  -> frontend dashboard
```

Moi plan chay test scope rieng va tao mot JSON artifact. Test suite pass khong tu dong co nghia
mot research run du dieu kien publish. Neu thieu run-specific artifact, lop do duoc danh dau
`blocked`; diem narrative hoac LLM judge khong duoc ghi de deterministic failure.

Chay evaluation cho ticker pilot:

```powershell
python scripts/run_project_evaluation.py --ticker DHG --output-dir output/evaluation/eval_result
```

Output chinh:

```text
output/evaluation/eval_result/
|-- evaluation_packet.json
|-- data_quality.json
|-- retrieval_eval.json
|-- financial_eval.json
|-- citation_eval.json
|-- agent_eval.json
|-- report_eval.json
|-- observability_eval.json
`-- rollout_ci_eval.json
```

### API va frontend

FastAPI dang ky API route truoc khi mount frontend static:

| Endpoint | Vai tro |
|---|---|
| `GET /eval/framework` | Tra ve evaluation packet moi nhat cho dashboard |
| `GET /eval/results/{artifact_name}` | Tra ve artifact chi tiet da duoc allow-list |
| `GET /research/{run_id}/evaluation` | Tra ve evaluation packet runtime cua mot research run |
| `GET /research/{run_id}/evaluation/{artifact_name}` | Tra ve runtime evaluation artifact chi tiet |
| `GET /` | Phuc vu `frontend/dist/` neu production build ton tai |

Trong development, Vite chay tai cong `5173` va proxy `/eval`, `/research`, `/reports` sang FastAPI
tai cong `8010`. Trong production, FastAPI phuc vu truc tiep build trong `frontend/dist/`.

### Cau truc thu muc lien quan

```text
.
|-- backend/
|   |-- api.py                         # Evaluation API va static frontend mount
|   `-- evaluation/
|       `-- project_evaluator.py       # Sequential 8-plan evaluation harness
|-- eval/                              # Evaluation plans 01..08
|-- frontend/
|   |-- src/
|   |   |-- App.tsx                   # Dashboard UI
|   |   |-- api.ts                    # Typed evaluation API client
|   |   |-- evalFramework.ts          # Pipeline va maturity thresholds
|   |   `-- styles.css                # Dashboard visual system
|   |-- vite.config.ts                # Development proxy
|   `-- dist/                         # Production build, generated
|-- output/
|   `-- evaluation/
|       `-- eval_result/               # Latest evaluation packet va artifacts
|-- scripts/
|   `-- run_project_evaluation.py      # Evaluation CLI entrypoint
`-- tests/
    `-- unit/test_project_evaluator.py # Evaluator contract tests
```

---

## Chay frontend

### Development mode

Mo hai terminal tu project root.

Terminal 1 - chay FastAPI:

```powershell
python -m backend.main
```

Terminal 2 - cai dependency va chay Vite:

```powershell
cd frontend
npm install
npm run dev
```

Mo dashboard tai:

```text
http://localhost:5173
```

Neu chua co evaluation packet, chay evaluator truoc hoac trong mot terminal rieng:

```powershell
python scripts/run_project_evaluation.py --ticker DHG --output-dir output/evaluation/eval_result
```

Sau khi evaluator hoan tat, bam **Refresh packet** tren dashboard de tai ket qua moi.

### Production-like mode

Build frontend:

```powershell
cd frontend
npm install
npm run build
cd ..
```

Chay FastAPI:

```powershell
python -m backend.main
```

FastAPI se phuc vu dashboard da build tai:

```text
http://localhost:8010
```

### Frontend verification

```powershell
cd frontend
npm run build
npm test
```

`npm run build` kiem tra TypeScript va tao `frontend/dist/`. Dashboard mac dinh hien packet hau
kiem moi nhat. Mo `http://localhost:5173/?run_id=<research-run-id>` de xem packet runtime cua mot
research run. Runtime evaluator tu dong sinh artifact, nhung khong thay the final approval.

---

