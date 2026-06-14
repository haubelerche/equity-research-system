"""Manual valuation input pack loaders.

Manual packs are intentionally narrow: they cover market price, shares, peer
multiples, debt policy, corporate actions, and valuation assumptions that should
not be mixed into reported financial facts.
"""
from __future__ import annotations

import csv
import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

DEFAULT_MANUAL_DIR = Path(__file__).resolve().parents[2] / "data" / "manual"


@dataclass
class ManualPackBundle:
    market: dict[str, Any] = field(default_factory=dict)
    shares: dict[str, Any] = field(default_factory=dict)
    peers: dict[str, Any] = field(default_factory=dict)
    debt_policy: dict[str, Any] = field(default_factory=dict)
    corporate_actions: dict[str, Any] = field(default_factory=dict)
    tax_policy: dict[str, Any] = field(default_factory=dict)
    wacc_assumptions: dict[str, Any] = field(default_factory=dict)
    working_capital_policy: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _read_csv(path: Path, required_columns: set[str], warnings: list[str]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = required_columns - columns
        if missing:
            warnings.append(f"{path.name}: missing required columns {sorted(missing)}")
            return []
        return [dict(row) for row in reader]


def _accepted_rows(
    rows: list[dict[str, str]],
    *,
    ticker: str | None,
    as_of: date,
    warnings: list[str],
    file_name: str,
) -> list[dict[str, str]]:
    accepted: list[dict[str, str]] = []
    wanted_ticker = ticker.upper() if ticker else None
    for index, row in enumerate(rows, start=2):
        row_ticker = (row.get("ticker") or "").strip().upper()
        if wanted_ticker and row_ticker != wanted_ticker:
            continue
        status = (row.get("status") or "").strip().lower()
        source = (row.get("source") or "").strip()
        if not status or not source:
            warnings.append(f"{file_name}:{index}: rejected row missing status/source")
            continue
        if status != "accepted":
            continue
        row_date = _parse_date(row.get("as_of_date") or row.get("event_date"))
        if row_date is not None and row_date > as_of:
            continue
        accepted.append(row)
    return accepted


def _latest_by_as_of(rows: list[dict[str, str]]) -> dict[str, str] | None:
    if not rows:
        return None
    return sorted(
        rows,
        key=lambda row: _parse_date(row.get("as_of_date")) or date.min,
        reverse=True,
    )[0]


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct
    lower = int(pos)
    upper = min(lower + 1, len(ordered) - 1)
    weight = pos - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def load_market_pack(ticker: str, as_of: date, manual_dir: Path = DEFAULT_MANUAL_DIR) -> dict[str, Any]:
    warnings: list[str] = []
    rows = _read_csv(
        manual_dir / "market_prices.csv",
        {"as_of_date", "ticker", "price", "status", "source"},
        warnings,
    )
    row = _latest_by_as_of(_accepted_rows(rows, ticker=ticker, as_of=as_of, warnings=warnings, file_name="market_prices.csv"))
    result: dict[str, Any] = {"warnings": warnings}
    if row:
        price = _safe_float(row.get("price"))
        if price is not None and price > 0:
            result.update({
                "price": price,
                "as_of_date": row.get("as_of_date"),
                "source": row.get("source"),
                "status": "accepted",
            })
    return result


def load_shares_pack(ticker: str, as_of: date, manual_dir: Path = DEFAULT_MANUAL_DIR) -> dict[str, Any]:
    warnings: list[str] = []
    rows = _read_csv(
        manual_dir / "shares_outstanding.csv",
        {"as_of_date", "ticker", "shares_outstanding", "status", "source"},
        warnings,
    )
    row = _latest_by_as_of(_accepted_rows(rows, ticker=ticker, as_of=as_of, warnings=warnings, file_name="shares_outstanding.csv"))
    result: dict[str, Any] = {"warnings": warnings}
    if row:
        shares = _safe_float(row.get("shares_outstanding"))
        if shares is not None and shares > 0:
            result.update({
                "shares_outstanding": shares,
                "as_of_date": row.get("as_of_date"),
                "source": row.get("source"),
                "status": "accepted",
            })
    return result


def load_peer_pack(ticker: str, as_of: date, manual_dir: Path = DEFAULT_MANUAL_DIR) -> dict[str, Any]:
    warnings: list[str] = []
    rows = _read_csv(
        manual_dir / "peer_multiples.csv",
        {"as_of_date", "ticker", "peer_group", "pe_ttm", "ev_ebitda_ttm", "status", "source"},
        warnings,
    )
    accepted = _accepted_rows(rows, ticker=None, as_of=as_of, warnings=warnings, file_name="peer_multiples.csv")
    ticker_rows = [row for row in accepted if (row.get("ticker") or "").strip().upper() == ticker.upper()]
    anchor = _latest_by_as_of(ticker_rows)
    result: dict[str, Any] = {"warnings": warnings}
    if not anchor:
        return result

    group = (anchor.get("peer_group") or "").strip()
    if not group:
        warnings.append("peer_multiples.csv: accepted ticker row missing peer_group")
        return result

    by_member: dict[str, dict[str, str]] = {}
    for row in accepted:
        if (row.get("peer_group") or "").strip() != group:
            continue
        member = (row.get("ticker") or "").strip().upper()
        if not member:
            continue
        previous = by_member.get(member)
        if previous is None or (_parse_date(row.get("as_of_date")) or date.min) >= (_parse_date(previous.get("as_of_date")) or date.min):
            by_member[member] = row

    members = list(by_member.values())
    pe_values = [v for v in (_safe_float(row.get("pe_ttm")) for row in members) if v is not None and v > 0]
    ev_values = [v for v in (_safe_float(row.get("ev_ebitda_ttm")) for row in members) if v is not None and v > 0]
    result.update({
        "peer_group": group,
        "as_of_date": anchor.get("as_of_date"),
        "source": anchor.get("source"),
        "status": "accepted",
        "members": [
            {
                "ticker": (row.get("ticker") or "").strip().upper(),
                "pe_ttm": _safe_float(row.get("pe_ttm")),
                "ev_ebitda_ttm": _safe_float(row.get("ev_ebitda_ttm")),
                "as_of_date": row.get("as_of_date"),
                "source": row.get("source"),
            }
            for row in members
        ],
        "peer_pe_median": statistics.median(pe_values) if pe_values else None,
        "peer_pe_p25": _percentile(pe_values, 0.25),
        "peer_pe_p75": _percentile(pe_values, 0.75),
        "peer_ev_ebitda_median": statistics.median(ev_values) if ev_values else None,
        "peer_ev_ebitda_p25": _percentile(ev_values, 0.25),
        "peer_ev_ebitda_p75": _percentile(ev_values, 0.75),
    })
    return result


def _load_yaml_policy(path: Path, ticker: str, warnings: list[str]) -> dict[str, Any]:
    if not path.exists():
        return {}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        warnings.append(f"{path.name}: expected mapping at document root")
        return {}

    defaults = loaded.get("defaults") if isinstance(loaded.get("defaults"), dict) else {}
    tickers = loaded.get("tickers") if isinstance(loaded.get("tickers"), dict) else {}
    ticker_policy = tickers.get(ticker.upper()) if isinstance(tickers.get(ticker.upper()), dict) else {}

    if defaults or ticker_policy:
        selected = {**defaults, **ticker_policy}
    elif ticker.upper() in loaded and isinstance(loaded[ticker.upper()], dict):
        selected = loaded[ticker.upper()]
    else:
        selected = loaded

    if not selected:
        return {}
    status = str(selected.get("status") or "").lower()
    source = str(selected.get("source") or "").strip()
    if not status or not source:
        warnings.append(f"{path.name}: rejected policy missing status/source")
        return {}
    if status != "accepted":
        return {}
    return dict(selected)


def load_corporate_actions(ticker: str, as_of: date, manual_dir: Path = DEFAULT_MANUAL_DIR) -> dict[str, Any]:
    warnings: list[str] = []
    rows = _read_csv(
        manual_dir / "corporate_actions.csv",
        {"ticker", "event_date", "event_type", "shares_before", "shares_after", "ratio", "cash_amount_vnd", "source", "status"},
        warnings,
    )
    accepted = _accepted_rows(rows, ticker=ticker, as_of=as_of, warnings=warnings, file_name="corporate_actions.csv")
    events: list[dict[str, Any]] = []
    for row in sorted(accepted, key=lambda r: _parse_date(r.get("event_date")) or date.min):
        events.append({
            "ticker": ticker.upper(),
            "event_date": row.get("event_date"),
            "event_type": (row.get("event_type") or "").strip() or "no_action",
            "shares_before": _safe_float(row.get("shares_before")),
            "shares_after": _safe_float(row.get("shares_after")),
            "ratio": _safe_float(row.get("ratio")),
            "cash_amount_vnd": _safe_float(row.get("cash_amount_vnd")),
            "source": row.get("source"),
            "status": "accepted",
        })
    explicit_no_action = any(event["event_type"] == "no_action" for event in events)
    return {
        "status": "accepted" if events and not explicit_no_action else "no_action_recorded",
        "events": [] if explicit_no_action else events,
        "source": "corporate_actions.csv" if events else "manual_absent",
        "warnings": warnings,
    }


def load_manual_packs(
    ticker: str,
    as_of_date: date | str,
    manual_dir: str | Path = DEFAULT_MANUAL_DIR,
) -> ManualPackBundle:
    as_of = _parse_date(as_of_date) or date.today()
    root = Path(manual_dir)
    warnings: list[str] = []

    market = load_market_pack(ticker, as_of, root)
    shares = load_shares_pack(ticker, as_of, root)
    peers = load_peer_pack(ticker, as_of, root)
    corporate_actions = load_corporate_actions(ticker, as_of, root)
    for pack in (market, shares, peers, corporate_actions):
        warnings.extend(pack.pop("warnings", []) or [])

    debt_policy = _load_yaml_policy(root / "debt_policy.yaml", ticker, warnings)
    tax_policy = _load_yaml_policy(root / "tax_policy.yaml", ticker, warnings)
    wacc_assumptions = _load_yaml_policy(root / "wacc_assumptions.yaml", ticker, warnings)
    working_capital_policy = _load_yaml_policy(root / "working_capital_policy.yaml", ticker, warnings)

    return ManualPackBundle(
        market=market,
        shares=shares,
        peers=peers,
        debt_policy=debt_policy,
        corporate_actions=corporate_actions,
        tax_policy=tax_policy,
        wacc_assumptions=wacc_assumptions,
        working_capital_policy=working_capital_policy,
        warnings=warnings,
    )


def corporate_actions_to_share_rollforward(events: list[dict[str, Any]]) -> list[Any]:
    """Convert accepted corporate-action events to share-rollforward actions."""
    from backend.analytics.share_rollforward import CorporateAction

    actions: list[CorporateAction] = []
    for event in events:
        event_type = str(event.get("event_type") or "").lower()
        if event_type in {"cash_dividend", "no_action"}:
            continue
        event_date = _parse_date(event.get("event_date"))
        if event_date is None:
            continue
        before = event.get("shares_before")
        after = event.get("shares_after")
        ratio = event.get("ratio")
        issuance = 0.0
        buyback = 0.0
        if before is not None and after is not None:
            before_mn = before / 1_000_000 if before > 1_000_000 else before
            after_mn = after / 1_000_000 if after > 1_000_000 else after
            delta = after_mn - before_mn
            issuance = max(delta, 0.0)
            buyback = max(-delta, 0.0)
        elif before is not None and ratio is not None and event_type in {"stock_dividend", "bonus_share", "split"}:
            before_mn = before / 1_000_000 if before > 1_000_000 else before
            issuance = max(before_mn * ratio, 0.0)
        if issuance or buyback:
            actions.append(CorporateAction(
                forecast_label=f"{event_date.year}F",
                issuance_mn=issuance,
                buyback_mn=buyback,
            ))
    return actions
