# SEQUENCE — Luồng chạy backend

*Tài liệu mô tả các luồng chạy chính của backend `multi-agent equity research` cho Vietnam Pharma, bao gồm `full report`, `flash memo`, `catalyst refresh`, `HITL`, `retry`, `partial recompute`, và `budget guardrails`.*

---

## 1. Mục tiêu tài liệu

- Mô tả cách các thành phần backend tương tác trong từng run type.
- Làm rõ các điểm checkpoint, approval, retry, và escalation.
- Chốt quy tắc `partial recompute` và `cost-aware fallback` để phục vụ triển khai orchestration.

---

## 2. Thành phần tham gia

- `User`
- `ApiGateway`
- `ResearchOrchestrator`
- `ConnectorWorkers`
- `ValidationEngine`
- `FactStore`
- `RetrievalIndex`
- `ValuationService`
- `SynthesisWorker`
- `CitationValidator`
- `Reviewer`
- `ReportStore`
- `BudgetGuard`

---

## 3. Full report flow

```mermaid
sequenceDiagram
    participant User
    participant ApiGateway
    participant ResearchOrchestrator
    participant ConnectorWorkers
    participant ValidationEngine
    participant FactStore
    participant RetrievalIndex
    participant ValuationService
    participant SynthesisWorker
    participant CitationValidator
    participant Reviewer
    participant ReportStore

    User->>ApiGateway: POST /research/start
    ApiGateway->>ResearchOrchestrator: createRun(full_report)
    ResearchOrchestrator->>ConnectorWorkers: ingestSources
    ConnectorWorkers->>ValidationEngine: parsedData
    ValidationEngine->>FactStore: persistCanonicalFacts
    ValidationEngine->>RetrievalIndex: persistChunks
    ResearchOrchestrator->>ValuationService: buildValuationArtifacts
    ValuationService-->>ResearchOrchestrator: valuationArtifact
    ResearchOrchestrator->>SynthesisWorker: generateDraft
    SynthesisWorker-->>ResearchOrchestrator: reportSectionsAndClaims
    ResearchOrchestrator->>CitationValidator: validateClaims
    CitationValidator-->>ResearchOrchestrator: citationCoverageAndFlags
    ResearchOrchestrator->>Reviewer: requestApproval
    Reviewer-->>ResearchOrchestrator: approveOrReject
    ResearchOrchestrator->>ReportStore: publishApprovedArtifacts
    ReportStore-->>ApiGateway: reportReady
    ApiGateway-->>User: runStatusAndArtifacts
```

### Ghi chú

- `ValidationEngine` là cổng bắt buộc trước khi facts được phép vào `FactStore`.
- `CitationValidator` có quyền chặn publish nếu claim định lượng không đạt grounding.
- `Reviewer` có thể approve, reject, hoặc yêu cầu partial rerun.

---

## 4. Flash memo flow

```mermaid
sequenceDiagram
    participant User
    participant ApiGateway
    participant ResearchOrchestrator
    participant ConnectorWorkers
    participant ValidationEngine
    participant FactStore
    participant SynthesisWorker
    participant CitationValidator
    participant ReportStore

    User->>ApiGateway: POST /research/start (flash_memo)
    ApiGateway->>ResearchOrchestrator: createRun(flash_memo)
    ResearchOrchestrator->>ConnectorWorkers: fetchRecentSignals
    ConnectorWorkers->>ValidationEngine: normalizeSignalPayload
    ValidationEngine->>FactStore: persistSignalFacts
    ResearchOrchestrator->>SynthesisWorker: generateMemo
    SynthesisWorker-->>ResearchOrchestrator: memoDraft
    ResearchOrchestrator->>CitationValidator: validateMemoClaims
    CitationValidator-->>ResearchOrchestrator: passOrReview
    ResearchOrchestrator->>ReportStore: storeMemo
    ReportStore-->>ApiGateway: memoReady
    ApiGateway-->>User: memoArtifact
```

### Ghi chú

