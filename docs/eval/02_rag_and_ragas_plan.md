# RAG And Ragas Evaluation Plan

## Context

Retrieval trong du an khong phai chatbot Q&A thong thuong. No phuc vu viec tim bang chung cho claim, gan citation, xay evidence packet va dam bao agent khong viet vuot qua nguon. Repo hien co `backend/retrieval.py`, `backend/database/vector_store.py`, `backend/citations/`, `backend/evaluation/citation_coverage.py`, `backend/evaluation/source_provenance_gates.py`, `backend/news/citation_validator.py`, `backend/reporting/citation_artifact_writer.py` va cac migration cho `document_chunks`/`pgvector`.

## Problem Statement

Mot report co citation van co the sai neu retrieved context khong lien quan, citation chi la nguon chung chung, hoac context dung nhung khong du de support claim. RAG evaluation phai do ca retriever va generator: retriever lay dung evidence, generator chi dung evidence do, va citation map gan dung claim.

## Technical Deep-Dive

### 0. Current implementation alignment

| Logic hien tai | Dieu chinh trong ke hoach |
|---|---|
| Evidence packet va formula trace la sub-gates trong `PACKAGE_VALIDATION_GATE` | RAG eval khong chi cham retriever; no phai chung minh `EVIDENCE_PACKET_GATE` co artifact path va valuation co formula trace |
| Citation coverage trong report quality chi pass khi quantitative claim co lineage qua `fact_id`, `artifact_id`, `calculation_path`, `evidence_refs`, `supporting_refs` hoac `source_artifact_refs` | Golden query/evidence schema phai luu claim-level lineage, khong chi `source_title` |
| Generic citation bi nhan dien qua `is_vague_source` va block trong citation/report-quality/export gates | RAG plan phai co negative cases cho "du lieu tai chinh canonical", "bao cao cong ty" va label generic tuong tu |
| News/catalyst evidence co whitelist va citation validator rieng | Query set can tach official disclosure, company IR, reliable news va blocked unsupported events |
| Ragas la P1 semantic layer, chua phai final deterministic blocker | P0 blockers van la unsupported material claim, missing evidence packet, Tier 3-only material source va generic citation |

### 1. Doi tuong can eval

| Doi tuong | Metric can do | Failure mode |
|---|---|---|
| Chunking | Chunk coverage, metadata completeness, section/page availability | Chunk mat page/source nen citation khong audit duoc |
| Embedding retrieval | Hit-rate@k, MRR, context precision, context recall | Khong tim dung disclosure hoac annual report |
| Full-text fallback | Hit-rate@k khi embedding unavailable | Fallback tra ve nguon sai tier |
| Citation map | Claim-to-context support | Citation co nhung khong support claim |
| Evidence packet | Completeness va reproducibility | Report khong tai lap duoc evidence |
| Generated answer/report span | Faithfulness, response relevancy, unsupported claim rate | Agent hallucinate hoac suy dien qua nguon |

### 2. Framework va cong nghe

| Cong nghe | Vai tro | Ly do |
|---|---|---|
| `Ragas` | RAG metric suite | Co context precision, context recall, context entities recall, noise sensitivity, response relevancy va faithfulness |
| `pytest` | Golden retrieval regression | Bat loi deterministic tren golden query set |
| `Langfuse datasets` | Luu query, expected contexts, runs va scores | Phu hop regression theo prompt/model/code variant |
| PostgreSQL `pgvector` va full-text search | Retriever under test | Kiem tra ca vector path va fallback path |
| Custom finance citation validator | Domain-specific support check | Ragas khong thay the duoc official-source requirement |

### 3. Golden query set

| Query class | Vi du | Expected evidence |
|---|---|---|
| Financial fact lookup | `DHG revenue 2024` | Annual report or reconciled canonical fact |
| Valuation assumption support | `tax rate assumption DHG forecast` | Tax policy artifact or official historical tax evidence |
| Catalyst lookup | `DHG GMP EU factory update` | Company disclosure, HOSE/HNX/IR document, reliable news |
| Risk lookup | `API cost exposure DHG` | Company-specific source or explicit missing-evidence marker |
| Peer/multiple lookup | `Vietnam pharma peer P/E` | Peer dataset artifact or blocked status if unavailable |

### 4. Metrics and thresholds

| Metric | Tool | Threshold P0 | Threshold P1 |
|---|---|---:|---:|
| Hit-rate@5 | Custom pytest | >= 90% golden queries | >= 95% |
| MRR@5 | Custom pytest | >= 0.70 | >= 0.80 |
| Context precision | Ragas | >= 0.75 | >= 0.85 |
| Context recall | Ragas | >= 0.75 | >= 0.85 |
| Faithfulness | Ragas | >= 0.85 | >= 0.90 |
| Noise sensitivity | Ragas | <= agreed baseline | Improve by 20% |
| Unsupported claim rate | Custom validator | 0% for final | 0% |
| Tier-3-only material claim | Source gate | 0 | 0 |

### 5. Evaluation artifact schema

```json
{
  "ticker": "DHG",
  "run_id": "string",
  "retrieval_backend": "pgvector|full_text|hybrid",
  "query_set_version": "rag_golden_v1",
  "ragas_scores": {
    "context_precision": 0.0,
    "context_recall": 0.0,
    "faithfulness": 0.0,
    "response_relevancy": 0.0
  },
  "golden_scores": {
    "hit_rate_at_5": 0.0,
    "mrr_at_5": 0.0
  },
  "blocking_failures": []
}
```

## Strategic Recommendations

### 1. P0 implementation

| Hanh dong | Ket qua |
|---|---|
| Tao/cap nhat `config/benchmarks/02_ragas_retrieval/golden_queries/` | Co benchmark retrieval lap lai |
| Them test `tests/evaluation/test_retrieval_golden.py` | Bat regression khi chunking/retrieval thay doi |
| Bat buoc evidence packet co page/source metadata | Citation audit duoc den document goc |

### 2. P1 implementation

| Hanh dong | Ket qua |
|---|---|
| Them `ragas` dependency trong eval extras | Chay metric semantic cho retrieval/generation |
| Day query set va scores len Langfuse datasets | So sanh regression theo model, prompt va retriever |
| Xay negative retrieval set | Kiem tra he thong co tu choi khi khong co evidence |

### 3. Blocking policy

Ragas score thap khong nen tu dong block final neu khong lien quan claim material; tuy nhien bat ky quantitative claim nao khong co citation support hoac chi co Tier 3 generic source phai block export.
