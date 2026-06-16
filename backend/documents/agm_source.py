"""Parse + group AGM (ĐHCĐ) decision-PDF filenames collected in config/dataset/DHCD.

These are the 2026 annual-general-meeting packets (nghị quyết + báo cáo HĐQT / ban
giám đốc + kế hoạch 2026 + tờ trình) — a forward-looking *internal driver* source,
distinct from the audited annual report. Filenames are messy and human-named
("DHG DHCD 2026(1).pdf", "dtp dhcd 2026.pdf", "NDC HDCD 2026(1).pdf"); a ticker may
span several part files, ordered here by part.

Only the pure filename parsing lives here. The filesystem glob + OCR page loading live
in scripts/ingest_agm.py (the backend run-path never touches the local filesystem)."""
from __future__ import annotations

import re
from pathlib import Path

# "<TICKER> (DHCD|HDCD) <YEAR>[ (part)]" — HDCD is a real typo in the corpus.
_AGM_RE = re.compile(
    r"^(?P<ticker>\S+)\s+(?:dhcd|hdcd)\s+(?P<year>\d{4})(?!\d)\s*(?:\((?P<part>\d+)\))?",
    re.IGNORECASE,
)


def parse_agm_filename(name: str) -> tuple[str, int, int] | None:
    """Parse one AGM filename into (TICKER, meeting_year, part).

    part is 0 for an unnumbered (base) file, else the (n) suffix. Returns None for
    files that are not AGM packets."""
    stem = Path(name).stem
    m = _AGM_RE.match(stem)
    if not m:
        return None
    part = int(m.group("part")) if m.group("part") else 0
    return m.group("ticker").upper(), int(m.group("year")), part


def group_agm_files(paths: list[Path]) -> dict[str, list[Path]]:
    """Group AGM PDFs by ticker, ordered by part (base file first). Non-AGM files
    are ignored."""
    buckets: dict[str, list[tuple[int, Path]]] = {}
    for p in paths:
        parsed = parse_agm_filename(p.name)
        if parsed is None:
            continue
        ticker, _year, part = parsed
        buckets.setdefault(ticker, []).append((part, p))
    return {
        ticker: [p for _part, p in sorted(items, key=lambda ip: (ip[0], ip[1].name))]
        for ticker, items in buckets.items()
    }
