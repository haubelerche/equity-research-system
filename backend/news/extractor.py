"""Content extractor — pull main article text out of HTML (plan §4.5).

Uses the stdlib HTMLParser (no trafilatura/bs4 dependency). The heuristic keeps text inside
content tags (paragraphs, headings, list items) and discards boilerplate containers
(script/style/nav/footer/aside/header/form). Title prefers og:title, then <title>; published
time is read from common article meta tags. This is intentionally simple and deterministic;
per-domain extractor tuning is a Phase-2 concern (plan §13).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser

# Containers whose text is boilerplate and must be dropped.
_SKIP_CONTAINERS = {"script", "style", "nav", "footer", "aside", "header", "form", "noscript"}
# Inline/block tags whose text we keep as article body.
_CONTENT_TAGS = {"p", "h1", "h2", "h3", "h4", "li", "blockquote"}
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class ExtractedContent:
    title: str | None
    text: str
    published_at: str | None


class _ArticleHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._content_depth = 0
        self._in_title_tag = False
        self.title_tag: str | None = None
        self.og_title: str | None = None
        self.published_at: str | None = None
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "meta":
            self._handle_meta(dict(attrs))
            return
        if tag in _SKIP_CONTAINERS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title_tag = True
        if tag in _CONTENT_TAGS and self._skip_depth == 0:
            self._content_depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_CONTAINERS and self._skip_depth > 0:
            self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title_tag = False
        if tag in _CONTENT_TAGS and self._content_depth > 0:
            self._content_depth -= 1
            self._chunks.append("\n")  # paragraph boundary

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title_tag and self.title_tag is None:
            text = data.strip()
            if text:
                self.title_tag = text
            return
        if self._content_depth > 0:
            self._chunks.append(data)

    def _handle_meta(self, attrs: dict[str, str | None]) -> None:
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        content = attrs.get("content")
        if not content:
            return
        if key == "og:title" and self.og_title is None:
            self.og_title = content.strip()
        elif key in {"article:published_time", "pubdate", "publishdate", "date"} and self.published_at is None:
            self.published_at = content.strip()

    @property
    def text(self) -> str:
        joined = "".join(self._chunks)
        paragraphs = [_WHITESPACE.sub(" ", part).strip() for part in joined.split("\n")]
        return " ".join(p for p in paragraphs if p)


def extract_main_content(html: str) -> ExtractedContent:
    """Extract title, main body text, and published time from an article's HTML."""
    parser = _ArticleHTMLParser()
    if html:
        try:
            parser.feed(html)
        except Exception:  # noqa: BLE001 — malformed HTML must not crash extraction
            pass
    title = parser.og_title or parser.title_tag
    return ExtractedContent(title=title, text=parser.text, published_at=parser.published_at)
