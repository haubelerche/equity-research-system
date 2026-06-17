# Reporting và publication

Cập nhật: 2026-06-17

## Context

Reporting chuyển artifacts đã qua gate thành report model, sau đó render HTML/PDF khi có lệnh phù hợp. Runtime `PUBLISH` không xuất PDF trực tiếp; nó xác nhận model có thể publish, ghi manifest và phát hành trạng thái `DRAFT_PUBLISHABLE`. `scripts/generate_fast_report.py` là đường render nhanh từ artifact đã có, còn API `/reports/{ticker}/generate` có thể chọn `fast_render` hoặc `full_pipeline` tùy việc đã có snapshot và run renderable hay chưa.

## Problem Statement

Báo cáo client-facing có thể sai nếu renderer tự lấy dữ liệu ngoài manifest, nếu trạng thái `auto_exported` bị hiểu nhầm là approved, hoặc nếu report writer tự tạo claim thiếu citation. Reporting layer phải giữ ranh giới giữa draft tự động, review chuyên gia và final export.

## Technical Deep-Dive

### 1. Report assembly lifecycle

| Chặng | Module | Output |
|---|---|---|
| Draft | `ThesisReportAgent` | `report_draft` có sections, claims, tables/charts requirements |
| Assembly validation | `backend.reporting.report_assembler.ReportAssembler` | `report_assembly_validation` |
| Candidate model | `ReportAssembler.assemble` | `report_candidate_model` |
| Review promotion | `review_gate_promotion` | `review_passed_report_model` |
| Export promotion | `export_gate_promotion` | `publishable_final_report_model` |
| Manifest | `ResearchGraphRunner._write_run_manifest` | `{run_id}/manifest.json` |

### 2. Renderer stack

| Thành phần | Vai trò |
|---|---|
| Jinja2 templates | Render HTML từ view model |
| Matplotlib/Seaborn | Tạo charts deterministic |
| WeasyPrint | Primary PDF renderer |
| pdfkit/wkhtmltopdf | Fallback nếu có dependency hệ thống |
| Chrome/Edge headless | Fallback browser print-to-PDF nếu có cài |
| xhtml2pdf | Fallback cuối với Unicode font injection |
| pypdf preflight | Kiểm tra text extraction/mojibake/forbidden terms |

### 3. Fast report path

`generate_fast_report.py` thực hiện:

| Bước | Điều kiện |
|---|---|
| Kiểm tra snapshot | `latest_ready_snapshot(ticker)` phải tồn tại |
| Chọn run | Tìm run có `publishable_final_report_model` locked |
| Mode `client_final` | Chỉ lấy status `approved` và gọi `authorize_client_final` |
| Mode khác | Có thể dùng `approved` hoặc `auto_exported` tùy mode |
| Render local | Ghi `output/{TICKER}_fast_report.html` và `.pdf` |
| Workings | Tải `report_workings.md` nếu có |

Sau khi render report/explanation local, `post_render_audit.py` kiểm tra lỗi client-facing như thuật ngữ nội bộ, thiếu kỳ tài chính, bảng quá rộng, chart thiếu nguồn/takeaway, ảnh quá nhỏ, PDF clipping, font quá nhỏ và orphan page. Audit bổ sung display blockers; nó không thay đổi authorization token đã cấp.

Trong web flow hiện tại, `backend.reporting.report_delivery.render_and_store` render report và explanation vào thư mục tạm rồi upload lên Supabase Storage bucket `exports` theo key ổn định của ticker. Endpoint tải file ưu tiên đọc bản durable trong `exports`; nếu storage chưa cấu hình hoặc không có object, backend mới fallback sang `output/{TICKER}_report.pdf` và `output/{TICKER}_explanation.pdf`. Vì vậy khi viết đồ án, local output nên được gọi là bản render/cache phục vụ phát triển, không phải nguồn phân phối chính.

### 4. Approval boundary

| Status | Ý nghĩa |
|---|---|
| `auto_exported` | Hệ thống đã tạo publishable draft sau automatic gates |
| `approved` | Có phê duyệt cuối luồng phù hợp để render client-final |
| `blocked` | Thiếu artifact/gate hoặc có blocker |
| `failed` | Exception hoặc lỗi hạ tầng |

`auto_exported` không đồng nghĩa với báo cáo đã được chuyên gia phê duyệt.

### 5. Citation và claim policy

Report model phải có claim ledger và source refs cho claim trọng yếu. `CITATION_GATE`, `citation_coverage_gate`, source tier policy và Report quality cùng kiểm soát việc xuất bản. Generic citation, Tier-3-only material facts và unsupported numeric claims là blocker.

### 6. Report inventory cho frontend

Trang `/reports` đọc universe, run manifest, artifact metadata, export storage và local preview cache để tạo inventory. Backend ưu tiên manifest/storage lineage khi có; convention local `output/{TICKER}_report.pdf`, `output/{TICKER}_explanation.pdf` và `output/pdf_preview/{TICKER}_report_page_{n}.png` chỉ còn là fallback hiển thị. Client-final governance vẫn thuộc renderer/authorization path.

### 7. Trạng thái publishable sau nghiệm thu

| Phạm vi | Kết quả |
|---|---|
| MVP5 | DHG, IMP, DMC, TRA và DBD đều đạt `DRAFT_PUBLISHABLE` theo financial, citation, package, report-quality và snapshot-consistency gates |
| Report quality | Draft publishable report đạt score tối thiểu 85/100, không có blocker về valuation transparency hoặc citation quality |
| Evidence | Report model liên kết tới evidence packet, formula trace, claim ledger và source refs |
| Client-final | Vẫn yêu cầu approval fail-closed; không tự động biến draft thành final |

## Strategic Recommendations

| Rủi ro | Kiểm soát |
|---|---|
| Render nhầm artifact cũ | Dùng run manifest và locked report model |
| PDF lỗi tiếng Việt | Chuẩn hóa fonts và chạy PDF preflight |
| Draft bị hiểu là final | Tách status `auto_exported` và `approved` trong UI/API |
| Claim thiếu source | Block bằng citation/source provenance gates |
| Renderer quá chậm | Tái sử dụng artifact và chart cache nhưng không bỏ qua authorization |
