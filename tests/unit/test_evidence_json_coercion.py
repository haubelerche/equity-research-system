"""Production LLM extractor returns a JSON object (response_format=json_object), but
build_evidence needs a list of claim dicts. _coerce_to_list bridges the two shapes."""
from __future__ import annotations

import sys
from types import SimpleNamespace

from backend.news.evidence_builder import (
    _DEFAULT_LLM_MAX_RETRIES,
    _DEFAULT_LLM_TIMEOUT_SECONDS,
    _coerce_to_list,
    default_llm_extract,
)


def test_passes_through_a_bare_list() -> None:
    assert _coerce_to_list([{"claim": "a"}]) == [{"claim": "a"}]


def test_unwraps_first_list_value_in_an_object() -> None:
    data = {"facts": [{"claim": "a"}, {"claim": "b"}]}
    assert _coerce_to_list(data) == [{"claim": "a"}, {"claim": "b"}]


def test_returns_empty_for_object_without_a_list() -> None:
    assert _coerce_to_list({"note": "no claims"}) == []


def test_returns_empty_for_garbage() -> None:
    assert _coerce_to_list(None) == []
    assert _coerce_to_list("text") == []


def test_default_llm_extract_bounds_provider_wait(monkeypatch) -> None:
    client_kwargs: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"facts": []}'))]
            )

    def fake_openai(**kwargs):
        client_kwargs.update(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=fake_openai))

    assert default_llm_extract("article") == []
    assert client_kwargs == {
        "timeout": _DEFAULT_LLM_TIMEOUT_SECONDS,
        "max_retries": _DEFAULT_LLM_MAX_RETRIES,
    }
