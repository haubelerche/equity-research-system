#!/usr/bin/env python
"""Check OCR runtime dependencies (tesseract, Poppler, Python packages).

Verifies that all required OCR dependencies are installed and available:
  1. tesseract binary and --version
  2. Vietnamese language pack (vie)
  3. Poppler tools (pdftoppm or pdftocairo)
  4. Python packages: pytesseract, pdf2image, PIL

Exit code 0 if all checks pass.
Exit code 1 if any check fails.

Usage:
    python scripts/check_ocr_runtime.py

Output:
    [ocr-runtime] OK (if all pass)
    [ocr-runtime] FAILED (if any fail)
    Followed by individual check results.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def _check_tesseract_binary() -> tuple[bool, str]:
    """Check if tesseract binary is installed and accessible."""
    try:
        # Try to find tesseract
        tess_path = shutil.which("tesseract")

        # On Windows, also check common installation path
        if not tess_path and sys.platform == "win32":
            common_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
            if common_path.exists():
                tess_path = str(common_path)

        if not tess_path:
            return False, (
                "tesseract binary not found\n"
                "Install with:\n"
                "  Ubuntu/Debian: sudo apt-get install tesseract-ocr\n"
                "  macOS: brew install tesseract\n"
                "  Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki"
            )

        # Verify it runs
        result = subprocess.run(
            [tess_path, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return False, f"tesseract --version failed: {result.stderr.strip()}"

        return True, f"tesseract: found ({result.stdout.split()[0]})"

    except subprocess.TimeoutExpired:
        return False, "tesseract --version timed out"
    except Exception as e:
        return False, f"tesseract check error: {e}"


def _check_vietnamese_language() -> tuple[bool, str]:
    """Check if Vietnamese language pack (vie) is available for tesseract."""
    try:
        tess_path = shutil.which("tesseract")

        # On Windows, check common installation path
        if not tess_path and sys.platform == "win32":
            common_path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
            if common_path.exists():
                tess_path = str(common_path)

        if not tess_path:
            return False, "Cannot check languages: tesseract binary not found"

        result = subprocess.run(
            [tess_path, "--list-langs"],
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            return False, f"tesseract --list-langs failed: {result.stderr.strip()}"

        languages = result.stdout.strip().split("\n")

        if "vie" not in languages:
            lang_list = ", ".join(sorted(languages)[:5]) + (
                ", ..." if len(languages) > 5 else ""
            )
            return False, (
                f"Vietnamese language 'vie' not found in tesseract\n"
                f"Available languages: {lang_list}\n"
                f"Install Vietnamese language with:\n"
                f"  Ubuntu/Debian: sudo apt-get install tesseract-ocr-vie\n"
                f"  macOS: brew install tesseract-lang\n"
                f"  Windows: Download traineddata files from\n"
                f"    https://github.com/UB-Mannheim/tesseract/wiki\n"
                f"Or set TESSDATA_PREFIX to point to tessdata directory\n"
                f"  containing vie.traineddata"
            )

        return True, "language: vie found"

    except subprocess.TimeoutExpired:
        return False, "tesseract --list-langs timed out"
    except Exception as e:
        return False, f"Vietnamese language check error: {e}"


def _check_poppler() -> tuple[bool, str]:
    """Check if Poppler tools (pdftoppm or pdftocairo) are installed."""
    try:
        # Try pdftoppm first (more common)
        pdftoppm_path = shutil.which("pdftoppm")

        # On Windows, check common installation paths
        if not pdftoppm_path and sys.platform == "win32":
            common_paths = [
                Path(r"C:\Program Files\poppler\Library\bin\pdftoppm.exe"),
                Path(r"C:\Program Files (x86)\poppler\Library\bin\pdftoppm.exe"),
            ]
            for p in common_paths:
                if p.exists():
                    pdftoppm_path = str(p)
                    break

        # Try pdftocairo if pdftoppm not found
        pdftocairo_path = None
        if not pdftoppm_path:
            pdftocairo_path = shutil.which("pdftocairo")
            if not pdftocairo_path and sys.platform == "win32":
                common_paths = [
                    Path(r"C:\Program Files\poppler\Library\bin\pdftocairo.exe"),
                    Path(r"C:\Program Files (x86)\poppler\Library\bin\pdftocairo.exe"),
                ]
                for p in common_paths:
                    if p.exists():
                        pdftocairo_path = str(p)
                        break

        if not pdftoppm_path and not pdftocairo_path:
            return False, (
                "Poppler tools not found (need pdftoppm or pdftocairo)\n"
                "Install with:\n"
                "  Ubuntu/Debian: sudo apt-get install poppler-utils\n"
                "  macOS: brew install poppler\n"
                "  Windows: Download from https://github.com/oschwartz10612/poppler-windows/releases"
            )

        return True, "poppler: found"

    except Exception as e:
        return False, f"Poppler check error: {e}"


def _check_python_packages() -> tuple[bool, str]:
    """Check if required Python packages are installed."""
    missing = []

    # Check pytesseract
    try:
        import pytesseract  # noqa: F401
    except ImportError:
        missing.append("pytesseract")

    # Check pdf2image
    try:
        import pdf2image  # noqa: F401
    except ImportError:
        missing.append("pdf2image")

    # Check PIL/Pillow
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        missing.append("Pillow (PIL)")

    if missing:
        return False, (
            f"Missing Python packages: {', '.join(missing)}\n"
            f"Install with:\n"
            f"  pip install pytesseract pdf2image Pillow"
        )

    return True, "python packages: OK"


def check_ocr_runtime() -> bool:
    """Run all OCR runtime checks.

    Returns:
        True if all checks pass, False otherwise.
    """
    print()

    checks = [
        ("tesseract binary", _check_tesseract_binary),
        ("Vietnamese language", _check_vietnamese_language),
        ("Poppler tools", _check_poppler),
        ("Python packages", _check_python_packages),
    ]

    results = []
    for check_name, check_func in checks:
        passed, message = check_func()
        results.append((passed, message))

        if passed:
            print(f"  [OK] {message}")
        else:
            print(f"  [FAIL] {check_name}:")
            for line in message.split("\n"):
                print(f"    {line}")
            print()

    all_passed = all(passed for passed, _ in results)

    print()
    if all_passed:
        print("[ocr-runtime] OK")
        return True
    else:
        print("[ocr-runtime] FAILED")
        return False


def main() -> int:
    """Main entry point."""
    try:
        all_passed = check_ocr_runtime()
        return 0 if all_passed else 1
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"\nUnexpected error during OCR runtime check: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
