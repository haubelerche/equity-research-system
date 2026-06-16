"""AGM (ĐHCĐ) file resolver — parse messy filenames + group multi-part docs.

Pure functions: no filesystem in these tests. parse_agm_filename reads one name;
group_agm_files orders multi-part files per ticker.
"""
from __future__ import annotations

from pathlib import Path

from backend.documents import agm_source as src


def test_parse_simple_filename():
    assert src.parse_agm_filename("AGP DHCD 2026.pdf") == ("AGP", 2026, 0)


def test_parse_lowercase_ticker_and_doctype_uppercased():
    assert src.parse_agm_filename("dtp dhcd 2026.pdf") == ("DTP", 2026, 0)


def test_parse_part_suffix():
    assert src.parse_agm_filename("DHG DHCD 2026(1).pdf") == ("DHG", 2026, 1)
    assert src.parse_agm_filename("DHG DHCD 2026(2).pdf") == ("DHG", 2026, 2)


def test_parse_space_before_paren():
    assert src.parse_agm_filename("CDP DHCD 2026 (1).pdf") == ("CDP", 2026, 1)


def test_parse_hdcd_typo_doctype():
    assert src.parse_agm_filename("NDC HDCD 2026(1).pdf") == ("NDC", 2026, 1)


def test_parse_non_agm_filename_returns_none():
    assert src.parse_agm_filename("README.txt") is None
    assert src.parse_agm_filename("DHG annual report 2025.pdf") is None


def test_group_orders_multipart_by_part():
    paths = [
        Path("DHG DHCD 2026(2).pdf"),
        Path("DHG DHCD 2026(1).pdf"),
    ]
    grouped = src.group_agm_files(paths)
    assert [p.name for p in grouped["DHG"]] == [
        "DHG DHCD 2026(1).pdf",
        "DHG DHCD 2026(2).pdf",
    ]


def test_group_base_file_orders_before_numbered_part():
    # DP2 has an unnumbered base and a (2) part — base (part 0) comes first.
    paths = [
        Path("DP2 DHCD 2026(2).pdf"),
        Path("DP2 DHCD 2026.pdf"),
    ]
    grouped = src.group_agm_files(paths)
    assert [p.name for p in grouped["DP2"]] == [
        "DP2 DHCD 2026.pdf",
        "DP2 DHCD 2026(2).pdf",
    ]


def test_group_ignores_non_agm_files():
    grouped = src.group_agm_files([Path("notes.md"), Path("AGP DHCD 2026.pdf")])
    assert set(grouped) == {"AGP"}
