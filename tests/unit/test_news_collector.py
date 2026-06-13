from __future__ import annotations

import subprocess
from types import SimpleNamespace

from backend.news.collector import rendered_html_fetch
from backend.reporting import pdf_renderer


def test_rendered_html_fetch_decodes_chrome_dom_as_utf8(monkeypatch) -> None:
    run_kwargs: dict[str, object] = {}

    monkeypatch.setattr(pdf_renderer, "_find_chromium_executable", lambda: "chrome")

    def fake_run(*args, **kwargs):
        run_kwargs.update(kwargs)
        return SimpleNamespace(stdout="<html>Tiếng Việt</html>")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert rendered_html_fetch("https://vietstock.vn/example") == "<html>Tiếng Việt</html>"
    assert run_kwargs["encoding"] == "utf-8"
    assert run_kwargs["errors"] == "replace"
