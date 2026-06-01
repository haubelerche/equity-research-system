"""Tests for PDFRenderer.

All tests pass without weasyprint or pdfkit installed — they rely on the
stub fallback path.
"""
from __future__ import annotations

import builtins
import unittest.mock as mock
from pathlib import Path

import pytest

from backend.reporting.pdf_renderer import PDFRenderer


def test_instantiates():
    """PDFRenderer() must not raise."""
    PDFRenderer()


def test_is_available_returns_bool():
    renderer = PDFRenderer()
    assert isinstance(renderer.is_available(), bool)


def test_render_returns_path(tmp_path):
    html = tmp_path / "test_report.html"
    html.write_text("<html><body>Test</body></html>", encoding="utf-8")
    result = PDFRenderer().render(html, output_dir=tmp_path)
    assert isinstance(result, Path)
    assert result.exists()  # PDF or stub


def test_output_filename_no_run_id(tmp_path):
    html = tmp_path / "DHG_report.html"
    html.write_text("<html><body>DHG</body></html>", encoding="utf-8")
    result = PDFRenderer().render(html, output_dir=tmp_path)
    # stem of result (ignoring .pdf / .pdf-pending) should start with "DHG"
    assert result.name.startswith("DHG")


def test_output_filename_with_run_id(tmp_path):
    html = tmp_path / "DHG_report.html"
    html.write_text("<html><body>DHG</body></html>", encoding="utf-8")
    result = PDFRenderer().render(html, output_dir=tmp_path, run_id="RUN_001")
    assert "RUN_001" in result.name


def test_stub_contains_helpful_message(tmp_path):
    """Verify stub file contains 'HTML report' when all PDF backends are unavailable."""
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name in ("weasyprint", "pdfkit", "xhtml2pdf"):
            raise ImportError(f"mocked: {name} not available")
        return original_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=mock_import):
        renderer = PDFRenderer()
        html = tmp_path / "DHG_report.html"
        html.write_text("<html><body>DHG</body></html>", encoding="utf-8")
        result = renderer.render(html, output_dir=tmp_path)

    assert result.exists()
    assert "HTML report" in result.read_text(encoding="utf-8")
