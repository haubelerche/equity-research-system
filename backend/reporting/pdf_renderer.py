"""PDF renderer — HTML → A4 PDF.

Primary backend: weasyprint (best Vietnamese Unicode support via system fonts).
Fallback 1: pdfkit (needs wkhtmltopdf with --encoding utf-8).
Fallback 2: xhtml2pdf with DejaVu/NotoSans font embedding from Google Fonts CDN.
Fallback 3: .pdf-pending stub — pipeline continues without crashing.

Vietnamese font rendering requires one of:
  - WeasyPrint + Noto Sans installed (Linux/Docker)
  - wkhtmltopdf with system Vietnamese fonts
  - xhtml2pdf with @font-face referencing a Unicode TTF (DejaVu, Noto Sans)

On Windows with xhtml2pdf, the HTML is preprocessed to inject a @font-face
pointing at a DejaVu Sans TTF if available in the project, or a warning is
written to the stub file.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]

# Paths to bundled Unicode fonts (optional — shipped for xhtml2pdf fallback)
_FONTS_DIR = _ROOT / "assets" / "fonts"
_DEJAVU_TTF = _FONTS_DIR / "DejaVuSans.ttf"
_NOTO_TTF = _FONTS_DIR / "NotoSans-Regular.ttf"

_BROKEN_TEXT_MARKERS = (
    "\ufffd",               # Unicode replacement character.
    "\u00ef\u00bf\u00bd",   # UTF-8 replacement bytes decoded as Latin-1.
    "Gi\u00ef",
    "Ch?",
    "B->o",
    "c->o",
    "d? li?u",
)

CLIENT_FORBIDDEN_PDF_TERMS = (
    "DRAFT",
    "BÁO CÁO NHÁP",
    "Cần analyst review",
    "Human review",
    "PENDING",
    "UNDER_REVIEW",
    "Mã hệ thống",
    "Valuation reproducibility",
    "Numeric Consistency",
    "Source Coverage",
    "Tier 0",
    "Tier 1",
    "Tier 2",
    "Tier 3",
    "database",
    "backend",
    "canonical facts",
    "valuation artifact",
    "forecast artifact",
    "artifact",
    "PASS",
    "FAIL",
    "WARN",
    "BLOCKED",
    "blocked",
    "pending_review",
    "default_unapproved",
    "gate",
    "OCR",
    "Không export final",
    "file:///",
    ".html",
)


class PDFRenderError(RuntimeError):
    """Raised when strict PDF export cannot produce a safe PDF artifact."""


class PDFPreflightError(PDFRenderError):
    """Raised when HTML/PDF text fails Vietnamese rendering preflight."""


def _find_unicode_font() -> Path | None:
    """Return path to an available Unicode TTF font, or None."""
    for candidate in [_NOTO_TTF, _DEJAVU_TTF]:
        if candidate.exists():
            return candidate
    # Also check system font directories (Windows)
    system_candidates = [
        Path(r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\seguiemj.ttf"),
        Path(r"C:\Windows\Fonts\NotoSans-Regular.ttf"),
    ]
    for p in system_candidates:
        if p.exists():
            return p
    return None


def _find_chromium_executable() -> Path | None:
    """Return an installed Chromium/Chrome/Edge executable, if available."""
    candidates = [
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _safe_error_text(exc: BaseException) -> str:
    """Return exception text that is safe for narrow Windows consoles."""
    return str(exc).encode("ascii", errors="backslashreplace").decode("ascii")


def _inject_unicode_font_css(html_content: str, font_path: Path) -> str:
    """Inject @font-face for xhtml2pdf to embed a Unicode TTF.

    xhtml2pdf requires @font-face with a local file:// path to embed fonts.
    Without this, Vietnamese characters render as boxes.
    """
    font_uri = font_path.as_uri()  # file:///C:/path/to/font.ttf
    font_face = f"""
@font-face {{
    font-family: "UnicodeFallback";
    src: url("{font_uri}");
}}
"""
    # Replace the font-family in body/all elements to use the embedded font
    body_override = """
