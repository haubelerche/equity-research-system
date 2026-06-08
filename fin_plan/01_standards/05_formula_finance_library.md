# Kế hoạch triển khai thư viện công thức tài chính thành Python functions cho AI Agent

> Nguồn chuyển đổi: `Toàn bộ công thức của mình.docx` - bản tổng hợp 30 công thức tài chính và định giá doanh nghiệp.
>
> Mục tiêu của file này là làm tài liệu giao việc trực tiếp cho Claude Code/Codex/Cursor để biến toàn bộ công thức thành một thư viện Python thuần, có kiểm thử, có registry metadata, và có wrapper để AI Agent gọi an toàn khi sinh báo cáo định giá cổ phiếu.

---

## 1. Context

Dự án cần một lớp tính toán tài chính đáng tin cậy để Agent không tự suy luận hoặc tự bịa công thức khi lập báo cáo định giá cổ phiếu. Toàn bộ công thức phải được hiện thực thành các hàm Python deterministic, có input contract rõ ràng, xử lý lỗi chia cho 0, kiểm soát đơn vị dữ liệu và có test case bao phủ.

Các nhóm công thức cần triển khai:

1. Tăng trưởng và tỷ lệ cơ bản
2. Định giá thị trường
3. Khả năng sinh lời và hiệu quả hoạt động
4. Cấu trúc vốn và đòn bẩy tài chính
5. Khả năng thanh toán và thanh khoản
6. Hiệu quả quản lý tài sản và chu kỳ kinh doanh
7. Dòng tiền và cấu phần định giá
8. Chi phí vốn và định giá tài sản

---

## 2. Problem Statement

Hiện tại các công thức trong tài liệu đang ở dạng mô tả thủ công. Nếu để LLM Agent tự tính trực tiếp bằng prompt, hệ thống sẽ có các rủi ro sau:

- Công thức bị dùng sai do LLM diễn giải không nhất quán.
- Đơn vị phần trăm bị nhầm giữa `15` và `0.15`.
- Không xử lý được mẫu số bằng 0, dữ liệu âm bất thường hoặc thiếu dữ liệu.
- Không có test để chứng minh kết quả tính đúng.
- Không thể trace công thức nào đã được dùng trong báo cáo.
- Không tái sử dụng được cho nhiều ticker/nhiều kỳ tài chính.

Vì vậy cần tách logic tính toán thành một package Python độc lập, có thể được Agent gọi như một tool/function layer.

---

## 3. Design Principles

### 3.1. Deterministic-first

Mọi chỉ số phải được tính bằng Python function thuần. Agent chỉ được chọn công thức và truyền tham số; không được tự tạo công thức mới trong prompt.

### 3.2. Consistent unit policy

- Tất cả tỷ lệ/rate trong code trả về dạng decimal ratio.
  - Ví dụ: `0.15` nghĩa là `15%`.
  - Không trả về `15` cho `15%` ở core function.
- Presentation layer mới format thành `%`.
- Các biến đầu vào như `tax_rate`, `risk_free_rate`, `market_return`, `cost_of_debt`, `cost_of_equity` phải nhập dạng decimal.
  - Ví dụ: thuế suất 20% nhập là `0.20`.

### 3.3. No hidden data access

Các function không tự query database, không gọi API, không đọc file. Function chỉ nhận tham số số học đã được chuẩn hóa từ data pipeline.

### 3.4. Explicit error handling

- Mọi phép chia phải đi qua `safe_divide()`.
- Mặc định nếu mẫu số bằng 0 hoặc dữ liệu không hợp lệ, trả về `None` và warning metadata ở wrapper.
- Trong mode strict, raise `FormulaInputError`.

### 3.5. Traceability

Mỗi công thức phải có metadata:

- `formula_id`
- `name`
- `group`
- `description`
- `inputs`
- `output_unit`
- `formula_text`
- `function_name`

Agent cần dùng metadata này để trích dẫn công thức đã dùng trong báo cáo nội bộ.

---

## 4. Proposed Python Package Structure

```text
src/
  financial_formulas/
    __init__.py
    errors.py
    types.py
    utils.py
    growth.py
    market_valuation.py
    profitability.py
    capital_structure.py
    liquidity.py
    operating_cycle.py
    cash_flow.py
    cost_of_capital.py
    registry.py
    agent_tool.py

tests/
  test_growth.py
  test_market_valuation.py
  test_profitability.py
  test_capital_structure.py
  test_liquidity.py
  test_operating_cycle.py
  test_cash_flow.py
  test_cost_of_capital.py
  test_registry.py
  test_agent_tool.py
```

