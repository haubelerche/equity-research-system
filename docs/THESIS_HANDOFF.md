# Thesis Handoff: Current Thesis Framing

Cập nhật: 2026-06-17

## Context

Dự án là một hệ thống hỗ trợ nghiên cứu cổ phiếu dược và y tế Việt Nam theo mô hình workflow có kiểm soát. Khi viết đồ án, nên mô tả hệ thống như một research workbench có dữ liệu truy vết, định giá tất định, tác tử LLM bị giới hạn bởi artifact đã khóa, và cổng kiểm định fail-closed. Không nên mô tả hệ thống như nền tảng tự động phát hành khuyến nghị đầu tư hoặc chatbot RAG đơn giản.

File này dùng để định hướng cách viết luận văn. Trạng thái định lượng mới nhất phải đối chiếu thêm với `CURRENT_STATE_AND_UPDATES.md`, `output/evaluation/eval_result/benchmark_suite/benchmark_suite.json` và các artifact theo `run_id`. Các câu nghiệm thu cũ như “toàn bộ hệ thống đạt 9/10” chỉ được dùng nếu có artifact cụ thể chứng minh đúng phạm vi đó.

## Current Thesis Scope

| Phạm vi | Cách trình bày trung thực |
|---|---|
| MVP5 | Dùng làm phạm vi phân tích sâu gồm DHG, IMP, DMC, TRA và DBD; đây là nhóm phù hợp nhất để giải thích pipeline, dữ liệu, định giá và báo cáo. |
| Universe 43 ticker | Dùng làm phạm vi mở rộng để chứng minh khả năng cấu hình universe và chạy benchmark/cohort; không mặc định mọi ticker có chất lượng báo cáo sâu như MVP5. |
| Local rendered reports | Có thể dùng làm bằng chứng giao diện/kết xuất cho một số ticker, nhưng phải gọi là local output hoặc dev cache nếu chưa gắn với export storage/approval. |
| Benchmark suite hiện hành | Dùng để chứng minh cơ chế đánh giá fail-closed; nếu aggregate báo `BLOCKED_BY_P0`, phải trình bày như phát hiện chất lượng đang tồn tại. |
| Client-final | Chỉ được gọi là final khi có phê duyệt và authorization fail-closed; `auto_exported` hoặc `DRAFT_PUBLISHABLE` chưa phải phê duyệt chuyên gia. |

## Recommended Thesis Narrative

| Nội dung chương | Khung diễn giải nên dùng |
|---|---|
| Vấn đề nghiên cứu | Dữ liệu công bố của doanh nghiệp niêm yết Việt Nam phân tán, định dạng không đồng nhất, khó truy vết và tốn nhiều công analyst. |
| Đóng góp kỹ thuật | Hệ thống kết hợp thu thập dữ liệu, chuẩn hóa facts, truy xuất bằng chứng, định giá bằng mã chương trình và sinh báo cáo bằng tác tử LLM có kiểm soát. |
| Đóng góp kiến trúc | Workflow cố định thay cho agent tự trị; LLM chỉ tham gia diễn giải, tổng hợp và phản biện, còn dữ liệu/định giá/gate là deterministic. |
| Đóng góp dữ liệu | Dữ liệu đi qua observation, canonical fact, snapshot, evidence index và manifest theo run, giúp báo cáo có thể truy ngược nguồn. |
| Đóng góp đánh giá | Hệ thống có project evaluation, benchmark suite, report quality, citation, financial và observability checks; các kết quả fail phải được giữ nguyên thay vì làm đẹp. |
| Đóng góp sản phẩm | Frontend có `/reports` và `/eval`, hỗ trợ xem báo cáo, tải file, chạy generate theo fast/full route và quan sát evaluation artifacts. |

## Evidence To Cite

| Loại bằng chứng | Nơi kiểm tra |
|---|---|
| Workflow và gate | `docs/WORKFLOW.md`, `backend/harness/runner.py`, `backend/harness/gates.py` |
| Dữ liệu và snapshot | `docs/SOURCES_AND_INGESTION.md`, `docs/DATA_ARCHITECTURE_ER.md`, `backend/dataops/` |
| Định giá | `docs/VALUATION.md`, `backend/analytics/`, `backend/valuation/peer_multiples.py` |
| Báo cáo và render | `docs/REPORTING.md`, `backend/reporting/`, `scripts/generate_fast_report.py` |
| Evaluation | `docs/EVALUATION_GATES.md`, `backend/evaluation/`, `scripts/run_project_evaluation.py`, `scripts/run_benchmark_suite.py` |
| Frontend | `frontend/src/`, `frontend/README.md`, `frontend/vercel.json` |

## Hard Boundaries

- Không nói hệ thống tự động đưa ra lời khuyên đầu tư cuối cùng; hệ thống tạo bản nháp nghiên cứu có bằng chứng để analyst rà soát.
- Không nói LLM là nguồn sự thật tài chính; valuation, reconciliation, sensitivity và recommendation reconciliation phải do code tính.
- Không gộp `DRAFT_PUBLISHABLE`, `auto_exported` và `client_final` làm một.
- Không dùng full-universe benchmark để khẳng định mọi ticker đạt chất lượng báo cáo như MVP5.
- Không che trạng thái `BLOCKED_BY_P0`; đây là bằng chứng hệ thống fail-closed và cần được diễn giải như phát hiện đánh giá.

## Commands For Reproduction

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest -q tests
npm.cmd run test --prefix frontend
python scripts/run_project_evaluation.py --ticker DHG
python scripts/run_benchmark_suite.py --cohort mvp5_validated
python scripts/run_benchmark_suite.py --cohort full_universe --reuse-existing
python scripts/audit_universe_report_readiness.py --include-db --write-json output/universe_report_readiness_db.json
```
