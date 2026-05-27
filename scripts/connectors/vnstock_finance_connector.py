from __future__ import annotations

import argparse
import csv
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

# Ensure pip-installed vnstock is found before the local vnstock/ namespace folder.
if "" in sys.path:
    sys.path = [p for p in sys.path if p != ""] + [""]

import unicodedata

import pandas as pd
from vnstock.api.financial import Finance

from scripts.dataset.config_io import ROOT, load_financial_taxonomy, load_universe_tickers
from scripts.dataset.dqf import validate_financial_fact
from scripts.db.fact_store import FinancialFact, PostgresFactStore
from scripts.db.source_registry import SourceInput, SourceRegistry


CONNECTOR_VERSION = "vn_finance_v2"

MVP_FROM_YEAR = 2021
MVP_TO_YEAR = 2025
# Regex for an accepted annual period key e.g. "2024FY"
_FY_PERIOD_RE = re.compile(r"^(\d{4})FY$")

# Raw VND values from vnstock API are divided by this to produce vnd_bn units.
_VND_BN_DIVISOR = 1_000_000_000.0

# Path for unmatched line item audit CSV.
_UNMATCHED_AUDIT_PATH = ROOT / "artifacts" / "data_quality" / "unmatched_financial_items.csv"
_UNMATCHED_FIELDNAMES = [
    "run_id", "ticker", "provider", "statement_type", "period_type",
    "fiscal_year", "fiscal_period", "raw_label", "normalized_label", "raw_value",
]


def _slug(text: str) -> str:
    # Normalize Unicode (e.g. Vietnamese diacritics: "thuần" → "thuan") before slugifying.
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.strip().lower().replace("-", "_").replace("/", "_")
    text = re.sub(r"[^a-z0-9_ ]+", "", text)
    text = text.replace(" ", "_")
    text = re.sub(r"_+", "_", text)
    return text


def _period_from_column(name: str) -> tuple[int, str] | None:
    cleaned = name.strip().upper()
    year_match = re.search(r"(20\d{2})", cleaned)
    if not year_match:
        return None
    year = int(year_match.group(1))
    quarter_match = re.search(r"Q([1-4])", cleaned)
    if quarter_match:
        return year, f"Q{quarter_match.group(1)}"
    if "FY" in cleaned or "NAM" in cleaned or "YEAR" in cleaned:
        return year, "FY"
    return year, "FY"


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.replace(",", "").replace(".", "", value.count(".") - 1).strip()
        if stripped in {"", "-", "nan", "None"}:
            return None
        try:
            return float(stripped)
        except ValueError:
            try:
                return float(value.replace(",", ""))
            except ValueError:
                return None
    return None


