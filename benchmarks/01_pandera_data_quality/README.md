# 01 — Pandera Data Quality Benchmark

Mục tiêu: xác nhận golden/canonical facts đủ điều kiện đi vào analysis, ratios, forecast, valuation và report.

## Dữ liệu chính

- `../shared/golden_financials/all_benchmark10_plus_recommended_facts.csv`
- `../shared/material_metrics.yaml`
- `../shared/fact_schema.json`
- `negative_fixtures/*.csv`

## Kiểm định bắt buộc

1. Schema validity: đủ cột, đúng kiểu, đúng enum.
2. Ticker/year/period validity: `period=2025FY` phải khớp `fiscal_year=2025`.
3. Material coverage: mỗi ticker/năm có đủ material metrics tối thiểu.
4. Provenance: accepted facts có `source_uri`, `source_title`, provider, confidence.
5. Duplicate/conflict: không có hai accepted facts cho cùng ticker-year-key mà value khác nhau.
6. Domain sanity: revenue/assets/equity/shares không âm; WACC và valuation input không lấy từ LLM.
7. Negative fixtures phải fail đúng rule mong đợi.

## Raw BCTC precondition

Benchmark 01 scores canonical/golden facts, not raw connector payloads. Local
raw files under `data/raw/bctc/<ticker>/*_year.json` must first contain
non-empty split-JSON `data` rows and then be promoted into
`../shared/golden_financials/<ticker>.csv`. If the raw files exist but all
`data` arrays are empty, the evaluator emits `raw_bctc_non_empty=warning` and
the release-gate metrics remain fail-closed through missing canonical facts.
This prevents a structurally valid empty payload from being treated as data
readiness for valuation or report generation.
