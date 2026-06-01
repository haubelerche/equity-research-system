# Claude Code Plan — Cleanup cấu trúc codebase Vietnam Pharma Equity Research Agent

## 0. Mục tiêu

Dọn cấu trúc dự án hiện tại theo hướng **giảm stale code, giảm repeated code, giảm overengineering**, nhưng không phá vỡ các phần đang có giá trị thật:

- `backend/analytics`: valuation, ratios, forecasting, sensitivity, confidence.
- `backend/facts`: canonical facts, normalizer, reconciliation, completeness.
- `backend/citations`: citation map, source-tier policy, numeric/citation validation.
- `backend/documents`: official document discovery, PDF/OCR extraction, fact promotion.
- deterministic report-generation path hiện có.

Mục tiêu cuối cùng là biến codebase từ trạng thái **functional but integration-heavy** thành trạng thái:

```text
CLI scripts thin -> Backend services reusable -> Harness/workflow only orchestrates services -> Tests protect finance/data-trust logic
```

Không được biến cleanup thành một lần rewrite lớn hoặc thêm abstraction mới không cần thiết.

---

## 1. Nguyên tắc bắt buộc

### 1.1. Preserve core domain logic

Không rewrite từ đầu các module finance đã chạy được. Chỉ refactor boundary, schema, service interface và tests.

Giữ các nhóm sau làm lõi:

```text
backend/analytics/
backend/facts/
backend/citations/
backend/documents/
backend/dataops/
backend/reconciliation/
```

### 1.2. Scripts are not libraries

Mọi file trong `scripts/` chỉ nên là CLI wrapper mỏng.

Không để script chứa:

```text
- business logic chính
- direct orchestration dài
- sys.exit() nằm trong function có thể được import
- direct DB query nếu đã có repository/service
- repeated load_dotenv/sys.path/logging bootstrap
```

Target pattern:

```python
def main() -> int:
    args = parse_args()
    result = service_function(args)
    return 0 if result.ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
```

### 1.3. Do not add agents to solve structure problems

Không tạo thêm agent mới để dọn codebase hoặc để bọc logic deterministic.

Các phần sau phải là deterministic services, không phải agent:

```text
- financial fact ingestion
- validation/reconciliation
- valuation calculation
- citation validation
- numeric consistency check
- export gate
```

LLM/agent chỉ được dùng cho:

```text
- narrative synthesis
- thesis critique
- catalyst interpretation
- report review language quality
```

### 1.4. Quarantine before delete

Không xóa file ngay trong cleanup đầu tiên. Với stale/debug/experimental code:

1. Kiểm tra import/caller.
2. Di chuyển vào `tools/debug/`, `tools/experiments/`, hoặc `legacy/`.
3. Thêm README giải thích lý do.
4. Chỉ xóa ở PR sau nếu không còn caller và tests pass.

### 1.5. Tests protect cleanup

Mọi phase cleanup phải có regression/smoke test. Không chấp nhận refactor nếu DHG report path, valuation artifact, citation gate hoặc fact validation bị hỏng.

---

## 2. Hiện trạng cần xử lý

### 2.1. Script layer đang quá nặng

Các file cần ưu tiên refactor:

```text
scripts/generate_report.py
scripts/run_valuation.py
scripts/build_index.py
scripts/auto_ingest_official_documents.py
scripts/run_research.py
```

Vấn đề:

```text
- nhiều trách nhiệm trong một file
- vừa CLI vừa orchestration vừa business logic
- khó unit test
- khó gọi lại từ API/harness
- dễ tạo duplicated logic
```

### 2.2. Bootstrap lặp lại

Cần tìm và gom các đoạn:

```text
load_dotenv
sys.path.insert / sys.path.append
Path(__file__).parents
logging.basicConfig
stdout encoding setup
argparse pattern lặp lại
manual env parsing
```

### 2.3. Harness đang nặng hơn nhu cầu hiện tại

`backend/harness/` hiện có nhiều lớp:

