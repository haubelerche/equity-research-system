from __future__ import annotations

import pandas as pd
import pandera as pa
from pandera import Column, Check, DataFrameSchema

ALLOWED_STATEMENTS = ["income_statement", "balance_sheet", "cash_flow", "capital_structure"]
ALLOWED_UNITS = ["vnd_bn", "vnd", "shares", "ratio", "percent", "unknown"]
ALLOWED_STATUS = ["accepted", "missing", "rejected", "needs_review"]
ALLOWED_SOURCE_TYPES = [
    "annual_report",
    "audited_financial_statement",
    "disclosure",
    "financial_statement",
    "official_document",
    "ocr_extracted",
]
MATERIAL_VALUE_KEYS = [
    "revenue.net",
    "gross_profit.total",
    "net_income.parent",
    "eps.basic",
    "total_assets.ending",
    "equity.parent",
    "cash_and_equivalents.ending",
    "operating_cash_flow.total",
    "capex.total",
    "shares_outstanding.ending",
]

fact_schema = DataFrameSchema(
    {
        "ticker": Column(str, Check.str_matches(r"^[A-Z0-9]{2,4}$"), nullable=False),
        "fiscal_year": Column(int, Check.in_range(2015, 2030), nullable=False),
        "period": Column(str, Check.str_matches(r"^[0-9]{4}(FY|Q[1-4]|YTD)$"), nullable=False),
        "statement_type": Column(str, Check.isin(ALLOWED_STATEMENTS), nullable=False),
        "canonical_key": Column(str, Check.str_length(3, 128), nullable=False),
        "raw_label": Column(str, nullable=True),
        "value": Column(float, nullable=True),
        "unit": Column(str, Check.isin(ALLOWED_UNITS), nullable=False),
        "currency": Column(str, Check.isin(["VND", "N/A"]), nullable=False),
        "source_type": Column(str, Check.isin(ALLOWED_SOURCE_TYPES), nullable=False),
        "source_uri": Column(str, Check.str_length(1, None), nullable=False),
        "source_title": Column(str, Check.str_length(1, None), nullable=False),
        "provider": Column(str, Check.str_length(1, None), nullable=False),
        "confidence": Column(float, Check.in_range(0, 1), nullable=False),
        "validation_status": Column(str, Check.isin(ALLOWED_STATUS), nullable=False),
    },
    checks=[
        Check(lambda df: (df["period"].str[:4].astype(int) == df["fiscal_year"]).all(), error="period_matches_fiscal_year"),
        Check(lambda df: df[df["validation_status"].eq("accepted")].duplicated(["ticker", "fiscal_year", "period", "canonical_key"]).sum() == 0, error="duplicate_accepted_fact"),
        Check(lambda df: (df.loc[df["validation_status"].eq("accepted"), "confidence"] >= 0.85).all(), error="accepted_fact_confidence_min"),
        Check(lambda df: df.loc[df["validation_status"].eq("accepted") & df["canonical_key"].isin(MATERIAL_VALUE_KEYS), "value"].notna().all(), error="material_fact_null_without_missing_reason"),
        Check(lambda df: (df.loc[df["canonical_key"].isin(["revenue.net", "total_assets.ending", "equity.parent", "shares_outstanding.ending"]), "value"].dropna() >= 0).all(), error="non_negative_material_metrics"),
    ],
    strict=False,
    coerce=True,
)


def validate_facts(df: pd.DataFrame) -> pd.DataFrame:
    """Return the validated dataframe or raise pandera.errors.SchemaError."""
    return fact_schema.validate(df, lazy=True)
