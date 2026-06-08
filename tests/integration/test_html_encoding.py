"""Integration tests: Vietnamese text encoding in generated HTML reports.

Prerequisite: Run `scripts/render_report.py --ticker DHG --allow-latest-artifacts`
to generate the HTML report before running these tests.
"""
import pytest
from pathlib import Path

VIETNAMESE_MARKERS = [
    "Dược Hậu Giang",   # ư ậ
    "Công ty",           # ô
    "tài chính",         # à  (lowercase — appears in section body/titles)
    "Phân tích",         # â  (title-case — section header)
]
ROOT = Path(__file__).resolve().parents[2]


def _dhg_html():
    files = list((ROOT / "artifacts" / "reports_html").glob("DHG_*.html"))
    if not files:
        # Also try exact filename produced by the pipeline
        exact = ROOT / "artifacts" / "reports_html" / "DHG_report.html"
        if exact.exists():
            files = [exact]
    return files


@pytest.mark.integration
def test_html_has_no_mojibake():
    """Generated DHG HTML must pass the built-in Vietnamese encoding preflight."""
    from backend.reporting.html_renderer import preflight_rendered_html_text
    html_files = _dhg_html()
    if not html_files:
        pytest.skip("No DHG HTML report found — run render_report.py --ticker DHG first")
    html = html_files[-1].read_text(encoding="utf-8")
    preflight_rendered_html_text(html)


@pytest.mark.integration
def test_html_contains_vietnamese_text():
    """Generated DHG HTML must contain real Vietnamese diacritic characters."""
    html_files = _dhg_html()
    if not html_files:
        pytest.skip("No DHG HTML report found — run render_report.py --ticker DHG first")
    html = html_files[-1].read_text(encoding="utf-8")
    found = [m for m in VIETNAMESE_MARKERS if m in html]
    assert len(found) >= 3, (
        f"Only {len(found)}/{len(VIETNAMESE_MARKERS)} Vietnamese markers found: {found}. "
        "Expected at least 3 of: " + str(VIETNAMESE_MARKERS)
    )