```text
agent_registry.py
gates.py
graph.py
model_adapter.py
runner.py
state.py
tools.py
```

Không xóa harness, nhưng phải làm cho harness chỉ còn vai trò:

```text
- stateful workflow runner
- checkpoint/retry/resume boundary
- gọi backend services
- gọi LLM only where needed
```

Không để harness wrap các scripts lớn hoặc duplicate workflow logic.

### 2.4. Smoke/eval scripts phân tán

Các file như:

```text
scripts/validate_phase1.py
scripts/validate_phase2.py
scripts/validate_phase3.py
scripts/smoke_official_doc_e2e.py
scripts/test_retrieval.py
```

nên được phân loại lại thành:

```text
tests/smoke/
tests/regression/
tests/integration/
```

---

## 3. Target structure tối giản

Không tạo quá nhiều package mới. Chỉ thêm service boundary ở nơi đang có script quá lớn.

```text
backend/
  analytics/              # giữ nguyên lõi tính toán
  facts/                  # giữ nguyên canonical fact logic
  citations/              # giữ citation/source-tier/numeric validation
  documents/              # giữ discovery/PDF/OCR/fact promotion
  dataops/                # snapshot, quality report
  reconciliation/         # reconciliation workflows

  bootstrap.py            # NEW: shared env/logging/path bootstrap
  cli/
    common.py             # NEW: common CLI helpers

  valuation/              # NEW: service wrapper around analytics engines
    service.py
    schemas.py

  reporting/              # NEW: extracted from generate_report.py
    service.py
    assembler.py
    renderer_markdown.py
    export_gate.py

  indexing/               # NEW: extracted from build_index.py
    service.py
    chunk_models.py
    chunkers/

  workflows/              # NEW: long-running workflows only
    official_document_ingestion.py
    research_run.py       # optional only if replacing run_research.py cleanly

scripts/
  run_valuation.py        # thin wrapper
  generate_report.py      # thin wrapper
  build_index.py          # thin wrapper
  auto_ingest_official_documents.py  # thin wrapper
  run_research.py         # thin wrapper or deprecated wrapper

tests/
  unit/
  integration/
  regression/
  smoke/

tools/
  debug/
  experiments/

legacy/
  scripts/
```

Không tạo thêm các package như `core`, `engine`, `domain`, `application`, `infra` nếu chưa có nhu cầu thực tế. Tránh clean architecture quá mức.

---

## 4. Phase execution plan

## Phase 0 — Audit trước khi sửa

### Objective

Tạo bằng chứng về duplicated code, stale code, script side effects và file quá lớn.

### Commands

```bash
# duplicated bootstrap / CLI / side-effect patterns
rg "load_dotenv|sys.path|Path\(__file__\)|sys.exit|argparse|click|logging.basicConfig" scripts backend

# scripts calling scripts or subprocess-based orchestration
rg "subprocess|os.system|runpy|import scripts\." backend scripts

# largest Python files
find backend scripts -name "*.py" -print0 | xargs -0 wc -l | sort -nr | head -30

# likely unused code; do not blindly delete based on this
vulture backend scripts tests --min-confidence 80 || true

# imports of suspected legacy files
rg "backend\.orchestrator|scripts\._debug_recon|milvus_store|validate_phase1|validate_phase2|validate_phase3" backend scripts tests
```

### Deliverables

Create:

```text
docs/cleanup/CODEBASE_CLEANUP_AUDIT.md
docs/cleanup/DUPLICATION_REPORT.md
docs/cleanup/STALE_CANDIDATES.md
docs/cleanup/REFACTOR_TARGETS.md
```

### Acceptance criteria

```text
- Có danh sách file lớn nhất.
- Có danh sách duplicated bootstrap pattern.
- Có danh sách script side effects.
- Có danh sách stale candidates kèm evidence/caller status.
- Chưa xóa file nào ở phase này.
```

---

## Phase 1 — Chuẩn hóa bootstrap và CLI wrapper

### Objective

Loại bỏ repeated `.env`, `sys.path`, logging và exit behavior.

### Tasks

