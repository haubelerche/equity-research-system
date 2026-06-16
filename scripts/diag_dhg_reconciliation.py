"""Read-only: are DHG's IS reconciliation failures real, or false fails?

Prints the raw facts feeding IS_gross_profit_check and IS_net_income_check per
period, plus the check verdicts.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from backend.valuation.input_pack_builder import _load_fact_table_from_production
from backend.facts.reconciliation import _check_is_gross_profit, _check_is_net_income

ft = _load_fact_table_from_production("DHG", 2022, 2025)
fy = sorted({p for vals in ft.values() for p in vals if p.endswith("FY")})

def g(metric, period):
    e = ft.get(metric, {}).get(period)
    return getattr(e, "value", None) if e is not None else None

for p in fy:
    print(f"\n=== {p} ===")
    print(f"  revenue.net={g('revenue.net',p)} cogs.total={g('cogs.total',p)} gross_profit.total={g('gross_profit.total',p)}")
    print(f"  pbt={g('profit_before_tax.total',p)} tax={g('tax_expense.total',p)} "
          f"net_income.parent={g('net_income.parent',p)} net_income.total={g('net_income.total',p)} "
          f"minority={g('net_income.minority',p)}")
    gp = _check_is_gross_profit(ft, p)
    ni = _check_is_net_income(ft, p)
    if gp:
        print(f"  GP_check: {gp.status} | {gp.message}")
    if ni:
        print(f"  NI_check: {ni.status} | {ni.message}")
