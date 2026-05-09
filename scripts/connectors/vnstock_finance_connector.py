from __future__ import annotations

import argparse
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from vnstock import Vnstock

from scripts.dataset.config_io import ROOT, load_financial_taxonomy, load_universe_tickers
from scripts.dataset.dqf import validate_financial_fact
from scripts.db.fact_store import FinancialFact, PostgresFactStore
from scripts.db.source_registry import SourceRegistry, SourceVersionInput


CONNECTOR_VERSION = "vnstock_finance_connector_v1"


def _slug(text: str) -> str:
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


def _extract_rows(frame: pd.DataFrame) -> tuple[pd.Series, list[str]]:
    if frame.empty:
        return pd.Series(dtype=str), []
    label_column = frame.columns[0]
    labels = frame[label_column].astype(str)
    value_columns = [col for col in frame.columns[1:] if _period_from_column(str(col))]
    return labels, value_columns


def _build_alias_map() -> dict[str, tuple[str, str]]:
    taxonomy = load_financial_taxonomy()
    mapping: dict[str, tuple[str, str]] = {}
    for taxonomy_key, config in taxonomy["taxonomy"].items():
        unit = config.get("unit", "vnd_bn")
        mapping[_slug(taxonomy_key)] = (taxonomy_key, unit)
        for alias in config.get("aliases", []):
            mapping[_slug(str(alias))] = (taxonomy_key, unit)
        label_vi = config.get("label_vi")
        if label_vi:
            mapping[_slug(str(label_vi))] = (taxonomy_key, unit)
    return mapping


def _extract_facts_from_frame(
    ticker: str,
    frame: pd.DataFrame,
    source_version_id: str,
    parser_version: str,
    alias_map: dict[str, tuple[str, str]],
) -> list[FinancialFact]:
    labels, value_columns = _extract_rows(frame)
    if labels.empty:
        return []

    facts: list[FinancialFact] = []
    now = datetime.now(UTC)
    for idx, raw_label in labels.items():
        alias = _slug(raw_label)
        resolved = alias_map.get(alias)
        if resolved is None:
            continue
        taxonomy_key, unit = resolved
        for column in value_columns:
            parsed_period = _period_from_column(str(column))
            if parsed_period is None:
                continue
            value = _to_number(frame.at[idx, column])
            if value is None:
                continue
            fiscal_year, fiscal_period = parsed_period
            payload = {
                "company_ticker": ticker,
                "fiscal_year": fiscal_year,
                "fiscal_period": fiscal_period,
                "taxonomy_key": taxonomy_key,
                "value": value,
                "unit": unit,
                "currency": "VND",
                "source_version_id": source_version_id,
                "parser_version": parser_version,
                "validation_status": "accepted",
                "confidence": 0.95,
                "ingested_at": now.isoformat(),
            }
            dqf = validate_financial_fact(payload)
            facts.append(
                FinancialFact(
                    company_ticker=ticker,
                    fiscal_year=fiscal_year,
                    fiscal_period=fiscal_period,
                    taxonomy_key=taxonomy_key,
                    value=value,
                    unit=unit,
                    currency="VND",
                    source_version_id=source_version_id,
                    parser_version=parser_version,
                    validation_status=dqf.status if dqf.status != "rejected" else "needs_review",
                    confidence=dqf.confidence,
                    effective_date=None,
                    ingested_at=now,
                )
            )
    return facts


def _finance_frames(ticker: str, source: str) -> dict[str, pd.DataFrame]:
    client = Vnstock(symbol=ticker, source=source)
    return {
        "income_statement": client.finance.income_statement(period="quarter", lang="vi"),
        "balance_sheet": client.finance.balance_sheet(period="quarter", lang="vi"),
        "cash_flow": client.finance.cash_flow(period="quarter", lang="vi"),
        "ratio": client.finance.ratio(period="quarter", lang="vi"),
    }


def _register_source_version(
    registry: SourceRegistry,
    ticker: str,
    source: str,
    statement: str,
    frame: pd.DataFrame,
) -> str:
    payload = frame.to_json(date_format="iso", orient="split").encode("utf-8")
    source_uri = f"vnstock://{source.lower()}/finance/{statement}/{ticker}?period=quarter"
    raw_path = ROOT / "dataset" / "raw" / "bctc" / ticker / f"{statement}_quarter.json"
    checksum = registry.save_raw_snapshot(payload=payload, out_path=raw_path)
    return registry.register_version(
        SourceVersionInput(
            source_id="bctc_disclosure",
            source_uri=source_uri,
            source_type="financial_statement",
            checksum=checksum,
            connector_version=CONNECTOR_VERSION,
            raw_path=str(raw_path),
            published_at=datetime.now(UTC).isoformat(),
            notes=f"provider={source}",
        )
    )


def sync_financial_for_ticker(ticker: str, store: PostgresFactStore, registry: SourceRegistry) -> int:
    frames: dict[str, pd.DataFrame] | None = None
    provider = "KBS"
    for source in ("KBS", "VCI"):
        try:
            frames = _finance_frames(ticker=ticker, source=source)
            provider = source
            break
        except Exception:  # noqa: BLE001
            frames = None
    if frames is None:
        raise RuntimeError(f"Unable to fetch finance data for {ticker} from KBS/VCI")

    alias_map = _build_alias_map()
    all_facts: list[FinancialFact] = []
    parser_version = "vnstock_financial_parser_v1"
    for statement, frame in frames.items():
        if frame.empty:
            continue
        source_version_id = _register_source_version(registry=registry, ticker=ticker, source=provider, statement=statement, frame=frame)
        facts = _extract_facts_from_frame(
            ticker=ticker,
            frame=frame,
            source_version_id=source_version_id,
            parser_version=parser_version,
            alias_map=alias_map,
        )
        all_facts.extend(facts)

    return store.upsert_financial_facts(all_facts)


def sync_financial_for_universe(tickers: Iterable[str] | None = None) -> dict[str, int]:
    selected = list(tickers or load_universe_tickers())
    store = PostgresFactStore()
    registry = SourceRegistry(store=store)
    result: dict[str, int] = {}
    for ticker in selected:
        inserted = sync_financial_for_ticker(ticker=ticker, store=store, registry=registry)
        result[ticker] = inserted
        print(f"[finance] {ticker}: upserted {inserted} facts")
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync VN finance statements into PostgreSQL financial_facts.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated tickers; defaults to universe.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    tickers = [x.strip().upper() for x in args.tickers.split(",") if x.strip()] or None
    sync_financial_for_universe(tickers=tickers)


if __name__ == "__main__":
    main()

