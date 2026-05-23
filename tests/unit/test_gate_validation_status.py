"""Phase 3 gate invariant tests."""
import pytest
from backend.facts.normalizer import build_validation_status_table


def test_build_validation_status_table_import():
    """Smoke: function exists and is importable."""
    assert callable(build_validation_status_table)
