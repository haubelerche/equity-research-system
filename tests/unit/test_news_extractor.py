"""Tests for the news HTML content extractor (stdlib, no network)."""
from __future__ import annotations

from backend.news.extractor import extract_main_content


def test_extracts_paragraph_body_and_title():
    html = """
    <html><head>
      <meta property="og:title" content="DHG thay CEO">
      <meta property="article:published_time" content="2025-12-09T07:10:00">
      <title>fallback title</title>
    </head><body>
      <nav><p>menu noise</p></nav>
      <p>Dược Hậu Giang công bố thay đổi nhân sự.</p>
      <p>Quyết định có hiệu lực từ 2026.</p>
      <script>var x = "<p>not real</p>";</script>
    </body></html>
    """
    ex = extract_main_content(html)
    assert ex.title == "DHG thay CEO"
    assert ex.published_at == "2025-12-09T07:10:00"
    assert "Dược Hậu Giang công bố thay đổi nhân sự." in ex.text
    assert "Quyết định có hiệu lực từ 2026." in ex.text
    # nav/script boilerplate is dropped
    assert "menu noise" not in ex.text
    assert "not real" not in ex.text


def test_aspnet_form_wrapped_body_is_not_dropped():
    """Regression: CafeF /du-lieu/ disclosure pages wrap the whole body in a single
    <form runat="server">. Skipping <form> dropped the entire article (0 chars)."""
    html = """
    <html><body>
      <form name="aspnetForm" method="post" action="./x.aspx" id="aspnetForm">
        <div id="ContentPlaceHolder1_ucStockNewsDetail1_divContent">
          <p>Công ty Cổ phần Dược Hậu Giang thông báo thay đổi nhân sự như sau:</p>
          <p>Bổ nhiệm ông Osamu Fujimori giữ chức Phó Tổng giám đốc.</p>
        </div>
      </form>
    </body></html>
    """
    ex = extract_main_content(html)
    assert "Dược Hậu Giang thông báo thay đổi nhân sự" in ex.text
    assert "Osamu Fujimori" in ex.text


def test_empty_or_none_html_is_safe():
    assert extract_main_content("").text == ""
    assert extract_main_content(None).text == ""  # type: ignore[arg-type]
