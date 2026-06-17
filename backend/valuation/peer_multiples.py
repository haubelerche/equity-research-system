"""Peer-multiples for relative valuation (P/E, EV/EBITDA) sourced from vnstock.

Per the data-source contract, vnstock is primary. We build a peer pack for a ticker
by:
  - selecting same-sector peers that have financials in production facts;
  - peer P/E      = live price (vnstock overview) / EPS (production, latest FY);
  - peer EV/EBITDA = (market_cap + interest-bearing debt - cash & STI) / EBITDA;
  - taking the MEDIAN across peers, requiring >= MIN_PEERS valid (no fabrication —
    below that, relative valuation stays pending_peer_dataset).

Pure math (_peer_pe / _peer_ev_ebitda / _median) is unit-tested; the price/fact
loaders are injectable so the logic is testable without network or DB.
"""
from __future__ import annotations

import statistics
from typing import Any, Callable, Optional, Sequence


# Sanity bounds — drop nonsensical multiples (data errors) before taking the median.
_PE_BOUNDS = (3.0, 60.0)
_EV_EBITDA_BOUNDS = (2.0, 40.0)


def _peer_pe(price: float | None, eps: float | None) -> float | None:
    if price is None or eps is None or eps <= 0:
        return None
    pe = price / eps
    return pe if _PE_BOUNDS[0] <= pe <= _PE_BOUNDS[1] else None


def _peer_ev_ebitda(
    market_cap: float | None,
    total_debt: float | None,
    cash_sti: float | None,
    ebitda: float | None,
) -> float | None:
    if market_cap is None or ebitda is None or ebitda <= 0:
        return None
    ev = market_cap + (total_debt or 0.0) - (cash_sti or 0.0)
    if ev <= 0:
        return None
    val = ev / ebitda
    return val if _EV_EBITDA_BOUNDS[0] <= val <= _EV_EBITDA_BOUNDS[1] else None


def _median(values: Sequence[float | None]) -> float | None:
    clean = [v for v in values if isinstance(v, (int, float))]
    if len(clean) < MIN_PEERS:
        return None
    return float(statistics.median(clean))


def select_pharma_peers(ticker: str, *, limit: int = 12, conn: Any = None) -> list[str]:
    """Same-sector peers that have EPS in production facts (so a P/E is computable)."""
    from backend.database.canonical.connection import get_conn
    from contextlib import nullcontext

    self_t = ticker.strip().upper()
    ctx = nullcontext(conn) if conn is not None else get_conn()
    with ctx as c:
        with c.cursor() as cur:
            cur.execute(
                """
                SELECT pf.ticker
                FROM fact.production_facts pf
                JOIN ref.companies co ON co.ticker = pf.ticker
                WHERE pf.metric = 'eps.basic'
                  AND co.sector = (SELECT sector FROM ref.companies WHERE ticker = %s)
                  AND pf.ticker <> %s
                GROUP BY pf.ticker
                ORDER BY pf.ticker
                """,
                (self_t, self_t),
            )
            peers = [r[0] for r in cur.fetchall()]
    return peers[:limit]


def _default_price_loader(ticker: str) -> Optional[tuple]:
    """(price_vnd, market_cap_bn) from the vnstock VCI overview; None on failure."""
    try:
        from backend.reporting.market_snapshot import get_market_snapshot

        snap = get_market_snapshot(ticker, persist=False, base_dir=None)
        if snap is None or snap.last_price is None:
            return None
        market_cap_bn = (snap.market_cap / 1_000_000_000.0) if snap.market_cap else None
        return (snap.last_price, market_cap_bn)
    except Exception:  # noqa: BLE001 — provider/network errors are per-peer, non-fatal
        return None


def _default_fact_loader(ticker: str) -> Optional[dict]:
    """{eps, ebitda, total_debt, cash_sti} (vnd_bn except eps=vnd/share) from production."""
    try:
        from backend.valuation.input_pack_builder import _load_fact_table_from_production
        from backend.analytics._entry import entry_value
        from backend.analytics.debt_schedule import interest_bearing_debt

        ft = _load_fact_table_from_production(ticker, None, None)
        fys = sorted({p for vals in ft.values() for p in vals if p.endswith("FY")})
        if not fys:
            return None
        fy = fys[-1]

        def g(metric: str) -> float | None:
            e = ft.get(metric, {}).get(fy)
            return entry_value(e) if e is not None else None

        ebitda = g("ebitda.total")
        if ebitda is None:
            ebit, dep = g("ebit.total"), g("depreciation.total")
            ebitda = (ebit + abs(dep)) if (ebit is not None and dep is not None) else ebit
        cash = (g("cash_and_equivalents.ending") or 0.0) + (g("short_term_investments.ending") or 0.0)
        return {
            "eps": g("eps.basic"),
            "ebitda": ebitda,
            "total_debt": interest_bearing_debt(ft, fy) or 0.0,
            "cash_sti": cash,
        }
    except Exception:  # noqa: BLE001
        return None


def build_peer_pack_live(ticker: str, *, limit: int = 12) -> dict[str, Any]:
    """Production+vnstock peer pack: select pharma peers, fetch live price + facts, median."""
    peers = select_pharma_peers(ticker, limit=limit)
    return build_peer_pack(
        ticker,
        peer_tickers=peers,
        price_loader=_default_price_loader,
        fact_loader=_default_fact_loader,
    )


def build_peer_pack(
    ticker: str,
    *,
    peer_tickers: Sequence[str],
    price_loader: Callable[[str], Optional[tuple]],   # ticker -> (price_vnd, market_cap_bn) or None
    fact_loader: Callable[[str], Optional[dict]],     # ticker -> {eps, ebitda, total_debt, cash_sti} or None
) -> dict[str, Any]:
    """Build {peer_group, peer_pe_median, peer_ev_ebitda_median, ...} from injectable loaders.

    market_cap and EV/EBITDA inputs are expected in the same unit basis (VND bn);
    EPS and price in VND/share. Loaders own unit consistency.
    """
    self_t = ticker.strip().upper()
    pes: list[float | None] = []
    evs: list[float | None] = []
    used: list[str] = []
    for peer in peer_tickers:
        p = peer.strip().upper()
        if p == self_t:
            continue
        px = price_loader(p)
        fx = fact_loader(p)
        if not px or not fx:
            continue
        price, market_cap = (px + (None,))[:2] if isinstance(px, (list, tuple)) else (px, None)
        pe = _peer_pe(price, fx.get("eps"))
        ev = _peer_ev_ebitda(market_cap, fx.get("total_debt"), fx.get("cash_sti"), fx.get("ebitda"))
        if pe is not None or ev is not None:
            used.append(p)
        pes.append(pe)
        evs.append(ev)

    pe_median = _median(pes)
    ev_median = _median(evs)
    n_pe = sum(1 for v in pes if v is not None)
    n_ev = sum(1 for v in evs if v is not None)
    has_dataset = pe_median is not None or ev_median is not None
    return {
        "peer_group": f"VN pharma peers ({len(used)}): {', '.join(used)}" if used else "",
        "peer_pe_median": pe_median,
        "peer_ev_ebitda_median": ev_median,
        "n_pe": n_pe,
        "n_ev": n_ev,
        "peers_used": used,
        "peer_data_source": f"vnstock: {len(used)} VN pharma peers (price/EPS, EV/EBITDA)" if has_dataset else "",
        "relative_valuation_status": "peer_data_available" if has_dataset else "pending_peer_dataset",
    }
