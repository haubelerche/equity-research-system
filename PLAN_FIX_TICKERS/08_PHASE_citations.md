# Phase 08 — Citation & source rendering

**PLAN gốc:** §1.3, §2 Phase 8, §4.9.
**Đọc trước:** `00_AUDIT.md`, `07_PHASE_narrative.md`.

## Mục tiêu
Mỗi claim quan trọng có nguồn cụ thể; "Nguồn tham khảo chính" 5–10 mục; không citation generic.

## Hiện trạng code
- ĐÃ có: `backend/citations/citation_map.py`, `validator.py`, `event_linker.py`, `driver_evidence.py`; `backend/evaluation/citation_coverage.py`, `source_provenance_gates.py`; `backend/sources/source_registry.py`, `document_fetcher.py`; `scripts/evaluate_citations.py`.
- NHƯNG `client_report_view_model`: `source_captions` generic; `peer_table=None`; `catalyst_table=None`; không có bảng "Nguồn tham khảo chính".

## Việc cần làm
1. **Tạo binding source-evidence vào client view:** nạp `source_manifest.json` (đã có ở artifact) → render citation ngắn trong đoạn `[BCTC 2025]`, `[HOSE, ngày…]`, `[CafeF, ngày…]`, `[BCTN]`, `[Tin doanh nghiệp]`.
2. **Bảng "Nguồn tham khảo chính"** cuối báo cáo: 5–10 nguồn quan trọng (publisher, title, date, url/file). Full manifest để JSON, không nhồi backend term vào thân.
3. **Citation gate** (đã có `citation_coverage.py`) kiểm: factual claim có citation; numeric claim map `fact_id`/`computed_metric`/`valuation_result`/`approved_assumption`; source không stale; url/file tồn tại. Nối vào Phase 01 gate tổng.
4. **Cấm citation generic** `vnstock`/`database`/`market data`/`Vietnam Pharma Equity Research` (PLAN §1.3, §4.9).

## Acceptance
- `Nguồn tham khảo chính` không trống.
- Mỗi claim định lượng map tới fact/metric/valuation/assumption.
- Không citation generic trong client PDF.

## Test
- `tests/citations/*` (đã có) — bổ sung case client-facing rendering.
- `tests/evaluation/` citation coverage gate fail khi numeric claim thiếu fact_id.

## Rủi ro
- Final export sẽ RED đến khi official DHG PDFs được đặt (theo memory `source_provenance_rebuild`). Citation phải truy ngược được, không fake (CLAUDE.md §5.3).
