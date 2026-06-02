# SEQUENCE — Sơ đồ kiến trúc & luồng chạy

> Tài liệu mô tả kiến trúc hệ thống, use-case, luồng dữ liệu, multi-agent supervisor/worker,
> và các luồng xử lý chính của **Vietnam Pharma Equity Research Agent**.
> Mọi sơ đồ đều là Mermaid — copy trực tiếp vào [mermaid.live](https://mermaid.live) để vẽ.

---

## 0. Biểu đồ tuần tự hệ thống đầy đủ (Master Sequence Diagram)

> Sơ đồ này mô tả **toàn bộ hệ thống** từ góc độ tương tác giữa tất cả components:
> Analyst → CLI → Supervisor → LangGraph Runner → Data Services → LLM Agents →
> Valuation Engine → Report Engine → Evaluation → HITL → Export.

```mermaid
sequenceDiagram
  autonumber

  participant Analyst
  participant CLI as CLI / API<br/>(run_research.py)
  participant SUP as Supervisor<br/>(orchestrator.py)
  participant RUN as ResearchGraphRunner<br/>(harness/runner.py)
  participant STORE as RuntimeStore<br/>(runtime_store.py)
  participant BUDGET as BudgetGuard<br/>(services.py)
  participant INGEST as AutoIngestTool<br/>(documents/)
  participant VNSTOCK as VnstockConnector<br/>(connectors/)
  participant FACTS as BuildFactsTool<br/>(facts/ + reconciliation/)
  participant INDEX as BuildIndexTool<br/>(retrieval.py)
  participant LLM as OpenAIModelAdapter<br/>(harness/model_adapter.py)
  participant LANGFUSE as Langfuse<br/>(tracing)
  participant VAL as ValuationEngine<br/>(analytics/)
  participant REPORT as ReportEngine<br/>(reporting/)
  participant EVAL as EvaluationService<br/>(evaluation/ + harness/gates.py)

  %% ─────────────────────────────────────────────
  Note over Analyst,EVAL: PHASE 0 — KHỞI ĐỘNG RUN
  %% ─────────────────────────────────────────────

  Analyst->>CLI: python run_research.py<br/>--ticker DHG --report-type full_report
  CLI->>SUP: Supervisor.execute(RunContext)
  SUP->>RUN: ResearchGraphRunner.execute(context)
  RUN->>STORE: create_run(run_id, ticker, run_type,<br/>status=initialized)
  STORE-->>RUN: run_id confirmed

  RUN->>RUN: PREFLIGHT — validate policy,<br/>budget config, ticker whitelist
  RUN->>STORE: update_run_state(running, PREFLIGHT)
  RUN->>STORE: add_step(PREFLIGHT, status=completed)

  %% ─────────────────────────────────────────────
  Note over Analyst,EVAL: PHASE 1 — LẬP KẾ HOẠCH (SUPERVISOR PLAN)
  %% ─────────────────────────────────────────────

  RUN->>STORE: add_step(SUPERVISOR_PLAN, agent=supervisor)
  RUN->>LLM: model_adapter.run_agent(<br/>agent=supervisor,<br/>task="Create execution plan & HITL routing policy")
  LLM->>LANGFUSE: trace(run_id, agent, model, tokens)
  LLM->>BUDGET: charge(run_id, SUPERVISOR_PLAN,<br/>prompt_tokens, completion_tokens)
  BUDGET-->>LLM: BudgetDecision(allow=True)
  LLM-->>RUN: AgentResult{plan, policy, requires_human=False}
  RUN->>STORE: save_artifact(supervisor_plan, payload=plan)
  RUN->>STORE: close_step(SUPERVISOR_PLAN, completed)

  %% ─────────────────────────────────────────────
  Note over Analyst,EVAL: PHASE 2 — THU THẬP DỮ LIỆU (DATA_RETRIEVAL_RUN)
  %% ─────────────────────────────────────────────

  RUN->>STORE: add_step(DATA_RETRIEVAL_RUN)
  RUN->>STORE: update_run_state(running, DATA_RETRIEVAL_RUN)

  Note over INGEST: Step 2a — Ingest tài liệu chính thức
  RUN->>INGEST: auto_ingest_tool(ticker, from_year, to_year, ocr=False)
  INGEST->>INGEST: OfficialDocumentDiscovery<br/>discover candidate URLs<br/>(SSC / HNX / HOSE / IR)
  INGEST->>INGEST: DocumentFetcher<br/>download PDFs → data/official_documents/
  INGEST->>INGEST: PDFExtractor / OCR<br/>extract text + tables
  INGEST->>INGEST: SourceMetadata<br/>save source_id, checksum, tier=1
  INGEST-->>RUN: ServiceNodeResult{status=completed,<br/>docs_found, pages_extracted}
  RUN->>STORE: save_artifact(auto_ingest, summary)

  Note over FACTS: Step 2b — Build canonical facts
  RUN->>FACTS: build_facts_tool(ticker, from_year, to_year)
  FACTS->>VNSTOCK: VnstockConnector.fetch(<br/>financial_statements, FY 2021–2025)
  VNSTOCK-->>FACTS: raw income_stmt, balance_sheet, cashflow
  FACTS->>FACTS: FactNormalizer<br/>map raw → FactEntry<br/>{metric_name, value, unit,<br/>source_id, source_tier, confidence}
  FACTS->>FACTS: FinancialFactReconciler<br/>cross-source conflict detection<br/>Tier-1 overrides Tier-3
  FACTS->>FACTS: DataQualityGates<br/>coverage_gate / core_keys_gate<br/>source_validation_gate / valuation_gate
  FACTS->>STORE: persist canonical facts → facts_db
  FACTS-->>RUN: ServiceNodeResult{snapshot_id,<br/>periods_available, valuation_gate=pass}
  RUN->>STORE: save_artifact(build_facts, summary)
  RUN->>STORE: update_run_state(data_ready)

  Note over INDEX: Step 2c — Build evidence index
  RUN->>INDEX: build_index_tool(ticker, from_year, to_year)
  INDEX->>INDEX: DocumentChunker<br/>split PDFs + API text → chunks<br/>{chunk_id, source_id, text,<br/>section, fiscal_year}
  INDEX->>INDEX: Embedder<br/>vector embeddings → Milvus / SQLite
  INDEX-->>RUN: ServiceNodeResult{chunks_indexed, sources_covered}
  RUN->>STORE: save_artifact(index, summary)

  Note over LLM: Step 2d — Data retrieval agent review
  RUN->>LLM: run_agent(data_retrieval,<br/>"Review data inventory & retrieval readiness")
  LLM->>LANGFUSE: trace(tokens, latency, cost)
  LLM->>BUDGET: charge(DATA_RETRIEVAL_RUN)
  BUDGET-->>LLM: allow=True
  LLM-->>RUN: AgentResult{coverage_assessment,<br/>data_gaps, confidence}
  RUN->>STORE: save_artifact(data_retrieval_review)
  RUN->>STORE: close_step(DATA_RETRIEVAL_RUN, completed)

  %% ─────────────────────────────────────────────
  Note over Analyst,EVAL: PHASE 3 — QUALITY GATE: DATA
  %% ─────────────────────────────────────────────

  RUN->>EVAL: data_quality_gate(build_facts_summary)
  EVAL->>EVAL: check valuation_gate == pass<br/>check snapshot_id present<br/>check coverage_gate / core_keys_gate
  alt gate PASS
    EVAL-->>RUN: {gate=data_quality, passed=True, severity=none}
    RUN->>STORE: add_step(DATA_QUALITY_GATE, completed)
  else gate FAIL
    EVAL-->>RUN: {passed=False, blocking_reasons=[...]}
    RUN->>STORE: update_run_state(failed, DATA_QUALITY_GATE)
    RUN-->>CLI: BLOCKED — data quality insufficient
  end

  %% ─────────────────────────────────────────────
  Note over Analyst,EVAL: PHASE 4 — PHÂN TÍCH TÀI CHÍNH (FINANCIAL_ANALYST_RUN)
  %% ─────────────────────────────────────────────

  RUN->>LLM: run_agent(financial_analyst,<br/>"Interpret ratio tables,<br/>identify traceable diagnostics")
  LLM->>LANGFUSE: trace(tokens, latency)
  LLM->>BUDGET: charge(FINANCIAL_ANALYST_RUN)
  BUDGET-->>LLM: allow=True / fallback_model if soft budget hit
  LLM-->>RUN: AgentResult{financial_tables,<br/>diagnostics, confidence}
  RUN->>STORE: save_artifact(financial_analyst_review)
  RUN->>EVAL: financial_analyst_gate(financial_tables)
  EVAL-->>RUN: gate result (pass / fail)

  %% ─────────────────────────────────────────────
  Note over Analyst,EVAL: PHASE 5 — ĐỊNH GIÁ (VALUATION_RUN)
  %% ─────────────────────────────────────────────

  RUN->>VAL: run_valuation_tool(ticker, from_year, to_year)
  Note over VAL: Deterministic Python — no LLM arithmetic
  VAL->>VAL: FCFF DCF<br/>(EBIT × (1−tax) + D&A − CAPEX − ΔNWC)
  VAL->>VAL: FCFE DCF<br/>(NI + D&A − CAPEX − ΔNWC + NetBorrowing)
  VAL->>VAL: Blend DCF = 60% Price_FCFF + 40% Price_FCFE
  VAL->>VAL: P/E Multiples (peer median × EPS_FY1)
  VAL->>VAL: EV/EBITDA Multiples (peer median × EBITDA)
  VAL->>VAL: Sensitivity Table (WACC × Terminal Growth grid)
  VAL->>STORE: save ValuationArtifact JSON<br/>{assumptions, input_facts,<br/>output_values, sensitivity_table}
  VAL-->>RUN: ServiceNodeResult{snapshot_id,<br/>dcf_price, pe_price, ev_price, blend_price}
  RUN->>STORE: save_artifact(valuation, summary)

  RUN->>LLM: run_agent(valuation,<br/>"Review outputs, assumptions, model limitations")
  LLM->>BUDGET: charge(VALUATION_RUN)
  LLM-->>RUN: AgentResult{review, warnings, confidence}
  RUN->>STORE: save_artifact(valuation_review)

  RUN->>EVAL: valuation_gate(valuation_outputs)
  EVAL->>EVAL: check dcf_completeness<br/>check sensitivity_completeness<br/>check snapshot_id present
  EVAL-->>RUN: gate result
  RUN->>STORE: update_run_state(valuation_ready, VALUATION_GATE)

  %% ─────────────────────────────────────────────
  Note over Analyst,EVAL: PHASE 6 — HITL CHECKPOINT 1: ASSUMPTIONS APPROVAL
  %% ─────────────────────────────────────────────

  RUN->>STORE: update_run_state(needs_human_review,<br/>WAITING_ASSUMPTIONS_APPROVAL)
  RUN->>RUN: PAUSE — set requires_human=True<br/>next_resume_stage=VALUATION_LOCKED
  STORE-->>Analyst: 🔔 Awaiting valuation assumptions approval<br/>run_id, valuation_artifact, assumptions

  Analyst->>CLI: approve_report.py --run-id X<br/>--stage assumptions --decision approve<br/>[--feedback-patch {...}]
  CLI->>SUP: Supervisor.handle_approval(run_id, assumptions, approved)
  SUP->>RUN: handle_approval(run_id, stage, decision, reviewer, patch)
  RUN->>STORE: add_approval(valuation_assumptions, approved, reviewer)

  alt approved
    RUN->>STORE: lock_artifacts(run_id, [valuation_draft])<br/>is_locked=True — no further changes
    RUN->>STORE: add_audit_event(assumptions_approved)
    Note over RUN: Resume from VALUATION_LOCKED

  else rejected
    RUN->>STORE: mark_artifacts_stale(<br/>["valuation_draft","full_report_draft",<br/>"quality","citation_gate"])
    RUN->>STORE: update_run_state(needs_human_review, NEEDS_REVIEW)
    STORE-->>Analyst: ⚠ Assumptions rejected — please revise<br/>invalidated_sections listed
  end

  %% ─────────────────────────────────────────────
  Note over Analyst,EVAL: PHASE 7 — SINH BÁO CÁO (REPORT_WRITER_CRITIC_RUN)
  %% ─────────────────────────────────────────────

  RUN->>STORE: update_run_state(running, VALUATION_LOCKED)
  RUN->>REPORT: generate_report_tool(ticker, snapshot_id, mode=draft)
  REPORT->>REPORT: ReportDataLoader<br/>load facts + valuation artifact + retrieval context
  REPORT->>INDEX: Retriever.search(claim, top_k=5, tier_priority)
  INDEX-->>REPORT: EvidencePack{chunks, source_ids, support_scores}
  REPORT->>REPORT: SectionBuilder<br/>build 8 sections from grounded evidence<br/>(Executive Summary → Appendix)
  REPORT->>REPORT: CitationMap<br/>map claims → source_id<br/>compute coverage_ratio
  REPORT->>REPORT: HTMLRenderer (Jinja2 → HTML)<br/>ChartGenerator (matplotlib → 6 charts)
  REPORT->>REPORT: PDFRenderer (HTML → PDF)
  REPORT->>STORE: save ReportArtifact<br/>{sections, citation_map, approval_status=draft}
  REPORT-->>RUN: ServiceNodeResult{report_path, citation_map, coverage_ratio}
  RUN->>STORE: save_artifact(report, summary)

  RUN->>LLM: run_agent(report_writer_critic,<br/>"Check citations, numeric consistency, readiness")
  LLM->>BUDGET: charge(REPORT_WRITER_CRITIC_RUN)
  LLM-->>RUN: AgentResult{review_notes, warnings, confidence}
  RUN->>STORE: save_artifact(report_writer_critic_review)

  %% ─────────────────────────────────────────────
  Note over Analyst,EVAL: PHASE 8 — ĐÁNH GIÁ CHẤT LƯỢNG (QUALITY_EVALUATION)
  %% ─────────────────────────────────────────────

  RUN->>EVAL: evaluate_quality_tool(report_path, ticker)
  EVAL->>EVAL: numeric_consistency<br/>compare report numbers vs canonical facts
  EVAL->>EVAL: citation_coverage<br/>coverage_ratio ≥ threshold?<br/>all quantitative claims cited?
  EVAL->>EVAL: citation_validity<br/>citation content matches claim?
  EVAL->>EVAL: stale_data<br/>fiscal_year freshness, published_date check
  EVAL->>EVAL: valuation_reproducibility<br/>DCF recomputable from assumptions + input_facts?
  EVAL-->>RUN: EvalResult{gate, passed, severity, issues[]}
  RUN->>STORE: save_artifact(quality_evaluation)

  RUN->>EVAL: citation_gate(coverage_ratio, invalid_citations)
  EVAL-->>RUN: gate result (pass / warn / fail)

  RUN->>EVAL: export_gate(all_gate_results)
  alt all critical gates pass
    EVAL-->>RUN: {passed=True} — report publishable
    RUN->>STORE: update_run_state(report_ready, EXPORT_GATE)
  else critical gate fail
    EVAL-->>RUN: {passed=False, blocking_reasons}
    RUN->>STORE: update_run_state(needs_human_review)
    RUN-->>CLI: BLOCKED — cannot export, fix citations/numeric errors
  end

  %% ─────────────────────────────────────────────
  Note over Analyst,EVAL: PHASE 9 — HITL CHECKPOINT 2: FINAL APPROVAL
  %% ─────────────────────────────────────────────

  RUN->>STORE: update_run_state(needs_human_review,<br/>WAITING_FINAL_APPROVAL)
  RUN->>RUN: PAUSE — requires_human=True
  STORE-->>Analyst: 🔔 Awaiting final report approval<br/>report HTML + eval summary attached

  Analyst->>CLI: approve_report.py --run-id X<br/>--stage final_report --decision approve
  CLI->>SUP: handle_approval(final_report, approved)
  SUP->>RUN: handle_approval(run_id, final_report, approved)
  RUN->>STORE: add_approval(final_report, approved)

  alt approved
    RUN->>STORE: update_run_state(approved, PUBLISHED)
    RUN->>STORE: save ApprovalRecord{reviewer, timestamp, decision}
    RUN->>REPORT: publish artifacts<br/>(HTML + PDF → reports/ folder)
    RUN->>RUN: _write_evidence_packet()<br/>_write_run_manifest()
    RUN->>STORE: add_audit_event(final_report_published)
    STORE-->>Analyst: ✅ Report published<br/>reports/DHG_YYYYMMDD.html<br/>reports/DHG_YYYYMMDD.pdf

  else rejected
    RUN->>STORE: mark_artifacts_stale(<br/>["full_report_draft","quality","citation_gate"])
    RUN->>STORE: update_run_state(needs_human_review, NEEDS_REVIEW)
    STORE-->>Analyst: ⚠ Final rejected — revise report and regenerate
  end

  %% ─────────────────────────────────────────────
  Note over Analyst,EVAL: PHASE 10 — BUDGET GUARD (chạy song song ở mọi LLM call)
  %% ─────────────────────────────────────────────

  Note over BUDGET,LANGFUSE: BudgetGuard.charge() được gọi sau mỗi LLM response.<br/>Nếu run_total > soft_budget → dùng fallback_model cho bước tiếp theo.<br/>Nếu run_total > hard_budget → block run, escalate HITL.
```

---

## 1. System Context — Tổng quan hệ thống (C4 Level 1)

```mermaid
C4Context
  title Vietnam Pharma Equity Research Agent — System Context

  Person(analyst, "Analyst", "Kiểm duyệt báo cáo, phê duyệt định giá và xuất bản")
  Person(admin, "System Admin", "Quản lý lịch chạy, cấu hình ticker, budget policy")

  System(research_system, "Equity Research Agent", "Pipeline tự động: ingestion → facts → valuation → report → evaluation → HITL approval → export")

  System_Ext(vnstock, "vnstock / SSC / HNX / HOSE", "Nguồn dữ liệu tài chính Việt Nam (API + PDF)")
  System_Ext(cafef, "CafeF / IR websites", "Nguồn tài liệu doanh nghiệp bổ sung")
  System_Ext(llm_api, "LLM API (OpenAI/Anthropic)", "Mô hình ngôn ngữ cho synthesis & extraction")
  System_Ext(langfuse, "Langfuse", "Observability & tracing LLM calls")

  Rel(analyst, research_system, "Xem báo cáo nháp, phê duyệt, reject, export")
  Rel(admin, research_system, "Cấu hình cron job, budget, ticker universe")
  Rel(research_system, vnstock, "Fetch financial statements, market data")
  Rel(research_system, cafef, "Fetch annual reports, disclosures (PDF)")
  Rel(research_system, llm_api, "Synthesis, narrative generation, extraction")
  Rel(research_system, langfuse, "Trace LLM calls, cost, latency")
```

---

## 2. Use Case Diagram

```mermaid
%%{init: {"theme": "default"}}%%
graph LR
  subgraph Actors
    A1[Analyst]
    A2[System / Scheduler]
  end

  subgraph UseCases["Use Cases"]
    UC1(["Chạy full research pipeline\n(run_research.py)"])
    UC2(["Ingest dữ liệu tài chính\n(ingest_ticker.py)"])
    UC3(["Build canonical facts\n(build_facts.py)"])
    UC4(["Chạy định giá\n(run_valuation.py)"])
    UC5(["Build evidence index\n(build_index.py)"])
    UC6(["Generate báo cáo\n(generate_report.py)"])
    UC7(["Evaluate báo cáo\n(evaluate_report.py)"])
    UC8(["Phê duyệt / Từ chối\n(approve_report.py)"])
    UC9(["Export final report"])
    UC10(["Xem run status / artifacts"])
    UC11(["Cấu hình budget policy"])
    UC12(["Chạy batch nhiều ticker\n(batch.py)"])
    UC13(["Cron: weekly sync / refresh"])
  end

  A1 --> UC1
  A1 --> UC8
  A1 --> UC10
  A1 --> UC6
  A1 --> UC7
  A2 --> UC1
  A2 --> UC2
  A2 --> UC3
  A2 --> UC4
  A2 --> UC5
  A2 --> UC12
  A2 --> UC13
  A2 --> UC11

  UC1 -.includes.-> UC2
  UC1 -.includes.-> UC3
  UC1 -.includes.-> UC4
  UC1 -.includes.-> UC5
  UC1 -.includes.-> UC6
  UC1 -.includes.-> UC7
  UC8 -.extends.-> UC9
```

---

## 3. Pipeline Workflow — Luồng pipeline cốt lõi

```mermaid
flowchart TD
  Start([User / Scheduler\ntrigger run]) --> PREFLIGHT

  PREFLIGHT["PREFLIGHT\nValidate run_id, ticker, policy"] --> SUPERVISOR_PLAN

  SUPERVISOR_PLAN["SUPERVISOR_PLAN\nAgent: supervisor\nCreate execution plan\n& HITL routing policy"] --> DATA_RETRIEVAL_RUN

  subgraph DATA_LAYER["Data Layer (DATA_RETRIEVAL_RUN)"]
    AUTO_INGEST["auto_ingest_tool\nFetch official PDFs\n(SSC/HNX/HOSE/IR)\nOCR optional\nNon-blocking"]
    BUILD_FACTS["build_facts_tool\nNormalize canonical facts\n(Tier-1/2/3)\nFY periods 2021-2025"]
    BUILD_INDEX["build_index_tool\nChunk documents\nVector index\nDB retrieval"]
    DATA_AGENT["Agent: data_retrieval\nReview data inventory\n& retrieval readiness"]
    AUTO_INGEST --> BUILD_FACTS --> BUILD_INDEX --> DATA_AGENT
  end

  DATA_RETRIEVAL_RUN --> DATA_LAYER --> DATA_QUALITY_GATE

  DATA_QUALITY_GATE{{"DATA_QUALITY_GATE\ncoverage_gate\ncore_keys_gate\nsource_validation_gate\nvaluation_gate"}}
  DATA_QUALITY_GATE -->|pass| FINANCIAL_ANALYST_RUN
  DATA_QUALITY_GATE -->|fail| BLOCKED_DQ[/"BLOCKED\nNeeds data fix"/]

  FINANCIAL_ANALYST_RUN["FINANCIAL_ANALYST_RUN\nAgent: financial_analyst\nInterpret ratio tables\nIdentify diagnostics"]
  FINANCIAL_ANALYST_RUN --> FINANCIAL_ANALYST_GATE

  FINANCIAL_ANALYST_GATE{{"FINANCIAL_ANALYST_GATE\nConfidence check\nAnalysis quality"}}
  FINANCIAL_ANALYST_GATE -->|pass| VALUATION_RUN
  FINANCIAL_ANALYST_GATE -->|fail| BLOCKED_FA[/"BLOCKED\nLow confidence"/]

  subgraph VALUATION_LAYER["Valuation Layer (VALUATION_RUN)"]
    VAL_CODE["run_valuation_tool\nDCF FCFF + FCFE + Blend\nP/E multiples\nEV/EBITDA multiples\nSensitivity table\n(deterministic Python)"]
    VAL_AGENT["Agent: valuation\nReview outputs, assumptions\n& model limitations"]
    VAL_CODE --> VAL_AGENT
  end

  VALUATION_RUN --> VALUATION_LAYER --> VALUATION_GATE

  VALUATION_GATE{{"VALUATION_GATE\nDCF completeness\nSensitivity completeness\nSnapshot present"}}
  VALUATION_GATE -->|pass| WAITING_ASSUMPTIONS_APPROVAL
  VALUATION_GATE -->|fail| BLOCKED_VAL[/"BLOCKED\nValuation incomplete"/]

  WAITING_ASSUMPTIONS_APPROVAL(["WAITING_ASSUMPTIONS_APPROVAL\n⏸ HITL Checkpoint 1\nAnalyst review valuation assumptions"])
  WAITING_ASSUMPTIONS_APPROVAL -->|approved| VALUATION_LOCKED
  WAITING_ASSUMPTIONS_APPROVAL -->|rejected / revision| NEEDS_REVIEW_V[/"NEEDS_REVIEW\nRevise assumptions"/]

  VALUATION_LOCKED["VALUATION_LOCKED\nLock valuation artifacts\nNo further changes allowed"]

  subgraph REPORT_LAYER["Report Layer (REPORT_WRITER_CRITIC_RUN)"]
    GEN_REPORT["generate_report_tool\nBuild grounded narrative\nMap citations\nMode: draft"]
    CRITIC_AGENT["Agent: report_writer_critic\nCheck citations\nNumeric consistency\nFinal readiness"]
    GEN_REPORT --> CRITIC_AGENT
  end

  VALUATION_LOCKED --> REPORT_WRITER_CRITIC_RUN --> REPORT_LAYER --> QUALITY_EVALUATION

  QUALITY_EVALUATION["QUALITY_EVALUATION\nevaluate_quality_tool\n5 deterministic gates:\nnumeric_consistency\ncitation_coverage\ncitation_validity\nstale_data\nvaluation_reproducibility"]
  QUALITY_EVALUATION --> CITATION_GATE

  CITATION_GATE{{"CITATION_GATE\ncoverage_ratio ≥ threshold\nno invalid citations\nclaim grounding OK"}}
  CITATION_GATE -->|pass| EXPORT_GATE
  CITATION_GATE -->|fail| BLOCKED_CIT[/"BLOCKED\nCitation failure"/]

  EXPORT_GATE{{"EXPORT_GATE\nAll critical gates pass\nReport publishable"}}
  EXPORT_GATE -->|pass| WAITING_FINAL_APPROVAL
  EXPORT_GATE -->|fail| BLOCKED_EXP[/"BLOCKED\nCannot export"/]

  WAITING_FINAL_APPROVAL(["WAITING_FINAL_APPROVAL\n⏸ HITL Checkpoint 2\nAnalyst final review & sign-off"])
  WAITING_FINAL_APPROVAL -->|approved| PUBLISHED
  WAITING_FINAL_APPROVAL -->|rejected| NEEDS_REVIEW_F[/"NEEDS_REVIEW\nRevise report"/]

  PUBLISHED(["PUBLISHED\nArtifacts exported\nApproval record saved"])
```

---

## 4. Data Architecture — Kiến trúc dữ liệu

```mermaid
flowchart TD
  subgraph SOURCES["External Sources (Tier)"]
    T1["Tier-1: Official Audited PDFs\n(SSC, HNX, HOSE)"]
    T2["Tier-2: Disclosed PDFs\n(IR, CafeF)"]
    T3["Tier-3: vnstock API\n(live financial statements)"]
  end

  subgraph INGESTION["Ingestion Layer"]
    DISC["OfficialDocumentDiscovery\nDiscover candidate URLs"]
    FETCH["DocumentFetcher\nDownload & store raw PDF"]
    OCR["PDFExtractor / OCR\nExtract text + tables"]
    VNCONN["VnstockConnector\nFetch API data"]
    DISC --> FETCH --> OCR
  end

  subgraph FACTS["Canonical Facts Layer"]
    NORM["FactNormalizer\nMap → FactEntry schema\n{ticker, fiscal_year, quarter,\nmetric_name, value, source_id,\nconfidence, source_tier}"]
    RECON["FinancialFactReconciler\nCross-source reconciliation\nConflict detection"]
    DQ["DataQualityGates\ncoverage_gate\ncore_keys_gate\nsource_validation_gate\nvaluation_gate"]
    FACTDB[("facts_db\n(SQLite / canonical facts)")]
    NORM --> RECON --> DQ --> FACTDB
  end

  subgraph EVIDENCE["Evidence / Retrieval Layer"]
    CHUNKER["DocumentChunker\nSplit text → chunks\n{chunk_id, source_id,\nticker, text, section,\nfiscal_year, metadata}"]
    EMBEDDER["Embedder\nVector embeddings\n(Milvus / local)"]
    RETRIEVER["Retriever\nTop-k search\nTier-priority weighting"]
    EVIDDB[("retrieval_index\n(SQLite + Milvus)")]
    CHUNKER --> EMBEDDER --> EVIDDB
    RETRIEVER --> EVIDDB
  end

  subgraph VALUATION["Valuation Layer (Code-First, Deterministic)"]
    FCFF["FCFF DCF"]
    FCFE["FCFE DCF"]
    BLEND["Blend DCF\n(60% FCFF + 40% FCFE)"]
    PE["P/E Multiples"]
    EVEBITDA["EV/EBITDA Multiples"]
    SENSI["Sensitivity Table\n(WACC × Terminal Growth)"]
    VART[("ValuationArtifact JSON\n{valuation_id, ticker, method,\nassumptions, input_facts,\noutput_values, sensitivity_table}")]
    FCFF & FCFE --> BLEND
    BLEND & PE & EVEBITDA & SENSI --> VART
  end

  subgraph REPORT["Report Generation Layer"]
    CTXBLD["ReportDataLoader\nLoad facts + valuation\n+ retrieval context"]
    SECTBLD["SectionBuilder\nBuild sections from\ngrounded evidence packs"]
    CITMAP["CitationMap\nMap claims → source_id\ncoverage ratio"]
    HTMLREND["HTML Renderer\nJinja2 → HTML"]
    PDFREND["PDF Renderer\nHTML → PDF"]
    RPTART[("Report Artifacts\n{report_id, ticker, type,\nsections, citation_map,\neval_summary, approval_status}")]
    CTXBLD --> SECTBLD --> CITMAP --> HTMLREND --> PDFREND --> RPTART
  end

  subgraph EVALUATION["Evaluation Layer (Deterministic Gates)"]
    E1["numeric_consistency"]
    E2["citation_coverage"]
    E3["citation_validity"]
    E4["stale_data"]
    E5["valuation_reproducibility"]
    EVALRES[("EvalResult\n{gate, passed, severity,\nissue_id, blocking_reasons}")]
    E1 & E2 & E3 & E4 & E5 --> EVALRES
  end

  T1 & T2 --> INGESTION
  T3 --> VNCONN --> NORM
  OCR --> NORM
  FACTDB --> VALUATION
  FACTDB --> CHUNKER
  VART --> CTXBLD
  FACTDB --> CTXBLD
  RETRIEVER --> SECTBLD
  RPTART --> EVALUATION
  VART --> E5
  FACTDB --> E1
```

---

## 5. Multi-Agent Architecture — Supervisor & Worker Agents

```mermaid
graph TB
  subgraph ORCHESTRATION["Orchestration Layer"]
    SUPERVISOR["Supervisor\n(orchestrator.py)\nFacade → ResearchGraphRunner\nHITL routing\nRecompute planning\nOffline evaluation"]
    RUNNER["ResearchGraphRunner\n(harness/runner.py)\nLangGraph state machine\nStage execution\nBudget enforcement\nCheckpointing"]
    BUDGET["BudgetGuard\n(services.py)\nSoft/hard budget\nFallback model trigger\nCost ledger"]
    STORE["RuntimeStore\n(runtime_store.py)\nRun state\nArtifact registry\nApproval records\nAudit log\nStep trace"]
    SUPERVISOR --> RUNNER
    RUNNER --> BUDGET
    RUNNER --> STORE
  end

  subgraph AGENTS["LLM Agent Workers (model_adapter.py)"]
    AG_SUP["supervisor agent\nPlan execution\nHITL routing policy"]
    AG_DATA["data_retrieval agent\nReview data inventory\nSource coverage check"]
    AG_FA["financial_analyst agent\nInterpret ratio tables\nIdentify diagnostics\n(No arithmetic!)"]
    AG_VAL["valuation agent\nReview DCF outputs\nCheck assumptions\nFlag model limitations"]
    AG_REPORT["report_writer_critic agent\nCheck narrative grounding\nCitation consistency\nFinal readiness"]
  end

  subgraph SERVICES["Deterministic Service Tools"]
    SVC_INGEST["auto_ingest_tool\nFetch official PDFs\nOCR pipeline"]
    SVC_FACTS["build_facts_tool\nCanonical fact normalization\nDQ gate validation"]
    SVC_INDEX["build_index_tool\nChunking + embedding\nVector index"]
    SVC_VAL["run_valuation_tool\nDCF / P-E / EV-EBITDA\nSensitivity table"]
    SVC_REPORT["generate_report_tool\nSection builder\nCitation mapper\nHTML + PDF render"]
    SVC_EVAL["evaluate_quality_tool\n5 evaluation gates"]
  end

  subgraph GATES["Quality Gates (gates.py)"]
    G_DQ["data_quality_gate"]
    G_FA["financial_analyst_gate"]
    G_VAL["valuation_gate"]
    G_CIT["citation_gate"]
    G_EXP["export_gate"]
  end

  RUNNER -- "SUPERVISOR_PLAN" --> AG_SUP
  RUNNER -- "DATA_RETRIEVAL_RUN" --> SVC_INGEST & SVC_FACTS & SVC_INDEX
  RUNNER -- "DATA_RETRIEVAL_RUN" --> AG_DATA
  RUNNER -- "DATA_QUALITY_GATE" --> G_DQ
  RUNNER -- "FINANCIAL_ANALYST_RUN" --> AG_FA
  RUNNER -- "FINANCIAL_ANALYST_GATE" --> G_FA
  RUNNER -- "VALUATION_RUN" --> SVC_VAL
  RUNNER -- "VALUATION_RUN" --> AG_VAL
  RUNNER -- "VALUATION_GATE" --> G_VAL
  RUNNER -- "REPORT_WRITER_CRITIC_RUN" --> SVC_REPORT
  RUNNER -- "REPORT_WRITER_CRITIC_RUN" --> AG_REPORT
  RUNNER -- "QUALITY_EVALUATION" --> SVC_EVAL
  RUNNER -- "CITATION_GATE" --> G_CIT
  RUNNER -- "EXPORT_GATE" --> G_EXP

  LANGFUSE["Langfuse\nTracing & cost logging"]
  AG_SUP & AG_DATA & AG_FA & AG_VAL & AG_REPORT -.-> LANGFUSE
```

---

## 6. Run Lifecycle State Machine

```mermaid
stateDiagram-v2
  [*] --> initialized : createRun()

  initialized --> running : PREFLIGHT pass

  running --> data_ready : DATA_RETRIEVAL_RUN + DATA_QUALITY_GATE pass
  running --> needs_human_review : gate fail / error
  running --> failed : unrecoverable error

  data_ready --> analysis_ready : FINANCIAL_ANALYST_RUN + FINANCIAL_ANALYST_GATE pass
  analysis_ready --> valuation_ready : VALUATION_RUN + VALUATION_GATE pass

  valuation_ready --> needs_human_review : WAITING_ASSUMPTIONS_APPROVAL\n(HITL Checkpoint 1)
  needs_human_review --> running : approved → resume VALUATION_LOCKED
  needs_human_review --> needs_human_review : rejected → invalidate artifacts\nrevise and resubmit

  running --> report_ready : VALUATION_LOCKED → REPORT_WRITER_CRITIC_RUN\n+ QUALITY_EVALUATION + CITATION_GATE + EXPORT_GATE pass

  report_ready --> needs_human_review : WAITING_FINAL_APPROVAL\n(HITL Checkpoint 2)
  needs_human_review --> approved : final approved → PUBLISHED
  needs_human_review --> needs_human_review : final rejected → revise

  approved --> [*]
  failed --> [*]
  cancelled --> [*]

  running --> cancelled : manual cancel
```

---

## 7. HITL Approval Flow — Luồng phê duyệt của analyst

```mermaid
sequenceDiagram
  participant Analyst
  participant API as approve_report.py / API
  participant Runner as ResearchGraphRunner
  participant Store as RuntimeStore
  participant Runner2 as ResearchGraphRunner (resume)

  Note over Runner: Pipeline tự động dừng tại<br/>WAITING_ASSUMPTIONS_APPROVAL
  Runner ->> Store: update_run_state(needs_human_review)
  Store -->> Analyst: Notification: awaiting assumptions approval

  Analyst ->> API: POST /research/{run_id}/approve<br/>{stage: "assumptions", decision: "approve",<br/>reviewer, feedback_patch}
  API ->> Runner: handle_approval(run_id, stage, decision, reviewer, patch)
  Runner ->> Store: add_approval(valuation_assumptions, approved)

  alt Decision = approved
    Runner ->> Store: lock_artifacts(run_id, ["valuation_draft"])
    Runner ->> Runner2: run_until_pause(start_stage=VALUATION_LOCKED)
    Runner2 ->> Runner2: REPORT_WRITER_CRITIC_RUN\n→ QUALITY_EVALUATION\n→ CITATION_GATE\n→ EXPORT_GATE
    Runner2 ->> Store: update_run_state(report_ready, WAITING_FINAL_APPROVAL)
    Store -->> Analyst: Notification: awaiting final approval

    Analyst ->> API: POST /research/{run_id}/approve<br/>{stage: "final_report", decision: "approve"}
    API ->> Runner: handle_approval(run_id, final_report, approved)
    Runner ->> Runner2: run_until_pause(start_stage=PUBLISHED)
    Runner2 ->> Store: publishArtifacts → approved
    Store -->> Analyst: Report exported (HTML + PDF)

  else Decision = rejected (assumptions)
    Runner ->> Store: mark_artifacts_stale(["valuation_draft", "full_report_draft", "quality", "citation_gate"])
    Runner ->> Store: update_run_state(needs_human_review, NEEDS_REVIEW)
    Store -->> Analyst: Artifacts invalidated — please revise assumptions and rerun
  
  else Decision = rejected (final_report)
    Runner ->> Store: mark_artifacts_stale(["full_report_draft", "quality", "citation_gate"])
    Runner ->> Store: update_run_state(needs_human_review, NEEDS_REVIEW)
    Store -->> Analyst: Report invalidated — revise and regenerate
  end
```

---

## 8. Budget Guardrails Flow

```mermaid
flowchart TD
  STEP[LLM Agent Call\n(model_adapter.py)] --> CHARGE

  CHARGE["BudgetGuard.charge(\n  run_id, step_name,\n  model_name,\n  prompt_tokens, completion_tokens\n)"]

  CHARGE --> CALC["cost_usd =\n(prompt_tokens × 0.2 +\n completion_tokens × 0.8)\n/ 1_000_000"]

  CALC --> TOTAL["run_total =\nstore.run_cost_usd(run_id)\n+ cost_usd"]

  TOTAL --> HARD{run_total >\nhard_budget_usd?}

  HARD -->|Yes| STOP["BudgetDecision(allow=False)\nstop_reason: hard_budget_exceeded\nRunner blocks stage → escalate HITL"]

  HARD -->|No| SOFT{run_total >\nsoft_budget_usd?}

  SOFT -->|Yes| FALLBACK["BudgetDecision(allow=True)\nfallback_model = settings.fallback_model\nDowngrade model for next steps"]

  SOFT -->|No| ALLOW["BudgetDecision(allow=True)\nContinue with primary model"]

  CHARGE --> LOG["store.add_budget_entry(\n  cost_usd, fallback_model, stop_reason\n)"]
```

---

## 9. Partial Recompute Decision Flow

```mermaid
flowchart TD
  TRIGGER["New Source / Catalyst /\nPrompt Change detected"] --> CLASSIFY

  CLASSIFY["RecomputePlanner.decide(event_type)"]

  CLASSIFY --> SM[source_metadata_only]
  CLASSIFY --> CO[catalyst_only]
  CLASSIFY --> FC[fact_changed]
  CLASSIFY --> PC[prompt_or_template_changed]

  SM --> NO_RECOMPUTE["No Recompute\nIndex refresh only\n(re-chunk new document)"]

  CO --> IMPACT{Impacts\nValuation?}
  IMPACT -->|Yes| RERUN_VAL
  IMPACT -->|No| THESIS_ONLY

  FC --> RERUN_VAL["Invalidate valuation artifacts\nRerun: VALUATION_RUN\n→ VALUATION_GATE\n→ WAITING_ASSUMPTIONS_APPROVAL"]

  RERUN_VAL --> REFRESH_SYNTH["Refresh: REPORT_WRITER_CRITIC_RUN\n→ QUALITY_EVALUATION\n→ CITATION_GATE"]

  REFRESH_SYNTH --> REFRESH_CIT["Re-validate citations\nExport gate re-check"]

  PC --> THESIS_ONLY["Refresh: REPORT_WRITER_CRITIC_RUN only\n(valuation artifact unchanged)"]
  THESIS_ONLY --> REFRESH_CIT

  STORE_PLAN["Supervisor.recompute_plan()\nStore flags in RuntimeStore\nUpdate run state → NEEDS_REVIEW"] -.-> CLASSIFY
```

---

## 10. Evaluation Gate Flow

```mermaid
flowchart TD
  REPORT[Report Draft\n+ Valuation Artifact\n+ Facts DB] --> EQT

  EQT["evaluate_quality_tool\n(scripts/evaluate_report.py)"]

  EQT --> G1["numeric_consistency\nCompare report numbers\nvs canonical facts\nvs valuation artifact"]
  EQT --> G2["citation_coverage\ncoverage_ratio ≥ threshold\nall quantitative claims cited"]
  EQT --> G3["citation_validity\ncitation supports claim\nno fake/mismatched citations"]
  EQT --> G4["stale_data\nfiscal_year freshness check\nsource published_date check"]
  EQT --> G5["valuation_reproducibility\nDCF recomputable from assumptions\n+ input_facts"]

  G1 & G2 & G3 & G4 & G5 --> GATE_RESULT

  GATE_RESULT{{"All critical gates\npassed?"}}

  GATE_RESULT -->|Yes — all pass| CITATION_GATE
  GATE_RESULT -->|WARN — non-critical| CITATION_GATE_W["citation_gate\n(with warnings logged)"]
  GATE_RESULT -->|FAIL — critical| BLOCKED["BLOCKED: export_gate fails\nReport cannot be published\nAnalyst must fix root cause"]

  CITATION_GATE["citation_gate\ngate_result: passed\ncoverage_ratio OK\nno invalid citations"] --> EXPORT_GATE

  EXPORT_GATE["export_gate\nAll upstream gates pass\nReport artifact complete"] --> WAITING_FINAL_APPROVAL

  CITATION_GATE_W --> EXPORT_GATE
```

---

## 11. Full Research Sequence (End-to-End)

```mermaid
sequenceDiagram
  participant User
  participant CLI as run_research.py
  participant Supervisor
  participant Runner as ResearchGraphRunner
  participant DataSvc as Data Services
  participant ValSvc as Valuation Service
  participant LLM as LLM Agents
  participant EvalSvc as Evaluation Service
  participant Store as RuntimeStore
  participant Analyst

  User ->> CLI: python run_research.py --ticker DHG --report-type full_report
  CLI ->> Supervisor: execute(RunContext)
  Supervisor ->> Runner: execute(context)

  Runner ->> Store: create_run(run_id, ticker, status=initialized)
  Runner ->> Runner: PREFLIGHT — validate policy

  Runner ->> LLM: SUPERVISOR_PLAN — plan + HITL routing
  LLM -->> Runner: execution plan

  Runner ->> DataSvc: DATA_RETRIEVAL_RUN
  DataSvc ->> DataSvc: auto_ingest_tool (PDF fetch + OCR)
  DataSvc ->> DataSvc: build_facts_tool (normalize canonical facts)
  DataSvc ->> DataSvc: build_index_tool (chunk + embed)
  DataSvc ->> LLM: data_retrieval agent review
  DataSvc -->> Runner: data_inventory + retrieval_results
  Store ->> Store: update_run_state(data_ready)

  Runner ->> Runner: DATA_QUALITY_GATE
  Runner ->> LLM: FINANCIAL_ANALYST_RUN
  LLM -->> Runner: financial tables + diagnostics
  Runner ->> Runner: FINANCIAL_ANALYST_GATE

  Runner ->> ValSvc: VALUATION_RUN — run_valuation_tool
  ValSvc ->> ValSvc: DCF FCFF + FCFE + Blend\nP/E + EV/EBITDA\nSensitivity table
  ValSvc ->> LLM: valuation agent review
  ValSvc -->> Runner: ValuationArtifact
  Runner ->> Runner: VALUATION_GATE
  Store ->> Store: update_run_state(valuation_ready)

  Runner ->> Store: WAITING_ASSUMPTIONS_APPROVAL\nupdate_run_state(needs_human_review)
  Store -->> Analyst: Awaiting assumptions approval

  Analyst ->> CLI: approve_report.py --run-id X --stage assumptions --decision approve
  CLI ->> Runner: handle_approval(approved)
  Runner ->> Store: lock_artifacts(valuation_draft)

  Runner ->> Runner: VALUATION_LOCKED
  Runner ->> EvalSvc: REPORT_WRITER_CRITIC_RUN\ngenerate_report_tool → report_writer_critic agent
  EvalSvc -->> Runner: report draft + citation map

  Runner ->> EvalSvc: QUALITY_EVALUATION — evaluate_quality_tool
  EvalSvc -->> Runner: 5-gate evaluation result
  Runner ->> Runner: CITATION_GATE + EXPORT_GATE
  Store ->> Store: update_run_state(report_ready)

  Runner ->> Store: WAITING_FINAL_APPROVAL\nupdate_run_state(needs_human_review)
  Store -->> Analyst: Awaiting final approval

  Analyst ->> CLI: approve_report.py --run-id X --stage final_report --decision approve
  CLI ->> Runner: handle_approval(approved)
  Runner ->> Runner: PUBLISHED
  Runner ->> Store: save approval record\npublish artifacts (HTML + PDF)
  Store -->> User: Report exported → reports/DHG_*.html + .pdf
```

---

## 12. Agent Registry — Vai trò từng Agent

```mermaid
classDiagram
  class Supervisor {
    +execute(context: RunContext)
    +handle_approval(run_id, stage, decision, reviewer, patch)
    +recompute_plan(run_id, event_type)
    +run_offline_evaluation(run_id)
    -runner: ResearchGraphRunner
    -offline_eval: OfflineEvaluator
  }

  class ResearchGraphRunner {
    +execute(context)
    +run_until_pause(state, start_stage)
    +handle_approval(run_id, stage, decision, reviewer, patch)
    -budget: BudgetGuard
    -agent_registry: AgentRegistry
    -model_adapter: OpenAIModelAdapter
    -_compiled_graph: LangGraph
    -_run_stage(state, stage)
    -_execute_stage(state, stage)
  }

  class AgentRegistry {
    +get_agent(agent_id: str) AgentConfig
    +list_agents() list
  }

  class OpenAIModelAdapter {
    +call(agent_id, prompt, context) AgentResult
    -_trace_langfuse(call_id, tokens, cost)
  }

  class BudgetGuard {
    +charge(run_id, step_name, model, p_tokens, c_tokens, policy) BudgetDecision
    -hard_budget_usd: float
    -soft_budget_usd: float
    -fallback_model: str
  }

  class RuntimeStore {
    +create_run(run_id, ticker, run_type)
    +update_run_state(run_id, status, stage)
    +save_artifact(artifact_id, run_id, type, section_key, payload)
    +add_approval(run_id, stage, decision, reviewer, patch)
    +lock_artifacts(run_id, section_keys)
    +mark_artifacts_stale(run_id, section_keys, reason)
    +add_step(run_id, step_name, agent_name)
    +add_budget_entry(run_id, step_name, cost_usd)
    +add_audit_event(run_id, actor, action, payload)
    +latest_graph_state(run_id) dict
  }

  Supervisor --> ResearchGraphRunner
  ResearchGraphRunner --> AgentRegistry
  ResearchGraphRunner --> OpenAIModelAdapter
  ResearchGraphRunner --> BudgetGuard
  ResearchGraphRunner --> RuntimeStore
  Supervisor --> RuntimeStore
```

---

## 13. Data Model — Artifact Contracts

```mermaid
erDiagram
  RUN {
    string run_id PK
    string ticker
    string run_type
    string status
    string current_stage
    json   policy
    json   flags
    float  cost_usd_total
    datetime created_at
    datetime updated_at
  }

  CANONICAL_FACT {
    string fact_id PK
    string ticker
    int    fiscal_year
    string quarter
    string metric_name
    float  value
    string unit
    string currency
    string source_id FK
    int    source_tier
    float  confidence
    datetime created_at
  }

  SOURCE_METADATA {
    string source_id PK
    string ticker
    string source_type
    string source_title
    string source_url_or_path
    date   published_date
    int    fiscal_year
    int    reliability_tier
    string checksum
    datetime ingested_at
  }

  VALUATION_ARTIFACT {
    string valuation_id PK
    string ticker
    string method
    string snapshot_id
    json   assumptions
    json   input_facts
    json   output_values
    json   sensitivity_table
    datetime created_at
  }

  DOCUMENT_CHUNK {
    string chunk_id PK
    string source_id FK
    string ticker
    text   text
    string section
    int    fiscal_year
    json   metadata
    string embedding_id
  }

  REPORT_ARTIFACT {
    string report_id PK
    string ticker
    string report_type
    string run_id FK
    json   sections
    json   citation_map
    json   eval_summary
    string approval_status
    datetime created_at
  }

  APPROVAL_RECORD {
    string approval_id PK
    string run_id FK
    string stage
    string decision
    string reviewer
    json   feedback_patch
    datetime created_at
  }

  EVAL_RESULT {
    string eval_id PK
    string run_id FK
    string gate
    bool   passed
    string severity
    json   issues
    json   summary
    datetime created_at
  }

  RUN ||--o{ CANONICAL_FACT : "uses"
  RUN ||--o{ VALUATION_ARTIFACT : "produces"
  RUN ||--o{ REPORT_ARTIFACT : "produces"
  RUN ||--o{ APPROVAL_RECORD : "has"
  RUN ||--o{ EVAL_RESULT : "has"
  SOURCE_METADATA ||--o{ CANONICAL_FACT : "backs"
  SOURCE_METADATA ||--o{ DOCUMENT_CHUNK : "chunks into"
  VALUATION_ARTIFACT ||--|| REPORT_ARTIFACT : "grounded in"
```

---

## 14. Offline Evaluation Gate Flow (CI/CD)

```mermaid
flowchart TD
  CHANGE["Parser / Prompt /\nModel Change (PR)"] --> BENCH

  BENCH["RunOfflineBenchmarks\n(backend/dataset/offline_eval.py)"]

  BENCH --> C1["grounding_score\n(claim → source support)"]
  BENCH --> C2["citation_faithfulness\n(citation content matches claim)"]
  BENCH --> C3["factual_consistency\n(numbers match canonical facts)"]
  BENCH --> C4["stability_regression\n(output deterministic across runs)"]
  BENCH --> C5["eval_gate_coverage\n(all 5 gates exercised)"]

  C1 & C2 & C3 & C4 & C5 --> THRESHOLD{Meets\nThresholds?}

  THRESHOLD -->|Yes| PROMOTE["Promote to Production\nMerge to main"]
  THRESHOLD -->|No| ROLLBACK["Keep Current Version\nOpen Fix Loop\nDo NOT merge"]
```

---

## Ghi chú

- Mọi sơ đồ đều dùng Mermaid — paste vào [mermaid.live](https://mermaid.live) hoặc xem trong VSCode với extension Mermaid Preview.
- **LLM agents không được tính số liệu tài chính** — chỉ synthesis, interpretation, review.
- **Valuation artifacts bị lock** sau khi analyst approve tại checkpoint 1 — không thể sửa sau đó.
- **Export gate là hard block** — nếu bất kỳ critical gate nào fail, báo cáo không được publish.
- Sơ đồ phản ánh code thực tại `backend/harness/runner.py`, `backend/harness/graph.py`, `backend/orchestrator.py`, và `backend/services.py`.