def _extract_rows(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Return (label_frame, value_columns).

    label_frame has columns: 'primary' (Vietnamese item), and optionally 'en' (item_en), 'id' (item_id).
    value_columns are the period columns (e.g. '2025-Q4').
    """
    if frame.empty:
        return pd.DataFrame(), []
    value_columns = [col for col in frame.columns if _period_from_column(str(col))]
    label_frame = pd.DataFrame(index=frame.index)
    label_frame["primary"] = frame.iloc[:, 0].astype(str)
    if "item_en" in frame.columns:
        label_frame["en"] = frame["item_en"].astype(str)
    if "item_id" in frame.columns:
        label_frame["id"] = frame["item_id"].astype(str)
    return label_frame, value_columns


def _build_alias_map(statement: str | None = None) -> dict[str, tuple[str, str]]:
    """Build slug → (taxonomy_key, unit) mapping, optionally filtered by statement type.

    statement values match taxonomy 'statement' field: income_statement, balance_sheet,
    cash_flow, derived.  Pass None to include all.
    """
    taxonomy = load_financial_taxonomy()
    mapping: dict[str, tuple[str, str]] = {}
    for taxonomy_key, config in taxonomy["taxonomy"].items():
        if statement and config.get("statement") != statement:
            continue
        unit = config.get("unit", "vnd_bn")
        mapping[_slug(taxonomy_key)] = (taxonomy_key, unit)
        for alias in config.get("aliases", []):
            mapping[_slug(str(alias))] = (taxonomy_key, unit)
        label_vi = config.get("label_vi")
        if label_vi:
            mapping[_slug(str(label_vi))] = (taxonomy_key, unit)
    return mapping


def _resolve_label(label_row: "pd.Series[str]", alias_map: dict[str, tuple[str, str]]) -> tuple[str, str] | None:
    """Try primary Vietnamese label, then English label, then item_id to resolve taxonomy key."""
    for col in ("primary", "en", "id"):
        if col not in label_row.index:
            continue
        resolved = alias_map.get(_slug(label_row[col]))
        if resolved is not None:
            return resolved
    return None


def _append_unmatched(
    run_id: str,
    ticker: str,
    provider: str,
    statement_type: str,
    period_type: str,
    raw_label: str,
    normalized_label: str,
    frame: pd.DataFrame,
    idx: Any,
    value_columns: list[str],
) -> None:
    """Append unmatched rows to the audit CSV."""
    _UNMATCHED_AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_exists = _UNMATCHED_AUDIT_PATH.exists()
    with _UNMATCHED_AUDIT_PATH.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_UNMATCHED_FIELDNAMES, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        for col in value_columns:
            parsed = _period_from_column(str(col))
            fiscal_year = parsed[0] if parsed else None
            fiscal_period = parsed[1] if parsed else None
            raw_val = frame.at[idx, col] if col in frame.columns else None
            writer.writerow({
                "run_id": run_id,
                "ticker": ticker,
                "provider": provider,
                "statement_type": statement_type,
                "period_type": period_type,
                "fiscal_year": fiscal_year,
                "fiscal_period": fiscal_period,
                "raw_label": raw_label,
                "normalized_label": normalized_label,
                "raw_value": raw_val,
            })


def _extract_facts_from_frame(
    ticker: str,
    frame: pd.DataFrame,
    source_id: str,
    parser_version: str,
    alias_map: dict[str, tuple[str, str]],
    run_id: str,
    provider: str,
    statement_type: str,
    period_type: str,
) -> list[FinancialFact]:
    label_frame, value_columns = _extract_rows(frame)
    if label_frame.empty:
        return []

    facts: list[FinancialFact] = []
    now = datetime.now(UTC)
    for idx, label_row in label_frame.iterrows():
        resolved = _resolve_label(label_row, alias_map)
        if resolved is None:
            raw_label = str(label_row.get("primary", ""))
            normalized_label = _slug(raw_label)
            if raw_label and raw_label not in ("nan", "None", ""):
                _append_unmatched(
                    run_id=run_id,
                    ticker=ticker,
                    provider=provider,
                    statement_type=statement_type,
                    period_type=period_type,
                    raw_label=raw_label,
                    normalized_label=normalized_label,
                    frame=frame,
                    idx=idx,
                    value_columns=value_columns,
                )
            continue
        line_item_code, unit = resolved
        for column in value_columns:
            parsed_period = _period_from_column(str(column))
            if parsed_period is None:
                continue
            raw_value = _to_number(frame.at[idx, column])
            if raw_value is None:
                continue
            # Normalize raw VND to the declared unit.
            value = raw_value / _VND_BN_DIVISOR if unit == "vnd_bn" else raw_value
            fiscal_year, fiscal_period = parsed_period
            payload = {
                "ticker": ticker,
                "fiscal_year": fiscal_year,
                "fiscal_period": fiscal_period,
                "line_item_code": line_item_code,
                "value": value,
                "unit": unit,
                "currency": "VND",
                "source_id": source_id,
                "connector_version": parser_version,
                "validation_status": "accepted",
                "confidence": 0.95,
                "ingested_at": now.isoformat(),
            }
            dqf = validate_financial_fact(payload)
            facts.append(
                FinancialFact(
                    ticker=ticker,
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    line_item_code=line_item_code,
                    value=value,
                    unit=unit,
                    currency="VND",
                    source_id=source_id,
                    connector_version=parser_version,
                    validation_status=dqf.status if dqf.status != "rejected" else "needs_review",
                    confidence=dqf.confidence,
                    effective_date=None,
                    ingested_at=now,
                )
            )
    return facts


def _finance_frames(ticker: str, source: str, period: str) -> dict[str, pd.DataFrame]:
    client = Finance(source=source, symbol=ticker, period=period)
    return {
        "income_statement": client.income_statement(period=period, lang="vi"),
        "balance_sheet": client.balance_sheet(period=period, lang="vi"),
        "cash_flow": client.cash_flow(period=period, lang="vi"),
        "ratio": client.ratio(period=period, lang="vi"),
    }


def _register_source_version(
    registry: SourceRegistry,
    ticker: str,
    source: str,
    statement: str,
    period: str,
    frame: pd.DataFrame,
) -> str:
    payload = frame.to_json(date_format="iso", orient="split").encode("utf-8")
    source_uri = f"vnstock://{source.lower()}/finance/{statement}/{ticker}?period={period}"
    raw_path = ROOT / "dataset" / "raw" / "bctc" / ticker / f"{statement}_{period}.json"
    checksum = registry.save_raw_snapshot(payload=payload, out_path=raw_path)
    return registry.register_source(
        SourceInput(
            logical_id="bctc_disclosure",
            source_uri=source_uri,
            source_type="financial_statement",
            checksum=checksum,
            connector_version=CONNECTOR_VERSION,
            raw_path=str(raw_path),
            published_at=datetime.now(UTC).isoformat(),
            metadata_json={"provider": source, "period": period},
        )
    )


def sync_financial_for_ticker(
    ticker: str,
    store: PostgresFactStore,
    registry: SourceRegistry,
    period: str = "year",
    from_year: int = MVP_FROM_YEAR,
    to_year: int = MVP_TO_YEAR,
    provider: str = "auto",
) -> int:
    """Ingest annual financial statements for one ticker.

    For MVP, only ``period='year'`` is accepted.  Facts whose fiscal year falls
    outside [from_year, to_year] are silently dropped before upsert so the DB
    stays clean of out-of-range or quarterly rows introduced by the vnstock API.

    Args:
        ticker: Uppercase ticker symbol, e.g. 'DHG'.
        store: Fact store instance.
        registry: Source registry instance.
        period: Must be 'year' for MVP — 'quarter' is rejected.
        from_year: First fiscal year to keep (default 2021).
        to_year: Last fiscal year to keep (default 2025).
        provider: 'auto' tries VCI then KBS; or specify 'VCI' / 'KBS' directly.
    """
    if period == "quarter":
        raise ValueError(
            "Quarterly financial ingestion is disabled for MVP. Use period='year' only."
        )
    run_id = f"{ticker}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}"
    providers_to_try = (["VCI", "KBS"] if provider == "auto" else [provider.upper()])

    frames: dict[str, pd.DataFrame] | None = None
    provider_used = providers_to_try[0]
    fallback_triggered = False
    fallback_reason: str | None = None

    for i, src in enumerate(providers_to_try):
        try:
            frames = _finance_frames(ticker=ticker, source=src, period=period)
            provider_used = src
            if i > 0:
                fallback_triggered = True
            break
        except Exception as exc:  # noqa: BLE001
            if i == 0 and len(providers_to_try) > 1:
                fallback_reason = str(exc)
            frames = None

    if frames is None:
        raise RuntimeError(
            f"Unable to fetch finance data for {ticker} from {providers_to_try}. "
            f"Last error: {fallback_reason}"
        )

    if fallback_triggered:
        print(
            f"[finance] {ticker}: primary provider failed ({fallback_reason!r}), "
            f"using fallback {provider_used}"
        )

    # Map API statement names to taxonomy 'statement' field values.
    _statement_taxonomy_type = {
        "income_statement": "income_statement",
        "balance_sheet": "balance_sheet",
        "cash_flow": "cash_flow",
        "ratio": "derived",
    }
    all_facts: list[FinancialFact] = []
    parser_version = "vn_fin_parser_v1"
    for statement, frame in frames.items():
        if frame.empty:
            continue
        statement_type = _statement_taxonomy_type.get(statement)
        alias_map = _build_alias_map(statement=statement_type)
        source_id = _register_source_version(
            registry=registry,
            ticker=ticker,
            source=provider_used,
            statement=statement,
            period=period,
            frame=frame,
        )
        facts = _extract_facts_from_frame(
            ticker=ticker,
            frame=frame,
            source_id=source_id,
            parser_version=parser_version,
            alias_map=alias_map,
            run_id=run_id,
            provider=provider_used,
            statement_type=statement,
            period_type=period,
        )
        all_facts.extend(facts)

    # Drop quarterly and out-of-range facts — MVP accepts only annual FY within [from_year, to_year].
    fy_facts: list[FinancialFact] = []
    skipped_quarterly = 0
    skipped_range = 0
    for fact in all_facts:
        if fact.fiscal_period != "FY":
            skipped_quarterly += 1
            continue
        if not (from_year <= fact.fiscal_year <= to_year):
            skipped_range += 1
            continue
        fy_facts.append(fact)

    if skipped_quarterly:
        print(f"[finance] {ticker}: dropped {skipped_quarterly} quarterly facts (MVP FY-only mode)")
    if skipped_range:
        print(
            f"[finance] {ticker}: dropped {skipped_range} out-of-range facts "
            f"(outside {from_year}–{to_year})"
        )

    # Deduplicate: keep last occurrence per unique upsert key within this batch.
    seen: dict[tuple, FinancialFact] = {}
    for fact in fy_facts:
        key = (fact.ticker, fact.fiscal_year, fact.fiscal_period, fact.line_item_code, fact.source_id)
        seen[key] = fact
    return store.upsert_financial_facts(list(seen.values()))


def sync_financial_for_universe(
    tickers: Iterable[str] | None = None,
    period: str = "year",
    from_year: int = MVP_FROM_YEAR,
    to_year: int = MVP_TO_YEAR,
    provider: str = "auto",
) -> dict[str, int]:
    selected = list(tickers or load_universe_tickers())
    store = PostgresFactStore()
    registry = SourceRegistry(store=store)
    result: dict[str, int] = {}
    for ticker in selected:
        inserted = sync_financial_for_ticker(
            ticker=ticker,
            store=store,
            registry=registry,
            period=period,
            from_year=from_year,
            to_year=to_year,
            provider=provider,
        )
        result[ticker] = inserted
        print(f"[finance] {ticker}: upserted {inserted} facts")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync VN finance statements into PostgreSQL financial_facts.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated tickers; defaults to universe.")
    parser.add_argument(
        "--period",
        choices=["year", "quarter"],
        default="year",
        help="'year' returns 4 recent fiscal years (recommended); 'quarter' returns 4 recent quarters.",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="auto",
        help="'auto' tries VCI then KBS; or specify 'VCI' / 'KBS' directly.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()] or None
    sync_financial_for_universe(tickers=tickers, period=args.period, provider=args.provider)


if __name__ == "__main__":
    main()
