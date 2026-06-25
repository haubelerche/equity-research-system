
# Vietnam Pharma Equity Research Agent

Hệ thống nghiên cứu cổ phiếu dược và y tế Việt Nam theo nguyên tắc **evidence-grounded**, **code-first valuation** và **human-in-the-loop approval**. LLM chỉ hỗ trợ trích xuất, tổng hợp và phản biện; số liệu tài chính, forecast, FCFF, FCFE, debt schedule, multiples và gates được tính bằng code.

> Hệ thống dùng cho nghiên cứu nội bộ và học thuật. Đây không phải phần mềm tư vấn đầu tư; báo cáo client-final cần phê duyệt chuyên gia.
<img width="562" height="802" alt="Screenshot 2026-06-25 224339" src="https://github.com/user-attachments/assets/a019f227-6ffd-40ac-a1b2-cf67fa4a2f9f" /> 
## Cài đặt nhanh

```powershell
pip install -r requirements.txt
python -m backend.database.migrate
$env:PYTHONUTF8 = "1"
```

File `.env` tối thiểu cần có:

```env
DATABASE_URL=postgresql://postgres.your-project:your-password@aws-0-your-region.pooler.supabase.com:5432/postgres
OPENAI_API_KEY=sk-...
LOG_LEVEL=INFO
```

Nếu xử lý PDF scan, kiểm tra OCR runtime:

```powershell
python scripts/check_ocr_runtime.py
```

## Chạy dự án

Chạy một ticker từ đầu tới cuối, gồm PDF LLM gap-fill, ĐHCĐ/AGM ingest, full research harness và render PDF:

```powershell
make run-once TICKER=DHG FROM_YEAR=2021 TO_YEAR=2025 REPORT_MODE=standard
```

Kết quả chính:

```text
output/DHG_report.pdf
output/DHG_explanation.pdf
output/DHG_valuation_workings.md
artifacts/official_sources/DHG_pdf_llm_result.json
artifacts/official_sources/DHG_agm_result.json
```

Chạy thủ công từng chặng khi cần debug:

```powershell
python scripts/ingest_pdf_llm.py --ticker DHG --from-year 2021 --to-year 2025
python scripts/ingest_agm.py --ticker DHG
python scripts/run_research.py --ticker DHG --from-year 2021 --to-year 2025 --ocr --draft
python scripts/generate_fast_report.py --ticker DHG --mode standard
```

Chỉ chạy full harness khi dữ liệu bổ sung đã sẵn sàng:

```powershell
python scripts/run_research.py --ticker DHG --from-year 2021 --to-year 2025 --ocr --draft
```

Chỉ render lại từ artifact đã có:

```powershell
python scripts/generate_fast_report.py --ticker DHG --mode standard
```

## Luồng tổng

```text
Official PDFs / vnstock / CafeF / AGM documents
        │
        ▼
Ingestion and canonical fact promotion
        │
        ▼
Frozen snapshot + evidence index
        │
        ▼
Forecast + valuation
FCFF / FCFE / debt schedule / dividend schedule / peer multiples
        │
        ▼
System of Service + Agents
DataEvidence → FinancialAnalysis → ForecastValuation → ThesisReport → SeniorCritic
        │
        ▼
Quality gates + publishable draft artifact
        │
        ▼
Local PDF / explanation render
```

`--draft` tự approve assumption/final gate ở mức development draft. Không dùng draft artifact như báo cáo client-final đã được phê duyệt.

## Tài liệu chi tiết

| Nhu cầu | Tài liệu |
|---|---|
| Cài đặt, biến môi trường, lệnh vận hành | `docs/GETTING_STARTED.md`, `docs/CONFIGURATION.md` |
| Luồng full report, stage, artifact lifecycle | `docs/WORKFLOW.md` |
| Nguồn dữ liệu, PDF/OCR, canonical facts | `docs/SOURCES_AND_INGESTION.md`, `docs/DATA_AND_STORAGE.md` |
| Forecast, FCFF, FCFE, nợ, ĐHCĐ driver, valuation gates | `docs/VALUATION.md` |
| Agent/tool boundary và policy LLM | `docs/AGENTS_AND_TOOLS.md` |
| Reporting, render PDF, approval boundary | `docs/REPORTING.md` |
| Evaluation gates và kiểm thử | `docs/EVALUATION_GATES.md`, `docs/TESTING_AND_OPERATIONS.md` |
