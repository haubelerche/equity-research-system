"""Deterministic research insight pack (report-quality plan P1).

Turns the numbers the report already computes (growth, margins, leverage, valuation) and
the collected news into analyst-grade insights: each a claim with its evidence sources
([1] financial data, [2] valuation model, [3]+ news) and a 'so what' valuation implication.

Deterministic and pure — no LLM, no fabrication. An insight whose inputs are missing is
emitted with status 'insufficient_evidence' (and the missing fields) rather than invented.
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
    """Build the ordered insight pack from the report's computed inputs."""
    pack: list[dict[str, Any]] = []

    # 1. Growth quality — is profit growth driven by revenue (volume) or cost/margin?
    rev_g = inputs.get("revenue_growth_latest")
    prof_g = inputs.get("profit_growth_latest")
    if rev_g is not None and prof_g is not None and prof_g > rev_g + 0.05:
        claim = (
            "Lợi nhuận tăng nhanh hơn doanh thu, cho thấy tăng trưởng chủ yếu đến từ cải "
            "thiện biên lợi nhuận và tiết giảm chi phí, không phải từ tăng sản lượng."
        )
        valimp = (
            "Chất lượng tăng trưởng phụ thuộc vào khả năng duy trì biên; không nên nâng "
            "tăng trưởng dài hạn chỉ dựa trên mức lợi nhuận cao nhất thời."
        )
    else:
        claim = (
            "Tăng trưởng lợi nhuận đi cùng tăng trưởng doanh thu, cho thấy động lực đến từ "
            "quy mô kinh doanh."
        )
        valimp = "Tăng trưởng dựa trên doanh thu bền vững hơn cho giả định dài hạn."
    pack.append(_insight(
        "growth", claim,
        evidence_refs=["[1]", "[2]"],
        analysis_logic="So sánh tăng trưởng lợi nhuận với tăng trưởng doanh thu kỳ gần nhất.",
        valuation_implication=valimp, confidence="medium",
        inputs=inputs, required=["revenue_growth_latest", "profit_growth_latest"],
    ))

    # 2. Margin bridge — gross margin trend.
    gm, gm_prev = inputs.get("gross_margin_latest"), inputs.get("gross_margin_prev")
    if gm is not None and gm_prev is not None:
        widening = gm >= gm_prev
        claim = (
            f"Biên lợi nhuận gộp {'mở rộng' if widening else 'thu hẹp'} "
            f"({gm_prev * 100:.1f}% → {gm * 100:.1f}%)."
        )
        valimp = (
            "Biên mở rộng hỗ trợ dự phóng lợi nhuận; cần theo dõi giá vốn và cạnh tranh."
            if widening else
            "Biên thu hẹp gây áp lực lên dự phóng lợi nhuận; rà soát giả định giá vốn."
        )
    else:
        claim = "Chưa đủ dữ liệu biên lợi nhuận gộp để nhận định xu hướng."
        valimp = ""
    pack.append(_insight(
        "margin", claim,
        evidence_refs=["[1]"],
        analysis_logic="Đối chiếu biên lợi nhuận gộp kỳ gần nhất với kỳ trước.",
        valuation_implication=valimp, confidence="medium",
        inputs=inputs, required=["gross_margin_latest", "gross_margin_prev"],
    ))

    # 3. Leverage / balance-sheet quality — net debt / EBITDA.
    nde = inputs.get("net_debt_ebitda")
    if nde is not None and nde < 0:
        claim = "Doanh nghiệp ở vị thế tiền mặt ròng (nợ ròng âm so với EBITDA)."
        valimp = "Linh hoạt tài chính cao, hỗ trợ cổ tức/đầu tư; rủi ro đòn bẩy thấp."
    elif nde is not None and nde > 2:
        claim = f"Đòn bẩy ở mức cao (nợ ròng/EBITDA ≈ {nde:.1f}x)."
        valimp = "Rủi ro đòn bẩy cần theo dõi; chi phí lãi vay ảnh hưởng dòng tiền cổ đông."
    else:
        claim = "Đòn bẩy ở mức trung bình."
        valimp = "Cấu trúc vốn không phải rủi ro nổi bật ở hiện tại."
    pack.append(_insight(
        "leverage", claim,
        evidence_refs=["[1]"],
        analysis_logic="Đánh giá nợ ròng trên EBITDA kỳ gần nhất.",
        valuation_implication=valimp, confidence="medium",
        inputs=inputs, required=["net_debt_ebitda"],
    ))

    # 4. Valuation — upside + recommendation rule.
    upside = inputs.get("upside")
    rec = inputs.get("recommendation") or "—"
    if upside is not None:
        claim = f"Tiềm năng tăng/giảm giá theo mô hình định giá là {upside * 100:+.1f}%."
    else:
        claim = "Chưa xác định được tiềm năng tăng/giảm giá."
    pack.append(_insight(
        "valuation", claim,
        evidence_refs=["[2]"],
        analysis_logic="Chiết khấu dòng tiền (FCFF/FCFE) theo WACC, so với giá hiện tại.",
        valuation_implication=f"Khuyến nghị hệ thống: {rec}.",
        confidence="medium",
        inputs=inputs, required=["upside"],
    ))

    # 5. Catalyst — only when real news evidence exists.
    news_count = int(inputs.get("news_count") or 0)
    if news_count > 0:
        pack.append(_insight(
            "catalyst",
            f"Có {news_count} bài báo/sự kiện được trích dẫn liên quan trực tiếp đến doanh nghiệp.",
            evidence_refs=["[3]"],
            analysis_logic="Tổng hợp các bài báo whitelisted thu thập cho mã này.",
            valuation_implication="Xem mục Chú giải nguồn để đối chiếu từng sự kiện và đánh giá tác động.",
            confidence="medium",
            inputs=inputs, required=["news_count"],
        ))

    return pack
