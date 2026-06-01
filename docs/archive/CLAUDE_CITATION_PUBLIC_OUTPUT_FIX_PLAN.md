# CLAUDE PLAN — Citation UX, Public Source Labels, and Internal Audit Separation

## 0. Operating Instruction for Claude Code

Read this file as a standalone execution plan. Do **not** merge it into the existing report export / font / chart / narrative fix plan.

This plan is only about:

- fixing confusing citation presentation in user-facing reports,
- separating internal audit metadata from public report citations,
- preventing developer-only terms from leaking into Markdown / HTML / PDF,
- making citation labels understandable for non-technical equity research readers,
- enforcing export gates when citations are generic, Tier-3-only, or unreconciled.

Do not dilute this plan by refactoring unrelated report layout, valuation, chart, or font logic unless required to satisfy citation acceptance tests.

---

## 1. Context

The current citation layer has two conflicting behaviors:

1. The internal gate correctly detects that final export must be blocked when quantitative claims rely only on Tier-3 provider/API sources.
2. The public-facing draft/report still exposes confusing internal terminology and raw provenance fields that are not appropriate for readers.

Observed examples from current DHG citation artifacts:

```text
source_uri: vnstock://vci/finance/balance_sheet/DHG?period=year
source_title: Balance Sheet (VCI) [Tier 3 — API tổng hợp (cần kiểm chứng)]
fact_id: 272
source_id: 0ce025f55db53...
reconciliation_status: missing_official
official_document_id: null
tier_label: Chỉ số phái sinh
```

These fields are useful for developers and auditors but should **not** appear in final Markdown/HTML/PDF shown to users.

The product requirement is stricter:

```text
Public report citations must be clear, human-readable, and verifiable.
Internal provenance must remain available in audit artifacts, but must not leak into the user-facing report.
```

---

## 2. Problem Statement

### 2.1 Core Issue

The current citation system conflates three different concerns:

| Concern | Correct Audience | Current Problem |
|---|---|---|
| Internal lineage | Developer / auditor | Correctly stored, but too raw |
| Export gate | System / reviewer | Mostly correct, but draft can still look publishable |
| Public citation | Report reader | Too technical, ambiguous, and confusing |

### 2.2 User-Facing Failure Modes

The report reader sees or may see terms such as:

```text
Tier 3
vnstock://...
fact_id
source_uri
missing_official
official_document_id
reconciliation_status
provider/generic source label
API tổng hợp cần kiểm chứng
```

These terms create three problems:

1. They make the report look like a debugging artifact rather than an equity research report.
2. They confuse non-technical readers who only need to know whether the source is official, verified, or provisional.
3. They weaken trust because the citation label does not identify a concrete document, page, table, issuer, publication date, or retrieval path.

### 2.3 Trust Failure

A claim such as:

```text
Doanh thu thuần 2025 đạt X tỷ đồng.
Nguồn: Income Statement (VCI) [Tier 3 — API tổng hợp (cần kiểm chứng)]
```

is not a proper public citation.

The correct public behavior should be one of:

```text
Nguồn: BCTC kiểm toán DHG 2025, Báo cáo kết quả kinh doanh, mục "Doanh thu thuần".
```

or, if not verified:

```text
Nguồn tạm thời: Dữ liệu tổng hợp từ API thị trường, chưa đối chiếu với BCTC chính thức. Không đủ điều kiện cho bản final.
```

---

## 3. Target State

### 3.1 Separate Internal and Public Citation Contracts

Implement two distinct contracts:

```python
@dataclass(frozen=True)
class InternalCitationRecord:
    claim_id: str
    fact_id: str | None
    source_id: str | None
    source_uri: str | None
    source_title: str | None
    source_tier: int | None
    reliability_tier: int | None
    reconciliation_status: str | None
    official_document_id: str | None
    official_document_url: str | None
    document_title: str | None
    issuer: str | None
    published_at: str | None
    page_number: int | None
    table_name: str | None
    line_item_label: str | None
    extraction_method: str | None
    parser_version: str | None
    confidence: float | None
```

```python
@dataclass(frozen=True)
class PublicCitation:
    citation_id: str
    display_label: str
    source_type_label: str
    verification_label: str
    publication_date: str | None
    locator: str | None
    note: str | None
```

`InternalCitationRecord` is for audit JSON / internal QA only.

`PublicCitation` is the only structure allowed in Markdown/HTML/PDF user-facing report renderers.

---

## 4. Public Citation Taxonomy

### 4.1 Source Type Labels

Use plain Vietnamese labels.

