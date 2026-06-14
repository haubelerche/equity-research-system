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


def test_real_vnstock_vci_labels_resolve():
    """Lock in the ACTUAL vnstock VCI cash-flow labels (live-validation regression).

    The proceeds line is "Tiền thu được các khoản đi vay" (item_en "Proceeds from
    loans", item_id "proceeds_from_loans") — NOT "Tiền thu từ đi vay". The first
    alias guess missed it, so proceeds was silently dropped at ingestion.
    """
    alias = _build_alias_map(statement="cash_flow")
    proceeds = _resolve_label(
        _row("Tiền thu được các khoản đi vay", "Proceeds from loans", "proceeds_from_loans"),
        alias,
    )
    assert proceeds is not None and proceeds[0] == PROCEEDS
    repayment = _resolve_label(
        _row("Tiền trả nợ gốc vay", "Repayment of loans", "repayment_of_loans"),
        alias,
    )
    assert repayment is not None and repayment[0] == REPAYMENT
