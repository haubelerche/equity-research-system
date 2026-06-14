"""The two CFS financing line items must be registered so they survive ingestion."""
from __future__ import annotations

from backend.facts.metric_metadata import (
    SemanticType,
    get_semantic_type,
    is_known_metric,
    validate_and_normalize,
)

PROCEEDS = "proceeds_from_borrowings.total"
REPAYMENT = "repayment_of_borrowings.total"


def test_financing_line_items_are_known_metrics():
    assert is_known_metric(PROCEEDS)
    assert is_known_metric(REPAYMENT)


def test_financing_line_items_are_monetary():
    assert get_semantic_type(PROCEEDS) is SemanticType.MONETARY
    assert get_semantic_type(REPAYMENT) is SemanticType.MONETARY


def test_financing_line_items_normalize_billion_vnd():
    # 1.5 tỷ → 1_500_000_000 absolute VND (canonical monetary contract)
    norm = validate_and_normalize(PROCEEDS, 1.5, "tỷ")
    assert norm.status == "ok"
    assert norm.value == 1_500_000_000.0


def test_financing_line_items_reject_when_unit_missing():
    norm = validate_and_normalize(REPAYMENT, 1.5, None)
    assert norm.status == "reject"
