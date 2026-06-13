from decimal import Decimal
from pathlib import Path

from backend.dataops.official_fact_verifier import load_metric_patterns, verify_fact_in_chunk


PATTERNS = load_metric_patterns(Path("config/financial_metric_dictionary.yaml"))


def _fact() -> dict:
    return {"metric": "revenue.net", "value": Decimal("4676857"), "unit": "vnd_bn"}


def test_verifies_label_and_exact_value_in_same_window() -> None:
    chunk = {
        "source_doc_id": "official",
        "source_tier": 1,
        "chunk_index": 4,
        "chunk_text": "Doanh thu thuan\n4.676.857",
    }
    result = verify_fact_in_chunk(_fact(), chunk, PATTERNS)
    assert result is not None
    assert result.page_number == 5


def test_rejects_value_without_metric_label() -> None:
    chunk = {
        "source_doc_id": "official",
        "source_tier": 1,
        "chunk_index": 4,
        "chunk_text": "Tong tai san\n4.676.857",
    }
    assert verify_fact_in_chunk(_fact(), chunk, PATTERNS) is None


def test_rejects_label_with_different_value() -> None:
    chunk = {
        "source_doc_id": "official",
        "source_tier": 1,
        "chunk_index": 4,
        "chunk_text": "Doanh thu thuan\n4.000.000",
    }
    assert verify_fact_in_chunk(_fact(), chunk, PATTERNS) is None
