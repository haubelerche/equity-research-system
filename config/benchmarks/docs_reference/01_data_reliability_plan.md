# Data Reliability Evaluation Plan

## Context
Dùng framework pandera để đánh giá.
Data reliability la lop evaluation dau tien vi moi report, valuation va citation deu phu thuoc vao fact canonical. Trong repo hien tai, cac thanh phan lien quan gom `backend/documents/`, `backend/facts/`, `backend/dataops/`, `backend/reconciliation/`, `backend/database/canonical/`, `backend/evaluation/source_provenance_gates.py`, `backend/harness/gates.py`, `tests/unit/test_data_quality.py`, `tests/reconciliation/`, `tests/dataops/`, `tests/documents/`, `tests/official_sources/` va `tests/evaluation/test_final_source_gates.py`.

## Problem Statement

Rui ro chinh khong nam o viec thieu mot so lieu don le, ma nam o kha nang mot so lieu sai hoac stale duoc promote thanh canonical fact roi di vao forecast, valuation va report. Vi vay data evaluation phai do dung 6 yeu to: completeness, validity, freshness, reconciliation, provenance va promotion safety.

## Technical Deep-Dive

### 0. Current implementation alignment

| Logic hien tai | Dieu chinh trong ke hoach |
|---|---|
| `DATA_QUALITY_GATE` yeu cau `snapshot_id`, FY-only period scope, coverage/core/source gates, source-tier coverage va reconciliation khong fail/manual_review | `data_quality.json` phai expose cac field nay bang dung key de harness gate doc truc tiep |
| `source_provenance_gates.py` va source-tier policy da block Tier 3-only material claim | Data eval phai do source tier tren fact material, khong chi tren document inventory |
| OCR candidate facts chi duoc promote sau validation va reconciliation; `OCR_EXPORT_GATE` block final khi candidate material con `blocked` | Ke hoach OCR phai tach `candidate`, `promoted`, `blocked`, khong cho OCR raw di vao valuation |
| `publication_readiness` yeu cau valuation/report snapshot match | Data reliability phai coi snapshot immutability la dieu kien final, khong phai metadata phu |
| Tests hien co gom `tests/unit/test_golden_provenance_required.py`, `tests/unit/test_ocr_*`, `tests/reconciliation/test_financial_fact_reconciliation.py` | CI data plan phai neo vao cac test nay thay vi script cu khong con la entrypoint chinh |

### 1. Doi tuong can eval

| Doi tuong | Cau hoi kiem dinh | Failure mode can chan |
|---|---|---|
| Source registry | Nguon co duoc allow-list va gan tier dung khong | Dung nguon khong chinh thuc cho claim trong yeu |
| Raw observations | Payload co du ticker, period, statement, metric, unit khong | Mat dong du lieu hoac sai scope nam |
| Financial facts | Metric canonical co mapping dung voi taxonomy khong | Mapping sai `net_income`, `debt`, `cash`, `capex` |
| OCR candidate facts | OCR co du confidence, validation va reconciliation khong | OCR scan sai duoc promote truc tiep |
| Golden facts | Fact production co khop fixture DHG/DBD khong | Regression sau refactor normalizer |
| Freshness | Snapshot co qua cu so voi reporting period khong | Bao cao dung artifact stale |
| Reconciliation | Vnstock/API/OCR/official doc co mau thuan khong | Mot nguon aggregator ghi de official source |

### 2. Framework va cong nghe

| Cong nghe | Vai tro | Ap dung cu the |
|---|---|---|
| `pytest` | Regression va invariant tests | Chay `tests/unit/test_data_quality.py`, `tests/reconciliation/`, `tests/dataops/` |
| `Pydantic` | Contract cho records, run state, artifact schema | Validate structured payload va JSON artifacts |
| `Pandera` | DataFrame schema validation | Kiem tra pandas DataFrame tu connector truoc khi normalize |
| SQL constraints | Referential integrity va uniqueness | Enforce source/fact/snapshot uniqueness trong Supabase PostgreSQL |
| Golden CSV/JSON fixtures | Expected facts | Doi chieu `config/dataset/golden/financials/` |

### 3. Metrics

| Metric | Cong thuc | Threshold P0 |
|---|---|---:|
| Core metric coverage | So core metrics co fact hop le / tong core metrics bat buoc | >= 95% cho final |
| Period completeness | So period co day du statement / tong period yeu cau | 100% voi DHG pilot |
| Source provenance coverage | Facts co source_id, source_tier, source_doc_id / total facts | 100% cho facts dung trong valuation |
| Official reconciliation rate | Facts matched official hoac manual_reviewed / material facts | >= 95% |
| OCR unresolved rate | OCR candidate blocked hoac pending / OCR candidates material | 0% trong final |
| Freshness SLA | Days since latest accepted snapshot | Theo policy tung report; final khong duoc stale |
| Duplicate fact rate | Duplicate canonical key / total facts | 0% |

### 4. Test data

| Dataset | Muc dich |
|---|---|
| `config/dataset/golden/financials/DHG.csv` | Golden facts cho ticker pilot |
| `config/dataset/golden/financials/DBD.csv` | Cross-company regression |
| Official annual report PDFs | OCR and official reconciliation benchmark |
| Synthetic corrupt rows | Negative tests cho unit, duplicate, missing period, wrong unit |

### 5. Execution plan

| Tan suat | Lenh hoac job | Dieu kien pass |
|---|---|---|
| Moi PR | `python -m pytest tests/unit/test_data_quality.py tests/unit/test_golden_provenance_required.py tests/unit/test_ocr_promotion_gate.py tests/unit/test_ocr_reconciliation_gate.py tests/reconciliation/ tests/dataops/ tests/evaluation/test_final_source_gates.py` | Tat ca pass |
| Moi ingestion run | Data quality artifact sau `build_facts` | Khong co critical issue |
| Hang tuan | Freshness scan tren universe | Ticker stale duoc gan status blocked hoac refresh_required |
| Truoc export | Source provenance and reconciliation gates | Material facts co lineage va reconciliation hop le |

## Strategic Recommendations

### 1. P0 actions

| Hanh dong | Ket qua mong doi |
|---|---|
| Tao `data_quality.json` run-scoped | Moi report co bang chung data readiness |
| Chuan hoa severity | `critical` block export, `warning` cho review, `info` cho diagnostics |
| Them negative fixtures | Chung minh gate that bai khi sai unit, thieu source, duplicate fact |
| Khong cho OCR candidate unresolved vao final | OCR chi la ung vien, khong la source of truth |

### 2. P1 actions

| Hanh dong | Ket qua mong doi |
|---|---|
| Them `Pandera` schema cho connector DataFrame | Loi schema bi bat truoc normalization |
| Tao data drift dashboard | Phat hien bien dong bat thuong theo ticker/metric |
| Gan archetype data requirements | Distributor, hospital, manufacturer co metric bat buoc khac nhau |