---

## 5. Core Types and Error Policy

### 5.1. `types.py`

```python
from dataclasses import dataclass, field
from typing import Any, Literal

Number = int | float

@dataclass(frozen=True)
class FormulaResult:
    formula_id: str
    name: str
    value: float | None
    unit: Literal["ratio", "currency_per_share", "multiple", "days", "currency", "turnover", "raw"]
    inputs: dict[str, Any]
    warnings: list[str] = field(default_factory=list)
```

### 5.2. `errors.py`

```python
class FormulaError(Exception):
    pass

class FormulaInputError(FormulaError):
    pass
```

### 5.3. `utils.py`

```python
import math
from .errors import FormulaInputError


def validate_number(value: float | int | None, name: str, strict: bool = False) -> float | None:
    if value is None:
        if strict:
            raise FormulaInputError(f"Missing input: {name}")
        return None
    try:
        x = float(value)
    except (TypeError, ValueError):
        if strict:
            raise FormulaInputError(f"Invalid numeric input: {name}={value}")
        return None
    if not math.isfinite(x):
        if strict:
            raise FormulaInputError(f"Non-finite numeric input: {name}={value}")
        return None
    return x


def safe_divide(numerator: float | int | None, denominator: float | int | None, strict: bool = False) -> float | None:
    n = validate_number(numerator, "numerator", strict=strict)
    d = validate_number(denominator, "denominator", strict=strict)
    if n is None or d is None:
        return None
    if d == 0:
        if strict:
            raise FormulaInputError("Division by zero")
        return None
    return n / d


def average(begin_value: float | int | None, end_value: float | int | None, strict: bool = False) -> float | None:
    b = validate_number(begin_value, "begin_value", strict=strict)
    e = validate_number(end_value, "end_value", strict=strict)
    if b is None or e is None:
        return None
    return (b + e) / 2
```

---

## 6. Formula Implementation Specification

### 6.1. Nhóm 1 - Tăng trưởng và tỷ lệ cơ bản

File: `growth.py`

| ID | Chỉ số | Function | Output | Công thức |
|---|---|---|---|---|
| F001 | CAGR | `cagr(begin_value, end_value, periods)` | ratio | `(V_end / V_begin) ** (1 / n) - 1` |
| F002 | YoY Doanh thu | `yoy_revenue_growth(current_revenue, previous_revenue)` | ratio | `(DT_t - DT_t-1) / DT_t-1` |
| F003 | YoY Lợi nhuận | `yoy_net_income_growth(current_net_income, previous_net_income)` | ratio | `(LN_t - LN_t-1) / LN_t-1` |
| F004 | Tỷ lệ phần trăm cấu phần | `component_ratio(component_value, total_value)` | ratio | `component / total` |

Implementation notes:

- `cagr()` cần kiểm tra `periods > 0`.
- Nếu `begin_value <= 0`, CAGR truyền thống không ổn định với dữ liệu âm/0. Trả `None` hoặc raise trong strict mode.
- `YoY` có thể âm nếu doanh thu/lợi nhuận giảm; đây là kết quả hợp lệ.

Expected signatures:

```python
def cagr(begin_value: Number, end_value: Number, periods: Number, strict: bool = False) -> float | None: ...
def yoy_revenue_growth(current_revenue: Number, previous_revenue: Number, strict: bool = False) -> float | None: ...
def yoy_net_income_growth(current_net_income: Number, previous_net_income: Number, strict: bool = False) -> float | None: ...
def component_ratio(component_value: Number, total_value: Number, strict: bool = False) -> float | None: ...
```

---

### 6.2. Nhóm 2 - Định giá thị trường

File: `market_valuation.py`

