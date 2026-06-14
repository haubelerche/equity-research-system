# Evaluation Master Plan

## Context

Du an `multi-agent-equity-research` khong nen duoc danh gia bang mot diem chat luong tong quat duy nhat, vi pipeline gom nhieu lop co ban chat loi khac nhau: ingestion du lieu, promotion fact, retrieval evidence, tinh toan tai chinh, agent reasoning, report assembly, export governance va observability. Mot framework LLM evaluation don le khong the bao phu day du rui ro trong he thong nghien cuu co phieu, dac biet khi nguyen tac cot loi cua repo la LLM khong duoc tinh toan so lieu tai chinh.

## Problem Statement

Khau evaluation can tra loi bon cau hoi nghiem thu rieng biet:

| Cau hoi | Rui ro neu khong do | Lop danh gia phu hop |
|---|---|---|
| Du lieu dau vao co dung, day du, moi va truy vet duoc khong | Sai fact goc dan den sai valuation hang loat | Data reliability evaluation |
| Retrieval co lay dung bang chung va co du ngu canh khong | Report co citation nhung citation khong support claim | RAG and evidence evaluation |
| Mo hinh tai chinh co tinh dung, tai lap va nhat quan khong | Target price sai nhung van co ve chuyen nghiep | Financial calculation evaluation |
| Agent co viet dung pham vi evidence, dung vai tro va dung tool khong | Hallucination, tool misuse, vuot quyen agent | Agent workflow evaluation |
| Bao cao co dat chuan phan tich, citation, presentation va export governance khong | Tao PDF khong dat chuan hoac bypass gate | Institutional report quality evaluation |
| He thong co on dinh ve chi phi, do tre, trace va regression khong | Cost-to-serve tang, loi kho truy vet, latency bat on | Observability and CI evaluation |

## Technical Deep-Dive

### 0. Current implementation alignment

Ke hoach evaluation hien tai phai align voi runtime moi nhat thay vi mo hinh "render final" truc tiep:

| Runtime contract hien tai | He qua cho evaluation plan |
|---|---|
| `PUBLISH` tao `auto_exported` draft, khong dong nghia voi final client approval | Evaluation phai phan biet `publishable_final_report_model`, `auto_exported`, `approved` va `client_final` |
| `backend/reporting/publication_readiness.py` fail-closed truoc client-final render | Moi ke hoach report/export phai yeu cau `final_report_approval`, run status `approved`, `PACKAGE_VALIDATION_GATE`, report-quality `allow_export`, locked publishable model va snapshot match |
| `backend/evaluation/governance.py` gom shared deterministic rules cho decomposition, bridge, forecast sanity va valuation reproduction | Finance/report eval phai dung chung issue code thay vi tao rubric song song |
| `REPORT_QUALITY_GATE` co severity warning trong harness nhung `PACKAGE_VALIDATION_GATE` va `authorize_client_final` van chan final neu khong `allow_export` | LLM-as-judge khong duoc bien failed deterministic rubric thanh publishable |
| `evaluate_export_gate` sensitivity gate hien yeu cau FCFF, FCFE va blend sensitivity matrix hoac shape tuong duong trong `sensitivity` | Ke hoach finance phai test ca missing FCFE/blend sensitivity, khong chi FCFF WACC/g |
| `tests/evaluation/test_client_final_governance.py` va `tests/unit/test_publication_readiness.py` la regression anchors | CI plan phai dua cac test nay vao nhom governance bat buoc |

### 1. Framework stack duoc de xuat

| Lop evaluation | Cong nghe chinh | Ly do chon | Trang thai trong repo |
|---|---|---|---|
| Deterministic unit and invariant tests | `pytest` | Phu hop voi cong thuc tai chinh, gate, schema, regression co ket qua xac dinh | Da co trong `requirements.txt` va `tests/` |
| DataFrame schema and data quality | `Pandera` | Kiem tra kieu cot, mien gia tri, lazy validation, integration voi pandas; tai lieu chinh thuc mo ta runtime DataFrame validation va statistical checks | Chua co, nen them sau khi chot data contract |
| RAG evaluation | `Ragas` | Co metric cho context precision, context recall, response relevancy, faithfulness, noise sensitivity va agent/tool use | Chua co, can them neu bat dau benchmark retrieval |
| LLM-as-judge/custom rubric | `DeepEval` hoac OpenAI Evals | DeepEval thuan Python/CI, co RAG, agentic, safety va custom G-Eval; OpenAI Evals phu hop khi muon API-based graders co `data_source_config` va `testing_criteria` | Chua co, nen pilot tren report rubric truoc |
| Trace, dataset, online/offline eval | `Langfuse` | Repo da co Langfuse optional; phu hop de score traces, tao datasets, so sanh prompt/model/code changes va theo doi score theo thoi gian | Da khai bao dependency va co adapter optional |
| Finance correctness | Python deterministic validators | Cong thuc valuation khong nen dua vao LLM judge; can property-based va golden-file testing | Da co trong `backend/evaluation/governance.py`, `backend/evaluation/report_quality.py`, `backend/evaluation/numeric_consistency.py`, `backend/harness/gates.py` va nhieu `tests/unit/`, `tests/evaluation/` |