| Internal Source Type | Public Label |
|---|---|
| official audited financial statement | BCTC kiểm toán |
| official reviewed interim financial statement | BCTC soát xét |
| official quarterly financial statement | BCTC quý |
| annual report | Báo cáo thường niên |
| exchange disclosure | Công bố thông tin |
| regulator document | Văn bản cơ quan quản lý |
| tender result | Kết quả đấu thầu |
| company press release | Thông cáo doanh nghiệp |
| market data provider | Dữ liệu thị trường |
| provider API only | Dữ liệu tổng hợp chưa đối chiếu |

### 4.2 Verification Labels

| Internal Condition | Public Label |
|---|---|
| official document matched | Đã đối chiếu tài liệu chính thức |
| official document + line item matched | Đã đối chiếu dòng số liệu |
| derived from verified official facts | Tính toán từ số liệu đã đối chiếu |
| provider only / unreconciled | Chưa đối chiếu BCTC chính thức |
| conflicting sources | Nguồn đang mâu thuẫn |
| missing source | Thiếu nguồn |

### 4.3 Public Citation Examples

#### Verified Financial Fact

```text
Nguồn: BCTC kiểm toán DHG 2025, Báo cáo kết quả kinh doanh, mục “Doanh thu thuần” — đã đối chiếu dòng số liệu.
```

#### Derived Metric

```text
Nguồn: Tính toán từ BCTC kiểm toán DHG 2024–2025, dựa trên doanh thu thuần và lợi nhuận gộp đã đối chiếu.
```

#### Draft-Only Provider Data

```text
Nguồn tạm thời: Dữ liệu tổng hợp từ API thị trường, chưa đối chiếu với BCTC chính thức. Chỉ dùng cho bản nháp.
```

#### Missing Source

```text
Nguồn: Chưa đủ bằng chứng để xuất bản.
```

---

## 5. Hard Rules

### 5.1 Public Report Must Never Render These Tokens

Add a denylist validator for all public Markdown/HTML/PDF output.

```text
vnstock://
fact_id
source_id
source_uri
source_title
source_tier
tier_label
reliability_tier
official_document_id
reconciliation_status
missing_official
provider/generic
Tier 0
Tier 1
Tier 2
Tier 3
API tổng hợp
VCI
KBS
hash
parser_version
extraction_method
context_event_ids
```

Exception: internal audit files may contain these tokens.

### 5.2 Final Report Must Not Use Draft-Only Citation Labels

If a claim has only `provider API only` or `reconciliation_status = missing_official`, final export must be blocked.

Allowed final statuses:

```text
official_document_matched
official_line_item_matched
derived_from_verified_facts
```

Not allowed final statuses:

```text
missing_official
provider_only
generic_source_label
unknown_source
conflicting_source
missing_source
```

### 5.3 Draft Report Must Be Visibly Draft

If draft mode contains unreconciled data, the report must display a clear user-facing banner:

```text
Bản nháp: một số số liệu đang dùng nguồn tổng hợp chưa đối chiếu với tài liệu chính thức. Không dùng để phát hành hoặc ra quyết định đầu tư.
```

Do not show raw technical warnings in the main report body. Save full technical warnings in the audit artifact.

---

## 6. Required Architecture Changes

### Phase 1 — Citation Contract Split

#### Objective

Separate internal lineage from user-facing citation rendering.

#### Tasks

1. Locate current citation map generation code.
2. Identify every call site that passes raw citation map into report renderer.
3. Add `InternalCitationRecord` schema if not already present.
4. Add `PublicCitation` schema.
5. Implement mapper:

```python
def to_public_citation(record: InternalCitationRecord, mode: Literal["draft", "final"]) -> PublicCitation:
    ...
```

6. Ensure report renderer accepts only `PublicCitation`.
7. Ensure audit exporter keeps full `InternalCitationRecord`.

#### Acceptance Criteria

- User-facing Markdown no longer contains raw citation fields.
- Audit JSON still contains full lineage.
- No public renderer imports or serializes raw citation map directly.

---

### Phase 2 — Public Citation Label Mapper

#### Objective

Convert internal source metadata into clear Vietnamese public labels.

#### Tasks

Implement source mapping rules:

```python
if official_document_id and page_number and line_item_label:
    verification_label = "Đã đối chiếu dòng số liệu"
elif official_document_id:
    verification_label = "Đã đối chiếu tài liệu chính thức"
elif is_derived and all_inputs_verified:
    verification_label = "Tính toán từ số liệu đã đối chiếu"
elif source_tier == 3 or reconciliation_status == "missing_official":
    verification_label = "Chưa đối chiếu BCTC chính thức"
else:
    verification_label = "Thiếu nguồn"
```

Implement display labels:

```python
display_label = f"{source_type_label} {ticker} {fiscal_year}"
locator = f"trang {page_number}, bảng {table_name}, mục {line_item_label}"
```

Do not include internal provider names in the public label unless the report is explicitly an internal audit report.

#### Acceptance Criteria

