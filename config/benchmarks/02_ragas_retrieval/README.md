# 02 — Ragas Retrieval Benchmark

Mục tiêu: kiểm định retrieval/evidence grounding cho equity research, không chỉ kiểm câu trả lời hay.

## Dữ liệu chính

- `golden_queries/{TICKER}.yaml`: query, expected chunk id, metric key, năm, source tier.
- `golden_chunks/{TICKER}_chunks.jsonl`: chunks tổng hợp từ golden financial facts.
- `ragas/ragas_samples.jsonl`: định dạng dễ nạp vào Ragas.

## Metric

- Hit-rate@5 >= 90%.
- MRR@5 >= 75%.
- Source-tier hit >= 90%.
- Context precision/recall >= 80%.
- Faithfulness >= 90%.
- nDCG@10 >= 80%.
- Metadata filter accuracy >= 95%.
- Evidence span overlap >= 75%.
- Retrieval noise rate <= 20%.
- Unanswerable control phải trả lời `insufficient evidence`, không bịa guidance 2026.
