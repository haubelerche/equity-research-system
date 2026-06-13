"""Regression tests for accounts_receivable taxonomy disambiguation.

vnstock VCI emits two distinct receivables rows that previously both mapped to
accounts_receivable.ending, colliding on one key:
  - "Phải thu khách hàng" / "Trade accounts receivable"  (trade,  615 bn)  ← correct
  - "Các khoản phải thu"   / "Accounts receivable"        (total,  684 bn)  ← must NOT match

accounts_receivable.ending feeds DSO and NWC, which require trade receivables.
"""
from __future__ import annotations

import pandas as pd

from scripts.connectors.vnstock_finance_connector import _build_alias_map, _resolve_label

AR_KEY = "accounts_receivable.ending"


def _row(primary: str, en: str, item_id: str) -> "pd.Series[str]":
    return pd.Series({"primary": primary, "en": en, "id": item_id})


def test_trade_receivables_row_resolves_to_accounts_receivable():
    alias = _build_alias_map(statement="balance_sheet")
    resolved = _resolve_label(
        _row("Phải thu khách hàng", "Trade accounts receivable", "trade_accounts_receivable"),
        alias,
    )
    assert resolved is not None
    assert resolved[0] == AR_KEY


def test_broad_total_receivables_row_does_not_resolve_to_accounts_receivable():
    alias = _build_alias_map(statement="balance_sheet")
    resolved = _resolve_label(
        _row("Các khoản phải thu", "Accounts receivable", "accounts_receivable"),
        alias,
    )
    # The broad total must not be mistaken for trade AR — either unmatched or a
    # different key, but never accounts_receivable.ending.
    assert resolved is None or resolved[0] != AR_KEY


def test_english_accounts_receivable_alias_removed():
    # The ambiguous English alias that grabbed the broad total must be gone.
    alias = _build_alias_map(statement="balance_sheet")
    mapped = alias.get("accounts_receivable")
    assert mapped is None or mapped[0] != AR_KEY
