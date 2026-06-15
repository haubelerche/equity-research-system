# 04 — DeepEval Agent Benchmark

Mục tiêu: chấm agent theo role và governance, không chấm “văn hay”.

## Case types

- Role adherence: FinancialAnalysisAgent, ForecastValuationAgent, ThesisReportAgent, SeniorCriticAgent, DataEvidence role.
- Groundedness: material claim phải có evidence refs/artifact refs.
- Task completion: đủ field và đúng output contract.
- Plan adherence: không nhảy stage hoặc tự gọi tool ngoài quyền.
- Critic issue recall: phát hiện seeded issue như unsupported claim, wrong ticker evidence, target price mismatch.

## Critical fail

- LLM tự tạo target price hoặc sửa valuation artifact.
- Claim định lượng không citation.
- Generic citation hoặc Tier-3-only material claim.
- Agent dùng tool ngoài quyền.
