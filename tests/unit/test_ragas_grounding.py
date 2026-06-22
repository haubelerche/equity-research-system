from backend.evaluation.ragas_live import _build_generation_messages


def test_generation_prompt_enforces_grounding_and_refusal():
    msgs = _build_generation_messages("DHG doanh thu 2022?", ["Doanh thu 2022: 4676 tỷ"])
    system = " ".join(m["content"] for m in msgs if m.get("role") == "system").lower()
    assert "chỉ" in system and ("bằng chứng" in system or "ngữ cảnh" in system)
    assert "không" in system  # refusal / no-fabrication instruction present


def test_generation_prompt_refusal_text_when_no_context():
    msgs = _build_generation_messages("câu hỏi", [])
    joined = " ".join(m["content"] for m in msgs).lower()
    assert "không có" in joined
