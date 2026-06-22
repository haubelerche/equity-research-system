from backend.retrieval_enhance import expand_query


def test_expand_query_adds_vi_en_synonyms():
    out = expand_query("doanh thu thuần năm 2022")
    joined = " ".join(out).lower()
    assert "doanh thu thuần năm 2022" in joined          # original kept first
    assert "net revenue" in joined or "revenue" in joined  # EN synonym added


def test_expand_query_idempotent_for_unknown_terms():
    out = expand_query("một câu hỏi không có thuật ngữ tài chính")
    assert out[0] == "một câu hỏi không có thuật ngữ tài chính"