| ID | Chỉ số | Function | Output | Công thức |
|---|---|---|---|---|
| F005 | EPS | `eps(net_income_after_tax, preferred_dividends, weighted_avg_common_shares)` | currency_per_share | `(LNST - cổ tức ưu đãi) / CP phổ thông lưu hành bình quân` |
| F006 | P/E | `pe_ratio(market_price_per_share, eps_value)` | multiple | `price / EPS` |
| F007 | P/B | `pb_ratio(market_price_per_share, bvps_value)` | multiple | `price / BVPS` |
| F008 | P/S | `ps_ratio(market_price_per_share, sales_per_share_value)` | multiple | `price / SPS` |
| F009 | EV/EBITDA | `ev_to_ebitda(enterprise_value, ebitda)` | multiple | `EV / EBITDA` |
| F010 | BVPS | `bvps(total_equity, intangible_assets, common_shares_outstanding)` | currency_per_share | `(VCSH - tài sản vô hình) / CP phổ thông lưu hành` |

Helper functions nên có:

| Helper | Function | Công thức |
|---|---|---|
| Sales Per Share | `sales_per_share(net_revenue, weighted_avg_common_shares)` | `net_revenue / weighted_avg_common_shares` |
| Enterprise Value | `enterprise_value(market_cap, total_debt, cash_and_equivalents)` | `market_cap + total_debt - cash_and_equivalents` |

Implementation notes:

- EPS âm là hợp lệ nhưng P/E với EPS âm nên trả giá trị âm kèm warning ở wrapper, hoặc để core function trả số âm và presentation layer giải thích.
- Nếu EBITDA bằng 0, `ev_to_ebitda()` trả `None`.
- Nếu số cổ phiếu bằng 0 hoặc thiếu, EPS/BVPS/SPS trả `None`.

Expected signatures:

```python
def eps(net_income_after_tax: Number, preferred_dividends: Number, weighted_avg_common_shares: Number, strict: bool = False) -> float | None: ...
def pe_ratio(market_price_per_share: Number, eps_value: Number, strict: bool = False) -> float | None: ...
def pb_ratio(market_price_per_share: Number, bvps_value: Number, strict: bool = False) -> float | None: ...
def ps_ratio(market_price_per_share: Number, sales_per_share_value: Number, strict: bool = False) -> float | None: ...
def ev_to_ebitda(enterprise_value: Number, ebitda: Number, strict: bool = False) -> float | None: ...
def bvps(total_equity: Number, intangible_assets: Number, common_shares_outstanding: Number, strict: bool = False) -> float | None: ...
def sales_per_share(net_revenue: Number, weighted_avg_common_shares: Number, strict: bool = False) -> float | None: ...
def enterprise_value(market_cap: Number, total_debt: Number, cash_and_equivalents: Number, strict: bool = False) -> float | None: ...
```

---

### 6.3. Nhóm 3 - Khả năng sinh lời và hiệu quả hoạt động

File: `profitability.py`

| ID | Chỉ số | Function | Output | Công thức |
|---|---|---|---|---|
| F011 | ROA | `roa(net_income_after_tax, average_total_assets)` | ratio | `LNST / tổng tài sản bình quân` |
| F012 | ROE | `roe(net_income_after_tax, average_total_equity)` | ratio | `LNST / VCSH bình quân` |
| F013 | ROS | `ros(net_income_after_tax, net_revenue)` | ratio | `LNST / doanh thu thuần` |
| F020 | Biên lợi nhuận gộp | `gross_profit_margin(net_revenue, cost_of_goods_sold)` | ratio | `(doanh thu thuần - giá vốn) / doanh thu thuần` |
| F021 | Biên lợi nhuận ròng | `net_profit_margin(net_income_after_tax, net_revenue)` | ratio | `LNST / doanh thu thuần` |

Implementation notes:

- `ros()` và `net_profit_margin()` cùng công thức. Có thể giữ cả hai function để đúng vocabulary nghiệp vụ, nhưng implementation có thể dùng chung helper nội bộ.
- Không nhân `* 100` trong core function. Format `%` ở presentation layer.

Expected signatures:

```python
def roa(net_income_after_tax: Number, average_total_assets: Number, strict: bool = False) -> float | None: ...
def roe(net_income_after_tax: Number, average_total_equity: Number, strict: bool = False) -> float | None: ...
def ros(net_income_after_tax: Number, net_revenue: Number, strict: bool = False) -> float | None: ...
def gross_profit_margin(net_revenue: Number, cost_of_goods_sold: Number, strict: bool = False) -> float | None: ...
def net_profit_margin(net_income_after_tax: Number, net_revenue: Number, strict: bool = False) -> float | None: ...
```

---

