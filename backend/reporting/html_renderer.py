"""HTML renderer — converts report sections to professional A4 HTML via Jinja2.

Usage::

    from backend.reporting.section_builder import ReportContext, build_report_sections
    from backend.reporting.html_renderer import HTMLRenderer
    from pathlib import Path

    ctx = ReportContext(ticker="DHG", ...)
    sections = build_report_sections(ctx)
    out_path = HTMLRenderer().render(sections, ctx, output_dir=temporary_output_dir)
    print("Generated:", out_path)
"""
from __future__ import annotations

import base64
import re
from pathlib import Path

import markdown as _markdown
from jinja2 import Environment, FileSystemLoader, select_autoescape

from backend.reporting.section_builder import ReportContext, _rating_label

# Markdown extensions for professional rendering
_MD_EXTENSIONS = ["tables", "fenced_code", "nl2br", "sane_lists"]

# Directory that holds Jinja2 templates and CSS
_TEMPLATES_DIR = Path(__file__).parent / "templates"

# Project root for resolving relative image paths
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

_BROKEN_TEXT_MARKERS = (
    "\ufffd",
    "\u00ef\u00bf\u00bd",
    "Gi\u00ef",
    "Ch?",
    "B->o",
    "c->o",
    "d? li?u",
)


class HTMLPreflightError(RuntimeError):
    """Raised when generated HTML contains text corruption markers."""


def preflight_rendered_html_text(html_content: str) -> None:
    """Fail fast when generated HTML contains mojibake or replacement markers."""
    found = [marker for marker in _BROKEN_TEXT_MARKERS if marker in html_content]
    if found:
        raise HTMLPreflightError(
            "HTML text failed encoding preflight; broken markers found: "
            + ", ".join(found[:20])
        )


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
    # Image embedding helpers
    # ------------------------------------------------------------------

    def _resolve_image_path(self, src: str) -> Path | None:
        """Resolve an image src to an existing Path, or return None."""
        # Normalise backslashes → forward slashes
        src = src.strip("\"'").replace("\\", "/")
        p = Path(src)
        if p.is_absolute() and p.exists():
            return p
        # Try relative to project root
        candidate = _PROJECT_ROOT / src
        if candidate.exists():
            return candidate
        # Try relative to cwd
        candidate2 = Path(src)
        if candidate2.exists():
            return candidate2
        return None

    def _embed_images(self, html_content: str) -> str:
        """Replace <img src="..."> with base64 data URIs for self-contained HTML."""

        def replace_src(match: re.Match) -> str:
            full_tag = match.group(0)
            src_match = re.search(r'src=["\']([^"\']*)["\']', full_tag)
            if not src_match:
                return full_tag
            src = src_match.group(1)
            alt_match = re.search(r'alt=["\']([^"\']*)["\']', full_tag)
            alt = alt_match.group(1) if alt_match else "Chart"

            img_path = self._resolve_image_path(src)
            if img_path is not None:
                b64 = base64.b64encode(img_path.read_bytes()).decode()
                return (
                    f'<img alt="{alt}" src="data:image/png;base64,{b64}" '
                    f'style="max-width:100%;height:auto;display:block;margin:8pt auto;" />'
                )
            else:
                return (
                    f'<div style="background:#f0f4f8;border:1px dashed #aaa;'
                    f"padding:20px;text-align:center;color:#666;font-size:9pt;"
                    f'margin:8pt 0;">{alt} — chưa có dữ liệu</div>'
                )

        return re.sub(r"<img[^>]+>", replace_src, html_content)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render(
        self,
        sections: list[dict],
        ctx: ReportContext,
        output_dir: "Path | str | None" = None,
        run_id: str = "",
        render_mode: str = "",
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
        if output_dir is None:
            raise ValueError("output_dir must be an explicit temporary rendering directory")
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
        # Review/audit dashboard: the first section is the review summary.
        # In that mode we suppress the ACBS recommendation banner and the
        # "ĐANG HOÀN THIỆN" page headers so the output reads as a review, not a
        # finished analyst report.
        is_review = bool(enriched) and enriched[0].get("page") == "review_summary"

        # Client (ACBS-style) sections embed a recommendation hero card directly
        # inside the snapshot cover page.  Suppress the standalone template-level
        # recommendation banner to avoid a near-blank page before the cover page.
        is_client_sections = bool(enriched) and enriched[0].get("page") == "snapshot"

        display_status = "" if render_mode == "client_final" else ctx.status

        rendered = self._template.render(
            css=self._css,
            sections=enriched,
            ticker=ctx.ticker,
            company_name=ctx.company_name,
            report_date=ctx.report_date,
            rating=ctx.rating,
            recommendation_label=_rating_label(ctx.rating),
            status=display_status,
            is_review=is_review,
            suppress_rec_banner=is_client_sections,
            target_price_fmt=(
                "—" if ctx._target_price_missing else f"{ctx.target_price:,.0f} VND"
            ),
            upside_fmt=(
                "—" if ctx._upside_missing else f"{ctx.upside_pct:+.1f}%"
            ),
        )

        # Embed all images as base64 data URIs → self-contained HTML
        rendered = self._embed_images(rendered)

        preflight_rendered_html_text(rendered)

        out_path.write_text(rendered, encoding="utf-8")
        return out_path
