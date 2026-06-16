"""Read-only: show DHG interest-bearing debt + the debt-schedule method chosen.

Confirms why FCFE is blocked: which forecast method build_forecast_debt_schedule
selects and whether is_fcfe_publishable is True.
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
from backend.analytics.debt_schedule import (
    interest_bearing_debt, build_historical_debt_schedule, build_forecast_debt_schedule, DebtSchedule,
)

ticker = "DHG"
ft = _load_fact_table_from_production(ticker, 2022, 2025)
fy = sorted({p for vals in ft.values() for p in vals if p.endswith("FY")})
print(f"FY periods: {fy}")

def g(metric, period):
    e = ft.get(metric, {}).get(period)
    return getattr(e, "value", None) if e is not None else None

print("\nperiod | int_bearing_debt | total_debt.ending | st_borr | lt_borr | st_debt | lt_debt | proceeds | repay")
for p in fy:
    print(f"  {p} | {interest_bearing_debt(ft, p)} | {g('total_debt.ending',p)} | "
          f"{g('short_term_borrowings.ending',p)} | {g('long_term_borrowings.ending',p)} | "
          f"{g('short_term_debt.ending',p)} | {g('long_term_debt.ending',p)} | "
          f"{g('proceeds_from_borrowings.total',p)} | {g('repayment_of_borrowings.total',p)}")

hist = build_historical_debt_schedule(ticker, ft, fy)
print("\nHISTORICAL rows:")
for r in hist:
    print(f"  {r.label}: ending={r.ending_interest_bearing_debt} nb={r.net_borrowing} method={r.method} conf={r.confidence}")

f_labels = [f"{y}F" for y in range(2026, 2031)]
f_years = list(range(2026, 2031))
frows, method, warns = build_forecast_debt_schedule(ticker, ft, hist, f_labels, f_years)
print(f"\nFORECAST method={method}")
for r in frows:
    print(f"  {r.label}: ending={r.ending_interest_bearing_debt} nb={r.net_borrowing} conf={r.confidence}")
sched = DebtSchedule(ticker=ticker, historical_rows=hist, forecast_rows=frows, forecast_method=method, warnings=warns)
print(f"\nstatus={sched.status}  is_fcfe_publishable={sched.is_fcfe_publishable}")
print(f"fcfe_block_reason={sched.fcfe_block_reason}")
