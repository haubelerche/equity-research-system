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
  → Artifact JSON → artifacts/valuation/
        │
        ▼
[Evidence Index] build_index.py
  → Chunking tài liệu, citation map
        │
        ▼
[Report Generation] generate_report.py
  → Báo cáo Markdown + citation JSON
  → reports/{TICKER}_{timestamp}_full_report.md
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
  → Reviewer xem xét + approve/reject
  → ResearchGraphRunner.handle_approval → EXPORT_GATE → published run state
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

Cần một PostgreSQL instance (local hoặc Supabase). Chạy migrations theo thứ tự:

```bash
psql $DATABASE_URL -f backend/database/migrations/001_ref_schema.sql
psql $DATABASE_URL -f backend/database/migrations/002_ingest_schema.sql
psql $DATABASE_URL -f backend/database/migrations/003_fact_schema.sql
psql $DATABASE_URL -f backend/database/migrations/004_research_schema.sql
psql $DATABASE_URL -f backend/database/migrations/005_seed_reference_data.sql
psql $DATABASE_URL -f backend/database/migrations/006_grants_and_privileges.sql
psql $DATABASE_URL -f backend/database/migrations/007_expand_line_items.sql
psql $DATABASE_URL -f backend/database/migrations/008_research_snapshots.sql
```

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
DATABASE_URL=postgresql://user:password@localhost:5432/maer_dev
OPENAI_API_KEY=sk-...
DEFAULT_MODEL=gpt-4o-mini
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

## Chạy pipeline đầy đủ cho một ticker (ví dụ: DHG)

### Bước 1 — Thu thập dữ liệu

```bash
python scripts/ingest_ticker.py --ticker DHG --years 5
```

Kết quả:
- Raw financial data lưu DB + `artifacts/raw/`
- Source metadata ghi vào `ref.source_versions`
- Log ingestion run

### Bước 2 — Xây dựng canonical facts

```bash
python scripts/build_facts.py --ticker DHG
```

Kết quả:
- Canonical financial facts lưu `public.financial_facts`
- Validation report + completeness score
- Research snapshot tạo tại `research.snapshots`

### Bước 3 — Định giá (Valuation)

```bash
python scripts/run_valuation.py --ticker DHG
```

Tùy chọn thêm:

```bash
python scripts/run_valuation.py --ticker DHG --wacc 0.10 --terminal-growth 0.03
python scripts/run_valuation.py --ticker DHG --target-pe 18 --target-ev-ebitda 12
```

Kết quả tại `artifacts/valuation/DHG_{timestamp}_valuation.json`:
- Bảng ratio (revenue growth, gross margin, ROE, ROA, ...)
- DCF 3 kịch bản (bear / base / bull)
- **FCFF** — EBIT(1−T) + D&A − CAPEX − ΔNWC; chiết khấu WACC; bridge EV → Equity
- **FCFE** — NI + D&A − CAPEX − ΔNWC + Net Borrowing; chiết khấu Re; Equity Value trực tiếp
- **Blend 60% FCFF + 40% FCFE** — target price kết hợp theo cẩm nang định giá
- Sensitivity tables: WACC×g (FCFF), Re×g (FCFE), blend grid, P/E matrix, EV/EBITDA matrix

### Bước 4 — Xây dựng evidence index

```bash
python scripts/build_index.py --ticker DHG
```

Kết quả:
- Document chunks + citation map tại `artifacts/index/`

### Bước 5 — Sinh báo cáo

```bash
python scripts/generate_report.py --ticker DHG --report-type full_report
```

Kết quả tại `reports/DHG_{timestamp}_full_report.md`:
- §1 Tóm tắt điều hành + Draft rating
- §2 Giới thiệu doanh nghiệp
- §3 Kết quả tài chính lịch sử + dự phóng 5 năm
- §4 Định giá: DCF truyền thống, FCFF (60%), FCFE (40%), Blend DCF (60/40), Multiples
- §5 Rủi ro đầu tư
- §6 Kết luận + kiểm toán chất lượng
- Phụ lục: giả định, bảng bằng chứng, footnotes

### Bước 6 — Đánh giá chất lượng (7 cổng kiểm tra)

```bash
python scripts/evaluate_report.py --report reports/DHG_{timestamp}_full_report.md
```

| Cổng | Mô tả |
|------|-------|
| numeric_consistency | Số liệu báo cáo khớp canonical facts |
| citation_coverage | 100% claims có trích dẫn |
| valuation_reproducibility | Valuation tái lập được từ artifact |
| stale_data | Dữ liệu không quá 30 ngày |
| unsupported_claims | Không có "guaranteed return" hoặc absolute advice |
| user_facing_citation_quality | Citations hợp lệ |
| balance_sheet_identity_check | Assets = Liabilities + Equity trong forecast |

Kết quả `PASS` mới được phép export. `CRITICAL FAIL` chặn export tự động.

### Bước 7 — Phê duyệt và export

```bash
# Phê duyệt (sau khi tất cả evaluation gates PASS)
python scripts/approve_report.py --run-id <run_id> --decision approve --reviewer analyst --comment "Verified"

# Từ chối
python scripts/approve_report.py --run-id <run_id> --decision reject --reviewer analyst --comment "WACC assumption cần review lại"
```

