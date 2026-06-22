from __future__ import annotations

from backend.evaluation import runtime_evaluators as rt


def _retriever(chunks):
    def retrieve(*, ticker, query, fiscal_year, top_k):
        return chunks
    return retrieve


def _run(tmp_path, query, chunks, monkeypatch):
    import yaml
    gdir = tmp_path / "config" / "benchmarks" / "02_ragas_retrieval" / "golden_queries"
    gdir.mkdir(parents=True)
    (gdir / "TST.yaml").write_text(yaml.safe_dump(
        {"version": "t", "ticker": "TST", "queries": [query]}, allow_unicode=True),
        encoding="utf-8")
    monkeypatch.setattr(rt, "RETRIEVE_CALLABLE_OVERRIDE", _retriever(chunks))
    return rt._run_local_retrieval_benchmark(tmp_path, "TST", gdir / "TST.yaml")


def test_value_match_counts_as_hit_when_id_differs(tmp_path, monkeypatch):
    query = {"id": "rev", "query": "doanh thu 2022", "fiscal_year": 2022, "material": True,
             "expected_chunk_ids": ["GOLDEN_ID_NOT_IN_DB"], "expected_terms": ["doanh thu"],
             "expected_value": 4676.016, "expected_unit": "vnd_bn"}
    chunks = [{"chunk_id": "live_db_999", "fiscal_year": 2022, "reliability_tier": 1,
               "text": "Doanh thu thuần năm 2022 đạt 4.676 tỷ đồng"}]
    scores = _run(tmp_path, query, chunks, monkeypatch)
    assert scores["hit_rate_at_5"] == 1.0


def test_value_match_isolated_from_term_and_year(tmp_path, monkeypatch):
    # Chunk holds ONLY the value (no expected term, no year) — relevance can come
    # solely from value-matching. Without _chunk_contains_expected_value this is a miss.
    query = {"id": "rev", "query": "doanh thu 2022", "fiscal_year": 2022, "material": True,
             "expected_chunk_ids": ["GOLDEN_ID_NOT_IN_DB"], "expected_terms": ["doanh thu"],
             "expected_value": 4676.016, "expected_unit": "vnd_bn"}
    chunks = [{"chunk_id": "canonical_fact_42", "fiscal_year": None, "reliability_tier": 3,
               "text": "revenue.net 4.676"}]
    scores = _run(tmp_path, query, chunks, monkeypatch)
    assert scores["hit_rate_at_5"] == 1.0


def test_no_value_no_term_is_a_miss(tmp_path, monkeypatch):
    query = {"id": "rev", "query": "doanh thu 2022", "fiscal_year": 2022, "material": True,
             "expected_chunk_ids": ["GOLDEN_ID"], "expected_terms": ["doanh thu"],
             "expected_value": 4676.016, "expected_unit": "vnd_bn"}
    chunks = [{"chunk_id": "x", "fiscal_year": 2022, "reliability_tier": 1,
               "text": "Một đoạn không liên quan về quản trị công ty"}]
    scores = _run(tmp_path, query, chunks, monkeypatch)
    assert scores["hit_rate_at_5"] == 0.0
