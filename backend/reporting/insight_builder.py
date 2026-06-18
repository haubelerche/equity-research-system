"""Deterministic research insight pack for client reports.

The builder converts already-computed report inputs into publishable analytical
claims. It intentionally withholds generic prose: an insight is ``ready`` only
when the input signal is both available and material enough to affect an
investment interpretation.
"""
from __future__ import annotations

from typing import Any


def _insight(
    section: str,
    claim: str,
    *,
    evidence_refs: list[str],
    analysis_logic: str,
    valuation_implication: str,
    confidence: str,
    inputs: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    missing = [field for field in required if inputs.get(field) is None]
    return {
        "section": section,
        "claim": claim,
        "evidence_refs": evidence_refs,
        "analysis_logic": analysis_logic,
        "valuation_implication": valuation_implication,
        "confidence": confidence,
        "status": "ready" if not missing else "insufficient_evidence",
        "missing_fields": missing,
    }


def build_insight_pack(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """Build ordered, material insights from computed report inputs."""
    pack: list[dict[str, Any]] = []

    rev_g = inputs.get("revenue_growth_latest")
    prof_g = inputs.get("profit_growth_latest")
    growth_spread = None if rev_g is None or prof_g is None else prof_g - rev_g
    material_growth = growth_spread is not None and abs(growth_spread) >= 0.05
    if material_growth and prof_g > rev_g:
        growth_claim = (
            "Lợi nhuận tăng nhanh hơn doanh thu, cho thấy tăng trưởng chủ yếu đến từ cải thiện biên lợi nhuận "
            "và tiết giảm chi phí, không phải từ tăng sản lượng."
        )
        growth_implication = (
            "Chất lượng tăng trưởng phụ thuộc vào khả năng duy trì biên; không nên nâng tăng trưởng dài hạn "
            "chỉ dựa trên mức lợi nhuận cao nhất thời."
        )
    elif material_growth:
        growth_claim = (
            "Lợi nhuận tăng chậm hơn doanh thu, cho thấy doanh thu mới chưa chuyển hóa trọn vẹn thành lợi nhuận."
        )
        growth_implication = (
            "Cần rà soát biên gộp, SG&A và đòn bẩy vận hành trước khi nâng giả định tăng trưởng dài hạn."
        )
    else:
        growth_claim = "Chưa có chênh lệch vật chất giữa tăng trưởng doanh thu và lợi nhuận."
        growth_implication = ""
    pack.append(_insight(
        "growth",
        growth_claim,
        evidence_refs=["[1]", "[2]"],
        analysis_logic="So sánh tăng trưởng lợi nhuận với tăng trưởng doanh thu kỳ gần nhất.",
        valuation_implication=growth_implication,
        confidence="medium",
        inputs={**inputs, "material_growth_spread": True if material_growth else None},
        required=["revenue_growth_latest", "profit_growth_latest", "material_growth_spread"],
    ))

    gm = inputs.get("gross_margin_latest")
    gm_prev = inputs.get("gross_margin_prev")
    margin_delta = None if gm is None or gm_prev is None else gm - gm_prev
    material_margin = margin_delta is not None and abs(margin_delta) >= 0.005
    if material_margin:
        widening = gm >= gm_prev
        margin_claim = (
            f"Biên lợi nhuận gộp {'mở rộng' if widening else 'thu hẹp'} "
            f"({gm_prev * 100:.1f}% -> {gm * 100:.1f}%)."
        )
        margin_implication = (
            "Biên mở rộng hỗ trợ dự phóng lợi nhuận; cần theo dõi giá vốn và cạnh tranh."
            if widening else
            "Biên thu hẹp gây áp lực lên dự phóng lợi nhuận; rà soát giả định giá vốn."
        )
    else:
        margin_claim = (
            "Biên lợi nhuận gộp không có biến động vật chất hoặc chưa đủ dữ liệu để nhận định xu hướng."
        )
        margin_implication = ""
    pack.append(_insight(
        "margin",
        margin_claim,
        evidence_refs=["[1]"],
        analysis_logic="Đối chiếu biên lợi nhuận gộp kỳ gần nhất với kỳ trước.",
        valuation_implication=margin_implication,
        confidence="medium",
        inputs={**inputs, "material_margin_delta": True if material_margin else None},
        required=["gross_margin_latest", "gross_margin_prev", "material_margin_delta"],
    ))

    nde = inputs.get("net_debt_ebitda")
    material_leverage = nde is not None and (nde < 0 or nde > 2)
    if nde is not None and nde < 0:
        leverage_claim = "Doanh nghiệp ở vị thế tiền mặt ròng (nợ ròng âm so với EBITDA)."
        leverage_implication = "Linh hoạt tài chính cao, hỗ trợ cổ tức/đầu tư; rủi ro đòn bẩy thấp."
    elif nde is not None and nde > 2:
        leverage_claim = f"Đòn bẩy ở mức cao (nợ ròng/EBITDA khoảng {nde:.1f}x)."
        leverage_implication = "Rủi ro đòn bẩy cần theo dõi; chi phí lãi vay ảnh hưởng dòng tiền cổ đông."
    else:
        leverage_claim = "Nợ ròng/EBITDA không nằm trong vùng tín hiệu vật chất."
        leverage_implication = ""
    pack.append(_insight(
        "leverage",
        leverage_claim,
        evidence_refs=["[1]"],
        analysis_logic="Đánh giá nợ ròng trên EBITDA kỳ gần nhất.",
        valuation_implication=leverage_implication,
        confidence="medium",
        inputs={**inputs, "material_leverage_signal": True if material_leverage else None},
        required=["net_debt_ebitda", "material_leverage_signal"],
    ))

    upside = inputs.get("upside")
    rec = inputs.get("recommendation") or "-"
    if upside is not None:
        valuation_claim = f"Tiềm năng tăng/giảm giá theo mô hình định giá là {upside * 100:+.1f}%."
    else:
        valuation_claim = "Chưa xác định được tiềm năng tăng/giảm giá."
    pack.append(_insight(
        "valuation",
        valuation_claim,
        evidence_refs=["[2]"],
        analysis_logic="Chiết khấu dòng tiền (FCFF/FCFE) theo WACC, so với giá hiện tại.",
        valuation_implication=f"Trạng thái khuyến nghị theo mô hình: {rec}.",
        confidence="medium",
        inputs=inputs,
        required=["upside"],
    ))

    news_count = int(inputs.get("news_count") or 0)
    if news_count > 0:
        pack.append(_insight(
            "catalyst",
            f"Có {news_count} bài báo/sự kiện được trích dẫn liên quan trực tiếp đến doanh nghiệp.",
            evidence_refs=["[3]"],
            analysis_logic="Tổng hợp các bài báo whitelisted thu thập cho mã này.",
            valuation_implication=(
                "Xem mục Chú giải nguồn để đối chiếu từng sự kiện và đánh giá tác động."
            ),
            confidence="medium",
            inputs=inputs,
            required=["news_count"],
        ))

    return pack