1. Tạo `backend/bootstrap.py`:

```python
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def ensure_project_root_on_path() -> None:
    root = str(project_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def bootstrap_cli(log_level: str = "INFO") -> None:
    ensure_project_root_on_path()
    configure_logging(log_level)
```

2. Tạo `backend/cli/common.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class CliResult:
    ok: bool
    message: str = ""
    data: dict[str, Any] | None = None


def exit_code(result: CliResult) -> int:
    return 0 if result.ok else 1
```

3. Refactor scripts theo pattern:

```python
def main() -> int:
    ...
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

### Do not

```text
- Không thay đổi business logic trong phase này nếu không cần.
- Không thêm framework CLI mới nếu argparse hiện vẫn đủ.
- Không chỉnh database schema.
```

### Acceptance criteria

```bash
rg "load_dotenv|sys.path.insert|sys.path.append|logging.basicConfig" scripts backend
```

Kết quả còn lại phải có lý do rõ ràng hoặc đã được gom vào `backend/bootstrap.py`.

---

## Phase 2 — Extract valuation service từ `scripts/run_valuation.py`

### Objective

Đưa valuation orchestration ra khỏi script để API/harness/test có thể gọi trực tiếp.

### New files

```text
backend/valuation/__init__.py
backend/valuation/schemas.py
backend/valuation/service.py
```

### Minimal schema

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValuationRequest:
    ticker: str
    snapshot_id: str | None = None
    from_year: int | None = None
    to_year: int | None = None
    assumptions: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValuationResult:
    ok: bool
    ticker: str
    artifact: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
```

### Service contract

```python
def run_valuation(request: ValuationRequest) -> ValuationResult:
    """Run deterministic valuation from structured facts/artifacts.

    Must not call LLM.
    Must not mutate canonical financial facts.
    Must return reproducible valuation artifact.
    """
```

### Refactor rule

`scripts/run_valuation.py` becomes:

```text
parse args -> build ValuationRequest -> call run_valuation -> print/save result -> return exit code
```

### Acceptance criteria

```text
- Harness/API can import and call backend.valuation.service.run_valuation.
- `scripts/run_valuation.py` contains no core DCF/FCFF/FCFE/multiple calculation logic.
- Unit tests cover at least one deterministic DHG valuation request using fixture/mock facts.
```

---

## Phase 3 — Extract reporting service từ `scripts/generate_report.py`

### Objective

Tách report assembly/render/export gate khỏi CLI.

### New files

```text
backend/reporting/__init__.py
backend/reporting/service.py
backend/reporting/assembler.py
backend/reporting/renderer_markdown.py
backend/reporting/export_gate.py
```

### Service contract

```python
def generate_report(request: ReportRequest) -> ReportResult:
    """Generate grounded report from accepted artifacts.

    Must not create new financial facts.
    Must not bypass citation/numeric gates.
    Must not publish final output without approval gate result.
    """
```

### Responsibility split

```text
assembler.py
  - load accepted facts, valuation artifact, citation map, catalyst evidence
  - assemble section inputs

renderer_markdown.py
  - pure Markdown rendering
  - no DB write
  - no valuation calculation

export_gate.py
  - call citation validator
  - call numeric consistency validator
  - call approval gate
  - return pass/fail with reasons

service.py
  - orchestrate assembler -> renderer -> gates -> artifact persistence
```

### Do not

```text
- Không dùng LLM để sửa số liệu.
- Không tạo citation giả nếu thiếu source.
- Không regenerate toàn bộ report nếu chỉ có một section thay đổi, trừ khi hiện tại chưa có section-level cache.
```

### Acceptance criteria

```text
- `scripts/generate_report.py` còn là wrapper mỏng.
- Markdown renderer có thể test bằng fixture input.
- Export gate fail nếu quantitative claim thiếu citation.
- DHG report path vẫn chạy được.
```

---

## Phase 4 — Extract indexing service từ `scripts/build_index.py`

### Objective

Tách chunking/indexing theo source type, tránh một file gom mọi loại document/fact/event.

