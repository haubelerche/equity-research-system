from backend.facts.normalizer import build_fact_table, to_analytics_vnd_bn


def test_analytics_adapter_scales_only_monetary_facts():
    table = build_fact_table([
        {
            "line_item_code": "revenue.net",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "value": 5_267.0,
            "unit": "vnd_bn",
        },
        {
            "line_item_code": "eps.basic",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "value": 6_308.0,
            "unit": "vnd",
        },
        {
            "line_item_code": "shares_outstanding.ending",
            "fiscal_year": 2025,
            "fiscal_period": "FY",
            "value": 130_746_071.0,
            "unit": "shares",
        },
    ])

    adapted = to_analytics_vnd_bn(table)

    assert adapted["revenue.net"]["2025FY"].value == 5_267.0
    assert adapted["eps.basic"]["2025FY"].value == 6_308.0
    assert adapted["shares_outstanding.ending"]["2025FY"].value == 130_746_071.0
