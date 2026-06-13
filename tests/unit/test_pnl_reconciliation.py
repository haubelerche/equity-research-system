from backend.analytics.forecasting import reconcile_pnl


def test_pnl_closes_to_net_income():
    row = {
        "revenue": 2000.0, "cogs": -1050.0, "selling": -440.0, "admin": -150.0,
        "financial_income": 20.0, "financial_expense": -5.0, "other": 0.0, "tax": -60.0,
    }
    rec = reconcile_pnl(row)
    assert abs(rec["ebit"] - 360.0) < 0.01      # 2000-1050-440-150
    assert abs(rec["pbt"] - 375.0) < 0.01       # 360+20-5
    assert abs(rec["net_income"] - 315.0) < 0.01  # 375-60
    assert rec["reconciles"] is True


def test_pnl_flags_gap_against_reported_ni():
    row = {
        "revenue": 1865.0, "cogs": -981.0, "selling": -418.0, "admin": -140.0,
        "financial_expense": -4.0, "tax": -54.0, "net_income": 292.0,
    }
    rec = reconcile_pnl(row)
    # EBIT=326, PBT=322, NI=268 -> does NOT match reported 292 -> flagged
    assert rec["reconciles"] is False
