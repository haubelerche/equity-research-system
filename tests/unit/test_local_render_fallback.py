from __future__ import annotations

from backend.reporting.final_report_renderer import render_final_report_model_html


def test_render_final_report_model_html_produces_valid_html():
    """render_final_report_model_html returns valid HTML with ticker and sections."""
    model = {
        "ticker": "TEST",
        "run_id": "run_test_001",
        "checksum": "abc123",
        "sections": {
            "cover_investment_summary": {"title": "Test Cover"},
            "company_overview": {"summary": "Test company overview"},
        },
        "tables": {},
        "charts": {},
        "claim_ledger": {"claims": []},
    }
    html_content = render_final_report_model_html(model)
    assert "TEST Final Report" in html_content
    assert "Test Cover" in html_content
    assert "Test company overview" in html_content
    assert "<!DOCTYPE html>" in html_content
