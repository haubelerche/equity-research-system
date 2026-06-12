# Final Data Architecture Verification

## Context

This report records the final measured state after the June 9, 2026 database and filesystem cutover.

## Problem Statement

The prior architecture allowed duplicated database namespaces, loose artifact directories, implicit latest-file selection, and runtime access to legacy data. The target contract requires one governed database namespace per responsibility and run-scoped immutable filesystem artifacts.

## Technical Deep-Dive

### Live Database Proof

| Verification | Result |
| --- | --- |
| Maximum applied migration | `027_runtime_contract_alignment` |
| Canonical schemas | `ref`, `ingest`, `fact`, `research`, `valuation`, `report`, `audit` |
| `v2_*` schemas | 0 |
| Project business tables in `public` | 0 |
| Registered source paths | 4 |
| Registered source paths missing locally | 0 |
| Registered research runs | 162 |
| Registered run artifacts | 315 |

### Filesystem Proof

| Verification | Result |
| --- | ---: |
| `storage/sources/official_documents` files | 4 |
| `storage/runs` directories | 162 |
| `storage/runs` files | 315 |
| `storage/exports` files | 0 |
| `storage/archive` files | 4,255 |
| Legacy `artifacts/`, `data/`, and `reports/` roots | Absent |

The storage validator returned:

```json
{
  "missing_required_directories": [],
  "legacy_file_counts": {}
}
```

### Runtime Reference Proof

The comprehensive acceptance scan found no active `v2_*` schema references in core DAL modules, but it did find remaining operational legacy SQL and latest/loose-path behavior. These are production blockers under the requested hard rules:

| Match class | Scope | Disposition |
| --- | --- | --- |
| Production blocker: legacy SQL | `scripts/build_index.py`, `backend/retrieval.py`, `scripts/generate_report.py` | Still references removed `ingest.sources` or `ingest.official_documents` contracts |
| Production blocker: loose/latest artifacts | `scripts/generate_report.py`, `scripts/generate_charts.py`, `scripts/evaluate_report.py`, `scripts/evaluate_report_quality.py`, `scripts/evaluate_citations.py`, `scripts/render_report.py`, reporting chart loaders | Still exposes implicit run selection, loose paths, or debug glob fallback |
| Migration-only | `scripts/data_warehouse_legacy`, `backend/database/migrate.py`, `scripts/storage` | Retained for controlled migration and validation |
| Debug/demo-only | `scripts/debug`, `scripts/demo`, `scripts/validate_phase2.py`, `scripts/validate_phase3.py` | Excluded from production runtime |
| Source enumeration | `scripts/build_index.py`, `scripts/admin/chunk_pipeline.py` | Valid glob use; does not select latest run artifacts |

### Verification Commands

| Command | Result |
| --- | --- |
| `python -m compileall -q backend scripts` | Passed |
| Focused architecture and reporting suite | 90 passed |
| `pytest -q tests` | 1,430 passed, 17 skipped, 75 failed |
| `pytest -q` | Collection blocked by vendored `vnstock/tests/conftest.py` using unsupported non-top-level `pytest_plugins` |

The 75 repository-suite failures primarily assert deleted legacy schemas, loose artifact paths, and latest-file fallback behavior. Some are stale test-contract debt, while the comprehensive code scan also confirms real operational callers that still require refactoring. The all-tests-pass acceptance criterion is not satisfied.

## Strategic Recommendations

1. Refactor the listed operational callers to require explicit `run_id`, manifests, canonical source-document metadata, and run-scoped chart paths.
2. Replace or retire stale tests that explicitly require prohibited legacy behavior, preserving coverage for equivalent canonical contracts.
3. Isolate vendored `vnstock` tests from root-level pytest discovery.
4. Delete `archive_legacy` only after the defined retention period and an analyst sign-off confirms rollback is no longer required.

## Final Assessment

The live database and physical filesystem cutover is complete and verified. The end-to-end architecture task is not complete because operational legacy/latest-path references remain and the repository-wide test suite is not green. Acceptance criteria 11, 13, and 14 remain open.
