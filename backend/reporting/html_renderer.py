"""HTML renderer — converts report sections to professional A4 HTML via Jinja2.

Usage::

    from backend.reporting.section_builder import ReportContext, build_report_sections
    from backend.reporting.html_renderer import HTMLRenderer
    from pathlib import Path

    ctx = ReportContext(ticker="DHG", ...)
    sections = build_report_sections(ctx)
    out_path = HTMLRenderer().render(sections, ctx, output_dir=Path("artifacts/reports_html"))
    print("Generated:", out_path)
"""
from __future__ import annotations

from pathlib import Path

import markdown as _markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.reporting.section_builder import ReportContext

# Markdown extensions for professional rendering
_MD_EXTENSIONS = ["tables", "fenced_code", "nl2br", "sane_lists"]

# Directory that holds Jinja2 templates and CSS
_TEMPLATES_DIR = Path(__file__).parent / "templates"


class HTMLRenderer:
    """Render a list of report section dicts into a single A4 HTML file."""

    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(str(_TEMPLATES_DIR)),
            autoescape=select_autoescape(disabled_extensions=("html.j2",)),
        )
        self._template = self._env.get_template("report.html.j2")
        self._css = (_TEMPLATES_DIR / "report.css").read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(
        self,
        sections: list[dict],
        ctx: ReportContext,
        output_dir: "Path | str" = "artifacts/reports_html",
        run_id: str = "",
    ) -> Path:
        """Convert sections to HTML and write to *output_dir*.

        Parameters
        ----------
        sections:
            Exactly 8 section dicts as produced by ``build_report_sections``.
        ctx:
            The ``ReportContext`` used to generate the sections.
        output_dir:
            Target directory.  Created if it does not exist.
        run_id:
            Optional run identifier prepended to the filename.
            E.g. ``run_id="RUN_001"`` → ``RUN_001_DHG_report.html``.
            If empty, the filename is ``{ticker}_report.html``.

        Returns
        -------
        Path
            Absolute path to the generated HTML file.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Convert each section's markdown to HTML
        enriched = []
        for section in sections:
            md_text = section.get("markdown", "")
            html_body = _markdown.markdown(md_text, extensions=_MD_EXTENSIONS)
            enriched.append({**section, "html": html_body})

        # Build filename
        if run_id:
            filename = f"{run_id}_{ctx.ticker}_report.html"
        else:
            filename = f"{ctx.ticker}_report.html"

        out_path = output_dir / filename

        # Render via Jinja2
        rendered = self._template.render(
            css=self._css,
            sections=enriched,
            ticker=ctx.ticker,
            company_name=ctx.company_name,
            report_date=ctx.report_date,
            rating=ctx.rating,
            status=ctx.status,
        )

        out_path.write_text(rendered, encoding="utf-8")
        return out_path
