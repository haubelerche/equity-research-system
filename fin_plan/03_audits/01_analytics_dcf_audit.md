# Audit công thức và logic file Analytics/DCF (`dcf.py`)

**Ngày lập:** 2026-05-27  
**Phạm vi kiểm tra:** File `dcf.py` đang được dùng như module analytics/valuation DCF.  
**Mục tiêu:** Kiểm tra logic tài chính, công thức định giá, lỗi code tiềm ẩn và mức độ phù hợp để dùng trong AI Equity Research Agent.

---

## 1. Kết luận nhanh

File hiện tại **đã sửa đúng lỗi CAPEX bị cộng ngược** nếu `capex.total` đang lưu theo dấu âm từ báo cáo lưu chuyển tiền tệ. Cụ thể, code đang dùng:

```python
fcf_history[p] = ocf + capex
```

Điều này đúng nếu CAPEX trong CFS là số âm:

```text
OCF = 1,000
CAPEX_CFS = -200
FCF = 1,000 + (-200) = 800
```

Tuy nhiên, file vẫn còn nhiều vấn đề quan trọng nếu muốn dùng làm module định giá chính cho AI Equity Research Agent.

### Các lỗi/vấn đề chính

| Mức độ | Vấn đề | Ảnh hưởng |
|---|---|---|
| Critical | Mô hình đang gọi là EV/WACC nhưng FCF thực tế là `OCF + CAPEX`, chưa phải FCFF chuẩn | Có thể định giá sai vì discount rate và dòng tiền không khớp |
| Critical | Nếu FCF đầu kỳ âm, code có thể crash ở đoạn format CAGR | Agent có thể dừng giữa pipeline |
| Critical | Nếu `WACC <= terminal_growth`, code tự “cap g” thay vì báo invalid | Có thể tạo target price giả tạo thay vì chặn mô hình |
| High | Bear/Base/Bull không thực sự thay đổi FCF growth nếu dùng CAGR lịch sử | Scenario analysis bị sai ý nghĩa |
| High | Net debt chưa trừ short-term investments và chưa xét minority/non-operating assets | Equity value có thể bị lệch |
| High | CAPEX dương chỉ warning nhưng vẫn tính tiếp bằng công thức có thể sai | Nếu input CAPEX đã là số dương, FCF bị phóng đại |
| Medium | Shares suy ra từ `net_income / EPS`, không ưu tiên diluted shares | Giá/cp có thể lệch nếu EPS basic hoặc share count không khớp |
| Medium | Thiếu terminal value weight warning | Không biết mô hình phụ thuộc TV quá mức |
| Medium | Thiếu validation cho `forecast_years`, `wacc`, `terminal_growth`, `fcf_growth` | Có thể ra kết quả vô nghĩa |
| Medium | Docstring chưa khớp hoàn toàn với logic code | Dễ gây hiểu nhầm khi bảo trì |

---

## 2. Vấn đề lớn nhất: dòng tiền và discount rate chưa khớp

Code hiện tại tính FCF lịch sử như sau:

```python
fcf_history[p] = ocf + capex
```

Nếu `capex` là số âm từ CFS thì công thức này đúng về mặt dòng tiền đơn giản:

```text
FCF đơn giản = CFO + CAPEX_CFS
```

Nhưng vấn đề là dòng tiền này **chưa phải FCFF chuẩn**.

Nếu file đang dùng `WACC` để chiết khấu và tính ra `Enterprise Value`, dòng tiền nên là **FCFF**:

```text
FCFF = CFO + Interest Expense × (1 - Tax Rate) + CAPEX_CFS
```

Trong khi đó, nếu dùng **FCFE**, công thức nên là:

```text
FCFE = CFO + CAPEX_CFS + Net Borrowing
```

Và FCFE phải chiết khấu bằng **Cost of Equity**, không phải WACC.

### Vấn đề hiện tại

Code đang làm:

