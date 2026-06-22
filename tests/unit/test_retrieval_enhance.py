from backend.retrieval_enhance import expand_query


def test_expand_query_adds_vi_en_synonyms():
    out = expand_query("doanh thu thuần năm 2022")
    joined = " ".join(out).lower()
    assert "doanh thu thuần năm 2022" in joined          # original kept first
    assert "net revenue" in joined or "revenue" in joined  # EN synonym added


def test_expand_query_idempotent_for_unknown_terms():
    out = expand_query("một câu hỏi không có thuật ngữ tài chính")
    assert out[0] == "một câu hỏi không có thuật ngữ tài chính"


from backend.retrieval_enhance import reciprocal_rank_fusion


def test_rrf_promotes_chunks_ranked_high_in_both_lists():
    vec = [{"chunk_id": "A"}, {"chunk_id": "B"}, {"chunk_id": "C"}]
    fts = [{"chunk_id": "B"}, {"chunk_id": "A"}, {"chunk_id": "D"}]
    fused = reciprocal_rank_fusion([vec, fts], k=60, key="chunk_id")
    ids = [c["chunk_id"] for c in fused]
    assert ids[0] in {"A", "B"} and ids[1] in {"A", "B"}
    assert set(ids) == {"A", "B", "C", "D"}
