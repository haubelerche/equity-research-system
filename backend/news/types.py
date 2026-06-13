"""Shared dataclasses for the whitelisted news-research subsystem."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

# The four approved official sources. The single source of truth for the whitelist.
ALLOWED_DOMAINS: frozenset[str] = frozenset(
    {
        "vnexpress.net",
        "vneconomy.vn",
        "cafef.vn",
        "vietstock.vn",
    }
)

# Citation allowlist — a superset of the discovery whitelist. Automated discovery stays
# restricted to ALLOWED_DOMAINS, but a human-vetted article (manual ingest) may be cited
# from this wider set of reputable Vietnamese financial outlets and official company /
# exchange / regulator sites. A URL outside this set is never stored or cited.
CITATION_ALLOWED_DOMAINS: frozenset[str] = ALLOWED_DOMAINS | frozenset(
    {
        # Reputable financial media
        "tinnhanhchungkhoan.vn",
        "mekongasean.vn",
        "baodautu.vn",
        # Official company / exchange / regulator
        "dhgpharma.com.vn",
        "hsx.vn",
        "hnx.vn",
    }
)

# Discovery methods, in the plan's priority order (plan §4.2).
DISCOVERY_METHODS: frozenset[str] = frozenset({"rss", "sitemap", "search"})

# Human-readable source names keyed by approved domain (for citations and source_name fields).
SOURCE_DISPLAY_NAMES: dict[str, str] = {
    "vnexpress.net": "VnExpress",
    "vneconomy.vn": "VnEconomy",
    "cafef.vn": "CafeF",
    "vietstock.vn": "Vietstock",
    "tinnhanhchungkhoan.vn": "Tin nhanh Chứng khoán",
    "mekongasean.vn": "Mekong ASEAN",
    "baodautu.vn": "Báo Đầu tư",
    "dhgpharma.com.vn": "DHG Pharma",
    "hsx.vn": "HOSE",
    "hnx.vn": "HNX",
}


def source_name_for_domain(domain: str) -> str:
    """Return a display name for an approved domain, falling back to the domain itself."""
    return SOURCE_DISPLAY_NAMES.get(domain.lower(), domain.lower())


@dataclass(frozen=True)
class ResearchPlan:
    """Parsed research request: what to look for and where (plan §4.1)."""

    topic: str
    keywords: tuple[str, ...]
    allowed_domains: tuple[str, ...]
    ticker: str | None = None
    company_name: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ArticleCandidate:
    """A discovered candidate URL — metadata only, not yet fetched (plan §4.2)."""

    source_url: str
    source_domain: str
    source_name: str
    title: str | None = None
    published_at: str | None = None
    summary: str | None = None
    discovery_method: str = "rss"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RawArticle:
    """A fetched + extracted article ready to be stored in news.raw_articles (plan §4.5)."""

    source_name: str
    source_domain: str
    source_url: str
    title: str | None
    raw_text: str
    published_at: str | None = None
    accessed_at: str | None = None
    summary: str | None = None
    discovery_method: str = "rss"
    extraction_method: str = "stdlib_htmlparser"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceItem:
    """A factual claim extracted from one article, with its supporting passage (plan §6)."""

    claim: str
    evidence_text: str
    source_name: str
    source_domain: str
    source_url: str
    evidence_type: str | None = None
    confidence: str = "medium"
    topic: str | None = None
    ticker: str | None = None
    company_name: str | None = None
    published_at: str | None = None
    accessed_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvidencePacket:
    """The bundle handed to the Editor agent — verified evidence, never raw web access (plan §7.2)."""

    topic: str
    allowed_domains: tuple[str, ...]
    evidence: tuple[EvidenceItem, ...]
    ticker: str | None = None
    company_name: str | None = None

    def to_dict(self) -> dict:
        return {
            "topic": self.topic,
            "ticker": self.ticker,
            "company_name": self.company_name,
            "allowed_domains": list(self.allowed_domains),
            "evidence": [item.to_dict() for item in self.evidence],
        }
