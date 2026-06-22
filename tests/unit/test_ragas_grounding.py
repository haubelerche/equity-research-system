from backend.evaluation.ragas_live import (
    _build_generation_messages,
    _extract_grounded_fact_answer,
)


def test_extract_is_metric_aware_not_first_number():
    # multi-metric tier-3 summary: accounts_payable appears BEFORE revenue.
    ctx = [
        "## Tóm tắt tài chính IMP năm 2022 (FY)\n"
        "- Phải trả người bán: 80.8 tỷ VND (VND)\n"
        "- Doanh thu thuần (Báo cáo KQKD): 1234.5 tỷ VND (VND)\n"
        "- CAPEX: -26.9 tỷ VND (VND)"
    ]
    ans = _extract_grounded_fact_answer("IMP doanh thu thuần năm 2022 là bao nhiêu?", ctx)
    assert ans is not None
    assert "1234.5" in ans and "80.8" not in ans  # picked the revenue line, not the first number


def test_extract_returns_none_when_metric_line_absent():
    # revenue asked but only accounts_payable present -> must NOT fabricate from the wrong line.
    ctx = ["## Tóm tắt IMP 2022\n- Phải trả người bán: 80.8 tỷ VND (VND)"]
    ans = _extract_grounded_fact_answer("IMP doanh thu thuần năm 2022 là bao nhiêu?", ctx)
    assert ans is None


def test_generation_prompt_enforces_grounding_and_refusal():
    msgs = _build_generation_messages("DHG doanh thu 2022?", ["Doanh thu 2022: 4676 tỷ"])
    system = " ".join(m["content"] for m in msgs if m.get("role") == "system").lower()
    assert "chỉ" in system and ("bằng chứng" in system or "ngữ cảnh" in system)
    assert "không" in system  # refusal / no-fabrication instruction present


def test_generation_prompt_refusal_text_when_no_context():
    msgs = _build_generation_messages("câu hỏi", [])
    joined = " ".join(m["content"] for m in msgs).lower()
    assert "không có" in joined
