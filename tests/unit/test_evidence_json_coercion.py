"""Production LLM extractor returns a JSON object (response_format=json_object), but
build_evidence needs a list of claim dicts. _coerce_to_list bridges the two shapes."""
from __future__ import annotations

from backend.news.evidence_builder import _coerce_to_list


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