- `flash_memo` có thể bỏ qua một số bước nặng như full debate nếu policy chi phí yêu cầu.
- Memo vẫn phải có grounding cho các claim định lượng hoặc catalyst trọng yếu.

---

## 5. Catalyst refresh flow

```mermaid
sequenceDiagram
    participant ApiGateway
    participant ResearchOrchestrator
    participant ConnectorWorkers
    participant ValidationEngine
    participant FactStore
    participant BudgetGuard

    ApiGateway->>ResearchOrchestrator: triggerCatalystRefresh
    ResearchOrchestrator->>ConnectorWorkers: fetchCatalystSources
    ConnectorWorkers->>ValidationEngine: candidateEvents
    ValidationEngine->>FactStore: persistCatalystEvents
    ValidationEngine-->>ResearchOrchestrator: qualityDecision
    ResearchOrchestrator->>BudgetGuard: evaluateRecomputePolicy
    BudgetGuard-->>ResearchOrchestrator: recomputeScopeDecision
```

### Ghi chú

- Kết quả của flow này không nhất thiết sinh report ngay.
- Đầu ra quan trọng nhất là `recomputeScopeDecision`.

---

## 6. HITL review and resume flow

```mermaid
sequenceDiagram
    participant Reviewer
    participant ApiGateway
    participant ResearchOrchestrator
    participant ReportStore
    participant ValuationService
    participant SynthesisWorker

    Reviewer->>ApiGateway: POST /research/{runId}/approve or reject
    ApiGateway->>ResearchOrchestrator: applyReviewDecision
    alt approved
        ResearchOrchestrator->>ReportStore: publishArtifacts
        ReportStore-->>ApiGateway: published
    else assumptionsNeedUpdate
        ResearchOrchestrator->>ValuationService: rerunValuationWithFeedback
        ValuationService-->>ResearchOrchestrator: updatedValuationArtifact
        ResearchOrchestrator->>SynthesisWorker: refreshDraft
        SynthesisWorker-->>ResearchOrchestrator: refreshedDraft
    else narrativeOnlyChange
        ResearchOrchestrator->>SynthesisWorker: regenerateSections
        SynthesisWorker-->>ResearchOrchestrator: refreshedSections
    end
```

### Ghi chú

- Review action phải chỉ rõ `scope` để orchestration biết rerun phần nào.
- `narrativeOnlyChange` không được phép sửa valuation artifact.

---

## 7. Partial recompute decision flow

```mermaid
flowchart TD
    newInput[NewSourceOrCatalyst] --> classifyChange[ClassifyChange]
    classifyChange --> sourceOnly[SourceMetadataOnly]
    classifyChange --> catalystOnly[CatalystOnly]
    classifyChange --> factChanged[FactChanged]
    classifyChange --> promptChanged[PromptOrTemplateChanged]

    sourceOnly --> noRecompute[NoRecomputeOrIndexRefresh]
    catalystOnly --> analyzeRefresh[RefreshAnalysis]
    analyzeRefresh --> impactCheck{ImpactsValuation}
    impactCheck -->|Yes| rerunValuation[RerunValuation]
    impactCheck -->|No| thesisOnly[RefreshThesisOnly]

    factChanged --> rerunValuation
    rerunValuation --> refreshSynthesis[RefreshSynthesis]
    refreshSynthesis --> refreshCitations[RefreshCitations]

    promptChanged --> thesisOnly
    thesisOnly --> refreshCitations
```

### Ghi chú

- `source metadata only` là trường hợp thay đổi không ảnh hưởng facts hay reasoning.
- `prompt or template changed` thường chỉ yêu cầu refresh synthesis và citations.

---

## 8. Run lifecycle state machine