- A verified BCTC fact displays as a formal document citation.
- A derived metric displays as a calculation citation.
- A provider-only fact displays as draft-only provisional source.
- No `Tier` labels appear in public output.

---

### Phase 3 — Citation Gate Reconciliation

#### Objective

Ensure gate status and report mode are consistent.

#### Current Problem

The system can generate a draft with `PASS_WITH_WARNINGS` while the report body still appears too final. Final audit correctly blocks export when 96/96 quantitative claims are Tier-3 only, but the draft presentation does not make this sufficiently clear.

#### Tasks

1. Add explicit report mode:

```python
ReportMode = Literal["draft", "review", "final"]
```

2. Define gate behavior:

| Mode | Provider-only Data | Public Citation Label | Export |
|---|---|---|---|
| draft | allowed | “Nguồn tạm thời…” | allowed with banner |
| review | allowed only with warnings | “Chưa đối chiếu…” | reviewer only |
| final | blocked | not rendered | blocked |

3. If final export is blocked:
   - do not create a final-looking report path,
   - create `_BLOCKED.md` only as internal reviewer artifact,
   - do not render PDF final.

4. Add a public “source confidence summary” in draft/review:

```text
Tình trạng nguồn: 0/96 số liệu định lượng đã đối chiếu với tài liệu chính thức. Báo cáo chưa đủ điều kiện phát hành final.
```

#### Acceptance Criteria

- Draft visibly signals provisional source status.
- Final cannot render with provider-only quantitative claims.
- `_BLOCKED` artifacts are clearly internal/reviewer-only.

---

### Phase 4 — Public Report Citation Rendering

#### Objective

Make citations readable and similar to professional equity research notes.

#### Tasks

1. Render citations in footnote or compact source format.
2. Avoid putting citation debugging text inline after every sentence.
3. Recommended patterns:

For tables:

```text
Nguồn: BCTC kiểm toán DHG 2025; tính toán của hệ thống.
```

For charts:

```text
Nguồn: BCTC kiểm toán DHG 2022–2025; dữ liệu giá thị trường tại ngày 01/06/2026.
```

For narrative claims:

```text
... biên gộp giảm 120 bps so với năm trước. [1]
```

Footnote:

```text
[1] Tính toán từ doanh thu thuần và lợi nhuận gộp trong BCTC kiểm toán DHG 2024–2025.
```

4. If source is provisional:

```text
Nguồn tạm thời: dữ liệu tổng hợp chưa đối chiếu BCTC chính thức.
```

5. Do not use source labels that require readers to understand system architecture.

#### Acceptance Criteria

- Reader can understand citation without knowing data pipeline internals.
- Internal source IDs are absent.
- Tables/charts have concise source labels.
- Narrative claims use compact citations.

---

### Phase 5 — Citation Coverage at Claim Level

#### Objective

Prevent “generic source at section level” from pretending to support detailed claims.

#### Tasks

Implement claim-level citation contract:

```python
@dataclass(frozen=True)
class ClaimCitationBinding:
    claim_id: str
    claim_text: str
    claim_type: Literal["financial_fact", "derived_metric", "valuation_assumption", "forecast", "business_thesis", "risk", "catalyst"]
    required_source_type: list[str]
    citation_ids: list[str]
    verification_status: str
    publishability: Literal["publishable", "draft_only", "blocked"]
```

Rules:

| Claim Type | Minimum Required Citation |
|---|---|
| financial_fact | official line item or provider-only draft label |
| derived_metric | all input facts cited and verified |
| valuation_assumption | source or explicit analyst assumption |
| forecast | model artifact + assumption table |
| business_thesis | document/news/catalyst evidence |
| risk | evidence or clearly marked analyst judgment |
| catalyst | dated source/event |
| peer comparison | peer universe source + metric source |

#### Acceptance Criteria

- Every quantitative claim has a claim-level citation.
- Section-level generic source is not counted as enough for final.
- Derived metrics cite input facts or calculation artifact.
- Forecast claims cite assumption artifact.

---

### Phase 6 — Public/Private Artifact Separation

#### Objective

Prevent internal audit artifacts from being confused with user reports.

#### Tasks

Create clear output structure:

```text
reports/
  public/
    DHG_YYYYMMDD_draft.md
    DHG_YYYYMMDD_review.md
    DHG_YYYYMMDD_final.md
  internal/
    DHG_YYYYMMDD_citation_map.json
    DHG_YYYYMMDD_citation_audit.md
    DHG_YYYYMMDD_gate_results.json
    DHG_YYYYMMDD_blocked_reasons.md
```

Rules:

- `public/` must contain only user-readable citations.
- `internal/` may contain raw lineage fields.
- Report UI should default to public artifact.
- Internal artifacts should be linked only in reviewer/developer mode.

#### Acceptance Criteria

- No internal JSON-like source metadata appears in public report.
- Internal audit remains available.
- Users are not exposed to developer-only citation vocabulary.

