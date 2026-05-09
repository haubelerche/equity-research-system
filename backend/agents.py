from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scripts.connectors.catalyst_bhyt_connector import sync_bhyt_connector
from scripts.connectors.catalyst_dav_connector import sync_dav_connector
from scripts.connectors.catalyst_hose_connector import sync_hose_hnx_connector
from scripts.connectors.catalyst_tender_connector import sync_tender_connector
from scripts.connectors.vnstock_finance_connector import sync_financial_for_universe
from scripts.db.fact_store import PostgresFactStore

from backend.runtime_store import RuntimeStore
from backend.utils import deterministic_id


@dataclass(frozen=True)
class AgentResult:
    confidence: float
    payload: dict[str, Any]
    evidence_refs: list[dict[str, Any]]
    confidence_breakdown: dict[str, float]
    needs_human: bool = False


class DataAgent:
    def __init__(self, store: RuntimeStore) -> None:
        self.store = store

    def run(self, run_id: str, ticker: str) -> AgentResult:
        evidence_refs: list[dict[str, Any]] = []
        result = {"financial_facts_upserted": 0, "catalyst_events_upserted": 0, "connector_errors": []}

        try:
            upserted_facts = sync_financial_for_universe(tickers=[ticker]).get(ticker, 0)
            result["financial_facts_upserted"] = upserted_facts
            evidence_refs.append({"source": "financial_facts", "ticker": ticker, "rows": upserted_facts})
        except Exception as exc:  # noqa: BLE001
            result["connector_errors"].append(f"finance:{exc}")

        for name, fn in (
            ("hose_hnx", lambda: sync_hose_hnx_connector(tickers=[ticker])),
            ("dav", sync_dav_connector),
            ("tender", sync_tender_connector),
            ("bhyt", sync_bhyt_connector),
        ):
            try:
                upserted = fn()
                result["catalyst_events_upserted"] += int(upserted)
                evidence_refs.append({"source": f"catalyst_{name}", "rows": int(upserted)})
            except Exception as exc:  # noqa: BLE001
                result["connector_errors"].append(f"{name}:{exc}")

        errors = len(result["connector_errors"])
        confidence = 0.95 if errors == 0 else max(0.5, 0.9 - errors * 0.1)
        return AgentResult(
            confidence=confidence,
            payload=result,
            evidence_refs=evidence_refs,
            confidence_breakdown={"connector_health": confidence, "dqf_readiness": 0.9},
            needs_human=errors > 2,
        )


class QuantAgent:
    def __init__(self, fact_store: PostgresFactStore) -> None:
        self.fact_store = fact_store

    @staticmethod
    def _latest_metric(frame, metric_key: str) -> float | None:
        row = frame[frame["metrics"] == metric_key]
        if row.empty:
            return None
        cols = [c for c in row.columns if c != "metrics"]
        if not cols:
            return None
        latest_col = sorted(cols)[-1]
        value = row.iloc[0][latest_col]
        return float(value) if value is not None else None

    def run(self, ticker: str) -> AgentResult:
        frame = self.fact_store.query_financial_facts_wide(ticker=ticker, statement="income_statement")
        revenue = self._latest_metric(frame, "revenue.net")
        ebitda = self._latest_metric(frame, "ebitda.total")
        net_income = self._latest_metric(frame, "net_income.parent")
        eps = self._latest_metric(frame, "eps.basic")

        missing = [k for k, v in {"revenue.net": revenue, "ebitda.total": ebitda, "net_income.parent": net_income}.items() if v is None]
        if missing:
            return AgentResult(
                confidence=0.3,
                payload={"error": "missing_required_metrics", "missing": missing},
                evidence_refs=[{"source": "financial_facts", "ticker": ticker}],
                confidence_breakdown={"data_completeness": 0.3, "formula_integrity": 1.0},
                needs_human=True,
            )

        # Code-first deterministic valuation proxies for MVP stage.
        dcf_value = float(ebitda * 6.5)
        ev_ebitda_value = float(ebitda * 8.0)
        pe_target = float((eps or 0) * 12.0)
        confidence = 0.92 if eps is not None else 0.86

        payload = {
            "ticker": ticker,
            "methods": ["dcf_proxy", "ev_ebitda_proxy", "pe_proxy"],
            "valuation": {
                "dcf_proxy": dcf_value,
                "ev_ebitda_proxy": ev_ebitda_value,
                "pe_proxy": pe_target,
            },
            "drivers": {
                "revenue.net": revenue,
                "ebitda.total": ebitda,
                "net_income.parent": net_income,
                "eps.basic": eps,
            },
            "assumptions": {"dcf_multiple": 6.5, "ev_ebitda_multiple": 8.0, "pe_multiple": 12.0},
        }
        return AgentResult(
            confidence=confidence,
            payload=payload,
            evidence_refs=[{"source": "financial_facts", "ticker": ticker, "keys": list(payload["drivers"].keys())}],
            confidence_breakdown={"data_completeness": 0.9, "formula_integrity": 1.0},
            needs_human=False,
        )


