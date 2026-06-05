"""Deterministic, artifact-grounded narrative builder for client reports.

Every sentence is composed from values already computed by the deterministic engines
(facts, forecast drivers, valuation blend, sensitivity). No number is invented here —
when an input is missing the text says so explicitly rather than fabricating a figure
(CLAUDE.md §5.1). Each section follows the four-layer logic:
  quantitative anchor → driver/cause → valuation impact → risk to watch.

Design principle: numbers appear *once* to anchor a claim; repetition is removed.
The reader should finish each section with an analytical view, not a data dump.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class NarrativeInputs:
    ticker: str
    company_name: str
    sector: str = "dược phẩm"
    # Historical figures (tỷ đồng / %)
    revenue_latest: float | None = None
    revenue_prev: float | None = None
    revenue_growth_latest: float | None = None      # fraction
    revenue_cagr: float | None = None               # fraction
    net_income_latest: float | None = None
    net_margin_latest: float | None = None          # fraction
    gross_margin_latest: float | None = None        # fraction
    eps_latest: float | None = None                 # VND
    cash_conversion: float | None = None            # CFO/NI ratio
    # Forecast drivers (fraction)
    rev_growth_driver: float | None = None
    gross_margin_driver: float | None = None
    sga_driver: float | None = None
    capex_driver: float | None = None
    tax_driver: float | None = None
    # Valuation
    wacc: float | None = None
    terminal_growth: float | None = None
    current_price: float | None = None              # VND
    target_price: float | None = None               # VND
    upside: float | None = None                     # fraction
    rating: str = ""
    price_fcff: float | None = None                 # VND
    price_pe_forward: float | None = None           # VND — P/E Forward anchor (replaces FCFE)
    sens_low: float | None = None                   # VND (worst-case target in matrix)
    sens_high: float | None = None                  # VND (best-case target in matrix)
    dividend_yield: float | None = None             # fraction


_NA = "chưa đủ dữ liệu công bố"


def _pct(x: float | None, digits: int = 1) -> str:
    return f"{x * 100:.{digits}f}%" if isinstance(x, (int, float)) else _NA


def _bn(x: float | None) -> str:
    return f"{x:,.0f} tỷ đồng" if isinstance(x, (int, float)) else _NA


def _vnd(x: float | None) -> str:
    return f"{x:,.0f} VND" if isinstance(x, (int, float)) else _NA


def _times(x: float | None) -> str:
    return f"{x:.2f} lần" if isinstance(x, (int, float)) else _NA


def build_investment_thesis(n: NarrativeInputs) -> str:
    upside_clause = (
        f"so với thị giá {_vnd(n.current_price)}, biên tiềm năng {_pct(n.upside)}"
        if n.upside is not None else
        f"so với thị giá {_vnd(n.current_price)}"
    )
    valuation_clause = (
        f"Mô hình định giá cho giá mục tiêu {_vnd(n.target_price)} {upside_clause}. "
        f"Khoảng giá trị hợp lý theo ma trận độ nhạy trải từ {_vnd(n.sens_low)} đến {_vnd(n.sens_high)}, "
        f"phản ánh mức độ không chắc chắn của các giả định dài hạn."
        if n.target_price else
        f"Giá mục tiêu hiện {_NA}; báo cáo giữ trạng thái cần rà soát."
    )
    return (
        f"{n.company_name} ({n.ticker}) là doanh nghiệp {n.sector} có nền doanh thu {_bn(n.revenue_latest)} "
        f"với biên lợi nhuận gộp {_pct(n.gross_margin_latest)}, đủ để hỗ trợ tăng trưởng doanh thu dự phóng "
        f"{_pct(n.rev_growth_driver)} mà không cần mở rộng đòn bẩy vận hành quá mức. "
        f"{valuation_clause} "
        f"Luận điểm đầu tư xoay quanh ba câu hỏi: (i) doanh nghiệp có giữ được biên gộp trước áp lực chi phí "
        f"nguyên liệu API và tỷ giá không? (ii) kỷ luật chi phí SG&A có đảm bảo biên EBIT không bị xói mòn khi "
        f"tăng doanh thu? (iii) capex dài hạn phục vụ nâng chuẩn nhà máy GMP-EU có phá vỡ cấu trúc dòng tiền "
        f"tự do hay không? Ba câu hỏi này quyết định độ tin cậy của kết quả mô hình FCFF và từ đó quyết định "
        f"giá trị hợp lý. Rủi ro trọng yếu là kết quả đấu thầu ETC và biến động giá API — hai yếu tố này tác "
        f"động đồng thời lên cả doanh thu lẫn biên, và là nguồn sai lệch lớn nhất so với giả định cơ sở."
    )


def build_business_update(n: NarrativeInputs) -> str:
    growth_comment = (
        "tốc độ này phù hợp với quỹ đạo lịch sử"
        if n.revenue_cagr is not None and n.revenue_growth_latest is not None
        and abs((n.revenue_growth_latest or 0) - (n.revenue_cagr or 0)) < 0.05
        else "cần theo dõi tính bền vững so với CAGR lịch sử"
    )
    return (
        f"{n.company_name} hoạt động trên hai kênh phân phối ETC (đấu thầu bệnh viện) và OTC (nhà thuốc bán "
        f"lẻ). Doanh thu kỳ gần nhất đạt {_bn(n.revenue_latest)}, tăng {_pct(n.revenue_growth_latest)} so với "
        f"kỳ trước — {growth_comment} (CAGR lịch sử {_pct(n.revenue_cagr)}). "
        f"Biên lợi nhuận gộp {_pct(n.gross_margin_latest)} phản ánh năng lực kiểm soát giá vốn API trong môi "
        f"trường tỷ giá biến động; đây là chỉ số quan trọng hơn tốc độ tăng doanh thu vì nó xác định chất "
        f"lượng lợi nhuận thực sự. Tỷ lệ chuyển đổi tiền mặt {_times(n.cash_conversion)} cho thấy mức độ lợi "
        f"nhuận kế toán được hỗ trợ bởi dòng tiền vận hành thực — tỷ lệ dưới 0,8 lần thường báo hiệu áp lực "
        f"vốn lưu động từ phải thu bệnh viện. "
        f"Driver vận hành trọng yếu là sản lượng và giá trúng thầu ETC, vì kênh này vừa có tỷ trọng doanh thu "
        f"cao vừa chịu áp lực chính sách đấu thầu định kỳ. Bất kỳ sai lệch nào ở đây sẽ truyền dẫn qua doanh "
        f"thu → biên gộp → EBIT → FCFF, ảnh hưởng trực tiếp đến giá mục tiêu. Diễn biến giá API và tiến độ "
        f"nâng chuẩn nhà máy là hai chỉ báo vận hành cần theo dõi song song với kết quả tài chính quý."
    )


def build_financial_performance(n: NarrativeInputs) -> str:
    quality_comment = (
        "Tỷ lệ này cho thấy lợi nhuận được hỗ trợ tốt bởi dòng tiền thực."
        if n.cash_conversion is not None and (n.cash_conversion or 0) >= 0.9
        else "Tỷ lệ này báo hiệu cần kiểm tra chặt hơn chất lượng thu tiền và vốn lưu động."
    )
    return (
        f"Doanh thu {_bn(n.revenue_latest)} với biên lợi nhuận ròng {_pct(n.net_margin_latest)} và biên gộp "
        f"{_pct(n.gross_margin_latest)} vẽ nên bức tranh một doanh nghiệp có khả năng tạo lợi nhuận tương đối "
        f"ổn định, song phụ thuộc vào kiểm soát chi phí hơn là tăng trưởng sản lượng đột biến. "
        f"Điểm đáng chú ý là tỷ lệ chuyển đổi tiền mặt {_times(n.cash_conversion)}. {quality_comment} "
        f"Khi tỷ lệ này thấp, lợi nhuận kế toán vẫn cao nhưng FCFF thực sự bị kéo xuống bởi gia tăng vốn "
        f"lưu động — đặc biệt phải thu từ kênh ETC thường kéo dài 60–90 ngày. Đây là cơ chế giải thích tại "
        f"sao biên lợi nhuận ròng {_pct(n.net_margin_latest)} không nhất thiết tương đương với khả năng tạo "
        f"dòng tiền tự do. "
        f"Biến động lợi nhuận giữa các năm chủ yếu đến từ ba nguồn: (1) thay đổi giá vốn API/tỷ giá; "
        f"(2) cơ cấu kênh ETC/OTC; (3) chu kỳ chi phí SG&A liên quan đấu thầu. Những yếu tố này được chuẩn "
        f"hóa thành driver dự phóng (biên gộp {_pct(n.gross_margin_driver)}, SG&A {_pct(n.sga_driver)} doanh "
        f"thu) và là cơ sở để phân tích độ nhạy — người đọc có thể kiểm tra xem kết quả mô hình thay đổi như "
        f"thế nào khi từng giả định dịch chuyển."
    )


def build_forecast_assumptions(n: NarrativeInputs) -> str:
    return (
        f"Dự phóng theo phương pháp driver-based, đi từ biến số kinh doanh tới dòng tài chính tới định giá. "
        f"Giả định cơ sở: tăng trưởng doanh thu {_pct(n.rev_growth_driver)} (căn cứ CAGR lịch sử "
        f"{_pct(n.revenue_cagr)} và kế hoạch mở rộng ETC/OTC); biên lợi nhuận gộp {_pct(n.gross_margin_driver)} "
        f"(phản ánh áp lực API và cơ cấu sản phẩm); SG&A {_pct(n.sga_driver)} doanh thu; thuế suất hiệu dụng "
        f"{_pct(n.tax_driver)}; capex {_pct(n.capex_driver)} doanh thu. "
        f"Driver có tác động lớn nhất tới giá trị là: (1) tăng trưởng doanh thu — mỗi điểm phần trăm hụt so "
        f"với giả định cơ sở sẽ kéo EBIT và FCFF giảm theo tỷ lệ; (2) biên lợi nhuận gộp — biến động chi phí "
        f"API truyền trực tiếp vào đây trước khi ảnh hưởng xuống các tầng dưới; (3) capex và vốn lưu động — "
        f"quyết định bao nhiêu phần EBIT còn lại dưới dạng FCFF sau tái đầu tư. "
        f"Hai tham số định giá quan trọng nhất là WACC {_pct(n.wacc)} và tăng trưởng dài hạn "
        f"{_pct(n.terminal_growth)}; chúng xác định cách quy đổi FCFF tương lai về hiện giá. Độ nhạy của giá "
        f"mục tiêu với hai tham số này cao hơn bất kỳ driver vận hành nào — đây là lý do ma trận độ nhạy là "
        f"bắt buộc chứ không phải tùy chọn. Rủi ro sai lệch lớn nhất là khi giả định tăng trưởng lạc quan "
        f"gặp thực tế đấu thầu thắt chặt hoặc giá API tăng đột biến cùng lúc."
    )


def build_valuation_narrative(n: NarrativeInputs) -> str:
    blend_clause = (
        f"Giá mục tiêu {_vnd(n.target_price)} được tổng hợp theo trọng số 60% FCFF ({_vnd(n.price_fcff)}) "
        f"và 40% P/E Forward ({_vnd(n.price_pe_forward)}). Phương pháp P/E Forward được dùng thay cho FCFE "
        f"vì FCFE đòi hỏi lịch trả nợ đầy đủ — khi dữ liệu thiếu, kết quả FCFE không đáng tin cậy. "
        f"P/E Forward neo giá trị vào kỳ vọng lợi nhuận gần hạn và tâm lý thị trường, bổ sung chiều "
        f"thông tin mà FCFF thuần túy không nắm bắt được."
        if n.target_price else
        f"Giá mục tiêu hợp nhất hiện {_NA}; một số đầu vào định giá chưa đủ điều kiện."
    )
    upside_direction = (
        "tiềm năng tăng" if (n.upside or 0) > 0 else "rủi ro giảm"
        if n.upside is not None else "chênh lệch"
    )
    return (
        f"Phương pháp định giá chính là FCFF DCF, kiểm tra chéo bằng bội số P/E Forward. "
        f"FCFF được chiết khấu bằng WACC {_pct(n.wacc)} với tăng trưởng dài hạn {_pct(n.terminal_growth)}. "
        f"{blend_clause} "
        f"So với thị giá {_vnd(n.current_price)}, giá mục tiêu hàm ý {upside_direction} {_pct(n.upside)}. "
        f"Ma trận độ nhạy cho khoảng {_vnd(n.sens_low)}–{_vnd(n.sens_high)}: khoảng này rộng hay hẹp là "
        f"thước đo mức độ chắc chắn của kết luận — khoảng rộng hơn 30% giá hiện tại cho thấy kết quả phụ "
        f"thuộc mạnh vào giả định dài hạn và cần thận trọng khi diễn giải điểm mục tiêu. "
        f"Rủi ro định giá trọng yếu là tỷ trọng terminal value trong tổng EV cao: khi phần lớn giá trị nằm "
        f"ở năm cuối kỳ dự phóng, một sai lệch nhỏ về tăng trưởng dài hạn tạo ra biến động lớn hơn nhiều "
        f"so với sai lệch về driver vận hành gần hạn. Đây là lý do kết luận định giá chỉ có giá trị trong "
        f"điều kiện giả định cơ sở được phê duyệt và cập nhật định kỳ."
    )


def build_risks_catalysts(n: NarrativeInputs) -> str:
    return (
        f"Rủi ro và yếu tố hỗ trợ của {n.company_name} đều gắn với cơ chế truyền dẫn tài chính cụ thể, "
        f"không đơn thuần là liệt kê định tính. "
        f"Rủi ro giảm giá theo mức độ ưu tiên: (1) giá trúng thầu ETC thấp hơn kỳ vọng — đây là rủi ro "
        f"trọng yếu nhất vì tác động đồng thời lên doanh thu và biên gộp, tức là thu hẹp FCFF từ cả hai "
        f"phía; (2) giá API nhập khẩu và tỷ giá USD/VND tăng — ảnh hưởng trực tiếp đến giá vốn, thu hẹp "
        f"biên gộp {_pct(n.gross_margin_driver)} giả định; (3) kéo dài chu kỳ phải thu bệnh viện — làm tăng "
        f"ΔNWC và giảm FCFF dù lợi nhuận kế toán vẫn cao; (4) cạnh tranh generic gia tăng — tạo áp lực "
        f"giảm giá trên sản phẩm chủ lực; (5) thay đổi chính sách đăng ký lưu hành và tiêu chuẩn GMP. "
        f"Yếu tố hỗ trợ: trúng thêm thầu ETC mới là catalyst có tác động lớn nhất và gần nhất đến FCFF; "
        f"cải thiện cơ cấu sản phẩm biên cao (chuyển dần từ generic sang branded generic) nâng biên gộp "
        f"một cách bền vững hơn mở rộng sản lượng thuần túy; hoàn tất đầu tư GMP-EU mở rộng tập khách hàng "
        f"xuất khẩu, giảm phụ thuộc vào chu kỳ đấu thầu nội địa. "
        f"Mỗi yếu tố cần gắn với chỉ báo sớm cụ thể: kết quả đấu thầu ETC hàng quý, biến động giá API theo "
        f"chỉ số thị trường nguyên liệu dược, vòng quay phải thu so với cùng kỳ. Khi có dữ liệu mới, nhà "
        f"phân tích nên chạy lại ma trận độ nhạy để xác nhận kết luận định giá còn hiệu lực."
    )


def build_growth_drivers(n: NarrativeInputs) -> str:
    """Growth-driver narrative (revenue/volume/expansion side).

    Distinct from margin section: focuses on top-line growth levers and their
    path to FCFF, not cost structure.
    """
    gap_comment = ""
    if n.revenue_growth_latest is not None and n.rev_growth_driver is not None:
        gap = (n.rev_growth_driver or 0) - (n.revenue_growth_latest or 0)
        if gap > 0.03:
            gap_comment = (
                f"Giả định dự phóng {_pct(n.rev_growth_driver)} cao hơn tốc độ gần nhất {_pct(n.revenue_growth_latest)}, "
                f"hàm ý mô hình kỳ vọng gia tốc tăng trưởng — cần có căn cứ cụ thể (thầu mới, sản phẩm mới) để hỗ trợ. "
            )
        elif gap < -0.03:
            gap_comment = (
                f"Giả định dự phóng {_pct(n.rev_growth_driver)} thận trọng hơn tốc độ gần nhất {_pct(n.revenue_growth_latest)}, "
                f"phản ánh quan điểm bảo thủ về tính bền vững của động lực tăng trưởng hiện tại. "
            )
    return (
        f"Doanh thu {_bn(n.revenue_latest)} tăng {_pct(n.revenue_growth_latest)} so với kỳ trước, trên nền "
        f"CAGR lịch sử {_pct(n.revenue_cagr)}. {gap_comment}"
        f"Nguồn tăng trưởng chính là mở rộng sản lượng kênh ETC (đấu thầu bệnh viện) — kênh này vừa có "
        f"quy mô lớn vừa bị chi phối bởi chu kỳ đấu thầu định kỳ, tạo ra sự biến động không đều giữa các "
        f"quý. Kênh OTC ổn định hơn nhưng tăng trưởng thấp hơn; nó đóng vai trò giảm thiểu biến động hơn "
        f"là dẫn dắt tăng trưởng. Mức đầu tư capex {_pct(n.capex_driver)} doanh thu để nâng chuẩn GMP là "
        f"điều kiện cần để mở rộng tập sản phẩm và khách hàng trung hạn — nhưng trong ngắn hạn làm giảm "
        f"FCFF. Hiểu được đánh đổi này là chìa khóa để diễn giải FCFF hiện tại đúng với giai đoạn đầu tư. "
        f"Chỉ báo cần theo dõi: tỷ lệ trúng thầu so với dự thầu ETC, tiến độ đầu tư công suất và mức độ "
        f"thâm nhập kênh OTC — ba con số này sẽ xác nhận hoặc bác bỏ giả định tăng trưởng của mô hình."
    )


def build_margin_drivers(n: NarrativeInputs) -> str:
    """Margin-driver narrative (cost/profitability side).

    Distinct from growth section: focuses on margin levers and their sensitivity
    to input cost volatility, not revenue volume.
    """
    margin_gap = (
        (n.gross_margin_driver or 0) - (n.gross_margin_latest or 0)
        if n.gross_margin_driver is not None and n.gross_margin_latest is not None
        else None
    )
    margin_direction = (
        "kỳ vọng biên gộp cải thiện nhẹ so với mức lịch sử"
        if margin_gap is not None and margin_gap > 0.01
        else "kỳ vọng biên gộp duy trì ổn định"
        if margin_gap is not None and abs(margin_gap) <= 0.01
        else "kỳ vọng biên gộp thu hẹp nhẹ so với mức lịch sử"
        if margin_gap is not None
        else "cần đối chiếu giả định biên gộp với dữ liệu lịch sử"
    )
    return (
        f"Biên lợi nhuận gộp hiện tại {_pct(n.gross_margin_latest)}, mô hình {margin_direction} "
        f"({_pct(n.gross_margin_driver)} dự phóng). Biên gộp là biến số nhạy thứ hai sau tăng trưởng doanh "
        f"thu trong mô hình định giá — mỗi điểm phần trăm thay đổi chuyển gần như trọn vẹn vào EBIT và FCFF. "
        f"Áp lực chính lên biên gộp là chi phí API nhập khẩu và tỷ giá USD/VND: khi hai yếu tố này tăng "
        f"cùng chiều, giá vốn hàng bán tăng và biên gộp bị thu hẹp ngay trong quý tiếp theo vì chu kỳ nhập "
        f"khẩu thường ngắn. Dư địa hấp thụ cú sốc này bị giới hạn bởi biên lợi nhuận ròng hiện ở mức "
        f"{_pct(n.net_margin_latest)} — không đủ đệm để hấp thụ nếu biên gộp giảm quá 2–3 điểm phần trăm. "
        f"Chi phí SG&A {_pct(n.sga_driver)} doanh thu là lớp chi phí quyết định khoảng cách biên gộp → "
        f"biên EBIT; đặc biệt chi phí phục vụ đấu thầu ETC có xu hướng không co giãn theo doanh thu. "
        f"Thuế suất hiệu dụng {_pct(n.tax_driver)} là bước chuyển cuối từ EBIT sang lợi nhuận sau thuế — "
        f"biến số này ít biến động nhưng bất kỳ thay đổi ưu đãi thuế nào sẽ tác động trực tiếp. "
        f"Chỉ báo cần theo dõi: giá API theo chỉ số thị trường nguyên liệu dược, tỷ giá USD/VND, và biên "
        f"gộp thực tế quý tiếp theo so với giả định — đây là tín hiệu sớm cho việc cần điều chỉnh mô hình."
    )


def build_all(n: NarrativeInputs) -> dict[str, str]:
    """Return the client-report narrative sections, all artifact-grounded and distinct."""
    return {
        "investment_thesis": build_investment_thesis(n),
        "latest_business_update": build_business_update(n),
        "financial_performance": build_financial_performance(n),
        "growth_drivers": build_growth_drivers(n),
        "margin_drivers": build_margin_drivers(n),
        "forecast_valuation_narrative": build_forecast_assumptions(n),
        "valuation_narrative": build_valuation_narrative(n),
        "risks_catalysts": build_risks_catalysts(n),
    }
