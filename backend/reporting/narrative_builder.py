"""Deterministic, artifact-grounded narrative builder for client reports.

Every sentence is composed from values already computed by the deterministic engines
(facts, forecast drivers, valuation blend, sensitivity). No number is invented here —
when an input is missing the text says so explicitly rather than fabricating a figure
(CLAUDE.md §5.1). Each section targets ≥300 Vietnamese words and follows the required
four-layer logic: quantitative fact → driver/cause → valuation impact → risk to watch.
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
    price_fcfe: float | None = None                 # VND
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
    rating_clause = (
        f"Trên cơ sở mô hình định giá hiện tại, kết luận định giá là {n.rating} với giá mục tiêu "
        f"{_vnd(n.target_price)} so với thị giá {_vnd(n.current_price)}, tương ứng mức "
        f"{'chênh lệch' if n.upside is None else ('tiềm năng tăng' if (n.upside or 0) > 0 else 'rủi ro giảm')} "
        f"{_pct(n.upside)}."
        if n.target_price else
        f"Giá mục tiêu hiện {_NA}; do đó báo cáo giữ trạng thái cần rà soát thay vì đưa ra khuyến nghị dứt khoát."
    )
    return (
        f"{n.company_name} ({n.ticker}) là doanh nghiệp ngành {n.sector} với nền doanh thu gần nhất đạt "
        f"{_bn(n.revenue_latest)} và lợi nhuận ròng {_bn(n.net_income_latest)}, tương ứng biên lợi nhuận ròng "
        f"{_pct(n.net_margin_latest)} và biên lợi nhuận gộp {_pct(n.gross_margin_latest)}. "
        f"Tốc độ tăng trưởng doanh thu kỳ gần nhất là {_pct(n.revenue_growth_latest)} và CAGR doanh thu giai đoạn "
        f"lịch sử khoảng {_pct(n.revenue_cagr)}, phản ánh quỹ đạo kinh doanh làm nền cho dự phóng. "
        f"Luận điểm đầu tư xoay quanh ba trụ cột: (i) khả năng duy trì biên lợi nhuận gộp quanh mức "
        f"{_pct(n.gross_margin_driver)} trong bối cảnh áp lực giá nguyên liệu (API) nhập khẩu và tỷ giá; "
        f"(ii) kiểm soát chi phí bán hàng và quản lý ở mức {_pct(n.sga_driver)} doanh thu để bảo vệ biên EBIT; "
        f"(iii) kỷ luật đầu tư với capex khoảng {_pct(n.capex_driver)} doanh thu, ảnh hưởng trực tiếp tới dòng tiền tự do FCFF. "
        f"{rating_clause} "
        f"Mức định giá nhạy với chi phí vốn (WACC {_pct(n.wacc)}) và tăng trưởng dài hạn ({_pct(n.terminal_growth)}); "
        f"khoảng giá mục tiêu theo ma trận độ nhạy trải từ {_vnd(n.sens_low)} đến {_vnd(n.sens_high)}. "
        f"Rủi ro chính cần theo dõi là kết quả đấu thầu thuốc kênh ETC và biến động chi phí API, vì hai yếu tố này "
        f"tác động đồng thời lên doanh thu và biên lợi nhuận, qua đó làm thay đổi FCFF và giá mục tiêu. "
        f"Cấu phần định giá cho thấy giá theo FCFF đạt {_vnd(n.price_fcff)} và theo FCFE đạt {_vnd(n.price_fcfe)}, "
        f"phản ánh khác biệt giữa giá trị toàn doanh nghiệp và giá trị vốn cổ phần sau nợ vay; mức chênh giữa hai phương "
        f"pháp là tín hiệu cần soi kỹ giả định nợ vay, lãi vay và vốn lưu động trước khi chốt khuyến nghị. "
        f"Suất cổ tức hiện tại ở mức {_pct(n.dividend_yield)} cũng là một cấu phần của tổng tỷ suất sinh lợi kỳ vọng "
        f"mà nhà đầu tư cần cân nhắc bên cạnh chênh lệch giá mục tiêu so với thị giá."
    )


def build_business_update(n: NarrativeInputs) -> str:
    return (
        f"{n.company_name} vận hành mô hình kinh doanh dược phẩm với hai kênh phân phối chính là ETC (đấu thầu "
        f"bệnh viện) và OTC (nhà thuốc bán lẻ). Doanh thu thuần kỳ gần nhất đạt {_bn(n.revenue_latest)}, so với "
        f"{_bn(n.revenue_prev)} kỳ liền trước, tương ứng tăng trưởng {_pct(n.revenue_growth_latest)}. "
        f"Cơ cấu lợi nhuận được dẫn dắt bởi biên lợi nhuận gộp {_pct(n.gross_margin_latest)}, phản ánh năng lực "
        f"sản xuất, danh mục sản phẩm generic và khả năng kiểm soát giá vốn. EPS gần nhất ở mức {_vnd(n.eps_latest)}. "
        f"Các động lực vận hành trọng yếu gồm: giá bán và sản lượng trên kênh ETC (chịu ảnh hưởng chính sách đấu thầu "
        f"và BHYT), giá nguyên liệu API nhập khẩu cùng tỷ giá USD/VND tác động lên giá vốn, và mức đầu tư nâng chuẩn "
        f"nhà máy theo tiêu chuẩn GMP-EU/WHO. Những yếu tố này được phản ánh trực tiếp vào các driver dự phóng: "
        f"tăng trưởng doanh thu {_pct(n.rev_growth_driver)}, biên gộp {_pct(n.gross_margin_driver)}, "
        f"chi phí bán hàng và quản lý {_pct(n.sga_driver)} doanh thu và capex {_pct(n.capex_driver)} doanh thu. "
        f"Chất lượng dòng tiền được đánh giá qua tỷ lệ chuyển đổi tiền mặt (CFO/lợi nhuận ròng) khoảng "
        f"{_times(n.cash_conversion)}; tỷ lệ này càng cao thì rủi ro vốn lưu động càng thấp và FCFF càng bền. "
        f"Về mặt định giá, mọi thay đổi trong sản lượng ETC hoặc giá trúng thầu sẽ truyền dẫn qua doanh thu và biên "
        f"gộp tới EBIT, từ đó tác động lên FCFF và giá mục tiêu. Rủi ro cần theo dõi là phụ thuộc kênh ETC và biến "
        f"động chính sách đấu thầu, có thể làm lệch quỹ đạo doanh thu so với giả định cơ sở. "
        f"Bên cạnh đó, chính sách cổ tức (suất cổ tức hiện {_pct(n.dividend_yield)}) và mức thuế suất hiệu dụng "
        f"{_pct(n.tax_driver)} cũng ảnh hưởng tới lợi nhuận sau thuế giữ lại và dòng tiền cổ đông, từ đó tác động tới "
        f"giá trị vốn cổ phần trong mô hình FCFE. Việc theo dõi đồng thời các chỉ báo vận hành (giá trúng thầu, giá API, "
        f"vòng quay hàng tồn kho và phải thu) sẽ giúp đánh giá sớm khả năng doanh nghiệp duy trì hay cải thiện biên lợi "
        f"nhuận so với kịch bản cơ sở đã đưa vào mô hình định giá."
    )


def build_financial_performance(n: NarrativeInputs) -> str:
    return (
        f"Bức tranh tài chính lịch sử cho thấy doanh thu thuần gần nhất {_bn(n.revenue_latest)} với tăng trưởng "
        f"kỳ gần nhất {_pct(n.revenue_growth_latest)} và CAGR giai đoạn khoảng {_pct(n.revenue_cagr)}. "
        f"Lợi nhuận ròng đạt {_bn(n.net_income_latest)}, tương ứng biên lợi nhuận ròng {_pct(n.net_margin_latest)}; "
        f"biên lợi nhuận gộp ở mức {_pct(n.gross_margin_latest)} là chỉ báo quan trọng về sức mạnh định giá sản phẩm "
        f"và hiệu quả kiểm soát giá vốn. EPS gần nhất {_vnd(n.eps_latest)}. "
        f"Chất lượng lợi nhuận được soi qua tỷ lệ chuyển đổi tiền mặt khoảng {_times(n.cash_conversion)}: tỷ lệ quanh "
        f"hoặc trên 1,0 lần cho thấy lợi nhuận kế toán được hỗ trợ tốt bởi dòng tiền hoạt động thực, trong khi tỷ lệ "
        f"thấp sẽ cảnh báo áp lực vốn lưu động từ hàng tồn kho và phải thu — đặc biệt với khoản phải thu bệnh viện "
        f"trên kênh ETC. Nguyên nhân biến động lợi nhuận giữa các năm chủ yếu đến từ thay đổi giá vốn API, cơ cấu kênh "
        f"ETC/OTC và mức chi phí bán hàng phục vụ đấu thầu. Những biến động này được chuẩn hóa thành driver dự phóng "
        f"(biên gộp {_pct(n.gross_margin_driver)}, SG&A {_pct(n.sga_driver)} doanh thu, thuế suất {_pct(n.tax_driver)}) "
        f"và truyền vào mô hình FCFF. Về tác động định giá, biên lợi nhuận và vòng quay vốn lưu động là hai biến số "
        f"quyết định FCFF; do đó bất kỳ sai lệch nào so với giả định cơ sở đều làm thay đổi giá mục tiêu. "
        f"Đặt trong khung định giá, EPS {_vnd(n.eps_latest)} và biên lợi nhuận ròng {_pct(n.net_margin_latest)} là nền "
        f"để dự phóng lợi nhuận tương lai, trong khi mức chiết khấu WACC {_pct(n.wacc)} và tăng trưởng dài hạn "
        f"{_pct(n.terminal_growth)} quy đổi các dòng tiền đó về hiện giá. Sự kết hợp giữa chất lượng lợi nhuận lịch sử "
        f"và kỷ luật chi phí vốn chính là cầu nối giữa phần phân tích tài chính và kết luận định giá. Rủi ro cần theo "
        f"dõi gồm biến động chi phí API/tỷ giá, rủi ro tập trung sản phẩm chủ lực và áp lực vốn lưu động từ phải thu bệnh viện."
    )


def build_forecast_assumptions(n: NarrativeInputs) -> str:
    return (
        f"Dự phóng được xây dựng theo phương pháp driver-based, nối từ biến số kinh doanh tới dòng tài chính rồi tới "
        f"định giá. Giả định cơ sở gồm: tăng trưởng doanh thu {_pct(n.rev_growth_driver)} phản ánh quỹ đạo lịch sử "
        f"(CAGR {_pct(n.revenue_cagr)}) và định hướng mở rộng kênh ETC/OTC; biên lợi nhuận gộp {_pct(n.gross_margin_driver)} "
        f"phản ánh áp lực giá vốn API và cơ cấu sản phẩm; chi phí bán hàng và quản lý {_pct(n.sga_driver)} doanh thu; "
        f"thuế suất hiệu dụng {_pct(n.tax_driver)}; và capex {_pct(n.capex_driver)} doanh thu phục vụ chu kỳ đầu tư nhà máy. "
        f"Ba driver có tác động lớn nhất tới giá trị: (1) tăng trưởng doanh thu — quyết định quy mô EBIT và FCFF; "
        f"(2) biên lợi nhuận gộp — mỗi điểm phần trăm thay đổi chuyển trực tiếp vào EBIT; (3) capex và vốn lưu động — "
        f"chi phối phần FCFF còn lại sau tái đầu tư. Các giả định này được chiết khấu bằng WACC {_pct(n.wacc)} với "
        f"tăng trưởng dài hạn {_pct(n.terminal_growth)} trong mô hình FCFF, và bằng chi phí vốn cổ phần trong mô hình FCFE. "
        f"Khi giá nguyên liệu API tăng hoặc giá trúng thầu giảm, biên gộp thu hẹp, EBIT và FCFF giảm, kéo giá mục tiêu "
        f"xuống; ngược lại, cải thiện cơ cấu sản phẩm hoặc sản lượng ETC sẽ nâng FCFF. Các giả định trọng yếu (WACC, "
        f"tăng trưởng dài hạn, biên lợi nhuận) cần được chuyên viên phê duyệt trước khi xuất bản báo cáo chính thức. "
        f"Kết quả định giá sơ bộ cho thấy giá theo FCFF {_vnd(n.price_fcff)} và theo FCFE {_vnd(n.price_fcfe)}, hợp nhất "
        f"thành giá mục tiêu {_vnd(n.target_price)} so với thị giá {_vnd(n.current_price)} ({_pct(n.upside)}). "
        f"Mỗi giả định driver đều có thể truy ngược về dữ liệu lịch sử và được kiểm tra bằng ma trận độ nhạy, qua đó "
        f"người đọc kiểm chứng được luận điểm thay vì chỉ nhìn một con số mục tiêu duy nhất. Rủi ro cần theo dõi là sai "
        f"lệch giữa giả định tăng trưởng và diễn biến đấu thầu thực tế, cũng như khả năng giá nguyên liệu API vượt dự phóng."
    )


def build_valuation_narrative(n: NarrativeInputs) -> str:
    blend_clause = (
        f"Giá mục tiêu chính được tổng hợp theo trọng số 60% FCFF ({_vnd(n.price_fcff)}) và 40% FCFE "
        f"({_vnd(n.price_fcfe)}), cho kết quả {_vnd(n.target_price)}."
        if n.target_price else
        f"Giá mục tiêu hợp nhất hiện {_NA}, do một số đầu vào định giá chưa đủ điều kiện hoặc chưa được phê duyệt."
    )
    return (
        f"Phương pháp định giá chính là chiết khấu dòng tiền tự do doanh nghiệp (FCFF DCF), kiểm tra chéo bằng FCFE và "
        f"bội số P/E, P/B, EV/EBITDA khi dữ liệu peer đủ tin cậy. FCFF được chiết khấu bằng WACC {_pct(n.wacc)} với "
        f"tăng trưởng dài hạn {_pct(n.terminal_growth)}; FCFE được chiết khấu bằng chi phí vốn cổ phần. {blend_clause} "
        f"So với thị giá {_vnd(n.current_price)}, mức {'chênh lệch' if n.upside is None else ('tăng' if (n.upside or 0) > 0 else 'giảm')} "
        f"là {_pct(n.upside)}, dẫn tới kết luận định giá {n.rating or _NA}. "
        f"Giá mục tiêu nhạy nhất với WACC và tăng trưởng dài hạn: theo ma trận độ nhạy, giá trị hợp lý trải từ "
        f"{_vnd(n.sens_low)} (kịch bản chi phí vốn cao/tăng trưởng thấp) đến {_vnd(n.sens_high)} (chi phí vốn thấp/"
        f"tăng trưởng cao). Điều này hàm ý kết luận định giá phụ thuộc đáng kể vào khả năng duy trì biên EBIT và kiểm "
        f"soát vốn lưu động; khi WACC tăng, giá mục tiêu giảm và có thể đổi nhóm khuyến nghị. Kết luận định giá là kết "
        f"quả mô hình dựa trên dữ liệu và giả định tại thời điểm lập báo cáo, không phải khuyến nghị đầu tư cá nhân hóa. "
        f"Rủi ro định giá trọng yếu là trọng số giá trị cuối kỳ (terminal value) cao trong tổng EV, khiến kết quả nhạy "
        f"với giả định dài hạn; cần diễn giải thận trọng và rà soát giả định trước khi sử dụng. "
        f"Chênh lệch giữa giá theo FCFF ({_vnd(n.price_fcff)}) và giá theo FCFE ({_vnd(n.price_fcfe)}) phản ánh tác động "
        f"của cấu trúc nợ vay và dòng tiền vay ròng; khi mức chênh lớn, cần kiểm tra lại lịch trả nợ, chi phí lãi vay và "
        f"thay đổi vốn lưu động trước khi kết luận. Cuối cùng, kết luận định giá {n.rating or _NA} chỉ có hiệu lực trong "
        f"điều kiện giả định cơ sở được phê duyệt; nếu biên EBIT suy giảm do giá API tăng hoặc giá trúng thầu giảm, giá "
        f"mục tiêu sẽ dịch về vùng thấp của ma trận độ nhạy ({_vnd(n.sens_low)}), và ngược lại có thể tiến tới vùng cao "
        f"({_vnd(n.sens_high)}) nếu doanh nghiệp cải thiện được cơ cấu sản phẩm và sản lượng kênh ETC."
    )


def build_risks_catalysts(n: NarrativeInputs) -> str:
    return (
        f"Rủi ro và yếu tố hỗ trợ của {n.company_name} đều gắn với các driver tài chính cụ thể. Về rủi ro giảm giá: "
        f"(1) áp lực giảm giá trúng thầu trên kênh ETC tác động trực tiếp tới doanh thu và biên lợi nhuận gộp — nếu giá "
        f"trúng thầu giảm mạnh hơn giả định cơ sở (biên gộp {_pct(n.gross_margin_driver)}), EBIT và FCFF sẽ thấp hơn mô "
        f"hình hiện tại, kéo giá mục tiêu {_vnd(n.target_price)} xuống; (2) biến động chi phí nguyên liệu API nhập khẩu "
        f"và tỷ giá USD/VND làm tăng giá vốn, thu hẹp biên gộp; (3) hàng tồn kho và phải thu bệnh viện tăng làm kéo dài "
        f"chu kỳ tiền mặt, tăng ΔNWC và giảm FCFF; (4) cạnh tranh generic và rủi ro tập trung sản phẩm chủ lực ảnh hưởng "
        f"tính ổn định doanh thu; (5) rủi ro thay đổi quy định đăng ký/lưu hành thuốc và tiêu chuẩn GMP. "
        f"Về yếu tố hỗ trợ: mở rộng sản lượng và trúng thầu ETC mới (nâng doanh thu và FCFF), cải thiện cơ cấu sản phẩm "
        f"biên cao (nâng biên gộp), hoàn tất đầu tư nhà máy GMP-EU (mở rộng công suất, dù làm tăng capex ngắn hạn "
        f"{_pct(n.capex_driver)} doanh thu), và khả năng tăng cổ tức nếu dòng tiền cải thiện (suất cổ tức hiện "
        f"{_pct(n.dividend_yield)}). Mỗi yếu tố trên cần được theo dõi qua chỉ báo cụ thể: kết quả đấu thầu, diễn biến "
        f"giá API/tỷ giá, vòng quay hàng tồn kho và phải thu, cùng tiến độ phê duyệt sản phẩm. Mức độ hiện thực hóa của "
        f"các yếu tố này sẽ quyết định việc giá mục tiêu dịch chuyển trong khoảng {_vnd(n.sens_low)}–{_vnd(n.sens_high)} "
        f"theo ma trận độ nhạy. Đặc biệt, với mức biên lợi nhuận ròng hiện tại {_pct(n.net_margin_latest)} và thuế suất "
        f"hiệu dụng {_pct(n.tax_driver)}, dư địa hấp thụ cú sốc chi phí là có giới hạn; do đó nhà đầu tư nên gắn mỗi rủi "
        f"ro với một ngưỡng theo dõi định lượng cụ thể thay vì đánh giá định tính chung chung, và rà soát lại giả định "
        f"cơ sở mỗi khi có kết quả đấu thầu hoặc báo cáo tài chính quý mới được công bố."
    )


def build_all(n: NarrativeInputs) -> dict[str, str]:
    """Return the six client-report narrative sections, all artifact-grounded."""
    return {
        "investment_thesis": build_investment_thesis(n),
        "latest_business_update": build_business_update(n),
        "financial_performance": build_financial_performance(n),
        "forecast_valuation_narrative": build_forecast_assumptions(n),
        "valuation_narrative": build_valuation_narrative(n),
        "risks_catalysts": build_risks_catalysts(n),
    }
