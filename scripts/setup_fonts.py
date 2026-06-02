"""Provision Unicode fonts for PDF Vietnamese rendering (Windows only).

Run once to set up assets/fonts/NotoSans-Regular.ttf from Windows system fonts.
This font is the xhtml2pdf fallback for Vietnamese PDF output when Chrome is unavailable.

Note: This script is Windows-only. On Linux, install the `fonts-noto` package instead.
Note: The target file is named NotoSans-Regular.ttf for compatibility with pdf_renderer.py,
      but the actual bytes may come from a Windows system font (Segoe UI, Arial, etc.).
"""
import shutil
import sys
from pathlib import Path


def provision_fonts(root: Path | None = None) -> Path | None:
    """Copy a Unicode TTF from Windows system fonts to assets/fonts/NotoSans-Regular.ttf.

    Returns the target path if successful, None if no source font was found.
    """
    if root is None:
        root = Path(__file__).resolve().parent.parent
    fonts_dir = root / "assets" / "fonts"
    fonts_dir.mkdir(parents=True, exist_ok=True)

    CANDIDATES = [
        Path(r"C:\Windows\Fonts\segoeui.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\tahoma.ttf"),
    ]

    target = fonts_dir / "NotoSans-Regular.ttf"
    if target.exists():
        print(f"Font already present: {target} ({target.stat().st_size:,} bytes)")
        return target

    for src in CANDIDATES:
        if src.exists():
            shutil.copy(src, target)
            print(f"Copied {src} -> {target} (aliased as NotoSans-Regular.ttf for pdf_renderer.py)")
            return target

    print(
        "WARNING: No Unicode font found automatically. "
        "Place NotoSans-Regular.ttf at: " + str(target) + "\n"
        "Download: https://fonts.google.com/specimen/Noto+Sans\n"
        "Or on Linux: sudo apt-get install fonts-noto"
    )
    return None


if __name__ == "__main__":
    result = provision_fonts()
    sys.exit(0 if result else 1)
