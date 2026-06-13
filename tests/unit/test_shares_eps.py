from backend.analytics.shares import eps_reconciles


def test_eps_reconciles_with_weighted_shares():
    # NI 292 tỷ, weighted shares 109.2m -> EPS ~ 2,674
    assert eps_reconciles(net_income_bn=292.0, weighted_avg_shares_mn=109.2, eps_vnd=2674, tol=0.03)


def test_eps_mismatch_flagged():
    # NI 292 / 94m = 3,106, not 2,674 -> mismatch beyond tol
    assert not eps_reconciles(net_income_bn=292.0, weighted_avg_shares_mn=94.0, eps_vnd=2674, tol=0.03)


def test_eps_missing_inputs_block():
    assert not eps_reconciles(None, 100.0, 2000)
    assert not eps_reconciles(292.0, None, 2000)
    assert not eps_reconciles(292.0, 100.0, None)
    assert not eps_reconciles(292.0, 0.0, 2000)
