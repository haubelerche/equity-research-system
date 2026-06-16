"""Offline-safe tests for the live RAGAS runner.

These never hit the network: they exercise the honest-failure branches and the
contracts the caller relies on. The real model-backed path is verified manually
against the live DB + OpenAI (see retrieval_eval.json).
"""
from __future__ import annotations

from backend.evaluation.ragas_live import (
    _build_generation_messages,
    _build_live_samples,
    _default_generate,
    _select_context_chunks,
    run_live_ragas,
)


class _Chunk:
    def __init__(
        self,
        text: str,
        *,
        fiscal_year: int | None = None,
        reliability_tier: int = 1,
        extraction_method: str = "pdf_text",
        section_title: str = "",
    ) -> None:
        self.chunk_text = text
        self.fiscal_year = fiscal_year
        self.reliability_tier = reliability_tier
        self.extraction_method = extraction_method
        self.section_title = section_title


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


def test_live_sample_builder_uses_answer_reference_and_metadata_fiscal_year(monkeypatch):
    monkeypatch.setenv("RAGAS_RETRIEVAL_CANDIDATE_K", "3")
    calls = []

    def retrieve(ticker, query, fiscal_year=None, top_k=5):
        calls.append({
            "ticker": ticker,
            "query": query,
            "fiscal_year": fiscal_year,
            "top_k": top_k,
        })
        return [_Chunk("audited context")]

    rows = _build_live_samples(
        [{
            "id": "dhg_revenue_2024",
            "question": "DHG doanh thu 2024?",
            "answer": "DHG doanh thu 2024 la 4.884 ty dong.",
            "ground_truth": "4.884 ty dong",
            "metadata": {"ticker": "DHG", "fiscal_year": 2024},
        }],
        "DHG",
        retrieve,
        lambda question, contexts, model: f"answer from {contexts[0]}",
        "test-model",
        3,
    )

    assert calls == [{
        "ticker": "DHG",
        "query": "DHG doanh thu 2024?",
        "fiscal_year": 2024,
        "top_k": 3,
    }]
    assert rows[0]["reference"] == "DHG doanh thu 2024 la 4.884 ty dong."
    assert rows[0]["fiscal_year"] == 2024
    assert rows[0]["retrieved_contexts"] == ["audited context"]


def test_live_sample_builder_reranks_candidates_without_using_reference(monkeypatch):
    monkeypatch.setenv("RAGAS_RETRIEVAL_CANDIDATE_K", "3")

    def retrieve(ticker, query, fiscal_year=None, top_k=5):
        assert top_k == 3
        return [
            _Chunk("DHG 2022 trang bìa báo cáo thường niên.", fiscal_year=2022, reliability_tier=1),
            _Chunk("DHG 2022 chiến lược phát triển trung hạn.", fiscal_year=2022, reliability_tier=1),
            _Chunk(
                "DHG Lợi nhuận gộp năm 2022 là 2,257.4949 tỷ VND.",
                fiscal_year=2022,
                reliability_tier=3,
                extraction_method="synthetic_facts",
            ),
        ]

    rows = _build_live_samples(
        [{
            "id": "dhg_gross_profit_2022",
            "question": "DHG lợi nhuận gộp năm 2022 là bao nhiêu?",
            "answer": "This reference must not be needed for context selection.",
            "metadata": {"ticker": "DHG", "fiscal_year": 2022},
        }],
        "DHG",
        retrieve,
        lambda question, contexts, model: contexts[0],
        "test-model",
        1,
    )

    assert rows[0]["retrieved_candidate_count"] == 3
    assert rows[0]["retrieved_contexts"] == [
        "DHG Lợi nhuận gộp năm 2022 là 2,257.4949 tỷ VND."
    ]


def test_context_reranker_prefers_question_specific_financial_fact():
    chunks = [
        _Chunk("DHG 2022 có doanh thu thuần 4.676 tỷ đồng.", fiscal_year=2022),
        _Chunk(
            "DHG Chi đầu tư TSCĐ (CAPEX) năm 2022: -233.9916 tỷ VND.",
            fiscal_year=2022,
            reliability_tier=3,
            extraction_method="synthetic_facts",
        ),
    ]

    selected = _select_context_chunks(
        chunks,
        "DHG CAPEX / chi mua sắm tài sản cố định năm 2022 là bao nhiêu?",
        2022,
        1,
    )

    assert selected == [chunks[1]]


def test_default_generate_extracts_exact_fact_from_context_without_llm(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    answer = _default_generate(
        "DHG lợi nhuận gộp năm 2022 là bao nhiêu?",
        [
            "DHG Lợi nhuận gộp năm 2022\n\n"
            "Lợi nhuận gộp của DHG năm 2022: 2,257.4949 tỷ VND (VND)."
        ],
        "unused-model",
    )

    assert answer == (
        "Câu hỏi: DHG lợi nhuận gộp năm 2022 là bao nhiêu? "
        "Trả lời: DHG lợi nhuận gộp năm 2022 là 2257.4949 tỷ VND."
    )


def test_generation_prompt_preserves_financial_number_unit_and_year():
    messages = _build_generation_messages(
        "DHG doanh thu thuần năm 2024 là bao nhiêu?",
        ["DHG 2024 income_statement: revenue.net = 4884.123 vnd_bn."],
    )
    system = messages[0]["content"]
    user = messages[1]["content"]

    assert "đúng số liệu" in system
    assert "đúng năm" in system
    assert "đúng đơn vị" in system
    assert "không làm tròn" in system
    assert "4884.123 vnd_bn" in user
