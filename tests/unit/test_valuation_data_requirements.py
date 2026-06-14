from __future__ import annotations

from backend.valuation.data_requirements import (
    VALUATION_DATA_REQUIREMENTS,
    MethodRequirement,
    get_requirement,
)


def test_all_four_methods_registered():
    assert set(VALUATION_DATA_REQUIREMENTS) == {"fcff_dcf", "fcfe_dcf", "pe", "ev_ebitda"}


def test_fcfe_requires_gross_financing_lines():
    req = get_requirement("fcfe_dcf")
    assert "proceeds_from_borrowings.total" in req.required_facts
    assert "repayment_of_borrowings.total" in req.required_facts
    assert "operating_cash_flow.total" in req.required_facts
    assert "capex.total" in req.required_facts
    assert "shares_outstanding.ending" in req.required_facts
    assert "cost_of_equity" in req.required_assumptions
    assert "market_price" in req.required_market_data


def test_requirements_use_registered_canonical_keys():
    # Every required_fact must be a known canonical metric (else it can never be present).
    from backend.facts.metric_metadata import is_known_metric
    for req in VALUATION_DATA_REQUIREMENTS.values():
        for fact in req.required_facts:
            assert is_known_metric(fact), f"{req.method}: unknown canonical key {fact}"


def test_get_requirement_unknown_method_raises():
    import pytest
    with pytest.raises(KeyError):
        get_requirement("dividend_discount")


def test_requirement_is_frozen():
    req = get_requirement("pe")
    assert isinstance(req, MethodRequirement)
