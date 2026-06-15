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
  englishLabel: string,
  unit: string,
  comparator: MetricDef["comparator"],
  threshold: number,
  technology: string,
  formula: string,
  options: Omit<Partial<MetricDef>, "id" | "label" | "englishLabel" | "unit" | "comparator" | "threshold" | "technology" | "formula"> = {},
): MetricDef => ({ id, label, englishLabel, unit, comparator, threshold, technology, formula, ...options });

export const EVAL_LAYERS: EvalLayer[] = [
  {
    id: "data_reliability",
    title: "1 · Chất lượng và độ tin cậy dữ liệu",
    subtitle: "Kiểm tra tính đầy đủ, nguồn gốc, đối soát và tính nhất quán của dữ liệu đầu vào",
    artifact: "data_quality.json",
    metrics: [
      metric("data_reliability_score", "Điểm tin cậy dữ liệu tổng hợp", "Data reliability score", "%", "gte", 0.9, "Pandera + Financial Fact Reconciliation + OCR Validation Gate", "Weighted score từ coverage, reconciliation, provenance, period completeness, schema validity, fact confidence và OCR health", { thresholdLabel: "≥ 90/100", metricType: "score", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("core_metric_coverage", "Độ bao phủ chỉ số cốt lõi", "Core metric coverage", "%", "gte", 0.95, "Valuation Data Requirements", "Số fact bắt buộc cho các phương pháp định giá có dữ liệu accepted / Tổng fact bắt buộc", { thresholdLabel: "≥ 95%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("valuation_method_data_readiness", "Mức sẵn sàng dữ liệu cho phương pháp định giá", "Valuation method data readiness", "", "gte", 1, "Valuation Data Requirements + Pandera", "Core metric coverage >= 95%, official reconciliation >= 95%, không có duplicate fact và Pandera schema hợp lệ", { thresholdLabel: "= true", metricType: "boolean", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("period_completeness", "Mức đầy đủ theo kỳ bắt buộc", "Required periods completeness", "%", "gte", 1, "Data Quality Framework nội bộ", "Số kỳ bắt buộc có dữ liệu / Tổng số kỳ bắt buộc", { aliases: ["required_periods_completeness"], thresholdLabel: "= 100%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("provenance_coverage", "Độ bao phủ nguồn cho accepted facts", "Accepted facts source coverage", "%", "gte", 1, "Evidence Packet + Source Registry", "Số accepted facts có source_id hợp lệ / Tổng accepted facts dùng trong report", { aliases: ["source_provenance_coverage", "accepted_facts_source_coverage"], thresholdLabel: "= 100%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("official_reconciliation_rate", "Tỷ lệ đối soát dữ kiện trọng yếu với nguồn chính thức", "Material official reconciliation rate", "%", "gte", 0.95, "Financial Fact Reconciliation", "Số dữ kiện trọng yếu khớp nguồn chính thức / Tổng dữ kiện trọng yếu cần đối soát", { thresholdLabel: "≥ 95%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("material_ocr_error_count", "Số lỗi OCR ảnh hưởng số liệu trọng yếu", "Material OCR error count", "", "lte", 0, "OCR Validation Gate", "Số lỗi OCR ảnh hưởng số liệu dùng trong report", { aliases: ["ocr_material_error_count"], thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("ocr_unresolved_rate", "Tỷ lệ lỗi OCR toàn corpus chưa xử lý", "Corpus OCR unresolved rate", "%", "lte", 0.05, "OCR Validation Gate", "Số lỗi OCR chưa xử lý / Tổng đơn vị OCR kiểm tra", { thresholdLabel: "≤ 5%", metricType: "error_rate", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("duplicate_fact_count", "Số canonical fact trùng lặp chưa xử lý", "Duplicate canonical fact count", "", "lte", 0, "Fact Deduplication Gate", "Số fact chuẩn hóa bị trùng key ticker-period-line_item-source_priority", { aliases: ["duplicate_fact_rate"], thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
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
      metric("hit_rate_at_5", "Tỷ lệ truy vấn có bằng chứng đúng trong top 5", "Hit-rate@5", "%", "gte", 0.9, "Golden Retrieval Set", "Số truy vấn có ít nhất một evidence đúng trong top 5 / Tổng số truy vấn", { thresholdLabel: "≥ 90%", metricType: "coverage", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("mrr_at_5", "Thứ hạng nghịch đảo trung bình trong top 5", "MRR@5", "", "gte", 0.75, "Golden Retrieval Set", "Trung bình nghịch đảo thứ hạng của evidence đúng đầu tiên trong top 5", { thresholdLabel: "≥ 0.75", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("context_precision", "Độ chính xác của ngữ cảnh truy xuất", "Context Precision", "", "gte", 0.8, "Ragas", "Tỷ lệ context retrieved thực sự liên quan", { thresholdLabel: "≥ 0.80", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("context_recall", "Độ bao phủ bằng chứng cần thiết", "Context Recall", "", "gte", 0.8, "Ragas", "Tỷ lệ bằng chứng cần thiết được retrieve", { thresholdLabel: "≥ 0.80", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("faithfulness", "Mức độ bám sát bằng chứng", "Faithfulness", "", "gte", 0.85, "Ragas", "Điểm nội dung bám evidence", { thresholdLabel: "≥ 0.85", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("response_relevancy", "Mức độ đúng trọng tâm câu trả lời", "Response Relevancy", "", "gte", 0.85, "Ragas", "Điểm câu trả lời đúng trọng tâm truy vấn", { thresholdLabel: "≥ 0.85", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("source_tier_hit_rate", "Tỷ lệ truy vấn trọng yếu có nguồn ưu tiên trong top-k", "Source-tier hit rate", "%", "gte", 0.9, "Source-tier Retrieval Audit", "Số truy vấn trọng yếu có nguồn cấp ưu tiên trong top-k / Tổng truy vấn trọng yếu", { thresholdLabel: "≥ 90%", metricType: "coverage", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
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
      metric("accounting_invariant_violations", "Số vi phạm bất biến kế toán nghiêm trọng", "Critical accounting invariant violations", "", "lte", 0, "Deterministic Finance Gates", "Số lỗi như tài sản không khớp nợ phải trả cộng vốn chủ sở hữu hoặc cash flow không khớp biến động tiền", { aliases: ["critical_failures"], thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("fcff", "Số mã đạt công thức FCFF", "FCFF formula pass count", "", "gte", 10, "DCF Formula Gate", "FCFF = EBIT(1-tax) + D&A - CAPEX - delta NWC cho từng forecast row", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("fcfe", "Số mã đạt công thức FCFE", "FCFE formula pass count", "", "gte", 10, "FCFE Formula Gate", "FCFE = NI + D&A - CAPEX - delta NWC + net borrowing cho từng forecast row", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("target_price", "Số mã tái lập được giá mục tiêu", "Target price reproduction pass count", "", "gte", 10, "Valuation Bridge Reconciliation", "Target price phải tái lập được từ equity value và share count trong valuation artifact", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("gordon_growth", "Số mã đạt điều kiện Gordon Growth", "Gordon growth pass count", "", "gte", 10, "DCF Formula Gate", "Discount rate phải lớn hơn terminal growth", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("net_debt", "Số mã đối chiếu đúng nợ ròng", "Net debt reconciliation pass count", "", "gte", 10, "Net Debt Reconciliation", "Net debt = total debt - cash - short-term investments", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("sensitivity_varies", "Số mã có ma trận FCFF sensitivity biến thiên", "FCFF sensitivity variation pass count", "", "gte", 10, "Sensitivity Gate", "Ma trận FCFF WACC/g phải có nhiều hơn một giá trị hợp lệ", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("fcfe_sensitivity", "Số mã có ma trận FCFE sensitivity biến thiên", "FCFE sensitivity variation pass count", "", "gte", 10, "Sensitivity Gate", "Ma trận FCFE Re/g phải có nhiều hơn một giá trị hợp lệ hoặc được block rõ ràng theo artifact", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("blend_sensitivity", "Số mã có ma trận blend sensitivity biến thiên", "Blend sensitivity variation pass count", "", "gte", 10, "Sensitivity Gate", "Ma trận blend chỉ đạt khi FCFF và FCFE đều publishable và grid biến thiên", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("sensitivity_base_cell", "Số mã có ô base sensitivity khớp target", "Sensitivity base-cell reconciliation pass count", "", "gte", 10, "Sensitivity Gate", "Ô base của FCFF, FCFE và blend sensitivity phải khớp target tương ứng trong tolerance", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("formula_trace", "Số mã có formula trace", "Formula trace availability pass count", "", "gte", 10, "Formula Trace Audit", "Valuation artifact phải có trace công thức deterministic cho các phương pháp định giá", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("golden_drift_out_of_tolerance", "Số lỗi drift so với golden valuation fixture", "Golden valuation drift out of tolerance", "", "lte", 0, "Golden Valuation Regression", "Số case valuation fixture bị drift ngoài tolerance; not_evaluable nếu chưa có fixture", { aliases: ["valuation_regression_failures"], thresholdLabel: "= 0", metricType: "error_count", scope: "benchmark_suite", severity: "P0", blocksPublish: true }),
      metric("valuation_publishable", "Số mã đủ điều kiện publish valuation", "Valuation publishability pass count", "", "gte", 10, "Valuation Publishability Policy", "Policy chỉ pass khi primary method đủ confidence, bridge/sensitivity đầy đủ và không có divergence hoặc market-sanity blocker", { thresholdLabel: "pass", metricType: "coverage", scope: "release_gate", severity: "P0", blocksPublish: true }),
      metric("target_price_bridge_error", "Số lỗi cầu nối EV, equity value hoặc giá mục tiêu", "Target price bridge error", "", "lte", 0, "Valuation Bridge Reconciliation", "Số case không tái lập được target price từ valuation artifact", { aliases: ["valuation_bridge_error"], thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("wacc_terminal_growth_violation", "Số case WACC nhỏ hơn hoặc bằng tăng trưởng dài hạn", "WACC terminal growth violation", "", "lte", 0, "DCF Formula Gate", "Số case WACC <= terminal growth trong DCF", { thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("net_debt_reconciliation_error", "Số lỗi đối chiếu nợ ròng", "Net debt reconciliation error", "", "lte", 0, "Net Debt Reconciliation", "Số case nợ ròng không khớp công thức chuẩn", { thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
    ],
    methodology: [
      "Net debt = interest-bearing debt − cash − short-term investments.",
      "EPS = net income × 1.000 / diluted shares; FCFF = EBIT(1−tax) + D&A − CAPEX − ΔNWC.",
      "FCFE = NI + D&A − CAPEX − ΔNWC + net borrowing; discount rate phải lớn hơn terminal growth.",
      "Giá mục tiêu, cầu nối EV sang vốn chủ sở hữu và ma trận độ nhạy phải nhất quán với mô hình định giá.",
    ],
  },
  {
    id: "agent",
    title: "4 · Hiệu quả Agent và LLM Judge",
    subtitle: "Đánh giá tuân thủ vai trò, quyền công cụ, cấu trúc đầu ra và chất lượng lập luận",
    artifact: "agent_eval.json",
    metrics: [
      metric("tool_permission_compliance", "Tỷ lệ tuân thủ quyền sử dụng công cụ", "Tool permission compliance", "%", "gte", 1, "Agent Tool Permission Gate", "Số lượt gọi công cụ đúng quyền / Tổng lượt gọi công cụ", { thresholdLabel: "= 100%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("schema_validity", "Tỷ lệ cấu trúc JSON đầu ra hợp lệ", "JSON schema validity", "%", "gte", 1, "JSON Schema Validator", "Số output hợp lệ theo schema / Tổng output bắt buộc", { thresholdLabel: "= 100%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("no_unauthorized_calc", "Tỷ lệ không tự ý tính toán tài chính bằng LLM", "No unauthorized LLM financial calculation", "%", "gte", 1, "Agent Governance Gate", "Số lượt tuân thủ quy tắc / Tổng lượt cần kiểm tra", { thresholdLabel: "= 100%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("role_adherence", "Điểm tuân thủ vai trò", "Role adherence", "", "gte", 0.85, "DeepEval", "Điểm LLM Judge cho mức tuân thủ vai trò", { thresholdLabel: "≥ 0.85", metricType: "score", scope: "report_run", severity: "P2", blocksPublish: false }),
      metric("groundedness", "Điểm kết luận có căn cứ", "Groundedness judge score", "", "gte", 0.85, "DeepEval", "Điểm LLM Judge về mức kết luận có căn cứ", { thresholdLabel: "≥ 0.85", metricType: "score", scope: "report_run", severity: "P2", blocksPublish: false }),
      metric("task_completion", "Điểm hoàn thành nhiệm vụ", "Task completion", "", "gte", 0.85, "DeepEval", "Điểm hoàn thành yêu cầu bắt buộc", { thresholdLabel: "≥ 0.85", metricType: "score", scope: "report_run", severity: "P2", blocksPublish: false }),
      metric("plan_adherence", "Điểm tuân thủ kế hoạch", "Plan compliance", "", "gte", 0.8, "DeepEval", "Điểm thực hiện đúng kế hoạch", { thresholdLabel: "≥ 0.80", metricType: "score", scope: "report_run", severity: "P2", blocksPublish: false }),
      metric("critic_issue_recall", "Tỷ lệ phát hiện lỗi được cài trước", "Seeded issue detection", "%", "gte", 0.9, "Seeded Issue Evaluation", "Số lỗi cài trước được phát hiện / Tổng lỗi cài trước", { thresholdLabel: "≥ 90%", metricType: "coverage", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
    ],
    methodology: [
      "LLM Judge sử dụng rubric cố định; điểm cao không được ghi đè lỗi tất định hoặc vi phạm quản trị.",
      "Seeded Issue Evaluation đo khả năng Agent phản biện phát hiện các lỗi đã được chủ động cài vào bộ kiểm thử.",
    ],
  },
  {
    id: "observability",
    title: "5 · Vận hành, chi phí và độ trễ",
    subtitle: "Theo dõi độ ổn định, phương án dự phòng và lỗi trong quá trình tạo báo cáo",
    artifact: "observability_eval.json",
    metrics: [
      metric("llm_retry_rate", "Tỷ lệ gọi LLM phải thử lại", "LLM retry rate", "%", "lte", 0.05, "Langfuse Tracing", "Số lượt gọi LLM phải retry / Tổng lượt gọi LLM", { thresholdLabel: "≤ 5%", metricType: "error_rate", scope: "system_window", severity: "P3", blocksPublish: false }),
      metric("retrieval_fallback_rate", "Tỷ lệ truy xuất dùng fallback", "Retrieval fallback rate", "%", "lte", 0.2, "Retrieval Telemetry", "Số truy vấn dùng fallback / Tổng truy vấn retrieval", { thresholdLabel: "≤ 20%", metricType: "error_rate", scope: "system_window", severity: "P2", blocksPublish: false }),
      metric("ocr_failure_rate", "Tỷ lệ OCR thất bại trên tài liệu trọng yếu", "Material OCR failure rate", "%", "lte", 0.05, "OCR Runtime Metrics", "Số tài liệu OCR trọng yếu thất bại / Tổng tài liệu OCR trọng yếu", { thresholdLabel: "≤ 5%", metricType: "error_rate", scope: "system_window", severity: "P1", blocksPublish: true }),
      metric("final_ocr_error_count", "Số lỗi OCR ảnh hưởng số liệu final", "Final numeric OCR error count", "", "lte", 0, "OCR Final Artifact Gate", "Số lỗi OCR làm sai số liệu trong final report", { thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("artifact_upload_failures", "Số lỗi upload artifact cuối", "Final artifact upload failure", "", "lte", 0, "Artifact Storage Gate", "Số artifact cuối tải lên thất bại", { thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("pdf_render_failures", "Số lỗi render PDF cuối", "Final PDF render failure", "", "lte", 0, "PDF Render Gate", "Số lần render PDF cuối thất bại", { thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("warm_full_report_p95_latency", "Độ trễ p95 full report khi warm run", "Full report p95 latency, warm run", "phút", "lte", 10, "Runtime Latency Window", "p95 thời gian tạo full report khi dữ liệu/artifact đã có sẵn", { aliases: ["full_run_duration"], thresholdLabel: "≤ 10 phút", metricType: "latency_percentile", scope: "system_window", severity: "P3", blocksPublish: false }),
      metric("cold_full_report_p95_latency", "Độ trễ p95 full report khi cold run", "Full report p95 latency, cold run", "phút", "lte", 30, "Runtime Latency Window", "p95 thời gian tạo full report khi cần ingest/OCR/xử lý lại", { thresholdLabel: "≤ 30 phút", metricType: "latency_percentile", scope: "system_window", severity: "P3", blocksPublish: false }),
      metric("render_only_p95_latency", "Độ trễ p95 dựng PDF từ artifact đã khóa", "Render-only p95 latency", "phút", "lte", 2, "PDF Render Telemetry", "p95 thời gian dựng PDF từ artifact đã khóa", { thresholdLabel: "≤ 2 phút", metricType: "latency_percentile", scope: "system_window", severity: "P1", blocksPublish: true }),
      metric("flash_memo_warm_p95_latency", "Độ trễ p95 flash memo khi warm run", "Flash memo p95 latency, warm run", "giây", "lte", 90, "Runtime Latency Window", "p95 thời gian tạo flash memo khi dữ liệu đã có sẵn", { thresholdLabel: "≤ 90 giây", metricType: "latency_percentile", scope: "system_window", severity: "P3", blocksPublish: false }),
      metric("flash_memo_cold_retrieval_p95_latency", "Độ trễ p95 flash memo khi cần retrieval", "Flash memo p95 latency, cold retrieval", "phút", "lte", 3, "Runtime Latency Window", "p95 thời gian tạo flash memo khi cần retrieval/crawl thêm", { thresholdLabel: "≤ 3 phút", metricType: "latency_percentile", scope: "system_window", severity: "P3", blocksPublish: false }),
      metric("latency_regression_ratio", "Tỷ lệ hồi quy độ trễ so với baseline", "Latency regression", "", "lte", 1.25, "Latency Regression Gate", "p95 mới / p95 baseline", { thresholdLabel: "≤ 1.25x", metricType: "score", scope: "benchmark_suite", severity: "P3", blocksPublish: false }),
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
