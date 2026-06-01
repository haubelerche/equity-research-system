"""Regression: legacy ResearchRunner must call build_facts with correct signature."""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def test_research_runner_does_not_pass_strict_kwarg():
    """ResearchRunner must use strict_completeness=, not the deprecated strict=."""
    import inspect
    from scripts.run_research import ResearchRunner
    src = inspect.getsource(ResearchRunner.run)
    assert "strict=True" not in src, (
        "Found 'strict=True' in ResearchRunner.run — must be 'strict_completeness=True'"
    )


def test_research_runner_does_not_unpack_build_facts_tuple():
    """build_facts returns a single dict; unpacking as 2-tuple raises ValueError at runtime."""
    import inspect
    from scripts.run_research import ResearchRunner
    src = inspect.getsource(ResearchRunner.run)
    assert "report, artifact = build_facts" not in src, (
        "build_facts returns a single dict — do not unpack into (report, artifact)"
    )


def test_build_facts_function_signature_has_strict_completeness():
    """Confirm the canonical function signature for reference."""
    import inspect
    from scripts.build_facts import build_facts
    sig = inspect.signature(build_facts)
    assert "strict_completeness" in sig.parameters
    assert "strict" not in sig.parameters
