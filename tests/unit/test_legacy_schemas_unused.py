"""
Phase 9 â€” Legacy schema absence proof.

Proves that production Python code does not reference legacy schema tables,
that build_facts.py imports from v2 DAL modules, and that the golden CSV
override path has been fully removed.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parents[2]
PRODUCTION_DIRS = [
    REPO_ROOT / "backend",
    REPO_ROOT / "scripts",
]

# Files explicitly allowed to reference legacy table names
# (shims, TODO-rewrites documented in legacy_code_path_removal_report.md)
_ALLOWLIST_SUFFIXES = {
    "backend/database/fact_store.py",
    "backend/dataops/snapshot.py",
    "backend/database/source_registry.py",
    "backend/database/official_documents.py",
    "scripts/ingest_ticker.py",
    # Legacy scripts pending move to legacy/ directory
    "scripts/cleanup_financial_facts.py",
    "scripts/validate_data.py",
}

_LEGACY_TABLE_PATTERNS = [
    r"\bfact\.financial_facts\b",
    r"\bfact\.accepted_financial_facts\b",
]

_LEGACY_RE = re.compile("|".join(_LEGACY_TABLE_PATTERNS))


def _is_allowlisted(path: Path) -> bool:
    posix = path.as_posix()
    return any(posix.endswith(s.replace("/", "/")) for s in _ALLOWLIST_SUFFIXES)


def _production_py_files() -> list[Path]:
    files = []
    for d in PRODUCTION_DIRS:
        if d.exists():
            files.extend(
                path for path in d.rglob("*.py")
                if not {"debug", "demo", "data_warehouse_legacy", "storage"}.intersection(path.parts)
                and not path.name.startswith("validate_phase")
            )
    return files


# ---------------------------------------------------------------------------
# Legacy table reference tests
# ---------------------------------------------------------------------------

def test_no_legacy_table_references_in_production_code():
    """No non-allowlisted production file may reference legacy schema table names."""
    violations: list[str] = []
    for py_file in _production_py_files():
        if _is_allowlisted(py_file):
            continue
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        matches = _LEGACY_RE.findall(text)
        if matches:
            rel = py_file.relative_to(REPO_ROOT)
            violations.append(f"{rel}: {sorted(set(matches))}")

    assert not violations, (
        f"Found {len(violations)} file(s) referencing legacy tables:\n"
        + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# build_facts.py import checks
# ---------------------------------------------------------------------------

def _build_facts_source() -> str:
    bf = REPO_ROOT / "scripts" / "build_facts.py"
    assert bf.exists(), "scripts/build_facts.py not found"
    return bf.read_text(encoding="utf-8")


def test_build_facts_imports_v2_fact_dal():
    src = _build_facts_source()
    assert "from backend.database.canonical.fact_dal import" in src or \
           "backend.database.canonical.fact_dal" in src, \
        "build_facts.py must import from backend.database.canonical.fact_dal"


def test_build_facts_imports_v2_snapshot_dal():
    src = _build_facts_source()
    assert "from backend.database.canonical.snapshot_dal import" in src or \
           "backend.database.canonical.snapshot_dal" in src, \
        "build_facts.py must import from backend.database.canonical.snapshot_dal"


def test_build_facts_does_not_call_legacy_get_facts():
    src = _build_facts_source()
    assert "get_financial_facts_for_ticker" not in src, \
        "build_facts.py must not call legacy get_financial_facts_for_ticker()"


# ---------------------------------------------------------------------------
# Golden CSV override removal
# ---------------------------------------------------------------------------

def test_load_golden_fallback_removed():
    src = _build_facts_source()
    assert "_load_golden_fallback" not in src, \
        "_load_golden_fallback() still present â€” golden CSV inject path not removed"


def test_detect_golden_overrides_removed():
    src = _build_facts_source()
    assert "_detect_golden_overrides" not in src, \
        "_detect_golden_overrides() still present in build_facts.py"


def test_golden_dir_constant_removed():
    src = _build_facts_source()
    assert "GOLDEN_DIR" not in src, \
        "GOLDEN_DIR constant still present in build_facts.py"


def test_golden_csv_path_not_in_build_facts():
    src = _build_facts_source()
    assert "config/dataset/golden" not in src, \
        "Golden CSV directory path still hardcoded in build_facts.py"


def test_synthetic_source_id_not_constructable():
    src = _build_facts_source()
    assert "golden_csv_" not in src, \
        "Synthetic golden_csv_ source_id pattern still in build_facts.py"


def test_v2_mapper_present():
    """_canonical_facts_to_normalizer_shape must exist â€” proof the v2 read path is active."""
    src = _build_facts_source()
    assert "_canonical_facts_to_normalizer_shape" in src, \
        "_canonical_facts_to_normalizer_shape() not found â€” canonical fact read path is not active"


# ---------------------------------------------------------------------------
# Latest-file glob fallback removal
# ---------------------------------------------------------------------------

_GLOB_FALLBACK_RE = re.compile(
    r'glob\(.*artifacts/facts|glob\(.*_\*\.json|artifacts/facts.*glob',
    re.DOTALL,
)


def test_no_glob_artifact_fallback_in_production_code():
    """No production code should use glob to find 'latest' artifact files."""
    violations: list[str] = []
    for py_file in _production_py_files():
        text = py_file.read_text(encoding="utf-8", errors="ignore")
        if _GLOB_FALLBACK_RE.search(text):
            rel = py_file.relative_to(REPO_ROOT)
            violations.append(str(rel))

    assert not violations, (
        "Glob-based latest-file fallback found in:\n" + "\n".join(violations)
    )