```text
FCF = CFO + CAPEX_CFS
Discount bằng WACC
Ra Enterprise Value
Trừ Net Debt
Ra Equity Value
```

Điều này chưa chuẩn nếu kết quả được hiểu là FCFF DCF.

### Cách sửa đề xuất

Nên tách rõ 3 loại dòng tiền:

```text
1. simplified_fcf = CFO + CAPEX_CFS
   → chỉ dùng tham khảo, không nên dùng làm target price chính.

2. fcff = CFO + Interest Expense × (1 - Tax Rate) + CAPEX_CFS
   → discount bằng WACC
   → ra Enterprise Value
   → bridge sang Equity Value.

3. fcfe = CFO + CAPEX_CFS + Net Borrowing
   → discount bằng Cost of Equity
   → ra Equity Value trực tiếp
   → không trừ Net Debt lần nữa.
```

Nếu hệ thống đang định dùng mô hình chính là **60% FCFF + 40% FCFE**, file hiện tại **chưa đủ điều kiện** vì chưa tính riêng FCFF và FCFE.

---

## 3. CAPEX đã xử lý đúng một phần, nhưng chưa đủ an toàn

Điểm tốt là code đã sửa từ logic dễ sai:

```python
ocf - capex
```

sang:

```python
ocf + capex
```

Điều này đúng nếu `capex.total` là số âm từ CFS.

### Ví dụ đúng

```text
OCF = 1,000
CAPEX_CFS = -300
FCF = 1,000 + (-300) = 700
```

### Vấn đề còn lại

Nếu dữ liệu CAPEX được nhập là số dương, code chỉ cảnh báo:

```python
if capex > 0:
    capex_sign_anomaly.append(...)
```

nhưng vẫn tính:

```python
fcf_history[p] = ocf + capex
```

Khi đó sẽ sai.

### Ví dụ sai

```text
OCF = 1,000
CAPEX = +200
Code tính FCF = 1,200
Đúng phải là FCF = 800
```

### Cách sửa đề xuất

Có hai hướng.

#### Cách 1: Tự xử lý theo dấu CAPEX

```python
if capex > 0:
    warnings.append("CAPEX positive; treating as positive model input and subtracting it")
    fcf_history[p] = ocf - capex
else:
    fcf_history[p] = ocf + capex
```

#### Cách 2: Chặt hơn, phù hợp với valuation agent

```python
if capex > 0:
    raise ValueError("CAPEX sign convention invalid: expected negative CAPEX_CFS")
```

Với AI valuation agent, nên ưu tiên **chặn valuation nếu convention CAPEX chưa rõ**, vì sai dấu CAPEX có thể làm target price sai rất lớn.

---

## 4. Bug thật: FCF đầu kỳ âm có thể làm code crash

Đoạn hiện tại:

```python
cagr = _cagr(fcf_vals[0], fcf_vals[-1], len(fcf_vals) - 1)
fcf_growth = max(-0.10, min(0.25, cagr)) if cagr is not None else 0.05
if cagr != fcf_growth:
    warnings.append(f"FCF CAGR {cagr:.1%} capped to {fcf_growth:.1%} for projection")
```

Nếu `_cagr()` trả về `None`, code vẫn có thể chạy vào:

```python
warnings.append(f"FCF CAGR {cagr:.1%} capped to {fcf_growth:.1%} for projection")
```

Khi `cagr = None`, việc format bằng `:.1%` sẽ gây lỗi:

```text
TypeError: unsupported format string passed to NoneType.__format__
```

### Trường hợp dễ xảy ra

Nếu FCF năm đầu nhỏ hơn hoặc bằng 0:

```text
FCF năm đầu = -100
FCF năm cuối = 200
```

Hàm `_cagr()` trả về `None` vì CAGR không có ý nghĩa khi start <= 0.

### Sửa tối thiểu

