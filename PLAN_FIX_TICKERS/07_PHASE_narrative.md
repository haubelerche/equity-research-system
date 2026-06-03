# Phase 07 — Narrative analyst-grade (≥300 chữ/phần)

**PLAN gốc:** §1.4, §2 Phase 7, §4.8.
**Đọc trước:** `00_AUDIT.md`.

## Mục tiêu
Narrative có insight thật: dữ kiện định lượng → nguyên nhân/driver → tác động valuation → rủi ro. Tối thiểu 300 chữ/phần chính.

## Root cause
- `client_report_view_model.build_client_report_view_model` hardcode 6 chuỗi generic: `investment_thesis`, `latest_business_update`, `key_growth_drivers`, `key_margin_drivers`, `material_events`, `current_context` (dòng ~979–1010). Không bám fact/nguồn ⇒ chung chung.
- `report_data_loader.py` + `client_section_builder.py` là nơi nối narrative vào section.

## Việc cần làm
1. **Thay narrative hardcode bằng narrative bám artifact:**
   - Mỗi phần nhận `section_context`: 5–8 số liệu chính + driver quan trọng + source list + valuation impact + risk/catalyst liên quan (PLAN §2 Phase 7).
   - Writer (LLM) CHỈ diễn giải artifact, không bịa số (CLAUDE.md §5.1). Số do code điền, LLM viết câu chuyện quanh số.
2. **Phần chính ≥300 chữ:** investment thesis, business/company update, financial performance, forecast & assumptions, valuation, risks & catalysts.
3. **Cấm cụm rỗng** "nền tảng ổn định", "triển vọng tích cực" khi không có số + nguồn.
4. **Không lộ thuật ngữ backend** (`Tier`, `database`, `artifact`, `gate warning`) trong client PDF (PLAN §4.8) — đã có `CLIENT_FORBIDDEN_PDF_TERMS` trong `pdf_renderer.py`, mở rộng list.
5. Word-count check: lưu ý CLAUDE memory/commit gần đây nói word-cap 300 ở "Forbidden Actions" — đồng bộ ngưỡng (min 300, không phải max).

## Acceptance
- `Triển vọng đầu tư`/`Động lực biên lợi nhuận`/`Forecast`/`Valuation`/`Risk` không còn 1–3 câu.
- Mỗi phần có số cụ thể + citation + tác động valuation.

## Test
- `tests/unit/test_report_data_loader_agent_narrative.py` (đã có) — bổ sung assert độ dài ≥300 + có số + có citation token.
- Forbidden-term test trong `pdf_renderer`.

## Rủi ro
- LLM bịa số ⇒ bắt buộc numeric_consistency gate (Phase 01) chạy sau narrative.
- Chi phí token: dùng model rẻ cho phần đơn giản, model mạnh cho synthesis (CLAUDE.md §16).