### 2. Thu muc ke hoach

| File | Pham vi |
|---|---|
| `01_data_reliability_plan.md` | Data ingestion, OCR, fact promotion, freshness, reconciliation, source registry |
| `02_rag_and_ragas_plan.md` | Retrieval, chunking, citation evidence, Ragas metrics, synthetic and golden queries |
| `03_financial_calculation_plan.md` | Ratios, forecast, FCFF, FCFE, DCF, WACC, sensitivity, peer valuation |
| `04_citation_and_source_provenance_plan.md` | Citation coverage, source tier, official source requirement, claim lineage |
| `05_agent_workflow_and_llm_judge_plan.md` | Multi-agent behavior, tool permission, prompt compliance, LLM-as-judge |
| `06_report_quality_plan.md` | institutional report-quality acceptance, professional presentation, export gating |
| `07_observability_cost_latency_plan.md` | Langfuse, cost-to-serve, latency, reliability, regression dashboards |
| `08_rollout_and_ci_plan.md` | Rollout order, CI gates, acceptance thresholds, implementation roadmap |

### 3. External references

| Technology | Reference |
|---|---|
| Ragas metrics | https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/ |
| DeepEval metrics | https://deepeval.com/docs/metrics-introduction |
| Langfuse evaluation | https://langfuse.com/docs/evaluation/overview |
| OpenAI Evals | https://developers.openai.com/api/docs/guides/evals |
| Pandera | https://pandera.readthedocs.io/en/stable/ |
| pytest | https://docs.pytest.org/en/stable/ |

## Strategic Recommendations

### 1. Evaluation architecture

Danh gia phai chay theo thu tu fail-closed:

```text
Data reliability
-> Fact reconciliation
-> Retrieval and source provenance
-> Financial calculation invariants
-> Agent and narrative evaluation
-> Report quality
-> Package validation and auto-exported draft
-> Human final approval
-> Client-final render authorization
```

Neu mot lop deterministic critical fail thi khong duoc de LLM-as-judge ghi de bang diem cao. LLM-as-judge chi duoc dung cho nhung tieu chi mo ve narrative, insight, role adherence va report professionalism.

### 2. Minimum viable eval stack

| Giai doan | Nen lam ngay | Tam hoan |
|---|---|---|
| P0 | Chuan hoa deterministic gates bang `pytest`, bo sung ke hoach data/retrieval/finance/report | Chua can them nhieu dependency |
| P1 | Them `Ragas` cho retrieval benchmark va `Langfuse` datasets cho trace regression | Chua can open-ended red-team quy mo lon |
| P2 | Them `DeepEval` hoac OpenAI Evals cho rubric report-quality/agent judge | Chua nen thay the deterministic finance gates |
| P3 | Them `Pandera` schema validation cho dataframe contract neu ingestion mo rong | Great Expectations chi nen can nhac khi co data warehouse lon |

### 3. Definition of Done

Khau evaluation duoc xem la dat neu moi research run tao duoc mot `evaluation_packet` gom:

| Artifact | Noi dung bat buoc |
|---|---|
| `data_quality.json` | Coverage, freshness, source tier, reconciliation, OCR promotion status |
| `retrieval_eval.json` | Ragas scores, golden query hit-rate, unsupported-context failures |
| `financial_eval.json` | Formula invariants, bridge reconciliation, sensitivity variation, WACC/g sanity |
| `citation_eval.json` | Claim-level coverage, source tier, official document requirement |
| `agent_eval.json` | Tool permission, role adherence, groundedness, judge rubric |
| `report_eval.json` | Report quality score, failed gates, export decision |
| `publication_readiness.json` | Run approval, final approval, locked publishable model, package gate, Report-quality allow_export, snapshot match |
| `observability_eval.json` | Token cost, latency, retries, error rate, trace links |