```python
if cagr is None:
    fcf_growth = 0.05
    warnings.append("FCF CAGR unavailable; assuming 5% FCF growth")
else:
    fcf_growth = max(-0.10, min(0.25, cagr))
    if cagr != fcf_growth:
        warnings.append(f"FCF CAGR {cagr:.1%} capped to {fcf_growth:.1%} for projection")
```

---

## 5. `forecast_years = 0` làm code crash

Nếu người dùng truyền:

```python
DCFAssumptions(forecast_years=0)
```

thì:

```python
projected = []
```

Sau đó code gọi:

```python
terminal_fcf = projected[-1] * (1 + g)
```

Kết quả sẽ lỗi:

```text
IndexError: list index out of range
```

### Cách sửa

Nên validate ngay đầu hàm:

```python
if assumptions.forecast_years <= 0:
    warnings.append("forecast_years must be positive; DCF cannot be computed")
    return empty_result(...)
```

Hoặc chặt hơn:

```python
raise ValueError("forecast_years must be > 0")
```

---

## 6. `WACC <= terminal_growth` không nên tự cap, nên báo INVALID

Code hiện tại:

```python
if wacc <= g:
    warnings.append(f"WACC ({wacc:.1%}) ≤ terminal growth ({g:.1%}); terminal value undefined — capped g")
    g = wacc - 0.01
```

Tức là nếu giả định sai, code tự sửa `g`.

### Vì sao nguy hiểm?

Trong công thức Gordon Growth:

```text
Terminal Value = FCF_(n+1) / (WACC - g)
```

Nếu:

```text
WACC <= g
```

thì mẫu số bằng 0 hoặc âm. Terminal value không còn hợp lý.

Nếu code tự sửa `g`, agent có thể vẫn xuất ra target price nhìn có vẻ hợp lệ, trong khi giả định đầu vào đã invalid.

### Cách sửa đề xuất

Không nên tự điều chỉnh. Nên trả trạng thái invalid:

```python
if wacc <= g:
    return invalid_result(
        f"INVALID: WACC ({wacc:.1%}) must be greater than terminal growth ({g:.1%})"
    )
```

Hoặc thêm `blocking_errors`:

```python
blocking_errors.append(
    f"WACC ({wacc:.1%}) <= terminal growth ({g:.1%}); terminal value invalid"
)
```

---

## 7. Bear/Base/Bull đang không đúng như comment

Comment viết:

```text
Bear:  WACC +2pp, terminal_growth -1pp, FCF growth -3pp
Base:  as provided
Bull:  WACC -2pp, terminal_growth +1pp, FCF growth +3pp
```

Nhưng code thực tế:

```python
growth_override = (
    (base.fcf_growth_override or 0.0) + growth_delta
    if base.fcf_growth_override is not None
    else None
)
```

Nếu `base.fcf_growth_override = None`, tức là mô hình dùng CAGR lịch sử, thì bear và bull **không chỉnh FCF growth**.

### Hệ quả

Bear/Base/Bull chỉ khác nhau ở:

```text
WACC
terminal growth
```

nhưng không khác nhau ở tăng trưởng FCF vận hành.

Như vậy scenario analysis không phản ánh đầy đủ khác biệt giữa kịch bản xấu, cơ sở và tốt.

### Cách sửa đúng

Cần tách hàm xác định base growth ra riêng:

```python
base_growth = derive_fcf_growth(fcf_history, base)

bear_growth = base_growth - 0.03
base_growth = base_growth
bull_growth = base_growth + 0.03
```

Hoặc trong `run_three_scenarios()`, tính trước CAGR rồi truyền `fcf_growth_override` vào từng scenario.

---

## 8. Net Debt đang thiếu short-term investments và bridge item

Code hiện tại:

```python
total_debt = _get(fact_table, "total_debt.ending", latest_fy) or 0.0
cash = _get(fact_table, "cash_and_equivalents.ending", latest_fy) or 0.0
net_debt = total_debt - cash
```

Công thức này chưa đầy đủ.

### Công thức nên dùng