### 6.4. Nhóm 4 - Cấu trúc vốn và đòn bẩy tài chính

File: `capital_structure.py`

| ID | Chỉ số | Function | Output | Công thức |
|---|---|---|---|---|
| F014 | Nợ/VCSH | `debt_to_equity(total_debt_or_liabilities, total_equity)` | multiple | `tổng nợ / VCSH` |

Implementation notes:

- Tài liệu cho phép hiểu `tổng nợ` là `tổng nợ phải trả`, nhưng nhiều nhà phân tích dùng `nợ vay tài chính chịu lãi`. Vì vậy tên tham số nên trung lập: `total_debt_or_liabilities`.
- Trong data pipeline, cần ghi rõ đang dùng biến nào: `total_liabilities` hay `interest_bearing_debt`.

Expected signature:

```python
def debt_to_equity(total_debt_or_liabilities: Number, total_equity: Number, strict: bool = False) -> float | None: ...
```

---

### 6.5. Nhóm 5 - Khả năng thanh toán và thanh khoản

File: `liquidity.py`

| ID | Chỉ số | Function | Output | Công thức |
|---|---|---|---|---|
| F015 | Thanh toán tiền mặt | `cash_ratio(cash_and_equivalents, short_term_investments, current_liabilities)` | multiple | `(tiền + đầu tư ngắn hạn) / nợ ngắn hạn` |
| F018 | Thanh toán nhanh | `quick_ratio(current_assets, inventory, current_liabilities)` | multiple | `(tài sản ngắn hạn - tồn kho) / nợ ngắn hạn` |
| F022 | Thanh toán hiện thời | `current_ratio(current_assets, current_liabilities)` | multiple | `tài sản ngắn hạn / nợ ngắn hạn` |

Implementation notes:

- `current_liabilities = 0` phải trả `None`.
- Nếu `current_assets < inventory`, quick ratio âm là tín hiệu dữ liệu bất thường. Core có thể trả số âm; wrapper nên warning.

Expected signatures:

```python
def cash_ratio(cash_and_equivalents: Number, short_term_investments: Number, current_liabilities: Number, strict: bool = False) -> float | None: ...
def quick_ratio(current_assets: Number, inventory: Number, current_liabilities: Number, strict: bool = False) -> float | None: ...
def current_ratio(current_assets: Number, current_liabilities: Number, strict: bool = False) -> float | None: ...
```

---

### 6.6. Nhóm 6 - Hiệu quả quản lý tài sản và chu kỳ kinh doanh

File: `operating_cycle.py`

| ID | Chỉ số | Function | Output | Công thức |
|---|---|---|---|---|
| F016 | DSO - ngày thu tiền bình quân | `days_sales_outstanding(average_accounts_receivable, net_revenue, days=365)` | days | `(phải thu bình quân / doanh thu thuần) * 365` |
| F017 | DIO - ngày tồn kho bình quân | `days_inventory_outstanding(average_inventory, cost_of_goods_sold, days=365)` | days | `(tồn kho bình quân / giá vốn hàng bán) * 365` |
| F019 | DPO - ngày thanh toán bình quân | `days_payable_outstanding(average_accounts_payable, cost_of_goods_sold, days=365)` | days | `(phải trả bình quân / giá vốn hàng bán) * 365` |
| F023 | Vòng quay TSCĐ | `fixed_asset_turnover(net_revenue, average_net_fixed_assets)` | turnover | `doanh thu thuần / TSCĐ ròng bình quân` |

Implementation notes:

- Tham số `days` mặc định `365`; cho phép override `360` nếu sau này cần convention khác.
- Các chỉ số ngày âm thường là bất thường; wrapper nên warning nếu output `< 0`.
- DSO/DIO/DPO yêu cầu số bình quân. Không tự lấy kỳ đầu/cuối trong function chính; dùng helper `average()` ở `utils.py`.

Expected signatures:

```python
def days_sales_outstanding(average_accounts_receivable: Number, net_revenue: Number, days: Number = 365, strict: bool = False) -> float | None: ...
def days_inventory_outstanding(average_inventory: Number, cost_of_goods_sold: Number, days: Number = 365, strict: bool = False) -> float | None: ...
def days_payable_outstanding(average_accounts_payable: Number, cost_of_goods_sold: Number, days: Number = 365, strict: bool = False) -> float | None: ...
def fixed_asset_turnover(net_revenue: Number, average_net_fixed_assets: Number, strict: bool = False) -> float | None: ...
```

