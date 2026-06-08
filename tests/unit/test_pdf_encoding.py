"""Verify that render_report --pdf produces a real PDF file, not a stub."""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_pdf_renderer_produces_file_not_stub(tmp_path):
    """render_report --pdf must produce a real .pdf file, not a .pdf-pending stub."""
    result = subprocess.run(
        [sys.executable, "scripts/render_report.py", "--ticker", "DHG", "--pdf",
         "--allow-latest-artifacts", "--mode", "internal_debug"],
        cwd=str(ROOT),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    output = (result.stdout or "") + (result.stderr or "")
    # Must not fall back to stub
    assert ".pdf-pending" not in output, f"PDF render fell back to stub:\n{output}"
    # Extract the saved PDF path from output (e.g. "[pdf] saved (chrome): artifacts/...")
    pdf_match = re.search(r'\[pdf\]\s+(?:saved \([^)]+\)|path)\s*:?\s*(.+\.pdf)', output)
    assert pdf_match, f"No PDF save line found in output:\n{output}"
    pdf_file = Path(pdf_match.group(1).strip())
    if not pdf_file.is_absolute():
        pdf_file = ROOT / pdf_file
    assert pdf_file.exists(), f"PDF file not found on disk: {pdf_file}"
    assert pdf_file.stat().st_size > 10_000, (
        f"PDF is suspiciously small ({pdf_file.stat().st_size} bytes) — likely a stub"
    )