```text
Net Debt = Total Debt - Cash - Short-term Investments
```

Ngoài ra, khi bridge từ EV sang Equity Value, nên xét thêm:

```text
Equity Value = EV 
               - Net Debt
               + Non-operating Assets
               - Minority Interest
               - Preferred Equity
```

### Cách sửa đề xuất

```python
short_inv = _get(fact_table, "short_term_investments.ending", latest_fy) or 0.0
net_debt = total_debt - cash - short_inv
```

Mở rộng hơn:

```python
minority_interest = _get(fact_table, "minority_interest.ending", latest_fy) or 0.0
preferred_equity = _get(fact_table, "preferred_equity.ending", latest_fy) or 0.0
non_operating_assets = _get(fact_table, "non_operating_assets.ending", latest_fy) or 0.0

equity_val = (
    ev
    - net_debt
    + non_operating_assets
    - minority_interest
    - preferred_equity
)
```

---

## 9. Thiếu cảnh báo nếu debt/cash/share bị thiếu

Hiện tại code dùng:

```python
total_debt = _get(fact_table, "total_debt.ending", latest_fy) or 0.0
cash = _get(fact_table, "cash_and_equivalents.ending", latest_fy) or 0.0
```

Điều này khiến dữ liệu thiếu bị coi như bằng 0.

### Vì sao nguy hiểm?

Có hai trường hợp rất khác nhau:

```text
1. Total debt thật sự bằng 0
2. Total debt bị thiếu dữ liệu
```

Code hiện tại không phân biệt hai trường hợp này.

### Cách sửa

```python
total_debt = _get(fact_table, "total_debt.ending", latest_fy)
cash = _get(fact_table, "cash_and_equivalents.ending", latest_fy)

if total_debt is None:
    warnings.append("total_debt missing; net debt may be understated")
    total_debt = 0.0

if cash is None:
    warnings.append("cash_and_equivalents missing; net debt may be overstated")
    cash = 0.0
```

Với valuation chính, tốt hơn nên chặn nếu thiếu dữ liệu trọng yếu:

```python
if total_debt is None or cash is None:
    return invalid_result("Missing net debt inputs")
```

---

## 10. Shares suy ra từ NI/EPS là giải pháp tạm, chưa đủ chuẩn

Code hiện tại:

```python
shares_mn = (ni * 1_000) / eps
```

Công thức đúng về đơn vị nếu:

```text
net_income: tỷ VND
EPS: VND/cp
shares: triệu cổ phiếu
```

Ví dụ:

```text
Net income = 1,000 tỷ VND
EPS = 5,000 VND/cp

shares_mn = 1,000 × 1,000 / 5,000
shares_mn = 200 triệu cổ phiếu
```

### Rủi ro

Cách này có thể lệch vì:

1. EPS basic có thể khác EPS diluted.
2. EPS có thể là TTM, còn net income là FY.
3. EPS có thể đã điều chỉnh cổ phiếu thưởng hoặc stock split.
4. Net income dùng `net_income.parent`, nhưng EPS có thể tính theo cơ sở khác.
5. EPS thường bị làm tròn, khiến số cổ phiếu suy ra bị sai số.

### Cách sửa đề xuất

Ưu tiên dùng số cổ phiếu báo cáo:

```python
shares_mn = _get(fact_table, "shares_outstanding.diluted", latest_fy)
```

Fallback:

```python
shares_mn = _get(fact_table, "shares_outstanding.weighted_avg", latest_fy)
```

Cuối cùng mới suy ra từ NI/EPS:

```python
if shares_mn is None and ni is not None and eps is not None and eps > 0:
    shares_mn = (ni * 1_000) / eps
```

Nên thêm reconciliation:

```python
implied_shares = (ni * 1_000) / eps

if reported_shares and abs(implied_shares / reported_shares - 1) > 0.02:
    warnings.append("EPS-implied shares differ from reported shares by >2%")
```

---

