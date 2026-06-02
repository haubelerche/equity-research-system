from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Iterable

import yaml


ROOT = Path(__file__).resolve().parents[2]
MVP_SCOPE_FILE = ROOT / "config" / "dataset" / "mvp" / "mvp5_scope.yaml"
OUTPUT_FACTS = ROOT / "config" / "dataset" / "mvp" / "financial_facts_bootstrap.csv"
OUTPUT_EPS = ROOT / "config" / "dataset" / "mvp" / "eps_actuals_bootstrap.csv"


@dataclass
class FactRow:
    company_ticker: str
    fiscal_year: int
    fiscal_period: str
    taxonomy_key: str


def _iter_rows(tickers: list[str], taxonomy_keys: list[str], years: Iterable[int]) -> Iterable[FactRow]:
    for ticker in tickers:
        for year in years:
            for taxonomy_key in taxonomy_keys:
                yield FactRow(
                    company_ticker=ticker,
                    fiscal_year=year,
                    fiscal_period="FY",
                    taxonomy_key=taxonomy_key,
                )


def main() -> None:
    with MVP_SCOPE_FILE.open("r", encoding="utf-8") as f:
        scope = yaml.safe_load(f)

    tickers: list[str] = scope["tickers"]
    taxonomy_keys: list[str] = scope["required_taxonomy_keys"]
    target_years = int(scope["history_requirement"]["target_years"])

    current_year = datetime.now(UTC).year
    years = [current_year - i for i in range(1, target_years + 1)]
    now_iso = datetime.now(UTC).isoformat()

    fact_fields = [
        "company_ticker",
        "fiscal_year",
        "fiscal_period",
        "taxonomy_key",
        "value",
        "unit",
        "currency",
        "source_version_id",
        "source_uri",
        "parser_version",
        "validation_status",
        "confidence",
        "effective_date",
        "reconciled_at",
        "ingested_at",
    ]

    with OUTPUT_FACTS.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fact_fields)
        writer.writeheader()
        for row in _iter_rows(tickers, taxonomy_keys, years):
            writer.writerow(
                {
                    "company_ticker": row.company_ticker,
                    "fiscal_year": row.fiscal_year,
                    "fiscal_period": row.fiscal_period,
                    "taxonomy_key": row.taxonomy_key,
                    "value": "",
                    "unit": "vnd_bn",
                    "currency": "VND",
                    "source_version_id": "",
                    "source_uri": "",
                    "parser_version": "bctc_parser_v1",
                    "validation_status": "needs_review",
                    "confidence": "",
                    "effective_date": "",
                    "reconciled_at": "",
                    "ingested_at": now_iso,
                }
            )

    eps_fields = [
        "company_ticker",
        "fiscal_year",
        "fiscal_period",
        "eps_basic_vnd",
        "source_version_id",
        "source_uri",
        "parser_version",
        "validation_status",
        "confidence",
        "ingested_at",
    ]
    with OUTPUT_EPS.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=eps_fields)
        writer.writeheader()
        for ticker in tickers:
            for year in years:
                writer.writerow(
                    {
                        "company_ticker": ticker,
                        "fiscal_year": year,
                        "fiscal_period": "FY",
                        "eps_basic_vnd": "",
                        "source_version_id": "",
                        "source_uri": "",
                        "parser_version": "bctc_parser_v1",
                        "validation_status": "needs_review",
                        "confidence": "",
                        "ingested_at": now_iso,
                    }
                )

    print(f"Wrote bootstrap facts: {OUTPUT_FACTS}")
    print(f"Wrote bootstrap EPS: {OUTPUT_EPS}")


if __name__ == "__main__":
    main()
