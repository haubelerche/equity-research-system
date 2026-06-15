from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[2]


def recompute(case):
    inp = case["inputs"]
    base = inp["base_free_cash_flow_bn"]
    g = inp["growth"]
    wacc = inp["wacc"]
    tg = inp["terminal_growth"]
    fcf = [base * ((1 + g) ** i) for i in range(1, 6)]
    pv = [fcf[i] / ((1 + wacc) ** (i + 1)) for i in range(5)]
    tv = fcf[-1] * (1 + tg) / (wacc - tg)
    ev = sum(pv) + tv / ((1 + wacc) ** 5)
    equity = ev - inp["net_debt_bn"]
    tp = equity * 1e9 / inp["shares_outstanding"]
    return ev, equity, tp


def test_valuation_cases_reproducible():
    path = ROOT / "03_financial_benchmarks" / "golden_valuation" / "valuation_cases.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        case = json.loads(line)
        assert case["inputs"]["wacc"] > case["inputs"]["terminal_growth"]
        assert case["inputs"]["shares_outstanding"] > 0
        ev, equity, tp = recompute(case)
        assert abs(ev - case["expected_outputs"]["enterprise_value_bn"]) <= case["tolerances"]["enterprise_value_bn_abs"]
        assert abs(tp - case["expected_outputs"]["target_price_vnd"]) / max(abs(tp), 1) <= case["tolerances"]["target_price_vnd_pct"]
