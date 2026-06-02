"""Verify Vietnamese text survives the HTML -> PDF pipeline without mojibake."""
import subprocess
import sys
from pathlib import Path

VIETNAMESE_MARKERS = [
    "Dược Hậu Giang",   # u ậ
    "Công ty",           # ô
    "Tài chính",         # à
    "phân tích",         # â
]
ROOT = Path(__file__).resolve().parents[2]


def test_pdf_renderer_produces_file_not_stub(tmp_path):
    """render_report --pdf must produce a real .pdf, not a .pdf-pending stub."""
    result = subprocess.run(
        [sys.executable, "scripts/render_report.py", "--ticker", "DHG", "--pdf",
         "--allow-latest-artifacts"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    output = (result.stdout or "") + (result.stderr or "")
    # Should not fall back to stub
    assert ".pdf-pending" not in output, f"PDF render fell back to stub:\n{output}"
    # Should report a saved path
    assert ".pdf" in output, f"No PDF path in output:\n{output}"


def test_html_has_no_mojibake():
    """The generated HTML must pass the built-in preflight check."""
    from backend.reporting.html_renderer import preflight_rendered_html_text
    html_files = list((ROOT / "artifacts" / "reports_html").glob("DHG_*.html"))
    assert html_files, "No DHG HTML report found — run Task 2 first"
    html = html_files[-1].read_text(encoding="utf-8")
    preflight_rendered_html_text(html)  # raises HTMLPreflightError if broken


def test_html_contains_vietnamese_text():
    """The generated HTML must contain real Vietnamese characters."""
    html_files = list((ROOT / "artifacts" / "reports_html").glob("DHG_*.html"))
    assert html_files, "No DHG HTML report found — run Task 2 first"
    html = html_files[-1].read_text(encoding="utf-8")
    found = [m for m in VIETNAMESE_MARKERS if m in html]
    assert len(found) >= 2, (
        f"Only {len(found)}/{len(VIETNAMESE_MARKERS)} Vietnamese markers found: {found}"
    )
