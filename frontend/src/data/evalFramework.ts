import type { MetricDef } from "../lib/evalStatus";

export interface EvalLayer {
  id: string;
  title: string;
  subtitle: string;
  artifact: string;
  metrics: MetricDef[];
  methodology: string[];
}

const metric = (
  id: string,
  label: string,
  unit: string,
  comparator: MetricDef["comparator"],
  threshold: number,
  technology: string,
  formula: string,
): MetricDef => ({ id, label, unit, comparator, threshold, technology, formula });

export const EVAL_LAYERS: EvalLayer[] = [
  {
    id: "data_reliability",
    title: "1 · Chất lượng và độ tin cậy dữ liệu",
    subtitle: "Kiểm tra tính đầy đủ, nguồn gốc, đối soát và tính nhất quán của dữ liệu đầu vào",
    artifact: "data_quality.json",
    metrics: [
      metric("core_metric_coverage", "Độ bao phủ chỉ số cốt lõi", "%", "gte", 0.95, "Data Quality Framework nội bộ", "Số chỉ số cốt lõi có dữ liệu hợp lệ / Tổng số chỉ số cốt lõi bắt buộc"),
      metric("period_completeness", "Mức đầy đủ theo kỳ", "%", "gte", 1, "Data Quality Framework nội bộ", "Số kỳ báo cáo đầy đủ / Tổng số kỳ báo cáo bắt buộc"),
      metric("provenance_coverage", "Độ bao phủ nguồn gốc dữ liệu", "%", "gte", 1, "Evidence Packet + Source Registry", "Số dữ kiện có source_id hợp lệ / Tổng số dữ kiện"),
      metric("official_reconciliation_rate", "Tỷ lệ đối soát với nguồn chính thức", "%", "gte", 0.95, "Financial Fact Reconciliation", "Số dữ kiện khớp nguồn chính thức / Tổng số dữ kiện cần đối soát"),
      metric("ocr_unresolved_rate", "Tỷ lệ lỗi OCR chưa xử lý", "%", "lte", 0, "OCR Validation Gate", "Số lỗi OCR chưa xử lý / Tổng số dữ kiện OCR"),
      metric("duplicate_fact_rate", "Tỷ lệ dữ kiện trùng lặp", "%", "lte", 0, "Fact Deduplication Gate", "Số dữ kiện trùng lặp / Tổng số dữ kiện"),
    ],
    methodology: [
      "Dữ liệu chỉ được xem là đạt khi không còn lỗi OCR hoặc dữ kiện trùng lặp chưa xử lý.",
      "Nguồn gốc dữ liệu phải truy xuất được tới Source Registry và tài liệu bằng chứng tương ứng.",
    ],
  },
  {
    id: "rag_evidence",
    title: "2 · RAG",
    subtitle: "Đánh giá chất lượng truy xuất và mức độ bám sát bằng chứng của câu trả lời",
    artifact: "retrieval_eval.json",
    metrics: [
      metric("hit_rate_at_5", "Hit-rate@5", "%", "gte", 0.9, "Golden Retrieval Set", "Số truy vấn có tài liệu đúng trong 5 kết quả đầu / Tổng số truy vấn"),
      metric("mrr_at_5", "MRR@5", "", "gte", 0.8, "Golden Retrieval Set", "Trung bình nghịch đảo thứ hạng của tài liệu đúng trong 5 kết quả đầu"),
      metric("context_precision", "Context Precision", "", "gte", 0.85, "Ragas", "Tỷ lệ ngữ cảnh được truy xuất thực sự liên quan tới câu hỏi"),
      metric("context_recall", "Context Recall", "", "gte", 0.85, "Ragas", "Tỷ lệ thông tin cần thiết trong đáp án chuẩn xuất hiện trong ngữ cảnh truy xuất"),
      metric("faithfulness", "Faithfulness", "", "gte", 0.85, "Ragas", "Tỷ lệ luận điểm trong phản hồi được hỗ trợ bởi ngữ cảnh truy xuất"),
      metric("response_relevancy", "Response Relevancy", "", "gte", 0.85, "Ragas", "Mức độ phản hồi trực tiếp và phù hợp với câu hỏi"),
    ],
    methodology: [
      "Golden Retrieval Set đo khả năng tìm đúng tài liệu đã được chuyên gia xác nhận.",
      "Ragas đánh giá tự động chất lượng ngữ cảnh và câu trả lời dựa trên tập câu hỏi chuẩn.",
    ],
  },
  {
    id: "financial",
    title: "3 · Tính chính xác của mô hình tài chính",
    subtitle: "Kiểm tra tất định các công thức, bất biến kế toán và sai lệch định giá",
    artifact: "financial_eval.json",
    metrics: [
      metric("critical_failures", "Số bất biến tài chính nghiêm trọng bị vi phạm", "", "lte", 0, "Deterministic Finance Gates", "Tổng số kiểm tra tài chính mức critical không đạt"),
      metric("golden_drift_out_of_tolerance", "Số kết quả định giá chuẩn sai lệch vượt ngưỡng", "", "lte", 0, "Golden Valuation Regression", "Tổng số kết quả định giá lệch khỏi bộ chuẩn vượt dung sai cho phép"),
    ],
    methodology: [
      "Net debt = interest-bearing debt − cash − short-term investments.",
      "EPS = net income × 1.000 / diluted shares; FCFF = EBIT(1−tax) + D&A − CAPEX − ΔNWC.",
      "FCFE = NI + D&A − CAPEX − ΔNWC + net borrowing; discount rate phải lớn hơn terminal growth.",
      "Giá mục tiêu, cầu nối EV sang vốn chủ sở hữu và ma trận độ nhạy phải nhất quán với mô hình định giá.",
    ],
  },
  {
    id: "citation",
    title: "4 · Trích dẫn và nguồn bằng chứng",
    subtitle: "Kiểm tra độ bao phủ, tính hợp lệ và độ chính xác của trích dẫn",
    artifact: "citation_eval.json",
    metrics: [
      metric("quant_citation_coverage", "Độ bao phủ trích dẫn định lượng", "%", "gte", 1, "Citation Coverage Evaluator", "Số luận điểm định lượng có trích dẫn / Tổng số luận điểm định lượng"),
      metric("citation_key_resolution", "Tỷ lệ khóa trích dẫn phân giải thành công", "%", "gte", 1, "Citation Resolver", "Số khóa trích dẫn phân giải được / Tổng số khóa trích dẫn"),
      metric("source_id_validity", "Tỷ lệ mã nguồn hợp lệ", "%", "gte", 1, "Source Registry Validator", "Số source_id hợp lệ / Tổng số source_id"),
      metric("official_source_coverage", "Độ bao phủ nguồn chính thức cho số liệu trọng yếu", "%", "gte", 1, "Source Tier Policy", "Số số liệu trọng yếu có nguồn chính thức / Tổng số số liệu trọng yếu"),
      metric("numeric_mismatch_rate", "Tỷ lệ số liệu trích dẫn sai lệch", "%", "lte", 0, "Numeric Citation Reconciliation", "Số số liệu không khớp bằng chứng / Tổng số số liệu được trích dẫn"),
      metric("tier3_only_material_claims", "Luận điểm trọng yếu chỉ dựa vào nguồn cấp 3", "", "lte", 0, "Source Tier Policy", "Số luận điểm trọng yếu chỉ có nguồn cấp 3"),
      metric("generic_citations", "Nhãn trích dẫn chung chung", "", "lte", 0, "Citation Label Validator", "Số trích dẫn không xác định được tài liệu cụ thể"),
      metric("catalyst_without_evidence", "Sự kiện xúc tác thiếu đoạn bằng chứng", "", "lte", 0, "Catalyst Evidence Gate", "Số sự kiện xúc tác không có evidence span"),
    ],
    methodology: [
      "Mọi luận điểm định lượng và luận điểm trọng yếu phải truy xuất được tới bằng chứng cụ thể.",
      "Nguồn cấp 3 không đủ điều kiện làm nguồn duy nhất cho luận điểm trọng yếu.",
    ],
  },
  {
    id: "agent",
    title: "5 · Hiệu quả Agent và LLM Judge",
    subtitle: "Đánh giá tuân thủ vai trò, quyền công cụ, cấu trúc đầu ra và chất lượng lập luận",
    artifact: "agent_eval.json",
    metrics: [
      metric("tool_permission_compliance", "Tuân thủ quyền sử dụng công cụ", "%", "gte", 1, "Agent Tool Permission Gate", "Số hành động công cụ đúng quyền / Tổng số hành động công cụ"),
      metric("schema_validity", "Tỷ lệ cấu trúc đầu ra hợp lệ", "%", "gte", 1, "JSON Schema Validator", "Số đầu ra hợp lệ theo schema / Tổng số đầu ra"),
      metric("no_unauthorized_calc", "Không tự ý thực hiện tính toán tài chính", "%", "gte", 1, "Agent Governance Gate", "Số lượt tuân thủ quy tắc tính toán / Tổng số lượt cần kiểm tra"),
      metric("role_adherence", "Mức tuân thủ vai trò", "", "gte", 0.9, "LLM Judge Rubric", "Điểm LLM Judge cho mức tuân thủ phạm vi và trách nhiệm của vai trò"),
      metric("groundedness", "Tính có căn cứ của nội dung cuối", "", "gte", 0.9, "LLM Judge + Evidence Check", "Điểm phản ánh mức độ các kết luận được hỗ trợ bởi bằng chứng"),
      metric("task_completion", "Mức hoàn thành nhiệm vụ", "", "gte", 0.85, "LLM Judge Rubric", "Điểm hoàn thành các yêu cầu bắt buộc của nhiệm vụ"),
      metric("plan_adherence", "Mức tuân thủ kế hoạch", "", "gte", 0.85, "LLM Judge Rubric", "Điểm thực hiện đúng các bước và ràng buộc của kế hoạch"),
      metric("critic_issue_recall", "Tỷ lệ phát hiện vấn đề được cài trước", "%", "gte", 0.9, "Seeded Issue Evaluation", "Số vấn đề cài trước được phát hiện / Tổng số vấn đề cài trước"),
    ],
    methodology: [
      "LLM Judge sử dụng rubric cố định; điểm cao không được ghi đè lỗi tất định hoặc vi phạm quản trị.",
      "Seeded Issue Evaluation đo khả năng Agent phản biện phát hiện các lỗi đã được chủ động cài vào bộ kiểm thử.",
    ],
  },
  {
    id: "report_quality",
    title: "6 · Chất lượng báo cáo đầu tư",
    subtitle: "Đánh giá mức hoàn thiện, tính nhất quán và điều kiện xuất bản báo cáo",
    artifact: "report_eval.json",
    metrics: [
      metric("report_quality_score", "Điểm chất lượng báo cáo", "", "gte", 85, "Report Quality Rubric", "Tổng điểm có trọng số cho luận điểm đầu tư, định giá, rủi ro và trình bày"),
    ],
    methodology: [
      "Báo cáo phải đạt tối thiểu 85/100 và vượt qua toàn bộ cổng tài chính, trích dẫn và xuất bản.",
      "Báo cáo không được công bố nếu snapshot định giá không khớp hoặc chưa có phê duyệt cuối.",
    ],
  },
  {
    id: "observability",
    title: "7 · Vận hành, chi phí và độ trễ",
    subtitle: "Theo dõi độ ổn định, phương án dự phòng và lỗi trong quá trình tạo báo cáo",
    artifact: "observability_eval.json",
    metrics: [
      metric("llm_retry_rate", "Tỷ lệ LLM phải thử lại", "%", "lte", 0.05, "Langfuse Tracing", "Số lần gọi LLM phải thử lại / Tổng số lần gọi LLM"),
      metric("retrieval_fallback_rate", "Tỷ lệ truy xuất dùng phương án dự phòng", "%", "lte", 0.2, "Retrieval Telemetry", "Số truy vấn dùng phương án dự phòng / Tổng số truy vấn"),
      metric("ocr_failure_rate", "Tỷ lệ lỗi OCR trọng yếu", "%", "lte", 0.05, "OCR Runtime Metrics", "Số tài liệu OCR trọng yếu thất bại / Tổng số tài liệu OCR trọng yếu"),
      metric("artifact_upload_failures", "Số lỗi tải artifact cuối lên hệ thống", "", "lte", 0, "Artifact Storage Gate", "Tổng số artifact cuối tải lên thất bại"),
      metric("pdf_render_failures", "Số lỗi render PDF cuối", "", "lte", 0, "PDF Render Gate", "Tổng số lần render PDF cuối thất bại"),
    ],
    methodology: [
      "Langfuse cung cấp trace về lượt gọi LLM, token, chi phí, độ trễ và số lần thử lại.",
      "Bản cuối chỉ được xuất khi không còn lỗi tải artifact hoặc lỗi render PDF.",
    ],
  },
];

export const PIPELINE_ORDER: string[] = [
  "Chất lượng dữ liệu",
  "RAG",
  "Mô hình tài chính",
  "Trích dẫn",
  "Agent và LLM Judge",
  "Chất lượng báo cáo",
  "Kiểm soát xuất bản",
];

export const ACCEPTANCE_EXPLANATION: string[] = [
  "Bảng sử dụng một bộ ngưỡng chuẩn dành cho bản vận hành chính thức; P0, P1 và P2 đã được loại bỏ để tránh tạo trạng thái trung gian không phục vụ quyết định.",
  "Chỉ số dùng điều kiện ≥ sẽ Chưa đạt khi thấp hơn ngưỡng; chỉ số dùng điều kiện ≤ sẽ Chưa đạt khi cao hơn ngưỡng.",
  "Thiếu dữ liệu benchmark được xem là Chưa đạt vì hệ thống không có đủ bằng chứng để xác nhận chất lượng.",
];