### New files

```text
backend/indexing/__init__.py
backend/indexing/service.py
backend/indexing/chunk_models.py
backend/indexing/chunkers/__init__.py
backend/indexing/chunkers/pdf_chunker.py
backend/indexing/chunkers/ocr_chunker.py
backend/indexing/chunkers/catalyst_chunker.py
backend/indexing/chunkers/fact_chunker.py
```

### Chunk metadata bắt buộc

```python
@dataclass
class ChunkMetadata:
    ticker: str | None
    source_type: str
    source_id: str
    source_title: str | None
    fiscal_year: int | None
    published_date: str | None
    reliability_tier: str
    checksum: str | None
```

### Acceptance criteria

```text
- Mỗi source type có chunker riêng.
- `scripts/build_index.py` không chứa chunking logic chính.
- Có test cho metadata preservation.
- Không index operational financial facts như text nếu chúng cần được query qua structured fact store.
```

---

## Phase 5 — Extract official-document workflow từ `scripts/auto_ingest_official_documents.py`

### Objective

Biến official document ingestion thành workflow có stage boundary rõ ràng.

### New file

```text
backend/workflows/official_document_ingestion.py
```

### Workflow stages

```text
1. discover candidates
2. rank candidates
3. fetch/download document
4. detect PDF type
5. extract text/table or OCR
6. validate candidate facts
7. reconcile against secondary/provider facts
8. promote accepted facts
9. write audit summary
```

### Minimal result schema

```python
@dataclass
class WorkflowStepResult:
    step: str
    ok: bool
    artifact_id: str | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class OfficialDocumentIngestionResult:
    ok: bool
    ticker: str
    year: int | None
    steps: list[WorkflowStepResult]
```

### Acceptance criteria

```text
- Workflow can be called from script, API, or harness.
- Each stage can fail with clear reason.
- Failed validation/reconciliation does not promote facts.
- OCR dependency missing returns actionable error, not silent pass.
```

---

## Phase 6 — Move stale/debug/phase scripts

### Objective

Giảm noise mà không xóa nhầm code còn dùng.

### Candidate moves

```text
scripts/_debug_recon.py                  -> tools/debug/_debug_recon.py
scripts/validate_phase1.py               -> tests/smoke/test_phase1_source_tier.py or legacy/scripts/
scripts/validate_phase2.py               -> tests/smoke/test_phase2_fact_artifact.py or legacy/scripts/
scripts/validate_phase3.py               -> tests/smoke/test_phase3_source_coverage.py or legacy/scripts/
scripts/test_retrieval.py                -> tests/smoke/test_retrieval.py
scripts/smoke_official_doc_e2e.py        -> tests/integration/test_official_doc_e2e.py
scripts/db/milvus_store.py               -> tools/experiments/milvus_store.py if not used in production
backend/agents/__init__.py               -> keep with deprecation note until import cleanup
backend/orchestrator.py                  -> keep as deprecated facade only if callers remain
```

### Required check before move

```bash
rg "_debug_recon|validate_phase1|validate_phase2|validate_phase3|test_retrieval|smoke_official_doc_e2e|milvus_store|backend\.orchestrator|backend\.agents" backend scripts tests
```

### Acceptance criteria

```text
- No broken imports.
- Moved files have updated import paths.
- Legacy/debug folders have README.md.
- Tests still pass.
```

---

## Phase 7 — Simplify harness without deleting it

### Objective

Make harness a workflow runner over services, not another business-logic layer.

### Required changes

```text
backend/harness/tools.py
  - call backend.valuation.service, backend.reporting.service, backend.indexing.service, backend.workflows.*
  - do not call scripts directly

backend/harness/gates.py
  - delegate to deterministic validators/gates
  - no duplicated gate logic

backend/harness/model_adapter.py
  - only for LLM-based synthesis/review
  - no financial calculation

backend/harness/agent_registry.py
  - keep only real LLM roles
  - remove/deprecate fake deterministic agents if present
```

### Keep agent roles minimal

