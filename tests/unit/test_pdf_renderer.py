"""Tests for PDFRenderer.

All tests pass without weasyprint or pdfkit installed � they rely on the
stub fallback path.
"""
from __future__ import annotations

import builtins
import unittest.mock as mock
from pathlib import Path

import pytest

from backend.reporting.pdf_renderer import (
    CLIENT_FORBIDDEN_PDF_TERMS,
    PDFPreflightError,
    PDFRenderError,
    PDFRenderer,
    preflight_forbidden_terms,
)


def test_instantiates():
    """PDFRenderer() must not raise."""
    PDFRenderer()


def test_is_available_returns_bool():
    renderer = PDFRenderer()
    assert isinstance(renderer.is_available(), bool)


def test_render_returns_path(tmp_path):
    html = tmp_path / "test_report.html"
    html.write_text("<html><body>Test</body></html>", encoding="utf-8")
    result = PDFRenderer().render(html, output_dir=tmp_path, allow_stub=True)
    assert isinstance(result, Path)
    assert result.exists()  # PDF or stub


def test_output_filename_no_run_id(tmp_path):
    html = tmp_path / "DHG_report.html"
    html.write_text("<html><body>DHG</body></html>", encoding="utf-8")
    result = PDFRenderer().render(html, output_dir=tmp_path, allow_stub=True)
    # stem of result (ignoring .pdf / .pdf-pending) should start with "DHG"
    assert result.name.startswith("DHG")


def test_output_filename_with_run_id(tmp_path):
    html = tmp_path / "DHG_report.html"
    html.write_text("<html><body>DHG</body></html>", encoding="utf-8")
    result = PDFRenderer().render(html, output_dir=tmp_path, run_id="RUN_001", allow_stub=True)
    assert "RUN_001" in result.name


def test_stub_contains_helpful_message(tmp_path):
    """Verify stub file contains 'HTML report' when all PDF backends are unavailable."""
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name in ("weasyprint", "pdfkit", "xhtml2pdf"):
            raise ImportError(f"mocked: {name} not available")
        return original_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=mock_import), \
            mock.patch("backend.reporting.pdf_renderer._find_chromium_executable", return_value=None):
        renderer = PDFRenderer()
        html = tmp_path / "DHG_report.html"
        html.write_text("<html><body>DHG</body></html>", encoding="utf-8")
        result = renderer.render(html, output_dir=tmp_path, allow_stub=True)

    assert result.exists()
    assert "HTML report" in result.read_text(encoding="utf-8")


def test_strict_render_fails_when_no_backend(tmp_path):
    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name in ("weasyprint", "pdfkit", "xhtml2pdf"):
            raise ImportError(f"mocked: {name} not available")
        return original_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", side_effect=mock_import), \
            mock.patch("backend.reporting.pdf_renderer._find_chromium_executable", return_value=None):
        html = tmp_path / "DHG_report.html"
        html.write_text("<html><body>DHG</body></html>", encoding="utf-8")
        with pytest.raises(PDFRenderError):
            PDFRenderer().render(html, output_dir=tmp_path)


def test_accepts_valid_vietnamese_text(tmp_path):
    """Valid Vietnamese diacritics (UTF-8) must NOT trigger preflight failure."""
    html = tmp_path / "DBD_report.html"
    html.write_text("<html><body>Công ty CP Dược Bình Định</body></html>", encoding="utf-8")

    original_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name in ("weasyprint", "pdfkit", "xhtml2pdf"):
            raise ImportError(f"mocked: {name} not available")
        return original_import(name, *args, **kwargs)

    # Should NOT raise: valid Vietnamese is fine; unavailable PDF backends use stub.
    with mock.patch("builtins.__import__", side_effect=mock_import), \
            mock.patch("backend.reporting.pdf_renderer._find_chromium_executable", return_value=None):
        PDFRenderer().render(html, output_dir=tmp_path, allow_stub=True)


def test_rejects_actual_replacement_char_in_html(tmp_path):
    """HTML containing the Unicode replacement character U+FFFD must fail strict preflight."""
    html = tmp_path / "DBD_corrupt.html"
    html.write_text("<html><body>B�N — corrupt encoding</body></html>", encoding="utf-8")
    with pytest.raises(PDFPreflightError):
        PDFRenderer().render(html, output_dir=tmp_path, allow_stub=True, strict_preflight=True)


def test_rejects_client_facing_backend_terms():
    with pytest.raises(PDFPreflightError):
        preflight_forbidden_terms(
            "<html><body>Human review PENDING</body></html>",
            CLIENT_FORBIDDEN_PDF_TERMS,
        )