## 11. `to_dict()` dùng truthiness nên có thể che mất giá trị 0

Code hiện tại:

```python
"shares_mn": round(self.shares_mn, 4) if self.shares_mn else None
```

và:

```python
"intrinsic_value_per_share_vnd": (
    round(self.intrinsic_value_per_share_vnd, 0)
    if self.intrinsic_value_per_share_vnd else None
)
```

Nếu giá trị bằng `0`, nó sẽ bị chuyển thành `None`.

### Cách sửa

```python
"shares_mn": (
    round(self.shares_mn, 4)
    if self.shares_mn is not None
    else None
)
```

và:

```python
"intrinsic_value_per_share_vnd": (
    round(self.intrinsic_value_per_share_vnd, 0)
    if self.intrinsic_value_per_share_vnd is not None
    else None
)
```

---

## 12. Thiếu terminal value weight warning

DCF thường rất nhạy với terminal value. File hiện tại chưa tính tỷ trọng terminal value.

### Công thức cần thêm

```text
Terminal Value Weight = PV(Terminal Value) / Enterprise Value
```

### Vì sao cần?

Nếu terminal value chiếm quá lớn trong EV, mô hình phụ thuộc nhiều vào giả định dài hạn `g` và WACC.

Ngưỡng gợi ý:

```text
TV Weight > 70% → cần cảnh báo và sensitivity.
TV Weight > 85% → DCF rất rủi ro, không nên kết luận target price nếu không có luận cứ mạnh.
```

### Cách sửa

```python
tv_weight = pv_tv / ev if ev > 0 else None

if tv_weight is not None:
    if tv_weight > 0.85:
        warnings.append(f"Terminal value weight {tv_weight:.1%} > 85%; DCF highly unreliable")
    elif tv_weight > 0.70:
        warnings.append(f"Terminal value weight {tv_weight:.1%} > 70%; sensitivity required")
```

---

## 13. File chưa phải sensitivity analysis đầy đủ

`run_three_scenarios()` hiện chỉ tạo 3 kịch bản:

```text
bear
base
bull
```

Đây là scenario analysis đơn giản, chưa phải sensitivity analysis đầy đủ.

Một module analytics/valuation nên có thêm:

```text
1. One-way sensitivity
2. Two-way sensitivity: WACC × terminal growth
3. Scenario analysis
4. Tornado chart data
5. Break-even analysis
```

Với DCF, bảng quan trọng nhất là:

```text
WACC × terminal growth
```

Nếu có FCFE, cần thêm:

```text
Cost of Equity × terminal growth
```

### Các phần file hiện chưa có

```text
- WACC × g matrix
- Re × g matrix cho FCFE
- Terminal value weight
- Valuation gap giữa FCFF và FCFE
- Elasticity/sensitivity contribution
- Break-even WACC
- Break-even terminal growth
- Break-even P/E nếu có forward P/E
```

---

## 14. Thiếu trạng thái `invalid` / `valuation_allowed`

Hiện tại mọi vấn đề đều đưa vào:

```python
warnings
```

Nhưng hàm vẫn có thể trả kết quả định giá.

Ví dụ các trường hợp sau đáng lẽ nên chặn valuation:

```text
- Latest-year FCF is non-positive
- WACC <= terminal growth
- CAPEX positive anomaly nếu convention chưa rõ
- Missing CAPEX
- Missing net debt data
- Missing shares
- Negative equity value
```

### Cách sửa kiến trúc output

Nên thêm các field:

```python
status: str  # "ok", "warning", "invalid"
valuation_allowed: bool
blocking_errors: list[str]
```

Ví dụ:

```python
@dataclass
class DCFResult:
    ...
    status: str = "ok"
    valuation_allowed: bool = True
    blocking_errors: list[str] = field(default_factory=list)
```

Khi gặp lỗi nghiêm trọng:

```python
blocking_errors.append("WACC must be greater than terminal growth")
valuation_allowed = False
status = "invalid"
```