---

### 6.7. Nhóm 7 - Dòng tiền và cấu phần định giá

File: `cash_flow.py`

| ID | Chỉ số | Function | Output | Công thức |
|---|---|---|---|---|
| F024 | FCFF | `fcff(ebit_value, tax_rate, depreciation, capex_value, change_in_net_working_capital)` | currency | `EBIT * (1 - t) + depreciation - CAPEX - ΔNWC` |
| F025 | EBIT | `ebit(profit_before_tax, interest_expense)` | currency | `lợi nhuận trước thuế + chi phí lãi vay` |
| F026 | Khấu hao đường thẳng | `straight_line_depreciation(cost, salvage_value, useful_life_years)` | currency | `(nguyên giá - giá trị thanh lý) / thời gian sử dụng` |
| F027 | CAPEX | `capex(delta_ppe, depreciation)` | currency | `ΔPP&E + depreciation` |
| F028 | ΔNWC | `change_in_nwc(current_nwc, previous_nwc)` | currency | `NWC_t - NWC_t-1` |

Helper function nên có:

| Helper | Function | Công thức |
|---|---|---|
| NWC | `net_working_capital(current_assets, cash_and_equivalents, current_liabilities, short_term_interest_bearing_debt)` | `(current_assets - cash) - (current_liabilities - short_term_debt)` |

Implementation notes:

- `tax_rate` dùng decimal: `0.2` cho 20%.
- `useful_life_years` phải `> 0`.
- `delta_ppe` nên được data layer tính bằng `net_ppe_current - net_ppe_previous`.
- FCFF có thể âm; đây là kết quả hợp lệ, đặc biệt với doanh nghiệp đầu tư CAPEX mạnh hoặc tăng vốn lưu động lớn.

Expected signatures:

```python
def fcff(ebit_value: Number, tax_rate: Number, depreciation: Number, capex_value: Number, change_in_net_working_capital: Number, strict: bool = False) -> float | None: ...
def ebit(profit_before_tax: Number, interest_expense: Number, strict: bool = False) -> float | None: ...
def straight_line_depreciation(cost: Number, salvage_value: Number, useful_life_years: Number, strict: bool = False) -> float | None: ...
def capex(delta_ppe: Number, depreciation: Number, strict: bool = False) -> float | None: ...
def net_working_capital(current_assets: Number, cash_and_equivalents: Number, current_liabilities: Number, short_term_interest_bearing_debt: Number, strict: bool = False) -> float | None: ...
def change_in_nwc(current_nwc: Number, previous_nwc: Number, strict: bool = False) -> float | None: ...
```

---

### 6.8. Nhóm 8 - Chi phí vốn và định giá tài sản

File: `cost_of_capital.py`

| ID | Chỉ số | Function | Output | Công thức |
|---|---|---|---|---|
| F029 | WACC | `wacc(equity_value, debt_value, cost_of_equity, cost_of_debt, tax_rate)` | ratio | `(E/V * Re) + (D/V * Rd * (1 - t))` |
| F030 | CAPM/Re | `capm_cost_of_equity(risk_free_rate, beta, market_return)` | ratio | `Rf + beta * (Rm - Rf)` |

Implementation notes:

- `V = E + D`.
- Nếu `V == 0`, trả `None`.
- Rates nhập dạng decimal.
- `beta` có thể âm trong lý thuyết nhưng với cổ phiếu phổ thông thường beta âm là bất thường; wrapper nên warning, không nhất thiết chặn.

Expected signatures:

```python
def wacc(equity_value: Number, debt_value: Number, cost_of_equity: Number, cost_of_debt: Number, tax_rate: Number, strict: bool = False) -> float | None: ...
def capm_cost_of_equity(risk_free_rate: Number, beta: Number, market_return: Number, strict: bool = False) -> float | None: ...
```

---

## 7. Registry Design

File: `registry.py`

Mục tiêu: cho phép Agent tra cứu công thức theo `formula_id` hoặc `function_name`, thay vì hard-code tên hàm rải rác.

```python
from dataclasses import dataclass
from typing import Callable

@dataclass(frozen=True)
class FormulaSpec:
    formula_id: str
    name: str
    group: str
    function_name: str
    formula_text: str
    output_unit: str
    inputs: list[str]
    description: str
    fn: Callable
```

