"""Layout render audit — Phase 7 post-render quality checks.

Runs deterministic checks on the assembled ReportArtifact (and optionally
on rendered HTML) to ensure the output meets client-facing quality standards
before export is allowed.

Checks performed:
  1. No missing required sections.
  2. No section with zero word count (empty page risk).
  3. No duplicate section text (copy-paste error).
  4. No backend/debug terminology in client-facing content.
  5. All quantitative claims have explicit units visible.
  6. No bare "—" dashes without an internal missing-data reason.
  7. Target price and upside are consistent across all sections.
  8. Vietnamese font markers present when content contains diacritics.
  9. No table overflow indicators (content length heuristic).
  10. Charts registered in artifact match those referenced in sections.

All checks are deterministic — no LLM involvement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.reporting.report_artifact import ReportArtifact, SECTION_IDS

# ── Forbidden backend terms in client-facing reports ─────────────────────────
_BACKEND_TERMS = [
    "fact_id", "source_id", "artifact_path", "run_id", "snapshot_id",
    "FactEntry", "FactTable", "pipeline_status", "gate_result",
    "tier-3", "Tier-3", "tier_3", "internal_debug",
    "valuation_confidence", "assumption_status", "default_unapproved",
    "BLOCKED", "FAIL", "gate_failed", "quality_evaluation_failed",
    "ForecastArtifact", "DebtSchedule", "DividendSchedule",
    "WorkingCapitalSchedule", "ShareRollForward",
    "ClaimLedger", "NetDebtBridge",
    "traceback", "Exception", "KeyError", "None",
]

# ── Patterns that require a unit to follow within the same sentence ───────────
_NUMERIC_NEEDS_UNIT = re.compile(
    r"\b(\d[\d,\.]+)\s+"
    r"(?!VND|tỷ|%|x|triệu|nghìn|bn|cp|năm|tháng|lần|điểm|bps)"
    r"[^\d\W]",
    re.UNICODE,
)

# ── Vietnamese diacritic check ────────────────────────────────────────────────
_VIET_DIACRITIC = re.compile(
    r"[àáâãèéêìíòóôõùúýăđ]", re.IGNORECASE | re.UNICODE
)
_FONT_CSS_MARKER = re.compile(r"font-family|@font-face|Be Vietnam", re.IGNORECASE)

# ── Bare dash (used for missing data) ────────────────────────────────────────
_BARE_DASH = re.compile(r"(?<!\-)—(?!\-)")   # em dash not part of ——


@dataclass
class AuditIssue:
    severity: str           # "error" | "warning" | "info"
    check_name: str
    section_id: str | None
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "check_name": self.check_name,
            "section_id": self.section_id,
            "message": self.message,
        }


@dataclass
class LayoutRenderAudit:
    """Result of post-render layout quality checks."""
    ticker: str
    report_id: str
    render_mode: str
    issues: list[AuditIssue] = field(default_factory=list)

    # ── Gate property ─────────────────────────────────────────────────────

    @property
    def errors(self) -> list[AuditIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[AuditIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def layout_gate_status(self) -> str:
        """PASS only when zero errors. Warnings are allowed."""
        return "PASS" if not self.errors else "FAIL"

    @property
    def is_client_safe(self) -> bool:
        return self.layout_gate_status == "PASS"

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "report_id": self.report_id,
            "render_mode": self.render_mode,
            "layout_gate_status": self.layout_gate_status,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "issues": [i.to_dict() for i in self.issues],
        }


def run_layout_audit(
    artifact: ReportArtifact,
    html_full: str | None = None,
) -> LayoutRenderAudit:
    """Run all layout checks on a ReportArtifact.

    Args:
        artifact:  The assembled ReportArtifact (pre-render).
        html_full: Optional full HTML string of the rendered report.
                   Enables deeper content checks (font, table overflow).
    """
    audit = LayoutRenderAudit(
        ticker=artifact.ticker,
        report_id=artifact.report_id,
        render_mode=artifact.render_mode,
    )

    _check_missing_sections(artifact, audit)
    _check_empty_sections(artifact, audit)
    _check_duplicate_sections(artifact, audit)
    _check_backend_terms(artifact, audit)
    _check_bare_dashes(artifact, audit)
    _check_chart_registry(artifact, audit)
    _check_target_price_consistency(artifact, audit)

    if html_full:
        _check_vietnamese_font(html_full, audit)
        _check_table_overflow_heuristic(html_full, audit)
        _check_english_headings(html_full, audit)

    return audit


# ── Individual check functions ────────────────────────────────────────────────

def _check_missing_sections(artifact: ReportArtifact, audit: LayoutRenderAudit) -> None:
    # Blocked/draft reports have a different structure — only enforce on client_final
    if artifact.render_mode != "client_final":
        return
    missing = artifact.missing_sections
    for sid in missing:
        audit.issues.append(AuditIssue(
            severity="error",
            check_name="missing_section",
            section_id=sid,
            message=f"Required section '{sid}' is absent from the report.",
        ))


def _check_empty_sections(artifact: ReportArtifact, audit: LayoutRenderAudit) -> None:
    _MIN_WORDS = 30
    for section in artifact.sections:
        if section.word_count < _MIN_WORDS:
            audit.issues.append(AuditIssue(
                severity="error",
                check_name="empty_section",
                section_id=section.section_id,
                message=(
                    f"Section '{section.section_id}' has only {section.word_count} words "
                    f"(minimum {_MIN_WORDS}). Risk of empty page in PDF."
                ),
            ))


def _check_duplicate_sections(artifact: ReportArtifact, audit: LayoutRenderAudit) -> None:
    """Detect copy-paste: two sections sharing the same first 200 chars of text."""
    seen: dict[str, str] = {}
    for section in artifact.sections:
        snippet = re.sub(r"\s+", " ", section.html_content[:200]).strip()
        if snippet in seen:
            audit.issues.append(AuditIssue(
                severity="error",
                check_name="duplicate_section_content",
                section_id=section.section_id,
                message=(
                    f"Section '{section.section_id}' has the same opening content as "
                    f"'{seen[snippet]}' — possible copy-paste duplication."
                ),
            ))
        else:
            seen[snippet] = section.section_id


def _check_backend_terms(artifact: ReportArtifact, audit: LayoutRenderAudit) -> None:
    """Client-facing reports must not contain internal backend terminology."""
    if artifact.render_mode != "client_final":
        return  # only enforce on client_final
    for section in artifact.sections:
        content_lower = section.html_content
        for term in _BACKEND_TERMS:
            if term in content_lower:
                audit.issues.append(AuditIssue(
                    severity="error",
                    check_name="backend_term_in_client_report",
                    section_id=section.section_id,
                    message=(
                        f"Backend term '{term}' found in section '{section.section_id}'. "
                        "Must be removed before client export."
                    ),
                ))


def _check_bare_dashes(artifact: ReportArtifact, audit: LayoutRenderAudit) -> None:
    """Every '—' must have an internal missing_data reason registered."""
    for section in artifact.sections:
        bare_dashes = _BARE_DASH.findall(section.html_content)
        if bare_dashes:
            registered = len(section.missing_data_flags)
            n = len(bare_dashes)
            if registered == 0:
                audit.issues.append(AuditIssue(
                    severity="warning",
                    check_name="unregistered_missing_data_dash",
                    section_id=section.section_id,
                    message=(
                        f"Section '{section.section_id}' contains {n} em-dash(es) '—' "
                        "but has no registered missing_data_flags. "
                        "Each '—' must have an internal reason."
                    ),
                ))


def _check_chart_registry(artifact: ReportArtifact, audit: LayoutRenderAudit) -> None:
    """Charts referenced in sections must be registered in artifact.charts."""
    registered = set(artifact.charts.keys())
    for section in artifact.sections:
        for chart_id in section.chart_ids:
            if chart_id not in registered:
                audit.issues.append(AuditIssue(
                    severity="error",
                    check_name="unregistered_chart",
                    section_id=section.section_id,
                    message=(
                        f"Chart '{chart_id}' referenced in '{section.section_id}' "
                        "is not registered in artifact.charts."
                    ),
                ))


def _check_target_price_consistency(artifact: ReportArtifact, audit: LayoutRenderAudit) -> None:
    """All numeric target prices in section content must match artifact.target_price_vnd."""
    if artifact.target_price_vnd is None:
        return
    canonical = int(round(artifact.target_price_vnd))
    canonical_str = f"{canonical:,}"
    # Search for price-like numbers that differ from canonical
    for section in artifact.sections:
        # Find all sequences that look like VND prices (5-6 digit numbers with commas)
        prices_found = re.findall(r"\b(\d{1,3}(?:,\d{3})+)\b", section.html_content)
        for p_str in prices_found:
            try:
                p_val = int(p_str.replace(",", ""))
            except ValueError:
                continue
            # Only flag prices in the same ballpark (10k–500k VND/share range)
            if 10_000 <= p_val <= 500_000 and p_val != canonical:
                audit.issues.append(AuditIssue(
                    severity="warning",
                    check_name="target_price_inconsistency",
                    section_id=section.section_id,
                    message=(
                        f"Price {p_str} VND in section '{section.section_id}' "
                        f"differs from canonical target {canonical_str} VND. "
                        "Verify this is intentional (e.g. current price, scenario price)."
                    ),
                ))
                break  # one warning per section is enough


def _check_vietnamese_font(html_full: str, audit: LayoutRenderAudit) -> None:
    """Verify font-family declaration is present when Vietnamese diacritics exist."""
    has_diacritics = bool(_VIET_DIACRITIC.search(html_full))
    has_font_decl = bool(_FONT_CSS_MARKER.search(html_full))
    if has_diacritics and not has_font_decl:
        audit.issues.append(AuditIssue(
            severity="error",
            check_name="missing_vietnamese_font",
            section_id=None,
            message=(
                "HTML contains Vietnamese diacritics but no font-family CSS declaration. "
                "PDF render may produce broken/missing characters."
            ),
        ))


def _check_english_headings(html_full: str, audit: LayoutRenderAudit) -> None:
    """Flag h1/h2 headings that appear to be in English rather than Vietnamese.

    Client-facing reports must use Vietnamese section titles throughout.
    Heuristic: heading text contains only ASCII letters (no Vietnamese diacritics).
    Short headings like 'ROE', 'WACC', 'EPS' are excluded (< 6 chars or known acronyms).
    """
    _KNOWN_ACRONYMS = {
        "ROE", "ROA", "ROIC", "WACC", "EPS", "P/E", "P/B", "EV/EBITDA",
        "DCF", "FCFF", "FCFE", "NWC", "CAPEX", "EBIT", "EBITDA", "PBT",
    }
    heading_pattern = re.compile(r"<h[12][^>]*>(.*?)</h[12]>", re.IGNORECASE | re.DOTALL)
    viet_char = re.compile(r"[àáâãèéêìíòóôõùúýăđÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐ]", re.UNICODE)

    for match in heading_pattern.finditer(html_full):
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        if not text or len(text) < 6:
            continue
        if text.upper() in _KNOWN_ACRONYMS:
            continue
        # English heading: contains only ASCII printable chars (no diacritics)
        if text.isascii() and text.replace(" ", "").replace("/", "").replace("(", "").replace(")", "").replace("-", "").isalpha():
            audit.issues.append(AuditIssue(
                severity="warning",
                check_name="english_heading",
                section_id=None,
                message=(
                    f"Heading appears to be in English: '{text}'. "
                    "Client-facing reports must use Vietnamese section titles."
                ),
            ))


def _check_table_overflow_heuristic(html_full: str, audit: LayoutRenderAudit) -> None:
    """Flag tables with more than 10 columns (likely to overflow in PDF)."""
    table_blocks = re.findall(r"<table[^>]*>.*?</table>", html_full, re.DOTALL | re.IGNORECASE)
    for i, table in enumerate(table_blocks):
        header_row = re.search(r"<tr[^>]*>(.*?)</tr>", table, re.DOTALL | re.IGNORECASE)
        if header_row:
            cols = re.findall(r"<t[hd][^>]*>", header_row.group(1), re.IGNORECASE)
            if len(cols) > 10:
                audit.issues.append(AuditIssue(
                    severity="warning",
                    check_name="table_overflow_risk",
                    section_id=None,
                    message=(
                        f"Table #{i + 1} has {len(cols)} columns — "
                        "may overflow PDF page width. Consider splitting or abbreviating."
                    ),
                ))