body, table, th, td, p, h1, h2, h3, h4, li, blockquote {
    font-family: "UnicodeFallback", Arial, sans-serif;
}
"""
    injection = f"<style>{font_face}{body_override}</style>"

    # Inject just before </head>
    if "</head>" in html_content:
        return html_content.replace("</head>", injection + "\n</head>", 1)
    # Fallback: inject at the beginning
    return injection + html_content


def preflight_html_text(html_content: str) -> None:
    """Fail fast when the HTML already contains broken Vietnamese text markers."""
    found = [m for m in _BROKEN_TEXT_MARKERS if m in html_content]
    if found:
        raise PDFPreflightError(
            "HTML text failed Vietnamese preflight; broken markers found: "
            + ", ".join(found)
        )


def preflight_pdf_text(pdf_path: Path) -> None:
    """Best-effort PDF text preflight for missing glyph boxes and mojibake.

    If pypdf is unavailable the renderer still relies on the prior HTML
    preflight plus Unicode-capable backend selection; generated PDFs are not
    rejected solely because the optional text extractor is absent.
    """
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return

    text_parts: list[str] = []
    reader = PdfReader(str(pdf_path))
    for page in reader.pages:
        text_parts.append(page.extract_text() or "")
    extracted = "\n".join(text_parts)
    found = [m for m in _BROKEN_TEXT_MARKERS if m in extracted]
    if found:
        raise PDFPreflightError(
            f"PDF text failed Vietnamese preflight for {pdf_path}; broken markers found: "
            + ", ".join(found)
        )


def extract_pdf_text(pdf_path: Path) -> str:
    """Return extracted PDF text, or an empty string if pypdf is unavailable."""
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return ""
    reader = PdfReader(str(pdf_path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def preflight_forbidden_terms(text: str, forbidden_terms: tuple[str, ...]) -> None:
    """Fail if client-facing text contains internal/debug terminology."""
    found = [term for term in forbidden_terms if term in text]
    if found:
        raise PDFPreflightError(
            "Client-facing report text contains forbidden internal terms: "
            + ", ".join(found[:20])
        )


class PDFRenderer:
    """Render an HTML report file to A4 PDF."""

    def __init__(self) -> None:
        pass

    def is_available(self) -> bool:
        """Return True if weasyprint, pdfkit, or xhtml2pdf is importable."""
        try:
            import weasyprint  # noqa: F401
            return True
        except (ImportError, OSError):
            pass
        try:
            import pdfkit  # noqa: F401
            return True
        except (ImportError, OSError):
            pass
        try:
            from xhtml2pdf import pisa  # noqa: F401
            return True
        except (ImportError, OSError):
            pass
        return False

    def render(
        self,
        html_path: "Path | str",
        output_dir: "Path | str | None" = None,
        run_id: str = "",
        allow_stub: bool = False,
        forbidden_terms: tuple[str, ...] | None = None,
        strict_preflight: bool = False,
    ) -> Path:
        """Render *html_path* to PDF and return the output path.

        Parameters
        ----------
        html_path:
            Path to the input HTML file.
        output_dir:
            Directory to write the PDF.  Defaults to the same directory as
            *html_path*.  Created if it does not exist.
        run_id:
            Optional run identifier prepended to the filename.
        allow_stub:
            When True, writes a ``.pdf-pending`` diagnostic file if no backend
            is available. Strict report export should leave this False.

        Returns
        -------
        Path
            Path to the generated PDF, or a ``.pdf-pending`` diagnostic file
            only when ``allow_stub=True``.
        """
        html_path = Path(html_path)
        output_dir = Path(output_dir or html_path.parent)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Compute stem  strip trailing "_report" if present
        stem = html_path.stem
        if stem.endswith("_report"):
            stem = stem[: -len("_report")]

        # Build output filename
        if run_id:
            pdf_name = f"{run_id}_{stem}_report.pdf"
        else:
            pdf_name = f"{stem}_report.pdf"

        final_pdf_path = output_dir / pdf_name
        pdf_path = output_dir / f".{Path(pdf_name).stem}.tmp.pdf"
        if pdf_path.exists():
            pdf_path.unlink()

        def _publish_pdf(backend: str) -> Path:
            pdf_path.replace(final_pdf_path)
            print(f"[pdf] saved ({backend}): {final_pdf_path}")
            return final_pdf_path
        html_content_for_preflight = html_path.read_text(encoding="utf-8")
        try:
            preflight_html_text(html_content_for_preflight)
        except PDFPreflightError as _pf_err:
            if strict_preflight:
                raise
            print("[pdf] WARNING: preflight issue (non-strict mode): " + str(_pf_err).encode("ascii", errors="replace").decode("ascii"))
        if forbidden_terms:
            preflight_forbidden_terms(html_content_for_preflight, forbidden_terms)

        # --- Try weasyprint (best Unicode/Vietnamese support) ---
        try:
            import weasyprint  # type: ignore
            weasyprint.HTML(filename=str(html_path)).write_pdf(str(pdf_path))
            preflight_pdf_text(pdf_path)
            if forbidden_terms:
                preflight_forbidden_terms(extract_pdf_text(pdf_path), forbidden_terms)
            return _publish_pdf("weasyprint")
        except ImportError:
            pass
        except Exception as e:
            # GTK/OS error on Windows  fall through to pdfkit
            print(f"[pdf] weasyprint failed ({e}), trying pdfkit...")

        # --- Try pdfkit with UTF-8 encoding flag ---
        try:
            import pdfkit  # type: ignore
            options = {
                "encoding": "UTF-8",
                "page-size": "A4",
                "margin-top": "18mm",
                "margin-bottom": "18mm",
                "margin-left": "16mm",
                "margin-right": "16mm",
            }
            pdfkit.from_file(str(html_path), str(pdf_path), options=options)
            preflight_pdf_text(pdf_path)
            if forbidden_terms:
                preflight_forbidden_terms(extract_pdf_text(pdf_path), forbidden_terms)
            return _publish_pdf("pdfkit")
        except ImportError:
            pass
        except Exception as e:
            print(f"[pdf] pdfkit failed ({e}), trying Chrome...")

        # --- Try installed Chromium/Chrome/Edge headless print-to-PDF ---
        chrome = _find_chromium_executable()
        if chrome:
            try:
                if pdf_path.exists():
                    pdf_path.unlink()
                profile_dir = (output_dir / f".chrome-profile-{os.getpid()}").resolve()
                profile_dir.mkdir(parents=True, exist_ok=True)
                chrome_pdf_path = pdf_path.resolve()
                cmd = [
                    str(chrome),
                    "--headless=new",
                    "--disable-gpu",
                    "--no-sandbox",
                    "--disable-crash-reporter",
                    "--disable-extensions",
                    "--no-pdf-header-footer",
                    "--print-to-pdf-no-header",
                    f"--user-data-dir={profile_dir}",
                    f"--print-to-pdf={chrome_pdf_path}",
                    html_path.resolve().as_uri(),
                ]
                completed = subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                if completed.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
                    preflight_pdf_text(pdf_path)
                    if forbidden_terms:
                        preflight_forbidden_terms(extract_pdf_text(pdf_path), forbidden_terms)
                    return _publish_pdf("chrome")
                err = (completed.stderr or completed.stdout or "").strip()
                print(f"[pdf] chrome failed ({err[:400]}), trying xhtml2pdf...")
            except Exception as e:
                print(f"[pdf] chrome failed ({_safe_error_text(e)}), trying xhtml2pdf...")

        # --- Try xhtml2pdf with Unicode font injection ---
        try:
            from xhtml2pdf import pisa  # type: ignore
            if pdf_path.exists():
                pdf_path.unlink()

            html_content = html_content_for_preflight

            # Attempt to inject a Unicode TTF font for Vietnamese support
            font_path = _find_unicode_font()
            if font_path:
                html_content = _inject_unicode_font_css(html_content, font_path)
                print(f"[pdf] xhtml2pdf: injecting Unicode font from {font_path}")
            else:
                print(
                    "[pdf] WARNING: No Unicode TTF font found for xhtml2pdf. "
                    "Vietnamese characters may not render correctly. "
                    "Install Noto Sans to: assets/fonts/NotoSans-Regular.ttf"
                )

            with open(str(pdf_path), "wb") as f:
                result = pisa.CreatePDF(html_content, dest=f, encoding="utf-8")

            if not result.err and pdf_path.exists() and pdf_path.stat().st_size > 0:
                preflight_pdf_text(pdf_path)
                if forbidden_terms:
                    preflight_forbidden_terms(extract_pdf_text(pdf_path), forbidden_terms)
                return _publish_pdf("xhtml2pdf")
            else:
                print(f"[pdf] xhtml2pdf produced errors: {result.err}")
        except ImportError:
            pass
        except Exception as e:
            print(f"[pdf] xhtml2pdf failed: {_safe_error_text(e)}")

        # --- Stub fallback ---
        if not allow_stub:
            raise PDFRenderError(
                "No usable PDF backend is available for strict export. "
                "Install WeasyPrint, pdfkit/wkhtmltopdf, or xhtml2pdf with Unicode fonts."
            )

        font_path = _find_unicode_font()
        stub_path = final_pdf_path.with_suffix(".pdf-pending")
        stub_msg = (
            "PDF rendering requires one of:\n"
            "  1. WeasyPrint (best): pip install weasyprint  (+ GTK on Windows via msys2)\n"
            "  2. pdfkit: pip install pdfkit  (+ wkhtmltopdf binary with Vietnamese fonts)\n"
            "  3. xhtml2pdf: pip install xhtml2pdf  (+ place NotoSans-Regular.ttf in assets/fonts/)\n\n"
            f"HTML report is at: {html_path}\n"
            f"Unicode font found: {font_path or 'None  install Noto Sans'}\n"
        )
        stub_path.write_text(stub_msg, encoding="utf-8")
        print(f"[pdf] WARNING: no PDF backend  stub saved: {stub_path}")
        return stub_path
