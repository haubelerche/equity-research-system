"""vnstock CFS financing rows must resolve to the new canonical codes."""
from __future__ import annotations

import pandas as pd

from scripts.connectors.vnstock_finance_connector import _build_alias_map, _resolve_label

PROCEEDS = "proceeds_from_borrowings.total"
REPAYMENT = "repayment_of_borrowings.total"


def _row(primary: str, en: str, item_id: str) -> "pd.Series[str]":
    return pd.Series({"primary": primary, "en": en, "id": item_id})


def test_proceeds_from_borrowings_resolves():
    alias = _build_alias_map(statement="cash_flow")
    resolved = _resolve_label(
        _row("Tiền thu từ đi vay", "Proceeds from borrowings", "proceeds_from_borrowings"),
        alias,
    )
    assert resolved is not None
    assert resolved[0] == PROCEEDS


def test_repayment_of_borrowings_resolves():
    alias = _build_alias_map(statement="cash_flow")
    resolved = _resolve_label(
        _row("Tiền trả nợ gốc vay", "Repayment of borrowings", "repayment_of_borrowings"),
        alias,
    )
    assert resolved is not None
    assert resolved[0] == REPAYMENT
