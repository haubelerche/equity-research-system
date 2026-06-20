from __future__ import annotations

from backend.evaluation.runtime_evaluators import (
    _concept_tier,
    _score_from_concept_tiers,
    _report_quality_subscores,
)


def test_concept_tier_absent():
    assert _concept_tier("báo cáo không nhắc khái niệm này", ("roe",)) == 0.0


def test_concept_tier_mentioned_without_number():
    assert _concept_tier("doanh nghiệp có ROE ổn định qua các năm", ("roe",)) == 0.5


def test_concept_tier_quantified_with_number():
    assert _concept_tier("ROE đạt 18,2% trong 2025", ("roe",)) == 1.0


def test_concept_tier_quantified_uses_nearest_mention():
    text = "biên lợi nhuận gộp 42% năm 2025"
    assert _concept_tier(text, ("gross margin", "biên lợi nhuận gộp")) == 1.0


def test_score_from_concept_tiers_averages_groups():
    text = "ROE 18% và doanh thu tăng"  # roe quantified (1.0), revenue quantified (1.0) - number is within window on both sides
    score = _score_from_concept_tiers(text, (("roe",), ("doanh thu", "revenue")))
    assert score == 100.0


def test_score_from_concept_tiers_mixed_tiers_below_100():
    # Re-saturation canary: one concept quantified (roe near 18%), one only mentioned
    # (thương hiệu has no number within the window) -> average must be below 100.
    text = "ROE đạt 18%. Chiến lược dài hạn của doanh nghiệp tập trung vào thương hiệu."
    score = _score_from_concept_tiers(text, (("roe",), ("thương hiệu",)))
    assert score == 75.0


def test_score_from_concept_tiers_empty_groups_returns_none():
    assert _score_from_concept_tiers("anything", ()) is None


def test_concept_tier_quantified_when_number_precedes_mention():
    # number BEFORE the concept term must also count as quantified (both-sides window)
    assert _concept_tier("đạt 18,2% ROE trong năm", ("roe",)) == 1.0


def _rich_report_text() -> str:
    return (
        "Luận điểm đầu tư: khuyến nghị MUA, giá mục tiêu 120.000đ. "
        "Doanh thu 2025 đạt 5.200 tỷ (+12%), biên lợi nhuận gộp 42%, biên EBIT 18%, "
        "biên lợi nhuận ròng 15%, ROE 22%, OCF 800 tỷ, EPS 6.500đ, capex 300 tỷ, "
        "vốn lưu động 1.100 tỷ, cổ tức 2.000đ. "
        "Dự phóng: tăng trưởng doanh thu 12%, gross margin 42%, khấu hao 4% doanh thu, "
        "nợ vay 500 tỷ, thuế suất 20%. "
        "Định giá FCFF/FCFE, WACC 12,5%, terminal growth 3%, giá trị doanh nghiệp 9.000 tỷ, "
        "nợ ròng 200 tỷ, giá trị vốn chủ sở hữu 8.800 tỷ, số cổ phiếu 130 triệu. "
        "Độ nhạy theo WACC và terminal growth, ô base 120.000đ, ma trận grid. "
        "Rủi ro và cảnh báo monitoring, catalyst, xác suất 60%, thời gian 12 tháng. "
        "Nguồn [1] [2], công thức formula trace, đối chiếu reconciliation. "
        "Nhóm so sánh peers ngành dược, P/E 15x, EV/EBITDA 9x. "
        "Phụ lục: bảng chỉ tiêu, giá trị, thành phần."
    )


def _thin_report_text() -> str:
    return (
        "Báo cáo về công ty. Khuyến nghị mua. Doanh thu tăng trưởng tốt. "
        "Định giá hợp lý. Có một số rủi ro cần theo dõi. Nguồn nội bộ."
    )


def test_rich_report_scores_high_but_not_flat_100():
    scores = _report_quality_subscores({"exists": True, "text": _rich_report_text()}, {})
    dims = [v for k, v in scores.items() if isinstance(v, (int, float))]
    assert dims, "expected numeric dimension scores"
    assert max(dims) <= 100.0
    assert sum(v >= 70 for v in dims) >= len(dims) // 2


def test_thin_report_scores_materially_lower_than_rich():
    rich = _report_quality_subscores({"exists": True, "text": _rich_report_text()}, {})
    thin = _report_quality_subscores({"exists": True, "text": _thin_report_text()}, {})
    assert thin["financial_analysis_depth"] < rich["financial_analysis_depth"]
    assert thin["valuation_transparency"] < rich["valuation_transparency"]
    assert thin["thesis_specificity"] < rich["thesis_specificity"]


def test_missing_report_returns_all_none():
    scores = _report_quality_subscores({"exists": False, "text": ""}, {})
    assert all(value is None for value in scores.values())


def test_dimensions_are_independent_not_identical():
    scores = _report_quality_subscores({"exists": True, "text": _rich_report_text()}, {})
    distinct = {
        scores["thesis_specificity"],
        scores["forecast_rationale"],
        scores["risk_catalyst_quality"],
        scores["financial_analysis_depth"],
    }
    assert len(distinct) >= 2


import inspect
from backend.evaluation import runtime_evaluators


def test_evaluate_report_wiring_uses_graded_for_display_and_structured_for_gate():
    """Guard the decoupling: display scores from graded heuristic, blocking from structured."""
    source = inspect.getsource(runtime_evaluators.evaluate_report)
    assert "display_scores" in source
    assert "_report_quality_total(display_scores)" in source
    assert "structured_total_score >= 85" in source
