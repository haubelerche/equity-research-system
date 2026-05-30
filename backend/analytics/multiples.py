"""Deterministic market multiples valuation.

Computes P/E, EV/EBITDA, and P/B implied target prices from the latest market price
and canonical financial facts.

Requires a current market price (VND/share). If unavailable, multiples are still
computed as ratios but implied values are omitted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.facts.normalizer import FactTable


@dataclass
class MultiplesResult:
    ticker: str
    latest_fy: str
    current_price_vnd: float | None

    # Fundamental inputs
    eps_vnd: float | None
    book_value_per_share_vnd: float | None
    ebitda_vnd_bn: float | None
    net_debt_vnd_bn: float | None
    shares_mn: float | None

    # Observed multiples (computed from current_price)
    pe_ratio: float | None
    pb_ratio: float | None

    # Implied values at target multiples
    target_pe: float | None
    target_pb: float | None
    target_ev_ebitda: float | None

    implied_price_pe: float | None
    implied_price_pb: float | None
    implied_price_ev_ebitda: float | None

    # Peer data status
    peer_data_source: str | None = None
    relative_valuation_status: str = "pending_peer_dataset"

    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        def _r(v: float | None, d: int = 2) -> float | None:
            return round(v, d) if v is not None else None

        return {
            "ticker": self.ticker,
            "latest_fy": self.latest_fy,
            "current_price_vnd": _r(self.current_price_vnd, 0),
            "eps_vnd": _r(self.eps_vnd, 0),
            "book_value_per_share_vnd": _r(self.book_value_per_share_vnd, 0),
            "ebitda_vnd_bn": _r(self.ebitda_vnd_bn),
            "net_debt_vnd_bn": _r(self.net_debt_vnd_bn),
            "shares_mn": _r(self.shares_mn),
            "pe_ratio": _r(self.pe_ratio),
            "pb_ratio": _r(self.pb_ratio),
            "target_pe": _r(self.target_pe),
            "target_pb": _r(self.target_pb),
            "target_ev_ebitda": _r(self.target_ev_ebitda),
            "implied_price_pe": _r(self.implied_price_pe, 0),
            "implied_price_pb": _r(self.implied_price_pb, 0),
            "implied_price_ev_ebitda": _r(self.implied_price_ev_ebitda, 0),
            "peer_data_source": self.peer_data_source,
            "relative_valuation_status": self.relative_valuation_status,
            "warnings": self.warnings,
        }


def _get(table: FactTable, key: str, period: str) -> float | None:
    entry = table.get(key, {}).get(period)
    if entry is None:
        return None
    return entry.value if hasattr(entry, "value") else float(entry)


def compute_multiples(
    ticker: str,
    fact_table: FactTable,
    current_price_vnd: float | None = None,
    target_pe: float | None = None,
    target_pb: float | None = None,
    target_ev_ebitda: float | None = None,
    peer_data_source: str | None = None,
) -> MultiplesResult:
    """Compute market multiples and implied target prices.

    Args:
        current_price_vnd: Latest market close price in VND.
        target_pe: Peer-derived forward P/E. Must have peer_data_source to be used.
        target_pb: Peer-derived P/B. Must have peer_data_source to be used.
        target_ev_ebitda: Peer-derived EV/EBITDA. Must have peer_data_source to be used.
        peer_data_source: Description of peer group source (e.g. "VN pharma peers: IMP, DMC, TRA").
            If None, target multiples are blocked — implied prices will be None.

    Peer guard rule:
        If peer_data_source is None, implied prices from target multiples are set to None.
        The relative_valuation_status is set to "pending_peer_dataset".
        No default P/E or EV/EBITDA targets are applied without peer_data_source.
    """
    warnings: list[str] = []

    fy_periods = sorted(
        p for p in {p for vals in fact_table.values() for p in vals} if p.endswith("FY")
    )
    if not fy_periods:
        return MultiplesResult(
            ticker=ticker, latest_fy="", current_price_vnd=current_price_vnd,
            eps_vnd=None, book_value_per_share_vnd=None,
            ebitda_vnd_bn=None, net_debt_vnd_bn=None, shares_mn=None,
            pe_ratio=None, pb_ratio=None,
            target_pe=target_pe, target_pb=target_pb, target_ev_ebitda=target_ev_ebitda,
            implied_price_pe=None, implied_price_pb=None, implied_price_ev_ebitda=None,
            warnings=["No FY periods in fact_table"],
        )

    latest_fy = fy_periods[-1]

    eps = _get(fact_table, "eps.basic", latest_fy)
    ni = _get(fact_table, "net_income.parent", latest_fy)
    equity = _get(fact_table, "equity.parent", latest_fy)
    ebitda = _get(fact_table, "ebitda.total", latest_fy)
    total_debt = _get(fact_table, "total_debt.ending", latest_fy) or 0.0
    cash = _get(fact_table, "cash_and_equivalents.ending", latest_fy) or 0.0

    # Shares outstanding (mn)
    shares_mn: float | None = None
    if ni is not None and eps is not None and eps > 0:
        shares_mn = (ni * 1_000) / eps  # VND bn * 1000 / VND per share = mn shares

    # Book value per share
    bvps: float | None = None
    if equity is not None and shares_mn and shares_mn > 0:
        bvps = (equity / shares_mn) * 1_000  # VND bn / mn shares * 1000 = VND/share

    net_debt = total_debt - cash

    # Observed multiples
    pe_ratio: float | None = None
    pb_ratio: float | None = None
    if current_price_vnd is not None:
        if eps and eps > 0:
            pe_ratio = current_price_vnd / eps
        else:
            warnings.append("EPS unavailable — P/E cannot be computed from current price")
        if bvps and bvps > 0:
            pb_ratio = current_price_vnd / bvps
        else:
            warnings.append("BVPS unavailable — P/B cannot be computed from current price")
    else:
        warnings.append("No current price provided — observed P/E and P/B omitted")

    # ── Peer guard: no default multiples without peer data source ─────────
    rv_status: str
    if peer_data_source is None:
        warnings.append(
            "Relative valuation is PENDING — no peer_data_source provided. "
            "Target P/E, P/B, and EV/EBITDA require a real peer group dataset. "
            "Implied prices blocked until peer data is available."
        )
        rv_status = "pending_peer_dataset"
        # Block all implied prices
        return MultiplesResult(
            ticker=ticker,
            latest_fy=latest_fy,
            current_price_vnd=current_price_vnd,
            eps_vnd=eps,
            book_value_per_share_vnd=bvps,
            ebitda_vnd_bn=ebitda,
            net_debt_vnd_bn=net_debt,
            shares_mn=shares_mn,
            pe_ratio=pe_ratio,
            pb_ratio=pb_ratio,
            target_pe=target_pe,
            target_pb=target_pb,
            target_ev_ebitda=target_ev_ebitda,
            implied_price_pe=None,
            implied_price_pb=None,
            implied_price_ev_ebitda=None,
            peer_data_source=None,
            relative_valuation_status=rv_status,
            warnings=warnings,
        )

    rv_status = "peer_data_available"

    # ── Implied prices at target multiples ────────────────────────────────
    implied_pe: float | None = None
    implied_pb: float | None = None
    implied_ev_ebitda: float | None = None

    if target_pe is not None and eps and eps > 0:
        implied_pe = target_pe * eps
    if target_pb is not None and bvps and bvps > 0:
        implied_pb = target_pb * bvps

    # EV/EBITDA: requires full bridge (EBITDA + net_debt + shares)
    if target_ev_ebitda is not None:
        if ebitda is None:
            warnings.append("EV/EBITDA blocked: EBITDA unavailable for EV bridge.")
        elif net_debt is None:
            warnings.append("EV/EBITDA blocked: net_debt unavailable — cannot compute EV-to-equity bridge.")
        elif not shares_mn or shares_mn <= 0:
            warnings.append("EV/EBITDA blocked: shares outstanding unavailable.")
        else:
            ev_impl = ebitda * target_ev_ebitda
            equity_impl = ev_impl - net_debt
            if equity_impl > 0:
                implied_ev_ebitda = (equity_impl / shares_mn) * 1_000
            else:
                warnings.append("EV/EBITDA: implied equity value is negative — omitted")

    return MultiplesResult(
        ticker=ticker,
        latest_fy=latest_fy,
        current_price_vnd=current_price_vnd,
        eps_vnd=eps,
        book_value_per_share_vnd=bvps,
        ebitda_vnd_bn=ebitda,
        net_debt_vnd_bn=net_debt,
        shares_mn=shares_mn,
        pe_ratio=pe_ratio,
        pb_ratio=pb_ratio,
        target_pe=target_pe,
        target_pb=target_pb,
        target_ev_ebitda=target_ev_ebitda,
        implied_price_pe=implied_pe,
        implied_price_pb=implied_pb,
        implied_price_ev_ebitda=implied_ev_ebitda,
        peer_data_source=peer_data_source,
        relative_valuation_status=rv_status,
        warnings=warnings,
    )
