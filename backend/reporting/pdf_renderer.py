"""PDF renderer — HTML → A4 PDF.

Primary backend: weasyprint.
Fallback: pdfkit (needs wkhtmltopdf).
If neither available: writes a .pdf-pending stub and logs a warning.
Never crashes the pipeline.
"""
from __future__ import annotations

from pathlib import Path


class PDFRenderer:
    """Render an HTML report file to A4 PDF."""

    def __init__(self) -> None:
        pass

    def is_available(self) -> bool:
        """Return True if weasyprint or pdfkit is importable."""
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
        return False

    def render(
        self,
        html_path: "Path | str",
        output_dir: "Path | str | None" = None,
        run_id: str = "",
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

        Returns
        -------
        Path
            Path to the generated PDF (or ``.pdf-pending`` stub when no
            PDF backend is available).
        """
        html_path = Path(html_path)
        output_dir = Path(output_dir or html_path.parent)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Compute stem — strip trailing "_report" if present
        stem = html_path.stem
        if stem.endswith("_report"):
            stem = stem[: -len("_report")]

        # Build output filename
        if run_id:
            pdf_name = f"{run_id}_{stem}_report.pdf"
        else:
            pdf_name = f"{stem}_report.pdf"

        pdf_path = output_dir / pdf_name

        # --- Try weasyprint ---
        try:
            import weasyprint  # type: ignore
            weasyprint.HTML(filename=str(html_path)).write_pdf(str(pdf_path))
            print(f"[pdf] saved: {pdf_path}")
            return pdf_path
        except ImportError:
            pass
        except Exception:
            # GTK/OS error on Windows — fall through to pdfkit
            pass

        # --- Try pdfkit ---
        try:
            import pdfkit  # type: ignore
            pdfkit.from_file(str(html_path), str(pdf_path))
            print(f"[pdf] saved: {pdf_path}")
            return pdf_path
        except ImportError:
            pass
        except Exception:
            pass

        # --- Stub fallback ---
        stub_path = pdf_path.with_suffix(".pdf-pending")
        stub_path.write_text(
            f"PDF rendering requires weasyprint (+ GTK on Windows) or pdfkit + wkhtmltopdf.\n"
            f"HTML report: {html_path}",
            encoding="utf-8",
        )
        print(f"[pdf] WARNING: no PDF backend — stub saved: {stub_path}")
        return stub_path