Allowed LLM roles:

```text
ResearchNarrativeAgent
CatalystInterpretationAgent
CriticReviewAgent
```

Do not create:

```text
DataIngestionAgent
ValuationCalculationAgent
CitationValidationAgent
FinancialFactAgent
```

Those are services, not agents.

### Acceptance criteria

```text
- Harness runs through backend services.
- No subprocess call to scripts from harness.
- No duplicate valuation/report/citation logic in harness.
- Stage order remains explicit and debuggable.
```

---

## Phase 8 — Regression tests and final cleanup gate

### Required tests

```text
tests/unit/test_valuation_service.py
tests/unit/test_reporting_renderer.py
tests/unit/test_reporting_export_gate.py
tests/unit/test_indexing_metadata.py
tests/integration/test_official_document_ingestion.py
tests/integration/test_dhg_full_report_path.py
tests/regression/test_golden_facts.py
tests/regression/test_report_numeric_consistency.py
tests/smoke/test_cli_wrappers_importable.py
```

### Smoke checks

```bash
pytest tests/unit tests/smoke -q
pytest tests/integration/test_dhg_full_report_path.py -q
python -m scripts.run_valuation --help
python -m scripts.generate_report --help
python -m scripts.build_index --help
python -m scripts.auto_ingest_official_documents --help
```

### Final acceptance criteria

```text
- All CLI scripts import without side effects.
- All large scripts are wrappers or explicitly documented exceptions.
- No harness path calls scripts through subprocess.
- Valuation service is deterministic and reproducible.
- Report generation still blocks unsupported quantitative claims.
- Citation/numeric/source-tier gates are preserved.
- Stale candidates are quarantined, not silently deleted.
- Cleanup docs explain what moved, what stayed, and why.
```

---

## 5. Priority order

Work in this exact order unless tests reveal a blocker:

```text
P0. Audit and document evidence.
P0. Standardize bootstrap/CLI side effects.
P0. Extract valuation service.
P0. Extract reporting service.
P1. Extract indexing service.
P1. Extract official-document ingestion workflow.
P1. Move smoke/phase scripts into tests.
P2. Quarantine debug/experimental/legacy code.
P2. Simplify harness to service orchestration.
P3. Repository layer cleanup only if duplicated DB access remains severe.
```

Do not start with repository-layer redesign. Do not start with a new agent framework. Do not start with database migration cleanup unless current tests require it.

---

## 6. Explicit non-goals

This cleanup task must not attempt to:

```text
- rewrite the whole architecture
- add a new multi-agent design
- redesign the database schema
- replace existing finance formulas
- introduce a new workflow framework
- add microservices
- migrate vector DB
- build UI
- optimize model prompts
- change business/product scope
```

If any of the above seems necessary, create a separate proposal first instead of mixing it into cleanup.

---

## 7. Definition of Done

The cleanup is complete when:

```text
1. The official execution path is documented.
2. Main scripts are thin wrappers.
3. Core valuation/reporting/indexing/official-doc workflows are callable as backend services.
4. Harness delegates to services, not scripts.
5. Debug/experimental/stale files are quarantined or converted to tests.
6. Repeated bootstrap code is centralized.
7. DHG full-report path still works.
8. Citation, numeric, source-tier, HITL, and valuation gates are preserved.
9. Regression tests pass.
10. No new unnecessary abstraction has been introduced.
```

---

## 8. Commit strategy

Use small commits. Recommended sequence:

```text
commit 1: add cleanup audit docs
commit 2: add backend/bootstrap.py and backend/cli/common.py
commit 3: refactor script entrypoints to main() -> int
commit 4: extract valuation service
commit 5: extract reporting service
commit 6: extract indexing service
commit 7: extract official-document ingestion workflow
commit 8: move smoke scripts into tests
commit 9: quarantine debug/legacy files
commit 10: simplify harness tools to call services
commit 11: add regression/smoke tests and final cleanup report
```

Each commit must keep tests passing or clearly mark temporary expected failures in the commit message.
