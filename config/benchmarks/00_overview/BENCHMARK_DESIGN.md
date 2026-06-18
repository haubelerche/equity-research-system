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

## Benchmark Architecture Contract v4

### Context

The system quality dashboard exposes six product-facing benchmark families:
data reliability, RAG/evidence, financial correctness, agent governance and LLM
judge, report quality, and operations/cost/latency. Citation/source provenance
and publication readiness remain mandatory sidecar gates: they feed
`publication_status` and blocking issues, but they do not need separate
first-screen cards when the product view is constrained to six panels.

### Problem Statement

The benchmark suite must not report a large sample count while leaving the
sample-level rows without evaluable state. A metric with 45 ticker-level samples
can legitimately expand to 900 nested evidence rows, but each nested row must
still be interpretable as measured evidence. `not_evaluable` is reserved for
missing evaluator inputs or missing required artifacts; it must not be used as a
placeholder for a row that was actually checked and found true, false, present,
accepted, reconciled, or scored.

### Technical Deep-Dive

| Layer | Plan | Artifact | Primary sample unit | Blocking semantics |
|---|---:|---|---|---|
| Data reliability | 01 | `data_quality.json` | ticker/report-run metric, with fact-level trace rows | P0 only for material reconciliation, OCR material errors, duplicate canonical facts, snapshot/source provenance; cohort coverage is readiness diagnostic unless explicitly report-run scoped |
| RAG and evidence | 02 | `retrieval_eval.json` | golden query or Ragas sample | Diagnostic by default; unsupported final claims escalate through citation/publication gates |
| Financial correctness | 03 | `financial_eval.json` | valuation artifact or formula step | P0 deterministic gates; zero-error counts remain the correct threshold for formula, bridge, WACC/g, net-debt, share-count, and recommendation failures |
| Agent governance and LLM judge | 05 | `agent_eval.json` | trace event, artifact output, or seeded case | Tool permission, schema validity, artifact manifest, and unauthorized calculation are deterministic gates; LLM judge scores are diagnostics after calibration |
| Report quality | 06 | `report_eval.json` | report artifact or rubric dimension | Completeness and valuation transparency can gate; narrative/rubric scores route to human review and never override deterministic failures |
| Operations, cost, latency | 07 | `observability_eval.json` | run, trace event, or system window | Upload failure, final OCR numeric error, and final PDF render failure gate; retry, fallback, cost, and latency are observability unless they corrupt final artifacts |

### Sample Contract

Every metric result must expose the normalized metric contract already defined
by `config/benchmarks/shared/metric_registry_v3.yaml`: `metric_id`,
`metric_name`, `category`, `layer`, `metric_type`, `scope`, `severity`,
`blocks_publish`, `value`, `threshold`, `threshold_operator`, `unit`, `status`,
`sample_size`, `failed_examples`, `evaluator`, `calculation`, `evidence`, and
`remediation_hint`.

`sample_size` counts the primary evaluation unit for the displayed metric. In a
cohort aggregate this is normally the ticker count, not the total number of
nested fact rows. Nested `calculation.per_sample_results[*].source_samples`
are trace rows and may expand 45 ticker samples into hundreds of fact/component
rows. Those trace rows must carry `sample_origin` and should carry both
`status` and `value`; if old artifacts lack those fields, the dashboard may
derive them from `component_score`, `passed`, `hit`, `present`, `complete`,
`accepted`, `schema_valid`, `reconciled`, `validation_status`, or
`evidence_available`.

### Strategic Recommendations

| Risk | Required control |
|---|---|
| Large sample tables show "missing" despite measured data | Normalize source samples in runtime evaluators and aggregate suite output; dashboard keeps a legacy inference path for old artifacts |
| Cohort readiness blocks like report-run P0 | Separate diagnostic cohort thresholds from release-gate report-run thresholds in the metric registry and dashboard overrides |
| LLM judge masks deterministic failures | Compute publication status only after deterministic metrics are evaluated; judge metrics remain advisory unless converted into explicit P1 human-review rules |
| Citation gate disappears from six-panel UI | Keep `citation_eval.json` in the packet and publication blocker list even when it is not a first-screen panel |
| Operations metrics mix observability with release gates | Only final artifact upload, final render, and final OCR numeric errors block; retry/fallback/latency/cost remain observability or regression diagnostics |
