from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, UTC
from typing import Any

import pandas as pd

from backend.dataset.config_io import load_universe_rows
from backend.database.fact_store import PostgresFactStore


STORE = PostgresFactStore()


def _facts_for_ticker(ticker: str) -> pd.DataFrame:
    with STORE.conn() as connection:
        frame = pd.read_sql_query(
            """
            SELECT ticker, CAST(SUBSTRING(period, 1, 4) AS SMALLINT) AS fiscal_year,
                   'FY' AS fiscal_period, metric AS line_item_code, value
            FROM fact.production_facts
            WHERE ticker = %s
            ORDER BY period DESC
            """,
            connection,
            params=(ticker,),
        )
    return frame


def _latest_price(ticker: str) -> float | None:
    with STORE.conn() as connection:
        df = pd.read_sql_query(
            """
            SELECT close
            FROM fact.price_history
            WHERE ticker = %s
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            connection,
            params=(ticker,),
        )
    if df.empty:
        return None
    return float(df.iloc[0]["close"]) if df.iloc[0]["close"] is not None else None


def _yearly_facts(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    annual = frame.groupby(["fiscal_year", "line_item_code"], as_index=False)["value"].last()
    return annual


def _financial_statement_like(frame: pd.DataFrame, statement: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    yearly = _yearly_facts(frame)
    years = sorted(yearly["fiscal_year"].unique(), reverse=True)
    records: list[dict[str, Any]] = []
    for year in years:
        period_rows = yearly[yearly["fiscal_year"] == year]
        get = lambda key: _val(period_rows, key)
        if statement == "income":
            records.append(
                {
                    "year": int(year),
                    "revenue": get("revenue.net"),
                    "costOfRevenue": get("cogs.total"),
                    "grossProfit": get("gross_profit.total"),
                    "sellingGeneralAndAdministrativeExpenses": get("sga.total"),
                    "ebitda": get("ebitda.total"),
                    "eps": get("eps.basic"),
                    "netIncome": get("net_income.parent"),
                }
            )
        elif statement == "balance":
            records.append(
                {
                    "year": int(year),
                    "cashAndCashEquivalents": get("cash_and_equivalents.ending"),
                    "inventory": get("inventory.ending"),
                    "totalDebt": get("total_debt.ending"),
                    "totalStockholdersEquity": get("equity.parent"),
                }
            )
        elif statement == "cash":
            records.append(
                {
                    "year": int(year),
                    "operatingCashFlow": get("operating_cash_flow.total"),
                    "capitalExpenditure": get("capex.total"),
                    "freeCashFlow": get("free_cash_flow.total"),
                }
            )
    return pd.DataFrame(records)


def _val(frame: pd.DataFrame, key: str) -> float | None:
    rows = frame[frame["line_item_code"] == key]
    if rows.empty:
        return None
    return float(rows.iloc[-1]["value"])


def _ratios_df(frame: pd.DataFrame) -> pd.DataFrame:
    yearly = _yearly_facts(frame)
    if yearly.empty:
        return pd.DataFrame()
    years = sorted(yearly["fiscal_year"].unique(), reverse=True)
    rows = []
    for year in years:
        period_rows = yearly[yearly["fiscal_year"] == year]
        net_income = _val(period_rows, "net_income.parent")
        equity = _val(period_rows, "equity.parent")
        eps = _val(period_rows, "eps.basic")
        price = None
        pe = None
        if eps and eps != 0:
            price = None
            pe = None
        rows.append(
            {
                "year": int(year),
                "priceEarningsRatio": pe,
                "peRatio": pe,
                "returnOnEquity": (net_income / equity) if (net_income is not None and equity not in (None, 0)) else None,
                "debtEquityRatio": _ratio(period_rows, "total_debt.ending", "equity.parent"),
                "priceToBookRatio": None,
            }
        )
    return pd.DataFrame(rows)


def _key_metrics_df(frame: pd.DataFrame, ticker: str) -> pd.DataFrame:
    yearly = _yearly_facts(frame)
    if yearly.empty:
        return pd.DataFrame()
    price = _latest_price(ticker)
    years = sorted(yearly["fiscal_year"].unique(), reverse=True)
    rows = []
    for year in years:
        period_rows = yearly[yearly["fiscal_year"] == year]
        ebitda = _val(period_rows, "ebitda.total")
        debt = _val(period_rows, "total_debt.ending")
        cash = _val(period_rows, "cash_and_equivalents.ending")
        equity = _val(period_rows, "equity.parent")
        eps = _val(period_rows, "eps.basic")
        market_cap = (price * equity) if (price and equity) else None
        enterprise_value = (market_cap + debt - cash) if (market_cap is not None and debt is not None and cash is not None) else None
        pe_ratio = (price / eps) if (price is not None and eps not in (None, 0)) else None
        rows.append(
            {
                "year": int(year),
                "enterpriseValue": enterprise_value,
                "enterpriseValueOverEBITDA": (enterprise_value / ebitda) if (enterprise_value is not None and ebitda not in (None, 0)) else None,
                "peRatio": pe_ratio,
                "priceEarningsRatio": pe_ratio,
                "pbRatio": None,
            }
        )
    return pd.DataFrame(rows)


def _ratio(frame: pd.DataFrame, num_key: str, den_key: str) -> float | None:
    num = _val(frame, num_key)
    den = _val(frame, den_key)
    if num is None or den in (None, 0):
        return None
    return num / den


def get_comprehensive_financial_data(ticker: str, api_key: str | None = None, period: str = "annual", limit: int = 5) -> dict:
    """Drop-in replacement for FinRobot's FMP-based function."""
    facts = _facts_for_ticker(ticker)
    return {
        "income_statement": _financial_statement_like(facts, "income").head(limit),
        "balance_sheet": _financial_statement_like(facts, "balance").head(limit),
        "cash_flow": _financial_statement_like(facts, "cash").head(limit),
        "ratios": _ratios_df(facts).head(limit),
        "key_metrics": _key_metrics_df(facts, ticker=ticker).head(limit),
    }


def combine_peer_financial_data(tickers: list[str], api_key: str | None = None, years_limit: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    ebitda_records: list[dict[str, Any]] = []
    ev_ebitda_records: list[dict[str, Any]] = []
    for ticker in tickers:
        data = get_comprehensive_financial_data(ticker=ticker, api_key=api_key, limit=years_limit)
        income = data["income_statement"]
        key_metrics = data["key_metrics"]
        if income is not None and not income.empty:
            for _, row in income.iterrows():
                if row.get("ebitda") is not None:
                    ebitda_records.append({"ticker": ticker, "year": row["year"], "EBITDA": row["ebitda"]})
        if key_metrics is not None and not key_metrics.empty:
            for _, row in key_metrics.iterrows():
                if row.get("enterpriseValueOverEBITDA") is not None:
                    ev_ebitda_records.append(
                        {"ticker": ticker, "year": row["year"], "EV/EBITDA": row["enterpriseValueOverEBITDA"]}
                    )
    df_ebitda = pd.DataFrame(ebitda_records)
    df_ev = pd.DataFrame(ev_ebitda_records)
    ebitda_pivot = df_ebitda.pivot(index="year", columns="ticker", values="EBITDA").sort_index() if not df_ebitda.empty else pd.DataFrame()
    ev_pivot = df_ev.pivot(index="year", columns="ticker", values="EV/EBITDA").sort_index() if not df_ev.empty else pd.DataFrame()
    return ebitda_pivot, ev_pivot


def get_company_news(ticker: str, api_key: str | None = None, days_back: int = 5, limit: int = 50) -> list[dict] | None:
    rows = STORE.get_company_news(ticker=ticker, days_back=days_back)
    return rows[:limit]


def get_comprehensive_company_metrics(ticker: str, api_key: str | None = None) -> dict:
    frame = _facts_for_ticker(ticker)
    latest_price = _latest_price(ticker)
    profile_row = next((row for row in load_universe_rows() if row["ticker"].upper() == ticker.upper()), {})
    latest_year = int(frame["fiscal_year"].max()) if not frame.empty else None
    yearly = _yearly_facts(frame)
    current_rows = yearly[yearly["fiscal_year"] == latest_year] if latest_year is not None else pd.DataFrame()
    eps = _val(current_rows, "eps.basic") if not current_rows.empty else None
    equity = _val(current_rows, "equity.parent") if not current_rows.empty else None
    debt = _val(current_rows, "total_debt.ending") if not current_rows.empty else None
    net_income = _val(current_rows, "net_income.parent") if not current_rows.empty else None
    market_cap = (latest_price * equity) if (latest_price is not None and equity is not None) else None

    return {
        "share_price": latest_price,
        "target_price": None,
        "market_cap": market_cap,
        "volume": None,
        "fwd_pe": (latest_price / eps) if (latest_price is not None and eps not in (None, 0)) else None,
        "pb_ratio": None,
        "dividend_yield": None,
        "free_float": 95.0,
        "roe": (net_income / equity * 100) if (net_income is not None and equity not in (None, 0)) else None,
        "net_debt_to_equity": (debt / equity) if (debt is not None and equity not in (None, 0)) else None,
        "rating": "N/A",
        "beta": None,
        "sector": profile_row.get("segment"),
        "industry": profile_row.get("segment"),
        "exchange": profile_row.get("exchange"),
        "52w_range": None,
        "shares_outstanding": equity,
    }


def get_fmp_current_price(ticker: str, api_key: str | None = None) -> float | None:
    return _latest_price(ticker)


def get_technical_indicators(ticker: str, api_key: str | None = None) -> dict:
    end = date.today()
    start = end - timedelta(days=365)
    df = STORE.get_price_history(ticker=ticker, start=start.isoformat(), end=end.isoformat())
    result = {
        "sma50": None,
        "sma200": None,
        "rsi14": None,
        "macd": None,
        "macd_signal": None,
        "macd_histogram": None,
        "avg_volume_20d": None,
        "latest_volume": None,
        "price": None,
        "ma_signal": "N/A",
        "rsi_signal": "N/A",
        "macd_signal_label": "N/A",
        "volume_signal": "N/A",
        "overall_signal": "N/A",
    }
    if df.empty:
        return result

    close = df["close"].astype(float)
    volume = df["volume"].fillna(0).astype(float)
    latest_price = close.iloc[-1]
    sma50 = close.rolling(50).mean().iloc[-1]
    sma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else None

    delta = close.diff()
    gains = delta.clip(lower=0).rolling(14).mean()
    losses = -delta.clip(upper=0).rolling(14).mean()
    rs = gains / losses.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()

    result["price"] = float(latest_price)
    result["sma50"] = float(sma50) if pd.notna(sma50) else None
    result["sma200"] = float(sma200) if sma200 is not None and pd.notna(sma200) else None
    result["rsi14"] = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None
    result["macd"] = float(macd.iloc[-1]) if pd.notna(macd.iloc[-1]) else None
    result["macd_signal"] = float(macd_signal.iloc[-1]) if pd.notna(macd_signal.iloc[-1]) else None
    result["macd_histogram"] = (
        result["macd"] - result["macd_signal"] if result["macd"] is not None and result["macd_signal"] is not None else None
    )
    result["avg_volume_20d"] = float(volume.tail(20).mean())
    result["latest_volume"] = float(volume.iloc[-1])

    if result["sma50"] and result["sma200"]:
        if latest_price > result["sma50"] > result["sma200"]:
            result["ma_signal"] = "Bullish"
        elif latest_price < result["sma50"] < result["sma200"]:
            result["ma_signal"] = "Bearish"
        else:
            result["ma_signal"] = "Neutral"

    if result["rsi14"] is not None:
        if result["rsi14"] > 70:
            result["rsi_signal"] = "Overbought"
        elif result["rsi14"] < 30:
            result["rsi_signal"] = "Oversold"
        else:
            result["rsi_signal"] = "Neutral"

    if result["macd_histogram"] is not None:
        result["macd_signal_label"] = "Bullish" if result["macd_histogram"] > 0 else "Bearish"

    if result["latest_volume"] and result["avg_volume_20d"]:
        result["volume_signal"] = "High" if result["latest_volume"] > 1.5 * result["avg_volume_20d"] else "Normal"

    votes = [result["ma_signal"], result["rsi_signal"], result["macd_signal_label"]]
    if votes.count("Bullish") >= 2:
        result["overall_signal"] = "Bullish"
    elif votes.count("Bearish") >= 2:
        result["overall_signal"] = "Bearish"
    else:
        result["overall_signal"] = "Neutral"
    return result