```mermaid
stateDiagram-v2
    [*] --> INIT
    INIT --> INGESTING
    INGESTING --> VALIDATING
    VALIDATING --> NORMALIZING
    NORMALIZING --> INDEXING
    INDEXING --> ANALYZING
    ANALYZING --> VALUATING
    VALUATING --> DEBATING
    DEBATING --> SYNTHESIZING
    SYNTHESIZING --> CITATION_CHECKING
    CITATION_CHECKING --> AWAITING_APPROVAL
    AWAITING_APPROVAL --> PUBLISHED

    INGESTING --> RETRYABLE_ERROR
    VALIDATING --> NEEDS_REVIEW
    VALUATING --> RETRYABLE_ERROR
    CITATION_CHECKING --> NEEDS_REVIEW
    AWAITING_APPROVAL --> FAILED

    RETRYABLE_ERROR --> INGESTING
    RETRYABLE_ERROR --> VALUATING
    NEEDS_REVIEW --> ANALYZING
    NEEDS_REVIEW --> SYNTHESIZING
```

### Ghi chú

- `NEEDS_REVIEW` là trạng thái nghiệp vụ, không phải lỗi hệ thống thuần túy.
- `FAILED` chỉ dùng khi run không còn khả năng tiến tiếp theo policy hiện tại.

---

## 9. Budget guardrails and fallback flow

```mermaid
flowchart TD
    runStart[RunStart] --> budgetInit[LoadBudgetPolicy]
    budgetInit --> stepExec[ExecuteStep]
    stepExec --> costCheck{WithinSoftBudget}
    costCheck -->|Yes| continueRun[ContinueRun]
    costCheck -->|No| fallbackCheck{FallbackAvailable}
    fallbackCheck -->|Yes| downgradeModel[DowngradeModelOrSkipLowValueStep]
    fallbackCheck -->|No| hardCheck{WithinHardBudget}
    downgradeModel --> continueRun
    hardCheck -->|Yes| continueRun
    hardCheck -->|No| escalateReview[EscalateToManualReview]
    escalateReview --> stopRun[StopOrPauseRun]
```

### Ghi chú

- `Soft budget` dùng để kích hoạt fallback hoặc cắt giảm step thấp giá trị.
- `Hard budget` là ngưỡng dừng bắt buộc.

---

## 10. Offline evaluation gate flow

```mermaid
flowchart TD
    candidateChange[ParserPromptModelChange] --> runBench[RunOfflineBenchmarks]
    runBench --> evalResult{MeetsThresholds}
    evalResult -->|Yes| promote[PromoteToProduction]
    evalResult -->|No| rollback[KeepCurrentVersionAndOpenFixLoop]
```

### Ghi chú

- `RunOfflineBenchmarks` cần bao phủ grounding, citation faithfulness, factual consistency, và stability regression.
- Chỉ khi đạt ngưỡng mới cho phép áp dụng vào run production.

---

## 11. Retry and escalation policy

### Retryable

- timeout connector,
- lỗi tạm thời của model provider,
- queue worker restart,
- lỗi mạng tạm thời khi ghi object store.

### Needs review

- fact validation có warning nghiêm trọng,
- citation fail cho claim bắt buộc,
- cost vượt hard budget,
- reviewer reject assumptions hoặc recommendation.

### Failed

- source không truy cập được lâu dài,
- parser không thể trích xuất dữ liệu tối thiểu,
- approval policy không thể thỏa mãn,
- run bị hủy thủ công.

---

## 12. Input and output contracts theo từng stage

### Ingestion

- Input: source config, company scope, date range.
- Output: raw assets, parsed payload, source metadata.

### Validation

- Input: parsed payload.
- Output: quality decision, accepted facts, rejected records, warnings.

### Valuation

- Input: fact snapshot, scenarios, peer context.
- Output: valuation artifact, warnings, sensitivity outputs.

### Synthesis

- Input: valuation artifact, retrieval context, catalyst summary.
- Output: report sections, claims, reviewer notes.

### Citation checking

- Input: claims, candidate citations.
- Output: coverage ratio, invalid claims, publish eligibility.

---

## 13. Kết luận

Các luồng chạy trên được thiết kế để bảo đảm bốn mục tiêu cùng lúc:

- đúng dữ liệu,
- đúng quy trình,
- đúng mức tự động hóa,
- đúng chi phí vận hành.

`SEQUENCE.md` là tài liệu chuẩn để triển khai orchestration, queue policies, review flow, và partial recompute trong backend.