---

## 15. Docstring chưa khớp hoàn toàn với code

Docstring đầu file ghi:

```text
FCF = operating_cash_flow.total - |capex.total|
```

Nhưng code thực tế dùng:

```python
fcf_history[p] = ocf + capex
```

Nếu CAPEX là số âm thì hai cách tương đương. Tuy nhiên, về bảo trì code, nên ghi rõ convention.

### Docstring nên sửa thành

```text
If capex.total is stored as a CFS signed value, usually negative:
    FCF = operating_cash_flow.total + capex.total

If CAPEX is normalized as positive:
    FCF = operating_cash_flow.total - capex_positive
```

---

## 16. Đề xuất thứ tự sửa ưu tiên

### Nhóm cần sửa ngay trước khi dùng tiếp

1. Tách rõ `simplified_fcf`, `fcff`, `fcfe`.
2. Không dùng `OCF + CAPEX` làm EV/WACC DCF chính nếu chưa cộng lại after-tax interest.
3. Sửa bug `cagr is None`.
4. Validate `forecast_years > 0`.
5. `WACC <= terminal_growth` phải trả `INVALID`, không tự cap.
6. Nếu CAPEX dương nhưng convention chưa rõ, chặn valuation.
7. Net debt phải trừ thêm `short_term_investments`.

### Nhóm nên sửa sớm

8. Ưu tiên reported/diluted shares thay vì suy ra từ EPS.
9. Thêm terminal value weight.
10. Thêm WACC × g sensitivity matrix.
11. Thêm `status`, `valuation_allowed`, `blocking_errors`.
12. Gắn `formula_id`, `calc_method`, `calc_version` cho từng metric nếu module này nằm trong pipeline analytics chuẩn.

---

## 17. Patch logic tối thiểu nên hướng tới

### 17.1. Tách dòng tiền

```python
def fcf_from_cfo_signed_capex(cfo: float, capex_cfs: float) -> float:
    if capex_cfs > 0:
        raise ValueError("Expected CAPEX_CFS to be negative. Normalize sign before valuation.")
    return cfo + capex_cfs


def fcff_from_cfo(
    cfo: float,
    capex_cfs: float,
    interest_expense: float,
    tax_rate: float,
) -> float:
    if capex_cfs > 0:
        raise ValueError("Expected CAPEX_CFS to be negative.")

    interest_abs = abs(interest_expense)
    return cfo + interest_abs * (1 - tax_rate) + capex_cfs


def fcfe_from_cfo(
    cfo: float,
    capex_cfs: float,
    net_borrowing: float,
) -> float:
    if capex_cfs > 0:
        raise ValueError("Expected CAPEX_CFS to be negative.")

    return cfo + capex_cfs + net_borrowing
```

### 17.2. Chặn terminal value invalid

```python
if discount_rate <= terminal_growth:
    return invalid_result("Discount rate must be greater than terminal growth")
```

### 17.3. Sửa CAGR khi FCF đầu kỳ âm

```python
cagr = _cagr(fcf_vals[0], fcf_vals[-1], len(fcf_vals) - 1)

if cagr is None:
    fcf_growth = 0.05
    warnings.append("FCF CAGR unavailable; assuming 5% FCF growth")
else:
    fcf_growth = max(-0.10, min(0.25, cagr))
    if cagr != fcf_growth:
        warnings.append(f"FCF CAGR {cagr:.1%} capped to {fcf_growth:.1%} for projection")
```

### 17.4. Sửa Net Debt

```python
total_debt = _get(fact_table, "total_debt.ending", latest_fy)
cash = _get(fact_table, "cash_and_equivalents.ending", latest_fy)
short_inv = _get(fact_table, "short_term_investments.ending", latest_fy) or 0.0

if total_debt is None:
    return invalid_result("Missing total debt input")

if cash is None:
    return invalid_result("Missing cash input")

net_debt = total_debt - cash - short_inv
```

