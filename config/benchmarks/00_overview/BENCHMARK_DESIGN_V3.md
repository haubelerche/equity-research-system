# Benchmark Design v3

## Context

Phiên bản v3 chuyển benchmark từ bộ dataset rời rạc sang bộ kiểm định có contract giống runtime thật. Mỗi metric được gắn với một trong ba lớp: `release_gate`, `diagnostic`, `observability`. Các lỗi tất định như sai bridge target price, citation hỏng, share count mismatch, PDF render fail hoặc artifact upload fail phải dùng threshold dạng error count `= 0`. Các chỉ số chất lượng mềm như RAG score, LLM judge, report quality và latency dùng threshold phần trăm, điểm số hoặc percentile.

## Design principles

1. Release gates quyết định report có an toàn để đưa sang human review/client-final không.
2. Quality diagnostics giải thích vì sao pipeline yếu và hỗ trợ regression giữa prompt/model/parser.
3. Observability đo cost-to-serve, latency, retry, fallback và reliability theo system window.
4. LLM judge không bao giờ ghi đè deterministic gate.
5. Mọi metric phải có scope, sample size, severity, owner và remediation hint.

## Mapping to dashboard

- Data panel đọc `data_quality_eval.json`.
- RAG panel đọc `rag_eval.json`.
- Finance panel đọc `financial_eval.json`.
- Agent panel đọc `agent_eval.json`.
- Ops panel đọc `observability_eval.json`.
- Citation, report quality và publication readiness là ba panel cần thêm để dashboard không giấu P0 blocker trong RAG/agent.

## Recommended benchmark cohorts

- `mvp5_validated`: DHG, IMP, DMC, TRA, DBD — scope chính để chứng minh chất lượng.
- `requested10`: 10 mã user đưa — scope coverage theo yêu cầu.
- `scale_sparse`: UPCOM/HNX/long-tail — scope dữ liệu thưa và readiness matrix.
- `recommended_core10`: scope cân bằng hơn cho thesis/main regression.

## Ad-hoc Benchmark 01 runs

When a user supplies a ticker-specific local dataset outside the configured
benchmark universe, the suite runner may execute only plan `01` with explicit
`--tickers`. In that mode the dashboard should treat other panels as not yet
evaluated and should rely on the data-quality artifact for fail-closed
diagnosis. Empty raw BCTC split-JSON files are surfaced through
`raw_bctc_non_empty=warning`, while publication-blocking readiness remains
controlled by canonical fact coverage, provenance, reconciliation, Pandera
schema validity, and valuation input readiness.