class ResearcherAgent:
    def run(self, ticker: str, valuation_payload: dict[str, Any]) -> AgentResult:
        valuations = valuation_payload.get("valuation", {})
        dcf_proxy = float(valuations.get("dcf_proxy") or 0.0)
        ev_ebitda_proxy = float(valuations.get("ev_ebitda_proxy") or 0.0)
        pe_proxy = float(valuations.get("pe_proxy") or 0.0)
        thesis = (
            f"{ticker}: valuation snapshot shows DCF proxy {dcf_proxy:.2f}, "
            f"EV/EBITDA proxy {ev_ebitda_proxy:.2f}, and PE proxy {pe_proxy:.2f}. "
            "Catalyst-sensitive assumptions must be reviewed before publication."
        )
        claims = [
            {
                "claim_id": deterministic_id(ticker, "claim", "dcf_proxy"),
                "text": f"{ticker} DCF proxy valuation = {dcf_proxy:.2f}",
                "value": dcf_proxy,
                "metric_key": "dcf_proxy",
            },
            {
                "claim_id": deterministic_id(ticker, "claim", "ev_ebitda_proxy"),
                "text": f"{ticker} EV/EBITDA proxy valuation = {ev_ebitda_proxy:.2f}",
                "value": ev_ebitda_proxy,
                "metric_key": "ev_ebitda_proxy",
            },
        ]
        return AgentResult(
            confidence=0.86,
            payload={"ticker": ticker, "thesis": thesis, "claims": claims},
            evidence_refs=valuation_payload.get("evidence_refs", []) if isinstance(valuation_payload.get("evidence_refs"), list) else [],
            confidence_breakdown={"narrative_coherence": 0.86, "grounded_input": 0.9},
            needs_human=False,
        )


class AuditorAgent:
    def run(self, ticker: str, claims: list[dict[str, Any]], evidence_refs: list[dict[str, Any]]) -> AgentResult:
        missing = []
        for claim in claims:
            if claim.get("value") in (None, ""):
                missing.append(claim["claim_id"])
        coverage = 0.0 if not claims else (len(claims) - len(missing)) / len(claims)
        passed = coverage >= 1.0 and len(evidence_refs) > 0
        payload = {
            "ticker": ticker,
            "citation_coverage_ratio": coverage,
            "missing_claim_ids": missing,
            "passed": passed,
        }
        return AgentResult(
            confidence=0.95 if passed else 0.6,
            payload=payload,
            evidence_refs=evidence_refs,
            confidence_breakdown={"claim_coverage": coverage, "evidence_presence": 1.0 if evidence_refs else 0.0},
            needs_human=not passed,
        )


class DebateAgent:
    """Phase-6 debate/critique loop: believer vs skeptic over locked artifacts."""

    def run(self, ticker: str, thesis_payload: dict[str, Any], valuation_payload: dict[str, Any]) -> AgentResult:
        claims = thesis_payload.get("claims", [])
        valuation = valuation_payload.get("valuation", {})
        believer_points = []
        skeptic_points = []

        if valuation.get("dcf_proxy") is not None:
            believer_points.append("DCF proxy supports upside if EBITDA remains stable.")
            skeptic_points.append("DCF proxy may overstate value under policy or reimbursement shocks.")
        if valuation.get("pe_proxy") is not None:
            believer_points.append("PE proxy indicates acceptable relative valuation for current earnings.")
            skeptic_points.append("PE proxy is sensitive to one-off earnings and accounting normalization.")

        critique_required = len(claims) < 2
        reconciled_actions = []
        if critique_required:
            reconciled_actions.append("Request ResearcherAgent to expand claim set before publish.")
        else:
            reconciled_actions.append("Proceed to AuditorAgent with current claim package.")

        payload = {
            "ticker": ticker,
            "believer_points": believer_points,
            "skeptic_points": skeptic_points,
            "reconciled_actions": reconciled_actions,
            "critique_required": critique_required,
        }
        confidence = 0.8 if not critique_required else 0.62
        return AgentResult(
            confidence=confidence,
            payload=payload,
            evidence_refs=thesis_payload.get("evidence_refs", []),
            confidence_breakdown={"debate_completeness": confidence, "artifact_lock_integrity": 0.95},
            needs_human=critique_required,
        )