Registry nên expose:

```python
FORMULA_REGISTRY: dict[str, FormulaSpec]

def get_formula(formula_id: str) -> FormulaSpec: ...
def list_formulas(group: str | None = None) -> list[FormulaSpec]: ...
def calculate(formula_id: str, inputs: dict, strict: bool = False) -> FormulaResult: ...
```

Acceptance criteria:

- Đủ 30 formula IDs từ `F001` đến `F030`.
- Mỗi formula có metadata đầy đủ.
- `calculate("F006", {"market_price_per_share": 100, "eps_value": 10})` trả `10.0`.
- Nếu thiếu input, trả `FormulaResult(value=None, warnings=[...])` trong non-strict mode.

---

## 8. Agent Tool Wrapper

File: `agent_tool.py`

Mục tiêu: cung cấp interface an toàn cho AI Agent.

```python
def calculate_financial_metric(formula_id: str, inputs: dict, strict: bool = False) -> dict:
    """
    Agent-facing wrapper.

    Returns JSON-serializable dict:
    {
        "formula_id": "F006",
        "name": "P/E",
        "value": 10.0,
        "unit": "multiple",
        "inputs": {...},
        "warnings": [],
        "formula_text": "P/E = market_price_per_share / EPS"
    }
    """
```

Rules for Agent:

- Agent không được tự tính công thức trong prompt khi formula_id đã tồn tại.
- Agent phải gọi tool `calculate_financial_metric()`.
- Agent phải hiển thị warning nếu output có cảnh báo.
- Agent phải format output theo `unit`:
  - `ratio`: hiển thị `%` ở report layer, ví dụ `0.1532 -> 15.32%`.
  - `multiple`: hiển thị `x`, ví dụ `12.5x`.
  - `days`: hiển thị `ngày`.
  - `currency_per_share`: hiển thị theo VND/cổ phiếu hoặc đơn vị dữ liệu gốc.

---

## 9. Validation and Warning Rules

Wrapper nên sinh warning cho các trường hợp sau:

| Trường hợp | Hành vi đề xuất |
|---|---|
| Thiếu input | `value=None`, warning `missing_input:<name>` |
| Mẫu số bằng 0 | `value=None`, warning `division_by_zero` |
| Rate có vẻ nhập nhầm dạng phần trăm, ví dụ `tax_rate=20` | warning `rate_may_be_percent_not_decimal` |
| Ratio sinh lời nhỏ hơn -100% | warning `extreme_negative_ratio` |
| Liquidity ratio âm | warning `negative_liquidity_ratio` |
| Days metric âm | warning `negative_days_metric` |
| P/E âm do EPS âm | warning `negative_earnings_multiple` |
| WACC âm hoặc quá cao, ví dụ > 100% | warning `unusual_wacc` |

Lưu ý: warning không nhất thiết làm fail calculation. Nó giúp Agent diễn giải thận trọng trong báo cáo.

---

## 10. Unit Test Plan

### 10.1. General tests

- Test mọi function với input bình thường.
- Test mẫu số bằng 0.
- Test input `None`.
- Test input không phải số.
- Test strict mode raise đúng exception.
- Test non-strict mode trả `None`.

### 10.2. Golden numeric examples

| Function | Input | Expected |
|---|---|---|
| `cagr` | `begin=100`, `end=121`, `periods=2` | `0.10` |
| `yoy_revenue_growth` | `120`, `100` | `0.20` |
| `eps` | `net_income=1000`, `preferred=100`, `shares=300` | `3.0` |
| `pe_ratio` | `price=60`, `eps=5` | `12.0` |
| `bvps` | `equity=1000`, `intangibles=100`, `shares=300` | `3.0` |
| `roa` | `net_income=50`, `avg_assets=1000` | `0.05` |
| `roe` | `net_income=50`, `avg_equity=250` | `0.20` |
| `gross_profit_margin` | `revenue=1000`, `cogs=600` | `0.40` |
| `debt_to_equity` | `debt=500`, `equity=250` | `2.0` |
| `cash_ratio` | `cash=100`, `sti=50`, `current_liabilities=300` | `0.5` |
| `dso` | `avg_ar=100`, `revenue=1000` | `36.5` |
| `dio` | `avg_inventory=200`, `cogs=1000` | `73.0` |
| `dpo` | `avg_ap=150`, `cogs=1000` | `54.75` |
| `fixed_asset_turnover` | `revenue=1000`, `avg_net_fixed_assets=500` | `2.0` |
| `fcff` | `ebit=100`, `tax=0.2`, `dep=10`, `capex=20`, `delta_nwc=5` | `65.0` |
| `ebit` | `pbt=80`, `interest=20` | `100.0` |
| `straight_line_depreciation` | `cost=1000`, `salvage=100`, `life=9` | `100.0` |
| `capex` | `delta_ppe=50`, `dep=10` | `60.0` |
| `change_in_nwc` | `current=120`, `previous=100` | `20.0` |
| `capm_cost_of_equity` | `rf=0.04`, `beta=1.2`, `rm=0.10` | `0.112` |
| `wacc` | `E=600`, `D=400`, `Re=0.12`, `Rd=0.08`, `tax=0.2` | `0.0976` |

