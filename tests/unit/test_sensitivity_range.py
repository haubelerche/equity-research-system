from backend.analytics.sensitivity import _centered_range


def test_range_centers_on_base():
    r = _centered_range(0.138, step=0.01, points_each_side=2)
    assert r == [0.118, 0.128, 0.138, 0.148, 0.158]
    assert 0.138 in r  # base cell must exist (audit NUMERIC-07)


def test_range_drops_nonpositive():
    r = _centered_range(0.01, step=0.01, points_each_side=2)
    assert all(x > 0 for x in r)
    assert 0.01 in r
