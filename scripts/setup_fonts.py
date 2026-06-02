"""Provision Unicode fonts for PDF Vietnamese rendering.

Run once to set up assets/fonts/NotoSans-Regular.ttf from Windows system fonts.
This font is required by the xhtml2pdf PDF backend for correct Vietnamese output.

Usage:
    python scripts/setup_fonts.py
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
fonts_dir = ROOT / "assets" / "fonts"
fonts_dir.mkdir(parents=True, exist_ok=True)

# Windows fonts with Unicode/Vietnamese coverage (in preference order)
CANDIDATES = [
    Path(r"C:\Windows\Fonts\segoeui.ttf"),    # Segoe UI — best Unicode coverage on Win11
    Path(r"C:\Windows\Fonts\arial.ttf"),       # Arial — broad Unicode
    Path(r"C:\Windows\Fonts\tahoma.ttf"),      # Tahoma
]

target = fonts_dir / "NotoSans-Regular.ttf"
if target.exists():
    print(f"Font already present: {target}")
else:
    for src in CANDIDATES:
        if src.exists():
            shutil.copy(src, target)
            print(f"Copied {src} -> {target}")
            break
    else:
        print("WARNING: No Unicode font found automatically.")
        print(f"Place NotoSans-Regular.ttf at: {target}")
        print("Download: https://fonts.google.com/specimen/Noto+Sans")
