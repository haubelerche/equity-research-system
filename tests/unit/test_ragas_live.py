"""Offline-safe tests for the live RAGAS runner.

These never hit the network: they exercise the honest-failure branches and the
contracts the caller relies on. The real model-backed path is verified manually
against the live DB + OpenAI (see retrieval_eval.json).
"""
from __future__ import annotations

from backend.evaluation.ragas_live import run_live_ragas


def _noop_retrieve(ticker, query, fiscal_year=None, top_k=5):
    return []


def test_empty_samples_not_executed():
    out = run_live_ragas([], "DBD", _noop_retrieve)
    assert out["execution_status"] == "not_executed"
    assert out["scores"] == {}


def test_missing_openai_key_is_honest_framework_unavailable(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = run_live_ragas(
        [{"id": "s1", "question": "q?", "expected_answer": "a"}],
        "DBD", _noop_retrieve,
    )
    # No key -> we do NOT fabricate scores; we report why.
    assert out["execution_status"] == "framework_unavailable"
    assert out["reason"] == "openai_api_key_missing"
    assert out["scores"] == {}
