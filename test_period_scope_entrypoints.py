import ast
from pathlib import Path

from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR


ROOT = Path(__file__).resolve().parent
SCOPED_ENTRYPOINTS = (
    "scripts/validate_data.py",
    "scripts/build_index.py",
    "scripts/ingest_ticker.py",
    "scripts/run_valuation.py",
    "scripts/connectors/vnstock_finance_connector.py",
    "backend/jobs/scheduler.py",
    "backend/jobs/__init__.py",
)


def test_default_period_scope_is_2022fy_through_2025fy() -> None:
    assert (DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR) == (2022, 2025)


def test_scoped_entrypoints_import_authoritative_period_defaults() -> None:
    for relative_path in SCOPED_ENTRYPOINTS:
        tree = ast.parse((ROOT / relative_path).read_text(encoding="utf-8-sig"))
        imported_names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module == "backend.period_scope"
            for alias in node.names
        }
        integer_constants = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, int)
        }
        referenced_names = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }

        assert {"DEFAULT_FROM_YEAR", "DEFAULT_TO_YEAR"} <= imported_names, relative_path
        assert {"DEFAULT_FROM_YEAR", "DEFAULT_TO_YEAR"} <= referenced_names, relative_path
        assert 2021 not in integer_constants, relative_path
