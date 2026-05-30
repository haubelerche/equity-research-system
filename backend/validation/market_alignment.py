"""Market data alignment validation (Plan §11.8).

Rules:
  - Historical P/E MUST use historical year-end price, NOT current price.
  - If current price is used with historical EPS, label must be
    "Current price applied to historical EPS" — not "Historical P/E".
  - Current P/E uses current price × latest EPS/TTM EPS — acceptable.
  - Current market cap = current_price × current_shares.
  - Historical market cap MUST use historical price × historical shares.

Returns a list of MarketAlignmentIssue, each with severity and a corrected_label
when the label is wrong.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional


Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]


@dataclass
class MarketAlignmentIssue:
    check_id: str
    severity: Severity
    period: str
    metric: str
    label_used: str
    correct_label: str
    message: str
    blocks_valuation: bool


def check_pe_label(
    label: str,
    price_date: Optional[str],
    eps_period: str,
    current_price_date: Optional[str] = None,
) -> Optional[MarketAlignmentIssue]:
    """Validate that a P/E label is consistent with the price date used.

    Args:
        label:             The label string used in the report/artifact.
        price_date:        ISO date string of the price used (e.g. "2022-12-30").
                           None means unknown.
        eps_period:        Fiscal period of the EPS used (e.g. "2022FY").
        current_price_date: ISO date string of the current price quote date.
                            None means unknown.

    Returns:
        MarketAlignmentIssue if the label is incorrect, else None.
    """
    label_lower = label.lower()
    is_historical_label = "historical" in label_lower and "p/e" in label_lower

    if not is_historical_label:
        return None

    # Extract the year from eps_period
    try:
        eps_year = int(eps_period[:4])
    except (ValueError, IndexError):
        eps_year = None

    # If price_date and current_price_date are the same → current price used
    if price_date is not None and current_price_date is not None:
        if price_date == current_price_date:
            return MarketAlignmentIssue(
                check_id="MARKET_PE_LABEL_MISMATCH",
                severity="HIGH",
                period=eps_period,
                metric="pe_ratio",
                label_used=label,
                correct_label=f"Current price applied to {eps_period} EPS",
                message=(
                    f"Label '{label}' uses current price ({price_date}) with "
                    f"{eps_period} EPS — must be labeled "
                    f"'Current price applied to {eps_period} EPS', not 'Historical P/E'"
                ),
                blocks_valuation=False,
            )

    # If price_date year differs from eps_year → misaligned historical data
    if price_date is not None and eps_year is not None:
        try:
            price_year = int(price_date[:4])
        except (ValueError, IndexError):
            price_year = None

        if price_year is not None and price_year != eps_year:
            return MarketAlignmentIssue(
                check_id="MARKET_PE_PERIOD_MISMATCH",
                severity="HIGH",
                period=eps_period,
                metric="pe_ratio",
                label_used=label,
                correct_label=f"P/E ({price_year} price / {eps_period} EPS)",
                message=(
                    f"Label '{label}': price year {price_year} does not match "
                    f"EPS period {eps_year} — verify price date or use cross-period label"
                ),
                blocks_valuation=False,
            )

    return None


def check_market_cap_consistency(
    label: str,
    price_date: Optional[str],
    shares_period: str,
    is_historical: bool,
) -> Optional[MarketAlignmentIssue]:
    """Check that market cap label is consistent with price and shares dates.

    Historical market cap MUST use historical price and historical shares.
    Current market cap uses current price and latest shares — acceptable.
    """
    label_lower = label.lower()
    uses_historical_label = "historical" in label_lower and "market cap" in label_lower

    if not uses_historical_label:
        return None

    if not is_historical and uses_historical_label:
        return MarketAlignmentIssue(
            check_id="MARKET_MKTCAP_LABEL_MISMATCH",
            severity="MEDIUM",
            period=shares_period,
            metric="market_cap",
            label_used=label,
            correct_label=f"Current market cap (current price × {shares_period} shares)",
            message=(
                f"Label '{label}' uses current price but is labeled as historical "
                f"market cap — use current market cap label"
            ),
            blocks_valuation=False,
        )

    return None


def validate_valuation_labels(
    valuation_artifact: dict,
) -> list[MarketAlignmentIssue]:
    """Scan a valuation artifact dict for market alignment issues.

    Checks every entry in 'multiples' or 'peer_multiples' for P/E and
    market cap label violations.

    Expected artifact structure (partial):
        {
          "multiples": {
            "pe_trailing": {
              "label": "Historical P/E",
              "price_date": "2025-12-31",
              "eps_period": "2025FY",
              "current_price_date": "2026-05-27"
            }, ...
          }
        }
    """
    issues: list[MarketAlignmentIssue] = []

    multiples = valuation_artifact.get("multiples", {})
    for key, entry in multiples.items():
        if not isinstance(entry, dict):
            continue
        label = entry.get("label", "")
        price_date = entry.get("price_date")
        eps_period = entry.get("eps_period", "")
        current_price_date = entry.get("current_price_date")

        if "pe" in key.lower() and label:
            issue = check_pe_label(label, price_date, eps_period, current_price_date)
            if issue:
                issues.append(issue)

        if "market_cap" in key.lower() and label:
            is_historical = entry.get("is_historical", False)
            issue = check_market_cap_consistency(
                label, price_date, eps_period, is_historical
            )
            if issue:
                issues.append(issue)

    return issues


def format_issues_for_report(issues: list[MarketAlignmentIssue]) -> list[dict]:
    """Serialize issues for inclusion in the validation report artifact."""
    return [
        {
            "check_id": i.check_id,
            "severity": i.severity,
            "period": i.period,
            "metric": i.metric,
            "label_used": i.label_used,
            "correct_label": i.correct_label,
            "message": i.message,
            "blocks_valuation": i.blocks_valuation,
        }
        for i in issues
    ]