---

## 11. Implementation Phases for Claude Code

### Phase 1 - Scaffold package

Tasks:

1. Create package structure under `src/financial_formulas/`.
2. Create `errors.py`, `types.py`, `utils.py`.
3. Configure `pyproject.toml` if project does not already have one.
4. Add pytest configuration.

Acceptance criteria:

- `pytest` runs successfully.
- `from financial_formulas import ...` works.
- `safe_divide()` and `average()` have tests.

### Phase 2 - Implement 30 formulas

Tasks:

1. Implement formulas by group modules.
2. Keep function names exactly as specified in this plan.
3. Keep return type `float | None` for core functions.
4. Use `safe_divide()` for all division.
5. Do not round inside core functions.

Acceptance criteria:

- 30 formulas are implemented.
- Helper functions are implemented: `average`, `sales_per_share`, `enterprise_value`, `net_working_capital`.
- All golden numeric examples pass.

### Phase 3 - Add formula registry

Tasks:

1. Implement `FormulaSpec`.
2. Register all 30 formula specs.
3. Implement `get_formula()`, `list_formulas()`, `calculate()`.
4. Ensure registry validates required inputs before calling function.

Acceptance criteria:

- `len(FORMULA_REGISTRY) == 30`.
- Every spec has `formula_id`, `name`, `group`, `function_name`, `formula_text`, `output_unit`, `inputs`, `description`, `fn`.
- `calculate()` returns `FormulaResult`.

### Phase 4 - Add Agent tool wrapper

Tasks:

1. Implement `calculate_financial_metric()`.
2. Convert `FormulaResult` to JSON-serializable dict.
3. Add warning rules for suspicious values.
4. Add tests for normal and abnormal cases.

Acceptance criteria:

- Tool wrapper never crashes in non-strict mode.
- Missing/invalid inputs produce warnings.
- Output includes formula metadata so Agent can trace calculation.

### Phase 5 - Documentation and examples

Tasks:

1. Create `docs/FORMULA_REFERENCE.md`.
2. Add usage examples for single metric and batch metric calculation.
3. Add example for formatting ratio/multiple/days outputs.
4. Add example showing how Agent should call the wrapper.

Acceptance criteria:

- A developer can implement/report a formula without reading the original `.docx`.
- Agent tool call contract is documented.

---

## 12. Claude Code Execution Prompt

Copy/paste prompt này cho Claude Code:

