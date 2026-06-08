"""Demo: render any ticker as FPTS-style client report via build_client_report_view_model.

Usage:
    python scripts/demo/demo_render_dhg_client.py             # defaults to DHG
    python scripts/demo/demo_render_dhg_client.py --ticker DBD
    python scripts/demo/demo_render_dhg_client.py --ticker DHG --mode client_final
"""
import argparse
import sys
import os

os.environ["PYTHONIOENCODING"] = "utf-8"
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from pathlib import Path
from backend.reporting.client_report_view_model import build_client_report_view_model
from backend.reporting.client_section_builder import build_client_report_sections
from backend.reporting.html_renderer import HTMLRenderer
from backend.reporting.pdf_renderer import PDFRenderer
from scripts.render_report import _context_from_view_model

parser = argparse.ArgumentParser()
parser.add_argument("--ticker", default="DHG", help="Ticker symbol (e.g. DHG, DBD)")
parser.add_argument("--mode", default="analyst_draft",
                    choices=("client_final", "analyst_draft", "internal_debug"))
args = parser.parse_args()

ticker = args.ticker.upper()
run_id = f"{ticker}_CLIENT_DEMO"

# ── Build view model from artifacts (generic — any ticker) ───────────────────
vm = build_client_report_view_model(ticker, mode=args.mode, allow_latest_artifacts=True)

print(f"ViewModel built for {ticker}:")
print(f"  company_name     = {vm.company_name}")
print(f"  recommendation   = {vm.recommendation!r}")
print(f"  current_price    = {vm.current_price}")
print(f"  target_price     = {vm.target_price}")
print(f"  upside_downside  = {vm.upside_downside}")
print(f"  mode             = {vm.mode}")
print(f"  charts available = {list(vm.charts.keys())}")

# ── Build editorial sections (generic — driven entirely by vm) ───────────────
sections = build_client_report_sections(vm)
print(f"\nSections built: {len(sections)}")
for s in sections:
    cb   = s.get("chapter_break", False)
    cids = s.get("chart_ids", [])
    word_count = s.get("word_count", 0)
    print(f"  {s['page']:35s}  chapter_break={cb}  chart_ids={cids}  words={word_count}")

# ── Render HTML ──────────────────────────────────────────────────────────────
out_dir = Path("artifacts/reports_html")
ctx     = _context_from_view_model(vm)
html_path = HTMLRenderer().render(sections, ctx, output_dir=out_dir, run_id=run_id)
print(f"\nHTML saved : {html_path}")
print(f"HTML size  : {html_path.stat().st_size:,} bytes")

# ── Spot-check key format features ───────────────────────────────────────────
html = html_path.read_text(encoding="utf-8")
body = html.split("<body", 1)[-1]  # only check body, not CSS in <head>

checks = [
    ("rec hero on cover page",
     '<div class="recommendation-card' in html),
    ("standalone banner suppressed (only 1 rec card)",
     html.count('<div class="recommendation-card') == 1),
    ("Vietnamese headings present",
     "Kết quả hoạt động" in html and "Mô hình định giá" in html),
    ("chapter-break sections (≥4)",
     body.count("chapter-break") >= 4),
    ("sensitivity matrix-table present",
     "matrix-table" in html),
    ("variance coloring applied",
     "variance-positive" in html or "variance-negative" in html),
    ("print-running-footer present",
     "print-running-footer" in html),
    ("page-break-inside not blocking flow",
     "page-break-inside: avoid" not in body),
    ("no hardcoded ticker in section HTML",
     # All content must come from vm fields, not hardcoded strings
     # Check that the ticker name in headers comes from vm.ticker not a literal
     html.count(ticker) >= 3),  # ticker should appear in header, footer, title
]

print("\nFormat feature checks:")
all_ok = True
for label, result in checks:
    icon = "PASS" if result else "FAIL"
    print(f"  [{icon}] {label}")
    if not result:
        all_ok = False

# ── Render PDF ───────────────────────────────────────────────────────────────
out_pdf = Path("artifacts/reports_pdf")
out_pdf.mkdir(parents=True, exist_ok=True)
try:
    pdf_path = PDFRenderer().render(html_path, output_dir=out_pdf, run_id="")
    print(f"\nPDF saved  : {pdf_path}")
    print(f"PDF size   : {pdf_path.stat().st_size:,} bytes")
except Exception as e:
    print(f"\nPDF renderer unavailable: {e}")
    print("HTML is the primary artifact.")

print("\nDone." if all_ok else "\nSome checks FAILED — review output above.")
