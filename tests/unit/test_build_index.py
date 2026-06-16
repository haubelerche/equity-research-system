from __future__ import annotations

import csv

from scripts import build_index


def test_local_golden_facts_supply_missing_accepted_share_count(tmp_path, monkeypatch):
    golden_dir = tmp_path / "config" / "benchmarks" / "shared" / "golden_financials"
    golden_dir.mkdir(parents=True)
    with (golden_dir / "DHG.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "ticker",
                "fiscal_year",
                "period",
                "statement_type",
                "canonical_key",
                "raw_label",
                "value",
                "unit",
                "currency",
                "source_type",
                "source_uri",
                "source_title",
                "provider",
                "confidence",
                "validation_status",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "ticker": "DHG",
            "fiscal_year": "2022",
            "period": "2022FY",
            "statement_type": "capital_structure",
            "canonical_key": "shares_outstanding.ending",
            "raw_label": "shares_outstanding_derived_from_net_income_and_eps",
            "value": "135071693",
            "unit": "shares",
            "currency": "VND",
            "source_type": "financial_statement",
            "source_uri": "local://data/raw/bctc/DHG/ratio_year.json",
            "source_title": "Derived shares from local raw BCTC cache DHG 2022FY",
            "provider": "local_raw_cache",
            "confidence": "0.85",
            "validation_status": "accepted",
        })
        writer.writerow({
            "ticker": "DHG",
            "fiscal_year": "2023",
            "period": "2023FY",
            "statement_type": "capital_structure",
            "canonical_key": "shares_outstanding.ending",
            "raw_label": "future row outside requested years",
            "value": "1",
            "unit": "shares",
            "currency": "VND",
            "source_type": "financial_statement",
            "source_uri": "local://ignored",
            "source_title": "ignored",
            "provider": "local_raw_cache",
            "confidence": "0.85",
            "validation_status": "accepted",
        })

    monkeypatch.setattr(build_index, "ROOT", tmp_path)

    facts = build_index._get_local_golden_facts("DHG", [2022])

    assert facts == [{
        "id": "golden_csv:DHG:2022:shares_outstanding.ending",
        "ticker": "DHG",
        "fiscal_year": 2022,
        "fiscal_period": "FY",
        "line_item_code": "shares_outstanding.ending",
        "value": 135071693.0,
        "unit": "shares",
        "currency": "VND",
        "statement_type": "capital_structure",
    }]


def test_fact_chunks_include_share_count_label():
    build_index.ticker_placeholder = "DHG"

    chunks = build_index._build_fact_chunks([
        {
            "ticker": "DHG",
            "fiscal_year": 2022,
            "fiscal_period": "FY",
            "line_item_code": "shares_outstanding.ending",
            "value": 135071693.0,
            "unit": "shares",
            "currency": "VND",
            "statement_type": "capital_structure",
        }
    ])

    assert "Số cổ phiếu lưu hành cuối kỳ" in chunks[0][1]
    assert "135071693.0 shares" in chunks[0][1]


def test_fact_chunks_do_not_add_thousands_separator_to_vnd_bn():
    build_index.ticker_placeholder = "DHG"

    chunks = build_index._build_fact_chunks([
        {
            "ticker": "DHG",
            "fiscal_year": 2023,
            "fiscal_period": "FY",
            "line_item_code": "revenue.net",
            "value": 5015.395,
            "unit": "vnd_bn",
            "currency": "VND",
            "statement_type": "income_statement",
        }
    ])

    assert "5015.395 tỷ VND" in chunks[0][1]
    assert "5,015.395 tỷ VND" not in chunks[0][1]
