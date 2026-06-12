"""Run-scoped market data contract for client reports.

The artifact keeps the source observations used by the report together with
derived trading performance.  All benchmark comparisons are aligned by
``trade_date``; list-position alignment is intentionally forbidden.
"""
from __future__ import annotations

import glob
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
MARKET_DATA_DIR = ROOT / "artifacts" / "market_data"
PERIODS = ("YTD", "1T", "3T", "12T")


@dataclass(frozen=True)
class MetricAvailability:
    available: bool
    source: str = ""
    as_of_date: str = ""
    reason: str = ""


@dataclass(frozen=True)
class TradingPerformance:
    periods: list[str]
    absolute_returns: dict[str, float | None]
    relative_returns: dict[str, float | None]
    benchmark_returns: dict[str, float | None]
    benchmark_symbol: str


@dataclass(frozen=True)
class TradingStatistics:
    last_close: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    avg_volume_30d: float | None = None
    avg_traded_value_30d: float | None = None
    market_cap: float | None = None


@dataclass
class MarketDataArtifact:
    ticker: str
    exchange: str
    primary_benchmark: str
    secondary_benchmark: str
    as_of_date: str
    retrieved_at: str
    source: str
    price_history: list[dict[str, Any]]
    primary_benchmark_history: list[dict[str, Any]]
    secondary_benchmark_history: list[dict[str, Any]]
    trading_performance: TradingPerformance
    trading_statistics: TradingStatistics
    availability: dict[str, MetricAvailability] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def benchmark_for_exchange(exchange: str) -> str:
    exchange = (exchange or "").strip().upper()
    return {"HNX": "HNXINDEX", "UPCOM": "UPCOMINDEX"}.get(exchange, "VNINDEX")


def _normalise_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    columns = [
        "trade_date", "open", "high", "low", "close", "adjusted_close",
        "volume", "traded_value", "market_cap",
    ]
    if frame is None or frame.empty:
        return pd.DataFrame(columns=columns)
    out = frame.rename(columns={"time": "trade_date", "date": "trade_date", "value": "traded_value"}).copy()
    if "trade_date" not in out.columns:
        return pd.DataFrame(columns=columns)
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.date
    for col in columns[1:]:
        if col not in out.columns:
            out[col] = None
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out["adjusted_close"] = out["adjusted_close"].fillna(out["close"])
    return out[columns].dropna(subset=["trade_date"]).sort_values("trade_date").drop_duplicates("trade_date", keep="last")


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in frame.to_dict(orient="records"):
        records.append({
            key: (value.isoformat() if isinstance(value, date) else None if pd.isna(value) else value)
            for key, value in row.items()
        })
    return records


def _period_start(as_of: date, period: str) -> date:
    if period == "YTD":
        return date(as_of.year, 1, 1)
    days = {"1T": 30, "3T": 91, "12T": 365}[period]
    return as_of - timedelta(days=days)


def _aligned_return(
    stock: pd.DataFrame,
    benchmark: pd.DataFrame,
    start: date,
) -> tuple[float | None, float | None]:
    left = stock[["trade_date", "adjusted_close"]].rename(columns={"adjusted_close": "stock"})
    right = benchmark[["trade_date", "adjusted_close"]].rename(columns={"adjusted_close": "benchmark"})
    aligned = left.merge(right, on="trade_date", how="inner").dropna()
    aligned = aligned[aligned["trade_date"] >= start]
    if len(aligned) < 2:
        return None, None
    first, last = aligned.iloc[0], aligned.iloc[-1]
    if not first["stock"] or not first["benchmark"]:
        return None, None
    return (
        float(last["stock"] / first["stock"] - 1.0),
        float(last["benchmark"] / first["benchmark"] - 1.0),
    )