```text
You are implementing a deterministic Python financial formula library for an AI stock valuation agent.

Read this plan file carefully and implement exactly the package described here.

Primary objective:
- Convert all 30 financial formulas into pure Python functions.
- Add safe input validation, division-by-zero protection, tests, formula registry, and an agent-facing wrapper.

Hard constraints:
1. Do not let LLM/prompt logic calculate formulas directly. All formulas must be deterministic Python functions.
2. Core functions must return `float | None` and must not round values internally.
3. Percent/rate outputs must be decimal ratios. Example: 15% = 0.15, not 15.
4. Inputs such as tax_rate, cost_of_equity, cost_of_debt, risk_free_rate, and market_return must be decimal ratios.
5. Every division must use `safe_divide()`.
6. Non-strict mode must never crash on bad input. Return None and surface warnings through the wrapper/registry.
7. Strict mode must raise `FormulaInputError` on missing input, invalid numeric input, or division by zero.
8. Implement all function names exactly as specified in this plan.
9. Add pytest tests for every function, including edge cases.
10. Add `FORMULA_REGISTRY` with exactly 30 formula specs F001-F030.

Target module structure:
- src/financial_formulas/errors.py
- src/financial_formulas/types.py
- src/financial_formulas/utils.py
- src/financial_formulas/growth.py
- src/financial_formulas/market_valuation.py
- src/financial_formulas/profitability.py
- src/financial_formulas/capital_structure.py
- src/financial_formulas/liquidity.py
- src/financial_formulas/operating_cycle.py
- src/financial_formulas/cash_flow.py
- src/financial_formulas/cost_of_capital.py
- src/financial_formulas/registry.py
- src/financial_formulas/agent_tool.py
- tests/test_*.py

Implementation order:
1. Scaffold package and utilities.
2. Implement formula modules.
3. Implement registry.
4. Implement agent tool wrapper.
5. Add tests and run pytest.
6. Fix all failures.
7. Add concise docs/examples.

Deliverable:
- Working Python package.
- Passing test suite.
- Clear formula registry for the agent.
- No undocumented formula behavior.
```

---

## 13. Definition of Done

Hoàn thành khi đạt toàn bộ tiêu chí sau:

- Có đủ 30 công thức từ tài liệu nguồn.
- Mỗi công thức có function riêng, tên rõ ràng, input contract rõ ràng.
- Các chỉ số tỷ lệ trả về decimal ratio.
- Không có phép chia trực tiếp không qua `safe_divide()`.
- Có registry metadata đầy đủ cho Agent.
- Có wrapper JSON-serializable cho Agent.
- Có pytest test cho happy path và edge cases.
- Không có function nào tự query database hoặc gọi API.
- Không round trong core calculation.
- Agent có thể trace được công thức nào tạo ra kết quả nào.

---

## 14. Formula ID Map

| ID | Name | Function | Module |
|---|---|---|---|
| F001 | CAGR | `cagr` | `growth.py` |
| F002 | YoY Doanh thu | `yoy_revenue_growth` | `growth.py` |
| F003 | YoY Lợi nhuận | `yoy_net_income_growth` | `growth.py` |
| F004 | Tỷ lệ phần trăm cấu phần | `component_ratio` | `growth.py` |
| F005 | EPS | `eps` | `market_valuation.py` |
| F006 | P/E | `pe_ratio` | `market_valuation.py` |
| F007 | P/B | `pb_ratio` | `market_valuation.py` |
| F008 | P/S | `ps_ratio` | `market_valuation.py` |
| F009 | EV/EBITDA | `ev_to_ebitda` | `market_valuation.py` |
| F010 | BVPS | `bvps` | `market_valuation.py` |
| F011 | ROA | `roa` | `profitability.py` |
| F012 | ROE | `roe` | `profitability.py` |
| F013 | ROS | `ros` | `profitability.py` |
| F014 | Nợ/VCSH | `debt_to_equity` | `capital_structure.py` |
| F015 | Thanh toán tiền mặt | `cash_ratio` | `liquidity.py` |
| F016 | DSO | `days_sales_outstanding` | `operating_cycle.py` |
| F017 | DIO | `days_inventory_outstanding` | `operating_cycle.py` |
| F018 | Thanh toán nhanh | `quick_ratio` | `liquidity.py` |
| F019 | DPO | `days_payable_outstanding` | `operating_cycle.py` |
| F020 | Biên lợi nhuận gộp | `gross_profit_margin` | `profitability.py` |
| F021 | Biên lợi nhuận ròng | `net_profit_margin` | `profitability.py` |
| F022 | Thanh toán hiện thời | `current_ratio` | `liquidity.py` |
| F023 | Vòng quay TSCĐ | `fixed_asset_turnover` | `operating_cycle.py` |
| F024 | FCFF | `fcff` | `cash_flow.py` |
| F025 | EBIT | `ebit` | `cash_flow.py` |
| F026 | Depreciation | `straight_line_depreciation` | `cash_flow.py` |
| F027 | CAPEX | `capex` | `cash_flow.py` |
| F028 | ΔNWC | `change_in_nwc` | `cash_flow.py` |
| F029 | WACC | `wacc` | `cost_of_capital.py` |
| F030 | CAPM/Re | `capm_cost_of_equity` | `cost_of_capital.py` |
