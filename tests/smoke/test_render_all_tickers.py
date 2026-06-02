"""Smoke tests: all 5 MVP tickers produce valid HTML reports with numbers present.

Prerequisite: Run the pipeline for all tickers first:
    python scripts/run_valuation.py --ticker DHG  (and IMP, DMC, TRA, DBD)
    python scripts/render_report.py --ticker DHG --allow-latest-artifacts  (and others)

Then run: pytest tests/smoke/ -v
"""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TICKERS = ["DHG", "IMP", "DMC", "TRA", "DBD"]


def _html_file(ticker: str) -> Path | None:
    """Return the most recent HTML report for a ticker, or None."""
    # Try exact filename first (as produced by render_report.py)
    exact = ROOT / "artifacts" / "reports_html" / f"{ticker}_report.html"
    if exact.exists():
        return exact
    # Fall back to glob for run-id prefixed files
    reports_dir = ROOT / "artifacts" / "reports_html"
    if not reports_dir.exists():
        return None
    files = sorted(reports_dir.glob(f"*{ticker}*.html"))
    return files[-1] if files else None


@pytest.mark.parametrize("ticker", TICKERS)
def test_render_produces_html(ticker):
    """render_report.py must exit 0 and produce an HTML file for each ticker."""
    result = subprocess.run(
        [sys.executable, "scripts/render_report.py", "--ticker", ticker,
         "--allow-latest-artifacts"],
        cwd=str(ROOT),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=90,
    )
    assert result.returncode == 0, (
        f"render_report failed for {ticker} (exit {result.returncode}):\n"
        f"STDOUT: {result.stdout[:500]}\nSTDERR: {result.stderr[:500]}"
    )
    html = _html_file(ticker)
    assert html is not None and html.exists(), (
        f"No HTML output file found for {ticker} in artifacts/reports_html/"
    )
    assert html.stat().st_size > 5_000, (
        f"{ticker} HTML is only {html.stat().st_size} bytes — suspiciously small"
    )


@pytest.mark.parametrize("ticker", TICKERS)
def test_html_has_formatted_numbers(ticker):
    """Generated HTML must contain formatted numbers (e.g. 94,400 not 0)."""
    html = _html_file(ticker)
    if not html:
        pytest.skip(f"No HTML for {ticker} — run render_report.py first")
    content = html.read_text(encoding="utf-8")
    # Numbers with thousands separators: 94,400 / 5,265 / 135.12 etc.
    nums = re.findall(r'\b\d{1,3}(?:,\d{3})+\b', content)
    assert len(nums) >= 5, (
        f"{ticker}: only {len(nums)} formatted numbers found — "
        "numbers may be all zeros or dashes. "
        "Check that valuation artifacts exist and run_valuation.py completed successfully."
    )


@pytest.mark.parametrize("ticker", TICKERS)
def test_html_has_no_mojibake(ticker):
    """Generated HTML must pass Vietnamese encoding preflight — no replacement chars."""
    from backend.reporting.html_renderer import preflight_rendered_html_text
    html = _html_file(ticker)
    if not html:
        pytest.skip(f"No HTML for {ticker} — run render_report.py first")
    content = html.read_text(encoding="utf-8")
    preflight_rendered_html_text(content)


@pytest.mark.parametrize("ticker", TICKERS)
def test_html_contains_ticker_name(ticker):
    """Generated HTML must mention the ticker symbol."""
    html = _html_file(ticker)
    if not html:
        pytest.skip(f"No HTML for {ticker} — run render_report.py first")
    content = html.read_text(encoding="utf-8")
    assert ticker in content, f"Ticker symbol '{ticker}' not found in generated HTML"
