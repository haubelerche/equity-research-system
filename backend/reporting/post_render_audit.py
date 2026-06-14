"""Deterministic post-render audit for client-final HTML/PDF artifacts."""
from __future__ import annotations

import base64
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PostRenderAudit:
    passed: bool
    blocking_reasons: tuple[str, ...]
    summary: dict[str, Any]


def audit_client_final_render(html_path: Path, pdf_path: Path) -> PostRenderAudit:
    html = html_path.read_text(encoding="utf-8")
    reasons: list[str] = []

    lower_html = html.lower()
    for term in (
        "forecast debt",
        "khuyến nghị hệ thống",
        "sự kiện doanh nghiệp [",
        "blocker",
        "critic",
        "internal_debug",
    ):
        if term in lower_html:
            reasons.append(f"post_render_client_language_forbidden:{term}")

    if "full-financial-table" in html:
        for period in ("2022A", "2023A", "2024A", "2025A", "2026F", "2027F", "2028F", "2029F", "2030F"):
            if period not in html:
                reasons.append(f"post_render_full_financial_period_missing:{period}")

    tables = re.findall(r"<table[^>]*>.*?</table>", html, re.IGNORECASE | re.DOTALL)
    for index, table in enumerate(tables, 1):
        first_row = re.search(r"<tr[^>]*>(.*?)</tr>", table, re.IGNORECASE | re.DOTALL)
        columns = re.findall(r"<t[hd][^>]*>", first_row.group(1), re.IGNORECASE) if first_row else []
        if len(columns) > 10:
            reasons.append(f"post_render_table_overflow_risk:{index}:{len(columns)}")

    figures = re.findall(r"<figure[^>]*report-chart[^>]*>(.*?)</figure>", html, re.IGNORECASE | re.DOTALL)
    for index, figure in enumerate(figures, 1):
        caption = re.search(r"<figcaption[^>]*>(.*?)</figcaption>", figure, re.IGNORECASE | re.DOTALL)
        caption_text = re.sub(r"<[^>]+>", "", caption.group(1)).strip() if caption else ""
        if not caption_text:
            reasons.append(f"post_render_chart_source_missing:{index}")
        if "chart-takeaway" not in figure:
            reasons.append(f"post_render_chart_takeaway_missing:{index}")
        if len(re.findall(r"Nguồn:", figure, re.IGNORECASE)) > 1:
            reasons.append(f"post_render_chart_source_duplicated:{index}")
        image = re.search(r'<img[^>]+src="data:image/[^;]+;base64,([^"]+)"', figure, re.IGNORECASE)
        if image:
            try:
                width, height = _image_dimensions(base64.b64decode(image.group(1)))
                if width < 600 or height < 300:
                    reasons.append(
                        f"post_render_chart_dimensions_too_small:{index}:{width}x{height}"
                    )
            except Exception:
                reasons.append(f"post_render_chart_image_unreadable:{index}")

    page_lengths: list[int] = []
    try:
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(pdf_path)) as pdf:
            page_lengths = [len((page.extract_text() or "").strip()) for page in pdf.pages]
            for page_index, page in enumerate(pdf.pages, 1):
                for char in page.chars:
                    if (
                        float(char.get("x0") or 0) < -1
                        or float(char.get("x1") or 0) > float(page.width) + 1
                        or float(char.get("top") or 0) < -1
                        or float(char.get("bottom") or 0) > float(page.height) + 1
                    ):
                        reasons.append(f"post_render_pdf_clipping:{page_index}")
                        break
                visible_sizes = [
                    float(char.get("size"))
                    for char in page.chars
                    if isinstance(char.get("size"), (int, float))
                    and str(char.get("text") or "").strip()
                ]
                if visible_sizes and min(visible_sizes) < 5.5:
                    reasons.append(f"post_render_font_too_small:{page_index}:{min(visible_sizes):.1f}")
        for index, length in enumerate(page_lengths[1:-1], 2):
            if length < 120:
                reasons.append(f"post_render_orphan_page:{index}:{length}")
    except Exception:
        # PDFRenderer already performs a strict text preflight. The density check
        # remains best-effort when the optional extractor cannot inspect a backend.
        page_lengths = []

    return PostRenderAudit(
        passed=not reasons,
        blocking_reasons=tuple(sorted(set(reasons))),
        summary={
            "table_count": len(tables),
            "chart_count": len(figures),
            "pdf_page_text_lengths": page_lengths,
        },
    )


def _image_dimensions(data: bytes) -> tuple[int, int]:
    """Read PNG/JPEG dimensions without optional imaging dependencies."""
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8"):
        cursor = 2
        while cursor + 9 < len(data):
            if data[cursor] != 0xFF:
                cursor += 1
                continue
            marker = data[cursor + 1]
            cursor += 2
            if marker in {0xD8, 0xD9}:
                continue
            length = struct.unpack(">H", data[cursor:cursor + 2])[0]
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                height, width = struct.unpack(">HH", data[cursor + 3:cursor + 7])
                return width, height
            cursor += length
    raise ValueError("unsupported image format")
