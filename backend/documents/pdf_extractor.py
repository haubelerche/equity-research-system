"""
Vietnamese BCTC PDF table extractor.

Parses Vietnamese annual report PDFs and extracts financial facts into rows
compatible with extracted_facts.csv.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Label normalization
# ---------------------------------------------------------------------------

def _slug_label(text: str) -> str:
    """Normalize a Vietnamese label to an ASCII slug for matching.

    Steps:
    - NFD decomposition to separate diacritics
    - Drop non-ASCII characters (removes combining marks / diacritics)
    - Lowercase
    - Strip leading/trailing whitespace
    - Collapse internal runs of whitespace to a single space
    """
    normalized = unicodedata.normalize("NFD", text)
    ascii_only = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    # Drop any remaining non-ASCII characters (e.g. đ → d already handled by NFD
    # but đ is a special case: NFD of đ is still đ because it's a base letter)
    # Handle đ/Đ explicitly:
    ascii_only = ascii_only.replace("đ", "d").replace("Đ", "D")
    ascii_only = ascii_only.encode("ascii", errors="ignore").decode("ascii")
    lowered = ascii_only.lower()
    stripped = lowered.strip()
    collapsed = re.sub(r"\s+", " ", stripped)
    return collapsed


# ---------------------------------------------------------------------------
# Value parser
# ---------------------------------------------------------------------------

_NULL_VALUES = {"", "—", "-", "n/a"}


def _parse_vnd_bn(raw: str) -> Optional[float]:
    """Parse a raw Vietnamese financial string to tỷ VND (billions VND).

    Returns None for empty/null markers.
    Handles:
    - Negative values in parentheses: "(273,600)" → -273.6
    - Comma-separated numbers: "4,127,400"
    - Values > 500,000 assumed to be in triệu VND → divide by 1_000 to get tỷ
    - Values ≤ 500,000 assumed already in tỷ VND
    """
    stripped = raw.strip()
    if stripped.lower() in _NULL_VALUES:
        return None

    negative = False
    if stripped.startswith("(") and stripped.endswith(")"):
        negative = True
        stripped = stripped[1:-1]

    # Track whether the raw number had commas (thousands-separator grouping)
    # Commas indicate the value is expressed in triệu VND and needs /1000 scaling.
    has_commas = "," in stripped

    # Remove commas
    stripped = stripped.replace(",", "")

    try:
        value = float(stripped)
    except ValueError:
        return None

    if negative:
        value = -value

    # Scale: values expressed with comma-thousands-separators are in triệu VND.
    # Values > 500,000 (absolute) are also assumed to be in triệu VND even without
    # explicit comma formatting.
    if has_commas or abs(value) > 500_000:
        value = value / 1_000.0

    return round(value, 3)


# ---------------------------------------------------------------------------
# Label → metric mapping
# ---------------------------------------------------------------------------

# Each entry: (compiled regex pattern, metric_id)
# First match wins.
_METRIC_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"doanh thu thuan"), "revenue.net"),
    (re.compile(r"loi nhuan gop"), "gross_profit.total"),
    (re.compile(r"loi nhuan.*hoat dong kinh doanh"), "operating_profit.total"),
    (re.compile(r"loi nhuan.*truoc.*thue"), "profit_before_tax.total"),
    # net_income.parent — several forms
    (re.compile(r"lnst.*cong ty me"), "net_income.parent"),
    (re.compile(r"loi nhuan sau thue.*co dong.*cong ty me"), "net_income.parent"),
    (re.compile(r"loi nhuan sau thue.*co dong cty me"), "net_income.parent"),
    (re.compile(r"loi nhuan sau thue cong ty me"), "net_income.parent"),
    # EPS
    (re.compile(r"lai co ban tren co phieu"), "eps.basic"),
    (re.compile(r"eps co ban"), "eps.basic"),
    (re.compile(r"lai.*co.*phieu"), "eps.basic"),
    # Balance sheet
    (re.compile(r"tong tai san"), "total_assets.ending"),
    (re.compile(r"tong cong tai san"), "total_assets.ending"),
    (re.compile(r"von chu so huu.*cong ty me"), "equity.parent"),
    (re.compile(r"vcsh.*cong ty me"), "equity.parent"),
    (re.compile(r"co dong cong ty me"), "equity.parent"),
    (re.compile(r"vay ngan han"), "short_term_debt.ending"),
    (re.compile(r"no ngan han.*vay"), "short_term_debt.ending"),
    (re.compile(r"vay dai han"), "long_term_debt.ending"),
    (re.compile(r"no dai han.*vay"), "long_term_debt.ending"),
    (re.compile(r"tong no phai tra"), "total_liabilities.ending"),
    (re.compile(r"tien va tuong duong tien"), "cash_and_equivalents.ending"),
    # Cash flow
    (re.compile(r"luu chuyen tien thuan tu hoat dong kinh doanh"), "operating_cash_flow.total"),
    (re.compile(r"mua sam.*tai san co dinh"), "capex.total"),
    (re.compile(r"chi.*mua.*tsc[dđ]"), "capex.total"),
    (re.compile(r"chi mua sam.*tsc[dđ]"), "capex.total"),
    (re.compile(r"mua sam xay dung tsc[dđ]"), "capex.total"),
    (re.compile(r"luu chuyen tien thuan tu hoat dong dau tu"), "investing_cash_flow.total"),
    (re.compile(r"luu chuyen tien thuan tu hoat dong tai chinh"), "financing_cash_flow.total"),
]


def _map_label_to_metric(slug: str) -> Optional[str]:
    """Map a slugged Vietnamese label to a canonical metric_id.

    Returns None if no pattern matches.
    """
    for pattern, metric_id in _METRIC_PATTERNS:
        if pattern.search(slug):
            return metric_id
    return None


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

_CSV_FIELDS = [
    "ticker",
    "fiscal_year",
    "period_type",
    "statement_type",
    "metric_id",
    "value",
    "unit",
    "document_title",
    "page_number",
    "table_name",
    "extracted_text",
    "extraction_method",
    "verified_by",
    "verified_at",
]


@dataclass
class ExtractedRow:
    ticker: str
    fiscal_year: int
    period_type: str
    statement_type: str
    metric_id: str
    value: float
    unit: str
    document_title: str
    page_number: int
    table_name: str
    extracted_text: str
    extraction_method: str
    verified_by: str
    verified_at: str

    def to_csv_dict(self) -> dict[str, str]:
        """Return all fields as a flat string dict for CSV writing."""
        return {
            "ticker": str(self.ticker),
            "fiscal_year": str(self.fiscal_year),
            "period_type": str(self.period_type),
            "statement_type": str(self.statement_type),
            "metric_id": str(self.metric_id),
            "value": str(self.value),
            "unit": str(self.unit),
            "document_title": str(self.document_title),
            "page_number": str(self.page_number),
            "table_name": str(self.table_name),
            "extracted_text": str(self.extracted_text),
            "extraction_method": str(self.extraction_method),
            "verified_by": str(self.verified_by),
            "verified_at": str(self.verified_at),
        }


# ---------------------------------------------------------------------------
# Extractor class
# ---------------------------------------------------------------------------

_INCOME_MARKERS = {"ket qua hoat dong kinh doanh", "bao cao kqkd", "income", "doanh thu"}
_BALANCE_MARKERS = {"can doi ke toan", "bang can doi", "balance sheet", "bcdk"}
_CASHFLOW_MARKERS = {"luu chuyen tien", "cash flow", "lctt"}


def _detect_statement_type(slug_text: str) -> Optional[str]:
    """Detect financial statement type from slugged page text."""
    for marker in _INCOME_MARKERS:
        if marker in slug_text:
            return "income_statement"
    for marker in _BALANCE_MARKERS:
        if marker in slug_text:
            return "balance_sheet"
    for marker in _CASHFLOW_MARKERS:
        if marker in slug_text:
            return "cash_flow_statement"
    return None


class VietnameseBCTCExtractor:
    """Extracts financial facts from Vietnamese BCTC (financial statements) PDFs."""

    def __init__(
        self,
        ticker: str,
        fiscal_year: int,
        document_title: str,
        page_number: int = 0,
        extraction_method: str = "pdf_table",
    ) -> None:
        self.ticker = ticker
        self.fiscal_year = fiscal_year
        self.document_title = document_title
        self.page_number = page_number
        self.extraction_method = extraction_method

    def extract_from_table_rows(
        self,
        rows: list[list[str]],
        *,
        statement_type: str,
        fiscal_years: list[int],
        table_name: str = "",
    ) -> list[ExtractedRow]:
        """Extract financial facts from a list of table rows.

        Args:
            rows: Each row is a list of strings. rows[i][0] is the Vietnamese
                  label; rows[i][1..n] are values corresponding to fiscal_years.
            statement_type: e.g. "income_statement", "balance_sheet", "cash_flow_statement"
            fiscal_years: List of int matching column order (e.g. [2023, 2022]).
            table_name: Optional descriptive name for the table.

        Returns:
            List of ExtractedRow (only recognized metrics with parseable values).
        """
        results: list[ExtractedRow] = []

        for row in rows:
            if not row:
                continue
            label = row[0] if row[0] else ""
            slug = _slug_label(label)
            metric_id = _map_label_to_metric(slug)
            if metric_id is None:
                continue

            # Determine unit: EPS is in VND/share, everything else in VND billions
            unit = "vnd" if metric_id == "eps.basic" else "vnd_bn"

            # Process each value column
            for col_idx, fy in enumerate(fiscal_years):
                value_col = col_idx + 1  # column 0 is the label
                if value_col >= len(row):
                    continue
                raw_value = row[value_col]
                parsed = _parse_vnd_bn(raw_value)
                if parsed is None:
                    continue

                results.append(
                    ExtractedRow(
                        ticker=self.ticker,
                        fiscal_year=fy,
                        period_type="annual",
                        statement_type=statement_type,
                        metric_id=metric_id,
                        value=parsed,
                        unit=unit,
                        document_title=self.document_title,
                        page_number=self.page_number,
                        table_name=table_name,
                        extracted_text=label,
                        extraction_method=self.extraction_method,
                        verified_by="",
                        verified_at="",
                    )
                )

        return results

    def extract_from_pdf(self, pdf_path: Path) -> list[ExtractedRow]:
        """Extract all financial facts from a Vietnamese BCTC PDF.

        Uses pdfplumber if available. Returns [] gracefully on any error.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            List of ExtractedRow instances.
        """
        try:
            import pdfplumber  # type: ignore
        except ImportError:
            return []

        results: list[ExtractedRow] = []

        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    try:
                        # Detect statement type from page text
                        page_text = page.extract_text() or ""
                        slug_text = _slug_label(page_text)
                        statement_type = _detect_statement_type(slug_text)
                        if statement_type is None:
                            continue

                        tables = page.extract_tables()
                        if not tables:
                            continue

                        for table in tables:
                            if not table or len(table) < 3:
                                continue

                            # Extract fiscal years from header row (first row)
                            header_row = table[0] or []
                            fiscal_years: list[int] = []
                            for cell in header_row:
                                if cell:
                                    found_years = re.findall(r"(20\d{2})", str(cell))
                                    fiscal_years.extend(int(y) for y in found_years)

                            # Deduplicate while preserving order
                            seen: set[int] = set()
                            unique_years: list[int] = []
                            for y in fiscal_years:
                                if y not in seen:
                                    seen.add(y)
                                    unique_years.append(y)
                            fiscal_years = unique_years

                            if not fiscal_years:
                                fiscal_years = [self.fiscal_year]

                            # Process data rows (skip header row)
                            extractor = VietnameseBCTCExtractor(
                                ticker=self.ticker,
                                fiscal_year=self.fiscal_year,
                                document_title=self.document_title,
                                page_number=page_num,
                                extraction_method=self.extraction_method,
                            )
                            rows = table[1:]  # skip header
                            extracted = extractor.extract_from_table_rows(
                                rows=[
                                    [str(cell) if cell is not None else "" for cell in row]
                                    for row in rows
                                ],
                                statement_type=statement_type,
                                fiscal_years=fiscal_years,
                                table_name="",
                            )
                            results.extend(extracted)

                    except Exception:
                        # Skip problematic pages gracefully
                        continue

        except Exception:
            # Return empty list on any file-level error
            return []

        return results


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def extract_to_csv(
    pdf_path: Path,
    ticker: str,
    fiscal_year: int,
    document_title: str,
    output_csv: Path,
) -> list[ExtractedRow]:
    """Extract facts from a PDF and write them to a CSV file.

    Args:
        pdf_path: Path to the source PDF.
        ticker: Stock ticker symbol (e.g. "DHG").
        fiscal_year: Primary fiscal year of the document.
        document_title: Human-readable title of the document.
        output_csv: Path to write the output CSV.

    Returns:
        List of ExtractedRow instances (may be empty).
    """
    extractor = VietnameseBCTCExtractor(
        ticker=ticker,
        fiscal_year=fiscal_year,
        document_title=document_title,
    )
    rows = extractor.extract_from_pdf(pdf_path)

    if rows:
        output_csv = Path(output_csv)
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow(row.to_csv_dict())

    return rows
