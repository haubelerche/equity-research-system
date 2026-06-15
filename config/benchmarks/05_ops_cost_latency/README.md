# 05 — Operations, Cost and Latency Benchmark

Mục tiêu: biến vận hành thành benchmark có số đo, thay vì chỉ ghi log.

## Dữ liệu chính

- `golden_run_traces.csv`: run-level duration, cost, tokens, status.
- `golden_stage_events.jsonl`: stage-level telemetry.
- `negative_ops_cases.jsonl`: storage failure, PDF timeout, high retry, hard budget.
- `ops_cost_latency_rubric.yaml`: SLA và budget.

## Gate

- Warm full report p95 <= 10 phút.
- Cold full report p95 <= 30 phút.
- Render-only p95 <= 2 phút.
- Soft budget <= 2 USD/run; hard budget <= 5 USD/run.
- Artifact upload failures = 0.
- PDF render failures = 0.
- Cost ledger và run manifest phải tồn tại.