def build_market_data_artifact(
    ticker: str,
    exchange: str,
    stock_frame: pd.DataFrame,
    primary_benchmark_frame: pd.DataFrame,
    secondary_benchmark_frame: pd.DataFrame | None = None,
    *,
    source: str = "market_data_provider",
    retrieved_at: str | None = None,
) -> MarketDataArtifact:
    stock = _normalise_frame(stock_frame)
    primary = _normalise_frame(primary_benchmark_frame)
    secondary = _normalise_frame(secondary_benchmark_frame)
    primary_symbol = benchmark_for_exchange(exchange)
    secondary_symbol = "VNINDEX"
    now = retrieved_at or datetime.now(timezone.utc).isoformat()
    as_of = stock["trade_date"].iloc[-1] if not stock.empty else datetime.now(timezone.utc).date()

    absolute: dict[str, float | None] = {}
    benchmark_returns: dict[str, float | None] = {}
    relative: dict[str, float | None] = {}
    for period in PERIODS:
        stock_ret, benchmark_ret = _aligned_return(stock, primary, _period_start(as_of, period))
        absolute[period] = stock_ret
        benchmark_returns[period] = benchmark_ret
        relative[period] = (
            stock_ret - benchmark_ret
            if stock_ret is not None and benchmark_ret is not None else None
        )

    trailing = stock[stock["trade_date"] >= as_of - timedelta(days=365)]
    last = stock.iloc[-1] if not stock.empty else None
    recent_30 = stock.tail(30)
    stats = TradingStatistics(
        last_close=float(last["close"]) if last is not None and pd.notna(last["close"]) else None,
        high_52w=float(trailing["high"].max()) if not trailing.empty and trailing["high"].notna().any() else None,
        low_52w=float(trailing["low"].min()) if not trailing.empty and trailing["low"].notna().any() else None,
        avg_volume_30d=float(recent_30["volume"].mean()) if recent_30["volume"].notna().any() else None,
        avg_traded_value_30d=float(recent_30["traded_value"].mean()) if recent_30["traded_value"].notna().any() else None,
        market_cap=float(last["market_cap"]) if last is not None and pd.notna(last["market_cap"]) else None,
    )
    availability = {
        "price_history": MetricAvailability(not stock.empty, source, str(as_of), "" if not stock.empty else "Không có lịch sử giá"),
        "primary_benchmark": MetricAvailability(not primary.empty, source, str(as_of), "" if not primary.empty else f"Không có dữ liệu {primary_symbol}"),
        "secondary_benchmark": MetricAvailability(not secondary.empty, source, str(as_of), "" if not secondary.empty else "Không có dữ liệu VNINDEX"),
    }
    warnings = []
    if not stock.empty and len(stock) < 200:
        warnings.append("Lịch sử giá chưa đủ 12 tháng giao dịch")

    return MarketDataArtifact(
        ticker=ticker.upper(),
        exchange=exchange.upper(),
        primary_benchmark=primary_symbol,
        secondary_benchmark=secondary_symbol,
        as_of_date=str(as_of),
        retrieved_at=now,
        source=source,
        price_history=_records(stock),
        primary_benchmark_history=_records(primary),
        secondary_benchmark_history=_records(secondary),
        trading_performance=TradingPerformance(
            periods=list(PERIODS),
            absolute_returns=absolute,
            relative_returns=relative,
            benchmark_returns=benchmark_returns,
            benchmark_symbol=primary_symbol,
        ),
        trading_statistics=stats,
        availability=availability,
        warnings=warnings,
    )


def fetch_market_data_artifact(
    ticker: str,
    exchange: str,
    *,
    days: int = 400,
    history_loader: Callable[[str, date, date], pd.DataFrame] | None = None,
) -> MarketDataArtifact:
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=days)
    if history_loader is None:
        from vnstock.api.quote import Quote

        def history_loader(symbol: str, start_date: date, end_date: date) -> pd.DataFrame:
            errors: list[Exception] = []
            for provider in ("KBS", "VCI"):
                try:
                    return Quote(source=provider, symbol=symbol).history(
                        start=start_date.isoformat(), end=end_date.isoformat(), interval="1D"
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)
            raise RuntimeError(f"Không thể lấy lịch sử giá {symbol}: {errors}")

    primary = benchmark_for_exchange(exchange)
    stock_frame = history_loader(ticker.upper(), start, end)
    primary_frame = history_loader(primary, start, end)
    secondary_frame = primary_frame if primary == "VNINDEX" else history_loader("VNINDEX", start, end)
    return build_market_data_artifact(
        ticker, exchange, stock_frame, primary_frame, secondary_frame, source="vnstock_quote"
    )


def write_market_data_artifact(
    artifact: MarketDataArtifact,
    *,
    run_id: str = "",
    base_dir: Path | str | None = None,
) -> Path:
    out_dir = Path(base_dir) if base_dir else MARKET_DATA_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{run_id}_" if run_id else ""
    path = out_dir / f"{prefix}{artifact.ticker}_market_data.json"
    path.write_text(json.dumps(artifact.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def market_data_from_dict(data: dict[str, Any]) -> MarketDataArtifact | None:
    if not data or not data.get("ticker"):
        return None
    return MarketDataArtifact(
        ticker=data["ticker"],
        exchange=data.get("exchange", ""),
        primary_benchmark=data.get("primary_benchmark", "VNINDEX"),
        secondary_benchmark=data.get("secondary_benchmark", "VNINDEX"),
        as_of_date=data.get("as_of_date", ""),
        retrieved_at=data.get("retrieved_at", ""),
        source=data.get("source", ""),
        price_history=data.get("price_history", []),
        primary_benchmark_history=data.get("primary_benchmark_history", []),
        secondary_benchmark_history=data.get("secondary_benchmark_history", []),
        trading_performance=TradingPerformance(**data.get("trading_performance", {
            "periods": list(PERIODS), "absolute_returns": {}, "relative_returns": {},
            "benchmark_returns": {}, "benchmark_symbol": "VNINDEX",
        })),
        trading_statistics=TradingStatistics(**data.get("trading_statistics", {})),
        availability={k: MetricAvailability(**v) for k, v in data.get("availability", {}).items()},
        warnings=data.get("warnings", []),
    )


def load_cached_market_data(
    ticker: str,
    *,
    run_id: str = "",
    base_dir: Path | str | None = None,
) -> MarketDataArtifact | None:
    if not run_id:
        return None
    out_dir = Path(base_dir) if base_dir else MARKET_DATA_DIR
    path = out_dir / run_id / "market_data.json"
    if not path.exists():
        return None
    try:
        return market_data_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