### 17.5. Thêm terminal value weight

```python
tv_weight = pv_tv / ev if ev > 0 else None

if tv_weight is not None:
    if tv_weight > 0.85:
        warnings.append(f"Terminal value weight {tv_weight:.1%} > 85%; DCF highly unreliable")
    elif tv_weight > 0.70:
        warnings.append(f"Terminal value weight {tv_weight:.1%} > 70%; sensitivity required")
```

### 17.6. Sửa `to_dict()`

```python
"shares_mn": (
    round(self.shares_mn, 4)
    if self.shares_mn is not None
    else None
),

"intrinsic_value_per_share_vnd": (
    round(self.intrinsic_value_per_share_vnd, 0)
    if self.intrinsic_value_per_share_vnd is not None
    else None
),
```

---

## 18. Gợi ý cấu trúc module analytics tốt hơn

Nếu muốn file này trở thành module analytics/valuation chính, nên tách thành các phần:

```text
analytics/
├── cashflow.py
│   ├── calculate_simplified_fcf()
│   ├── calculate_fcff()
│   └── calculate_fcfe()
│
├── dcf.py
│   ├── run_fcff_dcf()
│   ├── run_fcfe_dcf()
│   └── blend_valuation()
│
├── sensitivity.py
│   ├── wacc_g_matrix()
│   ├── re_g_matrix()
│   ├── tornado_inputs()
│   └── break_even_analysis()
│
├── validation.py
│   ├── validate_capex_sign()
│   ├── validate_required_facts()
│   ├── validate_discount_rate()
│   └── validate_terminal_value_weight()
│
└── result.py
    ├── ValuationResult
    ├── ScenarioResult
    └── ValidationStatus
```

---

## 19. Checklist kiểm định trước khi xuất target price

Trước khi agent xuất target price, nên kiểm tra:

```text
[ ] Có đủ CFO, CAPEX, debt, cash, shares.
[ ] CAPEX sign convention rõ ràng.
[ ] Nếu dùng FCFF, đã cộng lại after-tax interest.
[ ] Nếu dùng FCFE, đã cộng net borrowing.
[ ] Discount rate khớp với dòng tiền: FCFF → WACC, FCFE → Cost of Equity.
[ ] WACC hoặc Re lớn hơn terminal growth.
[ ] forecast_years > 0.
[ ] FCF mới nhất không âm hoặc có giải thích rõ.
[ ] Terminal value weight không quá cao.
[ ] Net debt đã trừ cash và short-term investments.
[ ] Shares dùng diluted hoặc reported shares nếu có.
[ ] Bear/Base/Bull thật sự thay đổi operating assumptions.
[ ] Có sensitivity WACC × g.
[ ] Có trạng thái `valuation_allowed`.
[ ] Nếu có lỗi blocking, không xuất target price/rating.
```

---

## 20. Kết luận cuối cùng

File hiện tại **ổn nếu chỉ dùng như một module tham khảo “OCF - CAPEX simplified DCF”**, nhưng **chưa đủ chuẩn để làm analytics/valuation chính cho AI Equity Research Agent**.

Điểm tốt nhất là logic CAPEX âm đã được xử lý đúng hơn trước. Tuy nhiên, còn các vấn đề cần sửa:

```text
- Dòng tiền chưa khớp với discount rate.
- Chưa tách FCFF và FCFE.
- Bug CAGR khi FCF đầu kỳ âm.
- Bear/Base/Bull chưa chỉnh FCF growth nếu dùng CAGR lịch sử.
- WACC <= terminal growth không được chặn.
- Net debt thiếu short-term investments.
- Shares suy ra từ EPS chỉ là fallback, chưa phải chuẩn.
- Thiếu terminal value weight.
- Thiếu hard gate invalid/valuation_allowed.
```

Nếu chưa sửa các điểm này, agent vẫn có thể tạo ra target price nhìn hợp lý nhưng sai bản chất mô hình.