---

### Phase 7 — Tests and Validation

#### Unit Tests

Create tests for:

```text
test_public_citation_does_not_expose_internal_fields
test_provider_only_source_maps_to_draft_only_label
test_official_document_maps_to_verified_public_label
test_derived_metric_requires_verified_inputs
test_final_blocks_missing_official_sources
test_draft_adds_unverified_source_banner
test_public_markdown_denylist
test_public_html_denylist
test_public_pdf_text_denylist
```

#### Integration Tests

Create one fixture with:

1. Verified BCTC fact.
2. Provider-only fact.
3. Derived metric with verified inputs.
4. Derived metric with unverified inputs.
5. Forecast assumption.
6. Catalyst claim with news/document source.

Expected outcomes:

| Fixture | Draft | Final |
|---|---|---|
| verified BCTC fact | allowed | allowed |
| provider-only fact | allowed with provisional label | blocked |
| verified derived metric | allowed | allowed |
| unverified derived metric | allowed with warning | blocked |
| forecast assumption | allowed if explicit assumption | reviewer approval required |
| catalyst claim | allowed if dated source exists | allowed |

#### Snapshot Tests

Generate sample public reports and assert:

```text
- no vnstock://
- no fact_id
- no source_uri
- no Tier 3
- no missing_official
- no provider/generic
- no hash-like source IDs
- contains source confidence summary
- contains human-readable source labels
```

---

## 7. Files to Inspect First

Claude should inspect these likely files or equivalent modules in the repo:

```text
backend/citations/
backend/citations/source_tier_gate.py
backend/citations/citation_map.py
backend/citations/rendering.py
backend/reporting/
backend/reporting/render_report.py
scripts/generate_report.py
scripts/run_research.py
templates/
reports/
tests/unit/
tests/integration/
```

If exact paths differ, search for:

```text
citation_map
source_tier_gate
source_title
source_uri
reconciliation_status
missing_official
Tier 3
PASS_WITH_WARNINGS
export_blocked
```

---

## 8. Implementation Order

Execute in this exact order:

```text
1. Add public/private citation schema split.
2. Implement mapper from internal citation record to public citation.
3. Replace report renderer input with PublicCitation only.
4. Add denylist validator for public outputs.
5. Fix draft/review/final mode behavior.
6. Add claim-level citation binding.
7. Separate public and internal artifact directories.
8. Add tests.
9. Run full DHG citation audit again.
10. Confirm final remains blocked until official sources exist.
```

Do not start with UI polish. The core fix is the citation contract boundary.

---

## 9. Definition of Done

This plan is complete only if all conditions are true:

```text
[ ] Public Markdown has zero internal citation fields.
[ ] Public HTML has zero internal citation fields.
[ ] Public PDF extracted text has zero internal citation fields.
[ ] Draft report shows clear provisional-source banner if any claim is unverified.
[ ] Final report is blocked when any quantitative claim relies only on provider/API source.
[ ] Citation audit still preserves full internal lineage.
[ ] Public citations are readable in Vietnamese.
[ ] Derived metrics are traced to input facts or calculation artifacts.
[ ] Forecast claims cite model assumptions and approval status.
[ ] Tests cover verified, provisional, missing, conflicting, and derived citations.
```

---

## 10. Expected User-Facing Output After Fix

### Draft Example

```text
Tình trạng nguồn: 0/96 số liệu định lượng đã đối chiếu với tài liệu chính thức.
Bản nháp này sử dụng dữ liệu tổng hợp chưa đối chiếu BCTC chính thức và chưa đủ điều kiện phát hành final.
```

Table source:

```text
Nguồn tạm thời: dữ liệu tổng hợp từ API thị trường, chưa đối chiếu với BCTC chính thức.
```

### Final Example

```text
Nguồn: BCTC kiểm toán DHG 2025, Báo cáo kết quả kinh doanh, mục “Doanh thu thuần” — đã đối chiếu dòng số liệu.
```

### Blocked Final Example

```text
Không thể xuất bản final: 96/96 số liệu định lượng chưa được đối chiếu với tài liệu chính thức. Vui lòng ingest và reconcile BCTC chính thức trước khi chạy lại report.
```

---

## 11. Non-Goals

Do not solve these in this plan:

```text
- Font rendering.
- Chart validation.
- Valuation calculation.
- Report layout redesign.
- Full narrative rewriting.
- OCR pipeline.
- Official document downloader.
```

Those belong to separate plans.

---

## 12. Final Instruction

The highest-priority invariant:

```text
Public reports must never expose internal citation implementation details.
```

The second invariant:

```text
A final report must never make provider-only or unreconciled quantitative claims look verified.
```

The third invariant:

```text
Internal audit should remain detailed, but public citations must remain concise and reader-friendly.
```
