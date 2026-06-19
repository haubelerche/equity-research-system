# Agent Workflow And LLM Judge Evaluation Plan

## Context

He thong co workflow co dinh voi nhieu vai tro, trong do mot so vai tro goi LLM de phan tich, viet report hoac review. Evaluation cua agent khong duoc danh dong voi evaluation cua valuation deterministic. Agent evaluation do role adherence, tool use, groundedness, completeness, reasoning discipline va output contract.

## Problem Statement

Rui ro agentic workflow gom: agent dung tool sai quyen, tao claim khong co evidence, sua so lieu tai chinh bang ngon ngu, bo qua gate, hoac report narrative khong phu hop archetype doanh nghiep. Nhung loi nay can ket hop deterministic trace checks va LLM-as-judge rubric.

## Technical Deep-Dive

### 0. Current implementation alignment

| Logic hien tai | Dieu chinh trong ke hoach |
|---|---|
| Kien truc hien tai la workflow co trang thai, khong phai he multi-agent tu tri hoan toan | Agent eval phai cham role adherence trong graph co dinh, khong cham kha nang tu lap ke hoach mo |
| `TOOL_PERMISSION_GATE` doc trace entries `kind == tool_call` va yeu cau `gate_inputs.tool_permission` | Trace fixtures phai co permission metadata tren tung tool call |
| `ARTIFACT_MANIFEST_GATE` yeu cau storage path cho artifact quan trong nhu facts, index, ratios, valuation, report, full_report_draft, evidence_packet | Agent eval phai coi artifact lineage/storage la output contract, khong chi noi dung prose |
| `SENIOR_CRITIC_GATE` co severity warning va threshold scorecard rieng, khong tu sua report | LLM judge/critic chi tao findings; correction phai la next run hoac deterministic assembly step |
| `REPORT_QUALITY_GATE` va `PACKAGE_VALIDATION_GATE` quyet dinh publishable draft; `authorize_client_final` quyet dinh client-final | Agent judge score cao khong duoc bypass final approval/authorization |

### 1. Doi tuong can eval

| Agent/lop | Can danh gia | Failure mode |
|---|---|---|
| ResearchService / PLAN role | Plan co dung scope, ticker, period va task registry khong | Plan sai pham vi lam downstream sai |
| DataEvidence role | Tool calls co dung permission va artifact contract khong | Tool bypass hoac thieu evidence packet |
| FinancialAnalysisAgent | Phan tich chi dien giai facts/ratios co san khong | LLM tinh lai so hoac tao metric moi |
| ForecastValuation role | Co tach deterministic valuation va narrative explanation khong | LLM tao target price |
| ThesisReportAgent | Claim co source, dung structure va khong vuot evidence khong | Hallucination narrative |
| SeniorCriticAgent | Co phat hien loi material va khong tu sua report khong | Critic cho pass de dai |

### 2. Framework va cong nghe

| Cong nghe | Vai tro | Ghi chu |
|---|---|---|
| `pytest` trace tests | Tool permission, artifact manifest, workflow status | Deterministic va bat buoc |
| `DeepEval` | Agentic metrics va custom G-Eval rubric | Phu hop CI Python |
| OpenAI Evals | API-based graders voi dataset va testing criteria | Phu hop khi muon quan tri eval tap trung |
| `Langfuse` | Trace, datasets, manual annotation, online/offline scores | Repo da co dependency optional |
| Custom JSON schema validation | Output contract cho tung stage | Khong de LLM output tu do |

### 3. Metrics

| Metric | Tool | Threshold |
|---|---|---:|
| Tool permission compliance | Custom gate | 100% |
| Output schema validity | Pydantic/JSON schema | 100% |
| Role adherence | DeepEval/OpenAI grader | >= 85% |
| Groundedness | Ragas/DeepEval/custom judge | >= 85% for final narrative |
| No unauthorized financial calculation | Custom regex + judge | 100% compliance |
| Task completion | DeepEval agentic metric | >= 85% |
| Plan adherence | DeepEval agentic metric | >= 80% |
| Critic issue recall on seeded failures | Golden bad reports | >= 90% |
| Stage handoff completeness | Trace artifact audit | >= 95% |
| Tool call success rate | Trace/runtime metrics | >= 95% |
| Repair loop rate | Trace/runtime metrics | <= 15% |
| Token budget adherence | Cost telemetry | >= 90% |
| Judge calibration agreement | Human/deterministic label set | >= 85% |
| Judge rationale evidence coverage | Judge output audit | >= 90% |

### 4. LLM judge rubric

| Dimension | Scoring question |
|---|---|
| Evidence discipline | Output co chi dua vao facts, valuation artifacts va cited evidence khong |
| Financial restraint | Agent co tranh tinh toan/tu tao so lieu tai chinh khong |
| Company specificity | Insight co rieng cho ticker va archetype khong |
| Materiality | Agent co uu tien driver anh huong forecast/valuation khong |
| Risk balance | Report co neu dieu kien bac bo thesis va downside khong |
| Citation integrity | Claim material co citation ro va citation support dung claim khong |
| Judge calibration | Judge co dong thuan voi deterministic labels va seeded defects khong |
| Rationale traceability | Moi fail/warning co artifact, trace span hoac rubric clause khong |
| Professional tone | Phu hop research report, khong marketing, khong overclaim |

### 5. Dataset

| Dataset | Muc dich |
|---|---|
| Golden successful traces | Baseline role/tool behavior |
| Seeded bad traces | Agent dung tool sai, thieu source, hallucinate, overrecommend |
| Bad report corpus | Kiem tra SeniorCritic co bat loi P0 khong |
| Archetype prompt set | Kiem tra narrative khong ap template pharma cho hospital/distributor |

## Strategic Recommendations

### 1. P0 actions

| Hanh dong | Ket qua |
|---|---|
| Bat buoc `TOOL_PERMISSION_GATE` va `ARTIFACT_MANIFEST_GATE` trong export | Khong cho agent artifact troi noi di vao report |
| Tao seeded failure fixtures cho SeniorCritic | Do duoc critic recall thay vi tin vao prompt |
| Cam agent output target price neu valuation artifact blocked | Bao ve ranh gioi LLM vs finance |
| Luu agent judge score nhu advisory artifact | Khong cho LLM judge ghi de `PACKAGE_VALIDATION_GATE` hoac `authorize_client_final` |

### 2. P1 actions

| Hanh dong | Ket qua |
|---|---|
| Dua traces len Langfuse datasets | So sanh prompt/model/code versions |
| Them DeepEval custom metrics | Cham diem role adherence va groundedness trong CI |
| Dung double-judge cho final report narrative | Giam bias cua mot judge duy nhat |