Kết quả:
- Quyết định phê duyệt được ghi qua `ResearchGraphRunner.handle_approval`.
- Runner resume từ checkpoint và chỉ publish khi `EXPORT_GATE` final pass.

---

## Chạy end-to-end một lệnh (Phase 8)

```bash
python scripts/run_research.py --ticker DHG --from-year 2021 --to-year 2025
```

Lệnh này chạy toàn bộ pipeline từ ingestion đến evaluation, ghi run trace vào DB.

### Luồng production đầy đủ và render run-scoped

Không chạy riêng lẻ `run_valuation.py`, `generate_report.py`, hoặc
`render_report.py --allow-latest-artifacts` để tạo báo cáo chính thức. Luồng
production phải dùng một `run_id` xuyên suốt:

```bash
python scripts/run_research.py --ticker DBD --report-type full_report --from-year 2021 --to-year 2025
python scripts/approve_report.py --run-id <run_id> --stage assumptions --decision approve --reviewer analyst --comment "Verified valuation assumptions"
python scripts/approve_report.py --run-id <run_id> --stage final --decision approve --reviewer analyst --comment "Verified final report"
python scripts/render_report.py --ticker DBD --run-id <run_id> --mode client_final --pdf
```

Nếu valuation hoặc artifact của run chưa đạt gate, PDF export sẽ dừng trước khi
ghi file và giữ nguyên bản PDF tốt gần nhất.

---

## Output mẫu — DHG (2026-05-26)

```
Ticker:        DHG (HOSE — Dược phẩm)
Giá thị trường: 94,400 VND/CP
Snapshot:      snap_0c2fbaf394e8fbc5ac14 (96 facts, 2022FY–2025FY)

Định giá:
  FCFF DCF (60%)          80,963 VND/CP   upside -14.2%
  FCFE DCF (40%)          87,026 VND/CP   upside  -7.8%
  Blend 60/40             83,388 VND/CP   upside -11.7%
  DCF truyền thống (base) 137,010 VND/CP  upside +45.1%
  P/E 15.0x               94,620 VND/CP
  EV/EBITDA 10.0x        109,608 VND/CP

Kiểm soát chất lượng:
  TV weight (FCFF/EV):  61.3%  [ok < 70%]
  FCFF/FCFE gap:         6.97%  [ok < 25%]

Evaluation: 7/7 gates PASS
Draft rating: BAN (SELL) — chưa được analyst phê duyệt
```

---

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
│   ├── harness/            # LangGraph 5-agent harness, gates, checkpoints
│
├── scripts/
│   ├── ingest_ticker.py    # Phase 2: Data ingestion
│   ├── build_facts.py      # Phase 3: Canonical facts
│   ├── run_valuation.py    # Phase 4: Valuation
│   ├── build_index.py      # Phase 5: Evidence index
│   ├── generate_report.py  # Phase 6: Report generation
│   ├── evaluate_report.py  # Phase 7: Evaluation gates
│   ├── run_research.py     # Phase 8: End-to-end pipeline
│   ├── approve_report.py   # Phase 9: run-scoped harness approval
│   └── connectors/         # vnstock connector layer
│
├── reports/
│   ├── *.md                # Draft reports
│   └── approved/           # Approved & exported reports
│
├── artifacts/
│   ├── valuation/          # Valuation JSON artifacts
│   ├── evaluation/         # Evaluation JSON artifacts
│   ├── runs/               # Run trace logs
│   └── index/              # Citation maps & chunks
│
├── config/
│   ├── agents/             # 5 product-agent YAML config and prompt library
│   ├── dataset/            # Dataset contracts, taxonomy, universe, and golden fixtures
│   └── harness/            # Harness policies, schemas, registries, and contracts
│
├── specs/                  # Architecture & data contract docs
├── tests/                  # Unit + integration tests
├── CLAUDE.md               # Project rules & implementation protocol
└── .env                    # Secrets (không commit)
```

---

## Ticker universe MVP

| Ticker | Công ty | Ưu tiên |
|--------|---------|---------|
| DHG | Dược Hậu Giang | ★ Ticker đầu tiên (đã hoàn thành) |
| IMP | Imexpharm | ★★ |
| DMC | Dược phẩm Trung Ương 2 | ★★ |
| TRA | Traphaco | ★★ |
| DBD | Dược Bình Định | ★★ |

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

## Tài liệu tham khảo nội bộ

| File | Nội dung |
|------|----------|
| `CLAUDE.md` | Project rules, implementation protocol, phase roadmap |
| `specs/02_ARCHITECTURE_DECISIONS.md` | Các quyết định kiến trúc |
| `specs/03_DATA_CONTRACTS.md` | Data contracts |
| `specs/07_EVALUATION_RUBRIC.md` | Rubric đánh giá báo cáo |
| `.claude/plan/Cam_nang_dinh_gia_60_FCFF_40_FCFE_ban_sach.md` | Cẩm nang định giá 60/40 |
| `.claude/plan/Huong_dan_danh_gia_sensitivity_analysis.md` | Hướng dẫn sensitivity analysis |
