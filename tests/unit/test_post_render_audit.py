from __future__ import annotations

import base64
import struct
import zlib
from pathlib import Path

from backend.reporting.post_render_audit import audit_client_final_render


def test_post_render_audit_blocks_wide_table_and_missing_chart_caption(tmp_path: Path) -> None:
    cells = "".join("<th>x</th>" for _ in range(11))
    html = tmp_path / "report.html"
    html.write_text(
        f"<table><tr>{cells}</tr></table><figure class='report-chart'><img src='x'></figure>",
        encoding="utf-8",
    )
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"not-a-real-pdf")

    audit = audit_client_final_render(html, pdf)

    assert not audit.passed
    assert any(reason.startswith("post_render_table_overflow_risk") for reason in audit.blocking_reasons)
    assert any(reason.startswith("post_render_chart_source_missing") for reason in audit.blocking_reasons)


def test_post_render_audit_blocks_small_embedded_chart(tmp_path: Path) -> None:
    raw = b"\x00" + (b"\xff\xff\xff" * 200)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 200, 100, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw * 100))
        + _png_chunk(b"IEND", b"")
    )
    encoded = base64.b64encode(png).decode("ascii")
    html = tmp_path / "report.html"
    html.write_text(
        f'<figure class="report-chart"><img src="data:image/png;base64,{encoded}">'
        "<figcaption>Nguon: company</figcaption></figure>",
        encoding="utf-8",
    )
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"not-a-real-pdf")

    audit = audit_client_final_render(html, pdf)

    assert any(
        reason.startswith("post_render_chart_dimensions_too_small")
        for reason in audit.blocking_reasons
    )


def test_post_render_audit_blocks_debug_language_and_incomplete_full_table(tmp_path: Path) -> None:
    html_path = tmp_path / "report.html"
    pdf_path = tmp_path / "report.pdf"
    html_path.write_text(
        '<div>forecast debt</div><table class="full-financial-table">'
        "<tr><th>Chỉ tiêu</th><th>2025A</th><th>2026F</th></tr></table>",
        encoding="utf-8",
    )
    pdf_path.write_bytes(b"not-a-pdf")

    audit = audit_client_final_render(html_path, pdf_path)

    assert "post_render_client_language_forbidden:forecast debt" in audit.blocking_reasons
    assert "post_render_full_financial_period_missing:2022A" in audit.blocking_reasons


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    payload = kind + data
    return struct.pack(">I", len(data)) + payload + struct.pack(">I", zlib.crc32(payload))
