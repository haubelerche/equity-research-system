from __future__ import annotations

from backend.evaluation.runtime_evaluators import (
    _concept_tier,
    _score_from_concept_tiers,
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


def test_score_from_concept_tiers_empty_groups_returns_none():
    assert _score_from_concept_tiers("anything", ()) is None


def test_concept_tier_quantified_when_number_precedes_mention():
    # number BEFORE the concept term must also count as quantified (both-sides window)
    assert _concept_tier("đạt 18,2% ROE trong năm", ("roe",)) == 1.0
