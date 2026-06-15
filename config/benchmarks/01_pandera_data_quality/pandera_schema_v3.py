from __future__ import annotations

import pandas as pd

REQUIRED_COLUMNS = {
    "ticker", "fiscal_year", "period", "statement_type", "canonical_key", "value", "unit",
    "currency", "source_type", "source_uri", "source_title", "provider", "confidence",
    "validation_status", "snapshot_id", "fact_id", "source_doc_id", "source_tier",
    "reconciliation_status", "freshness_status", "promotion_status", "ocr_status",
    "materiality", "canonical_version", "dataset_version",
}
ALLOWED_PROMOTION = {"candidate", "promoted", "blocked", "rejected"}
ALLOWED_RECONCILIATION = {"matched_official", "manual_reviewed", "not_required", "failed", "pending"}
ALLOWED_FRESHNESS = {"fresh", "stale", "unknown"}
MATERIAL_KEYS = {"revenue.net", "net_income.parent", "total_assets.ending", "equity.parent", "shares_outstanding.ending"}


def validate_facts_v3(df: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")
    if not (df["period"].astype(str).str[:4].astype(int) == df["fiscal_year"].astype(int)).all():
        raise ValueError("period/fiscal_year mismatch")
    accepted = df[df["validation_status"].eq("accepted")]
    if accepted.duplicated(["ticker", "period", "canonical_key", "source_tier"]).any():
        raise ValueError("duplicate canonical fact")
    if accepted["source_doc_id"].isna().any() or (accepted["source_doc_id"].astype(str).str.len() == 0).any():
        raise ValueError("accepted facts require source_doc_id")
    if accepted["snapshot_id"].isna().any() or (accepted["snapshot_id"].astype(str).str.len() == 0).any():
        raise ValueError("accepted facts require snapshot_id")
    if not accepted["promotion_status"].isin(ALLOWED_PROMOTION).all():
        raise ValueError("invalid promotion_status")
    material = accepted[accepted["canonical_key"].isin(MATERIAL_KEYS)]
    if (material["source_tier"].astype(int) > 2).any():
        raise ValueError("material facts cannot rely on weak source tier")
    if material["reconciliation_status"].isin({"failed", "pending"}).any():
        raise ValueError("material reconciliation unresolved")
    if material["freshness_status"].eq("stale").any():
        raise ValueError("material snapshot stale")
    blocked_ocr_material = accepted[(accepted["ocr_status"].eq("ocr")) & (accepted["promotion_status"].ne("promoted"))]
    if len(blocked_ocr_material):
        raise ValueError("OCR material candidate not promoted")
    return df
