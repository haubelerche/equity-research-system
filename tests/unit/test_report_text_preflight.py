from __future__ import annotations

import pytest

from scripts.generate_report import _assert_report_text_clean, _has_text_corruption


def test_markdown_preflight_accepts_clean_vietnamese() -> None:
    text = "# Báo cáo kiểm toán chất lượng\n\nDữ liệu tài chính đã được kiểm định."
    assert not _has_text_corruption(text)
    _assert_report_text_clean(text)


def test_markdown_preflight_rejects_legacy_corruption_markers() -> None:
    text = "# B->o c->o Ph->n t->ch\n\nD? li?u canonical."
    assert _has_text_corruption(text)
    with pytest.raises(RuntimeError, match="Markdown report failed encoding preflight"):
        _assert_report_text_clean(text)
