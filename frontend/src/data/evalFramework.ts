import type { MetricDef } from "../lib/evalStatus";

export interface EvalLayer {
  id: string;
  title: string;
  subtitle: string;
  artifact: string;
  artifactAliases?: string[];
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
  options: Omit<
    Partial<MetricDef>,
    "id" | "label" | "englishLabel" | "unit" | "comparator" | "threshold" | "technology" | "formula"
  > = {},
): MetricDef => ({ id, label, englishLabel, unit, comparator, threshold, technology, formula, ...options });

export const EVAL_LAYERS: EvalLayer[] = [
  {
    id: "data_reliability",
    title: "1 · Chất lượng và độ tin cậy dữ liệu",
    subtitle: "Kiểm tra tính đầy đủ, nguồn gốc, đối soát và tính nhất quán của dữ liệu đầu vào",
    artifact: "data_quality.json",
    metrics: [
      metric("data.benchmark_hardness_score", "Điểm chất lượng dữ liệu (chuẩn hoá độ khó)", "Data quality (difficulty-adjusted)", "%", "gte", 0.85, "Hard-mode Data Reliability Audit", "Weighted stress score phat confidence thap, lineage/OCR depth yeu, raw BCTC thieu file hoac provenance chua sau", { thresholdLabel: ">= 85%", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("data_reliability_score", "Điểm tin cậy dữ liệu tổng hợp", "Data reliability score", "%", "gte", 0.9, "Pandera + Financial Fact Reconciliation + OCR Validation Gate", "Weighted score từ coverage, reconciliation, provenance, period completeness, schema validity, fact confidence và OCR health", { thresholdLabel: "≥ 90%", metricType: "score", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("core_metric_coverage", "Độ bao phủ chỉ số cốt lõi", "Core metric coverage", "%", "gte", 0.95, "Valuation Data Requirements", "Số fact bắt buộc cho các phương pháp định giá có dữ liệu accepted / Tổng fact bắt buộc", { thresholdLabel: "≥ 95%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("valuation_method_data_readiness", "Mức sẵn sàng dữ liệu cho phương pháp định giá", "Valuation method data readiness", "%", "gte", 0.8, "Valuation Data Requirements + Pandera", "Tỷ lệ mã đủ dữ liệu cho ít nhất một phương pháp định giá chính", { thresholdLabel: "≥ 80%", metricType: "coverage", scope: "benchmark_suite", severity: "P1", blocksPublish: false }),
      metric("period_completeness", "Mức đầy đủ theo kỳ bắt buộc", "Required periods completeness", "%", "gte", 0.95, "Data Quality Framework nội bộ", "Số kỳ bắt buộc có dữ liệu / Tổng số kỳ bắt buộc", { aliases: ["required_periods_completeness"], thresholdLabel: "≥ 95%", metricType: "coverage", scope: "benchmark_suite", severity: "P1", blocksPublish: false }),
      metric("provenance_coverage", "Độ bao phủ nguồn cho accepted facts", "Accepted facts source coverage", "%", "gte", 0.95, "Evidence Packet + Source Registry", "Số accepted facts có source_id hợp lệ / Tổng accepted facts dùng trong report", { aliases: ["source_provenance_coverage", "accepted_facts_source_coverage"], thresholdLabel: "≥ 95%", metricType: "coverage", scope: "benchmark_suite", severity: "P1", blocksPublish: false }),
      metric("official_reconciliation_rate", "Tỷ lệ đối soát dữ kiện trọng yếu với nguồn chính thức", "Material official reconciliation rate", "%", "gte", 0.95, "Financial Fact Reconciliation", "Số dữ kiện trọng yếu khớp nguồn chính thức / Tổng dữ kiện trọng yếu cần đối soát", { thresholdLabel: "≥ 95%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("material_ocr_error_count", "Số lỗi OCR ảnh hưởng số liệu trọng yếu", "Material OCR error count", "", "lte", 0, "OCR Validation Gate", "Số lỗi OCR ảnh hưởng số liệu dùng trong report", { aliases: ["ocr_material_error_count"], thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
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
      metric("rag.retrieval_difficulty_score", "Điểm chất lượng truy xuất", "Retrieval quality score", "%", "gte", 0.85, "Hard-mode Golden Retrieval Audit", "Weighted stress score uu tien first-rank authoritative hit, source-tier match, MRR@5, query density va material query share", { thresholdLabel: ">= 85%", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("hit_rate_at_5", "Tỷ lệ truy vấn có bằng chứng đúng trong top 5", "Hit-rate@5", "%", "gte", 0.9, "Golden Retrieval Set", "Số truy vấn có ít nhất một evidence đúng trong top 5 / Tổng số truy vấn", { thresholdLabel: "≥ 90%", metricType: "coverage", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("mrr_at_5", "Thứ hạng nghịch đảo trung bình trong top 5", "MRR@5", "%", "gte", 0.75, "Golden Retrieval Set", "Trung bình nghịch đảo thứ hạng của evidence đúng đầu tiên trong top 5", { thresholdLabel: "≥ 75%", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("context_precision", "Độ chính xác của ngữ cảnh truy xuất", "Context Precision", "%", "gte", 0.8, "Ragas", "Tỷ lệ context retrieved thực sự liên quan", { thresholdLabel: "≥ 80%", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("context_recall", "Độ bao phủ bằng chứng cần thiết", "Context Recall", "%", "gte", 0.8, "Ragas", "Tỷ lệ bằng chứng cần thiết được retrieve", { thresholdLabel: "≥ 80%", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("faithfulness", "Mức độ bám sát bằng chứng", "Faithfulness", "%", "gte", 0.85, "Ragas", "Điểm nội dung bám evidence", { thresholdLabel: "≥ 85%", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("response_relevancy", "Mức độ đúng trọng tâm câu trả lời", "Response Relevancy", "%", "gte", 0.75, "Ragas", "Điểm câu trả lời đúng trọng tâm truy vấn", { thresholdLabel: "≥ 75%", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
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
      metric("finance.model_quality_score", "Điểm chất lượng mô hình tài chính", "Financial model quality score", "%", "gte", 0.75, "Hard-mode Financial Model Audit", "Weighted stress score phat method publishability thap, trace method thieu, sensitivity grid mong, forecast horizon ngan hoac khong co golden regression", { thresholdLabel: ">= 75%", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("accounting_invariant_violations", "Số vi phạm bất biến kế toán nghiêm trọng", "Critical accounting invariant violations", "", "lte", 0, "Deterministic Finance Gates", "Số lỗi như tài sản không khớp nợ phải trả cộng vốn chủ sở hữu hoặc cash flow không khớp biến động tiền", { aliases: ["critical_failures"], thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("fcff", "Số mã đạt công thức FCFF", "FCFF formula pass count", "", "gte", 10, "DCF Formula Gate", "FCFF = EBIT(1-tax) + D&A - CAPEX - delta NWC cho từng forecast row", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("fcfe", "Số mã đạt công thức FCFE", "FCFE formula pass count", "", "gte", 10, "FCFE Formula Gate", "FCFE = NI + D&A - CAPEX - delta NWC + net borrowing cho từng forecast row", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("target_price", "Số mã tái lập được giá mục tiêu", "Target price reproduction pass count", "", "gte", 10, "Valuation Bridge Reconciliation", "Target price phải tái lập được từ equity value và share count, và ô base của ma trận FCFF phải khớp target (not_applicable khi equity value không dương)", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("gordon_growth", "Số mã đạt điều kiện Gordon Growth", "Gordon growth pass count", "", "gte", 10, "DCF Formula Gate", "Discount rate phải lớn hơn terminal growth", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("net_debt", "Số mã đối chiếu đúng nợ ròng", "Net debt reconciliation pass count", "", "gte", 10, "Net Debt Reconciliation", "Net debt = total debt - cash - short-term investments", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("sensitivity_varies", "Số mã có ma trận FCFF sensitivity biến thiên", "FCFF sensitivity variation pass count", "", "gte", 10, "Sensitivity Gate", "Ma trận FCFF WACC/g phải có nhiều hơn một giá trị hợp lệ", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("fcfe_sensitivity", "Số mã có ma trận FCFE sensitivity biến thiên", "FCFE sensitivity variation pass count", "", "gte", 10, "Sensitivity Gate", "Ma trận FCFE Re/g phải có nhiều hơn một giá trị hợp lệ hoặc được block rõ ràng theo artifact", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("formula_trace", "Số mã có formula trace", "Formula trace availability pass count", "", "gte", 10, "Formula Trace Audit", "Valuation artifact phải có trace công thức deterministic cho các phương pháp định giá", { thresholdLabel: "pass", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("golden_drift_out_of_tolerance", "Số lỗi drift so với golden valuation fixture", "Golden valuation drift out of tolerance", "", "lte", 0, "Golden Valuation Regression", "Số case valuation fixture bị drift ngoài tolerance; not_evaluable nếu chưa có fixture", { aliases: ["valuation_regression_failures"], thresholdLabel: "= 0", metricType: "error_count", scope: "benchmark_suite", severity: "P0", blocksPublish: true }),
      metric("target_price_bridge_error", "Số lỗi cầu nối EV, equity value hoặc giá mục tiêu", "Target price bridge error", "", "lte", 0, "Valuation Bridge Reconciliation", "Số case không tái lập được target price từ valuation artifact", { aliases: ["valuation_bridge_error"], thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("wacc_terminal_growth_violation", "Số case WACC nhỏ hơn hoặc bằng tăng trưởng dài hạn", "WACC terminal growth violation", "", "lte", 0, "DCF Formula Gate", "Số case WACC <= terminal growth trong DCF", { thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("net_debt_reconciliation_error", "Số lỗi đối chiếu nợ ròng", "Net debt reconciliation error", "", "lte", 0, "Net Debt Reconciliation", "Số case nợ ròng không khớp công thức chuẩn", { thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
    ],
    methodology: [
      "Net debt = interest-bearing debt - cash - short-term investments.",
      "EPS = net income / diluted shares; FCFF = EBIT(1-tax) + D&A - CAPEX - delta NWC.",
      "FCFE = NI + D&A - CAPEX - delta NWC + net borrowing; discount rate phải lớn hơn terminal growth.",
      "Giá mục tiêu, cầu nối EV sang vốn chủ sở hữu và ma trận độ nhạy phải nhất quán với mô hình định giá.",
    ],
  },
  {
    id: "agent",
    title: "4 · Hiệu quả Agent và LLM Judge",
    subtitle: "Đánh giá tuân thủ vai trò, quyền công cụ, cấu trúc đầu ra và chất lượng lập luận",
    artifact: "agent_eval.json",
    metrics: [
      metric("agent.workflow_quality_score", "Điểm chất lượng quy trình agent", "Agent workflow quality score", "%", "gte", 0.75, "Hard-mode Agent Workflow Audit", "Weighted stress score phat trace thieu, token telemetry thieu, judge readiness thap, handoff yeu hoac repair loop cao", { thresholdLabel: ">= 75%", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("tool_permission_compliance", "Tỷ lệ tuân thủ quyền sử dụng công cụ", "Tool permission compliance", "%", "gte", 1, "Agent Tool Permission Gate", "Số lượt gọi công cụ đúng quyền / Tổng lượt gọi công cụ", { thresholdLabel: "= 100%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("schema_validity", "Tỷ lệ cấu trúc JSON đầu ra hợp lệ", "JSON schema validity", "%", "gte", 1, "JSON Schema Validator", "Số output hợp lệ theo schema / Tổng output bắt buộc", { thresholdLabel: "= 100%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("no_unauthorized_calc", "Tỷ lệ không tự ý tính toán tài chính bằng LLM", "No unauthorized LLM financial calculation", "%", "gte", 1, "Agent Governance Gate", "Số lượt tuân thủ quy tắc / Tổng lượt cần kiểm tra", { thresholdLabel: "= 100%", metricType: "coverage", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("role_adherence", "Điểm tuân thủ vai trò", "Role adherence", "", "gte", 0.85, "DeepEval", "Điểm LLM Judge cho mức tuân thủ vai trò", { thresholdLabel: "≥ 85%", metricType: "score", scope: "report_run", severity: "P2", blocksPublish: false }),
      metric("groundedness", "Điểm kết luận có căn cứ", "Groundedness judge score", "", "gte", 0.85, "DeepEval", "Điểm LLM Judge về mức kết luận có căn cứ", { thresholdLabel: "≥ 85%", metricType: "score", scope: "report_run", severity: "P2", blocksPublish: false }),
      metric("task_completion", "Điểm hoàn thành nhiệm vụ", "Task completion", "", "gte", 0.85, "DeepEval", "Điểm hoàn thành yêu cầu bắt buộc", { thresholdLabel: "≥ 85%", metricType: "score", scope: "report_run", severity: "P2", blocksPublish: false }),
      metric("plan_adherence", "Điểm tuân thủ kế hoạch", "Plan compliance", "", "gte", 0.8, "DeepEval", "Điểm thực hiện đúng kế hoạch", { thresholdLabel: "≥ 80%", metricType: "score", scope: "report_run", severity: "P2", blocksPublish: false }),
      metric("critic_issue_recall", "Tỷ lệ phát hiện lỗi được cài trước", "Seeded issue detection", "%", "gte", 0.9, "Seeded Issue Evaluation", "Số lỗi cài trước được phát hiện / Tổng lỗi cài trước", { thresholdLabel: "≥ 90%", metricType: "coverage", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("stage_handoff_completeness", "Độ đầy đủ handoff giữa các stage", "Stage handoff completeness", "%", "gte", 0.95, "Trace Artifact Audit", "Số handoff có đủ input, output, artifact reference và blocking decision / Tổng handoff", { aliases: ["agent.stage_handoff_completeness"], thresholdLabel: ">= 95%", metricType: "coverage", scope: "report_run", severity: "P1", blocksPublish: true }),
      metric("tool_call_success_rate", "Tỷ lệ tool call thành công", "Tool call success rate", "%", "gte", 0.95, "Trace Runtime Metrics", "Số tool call thành công hoặc fail có kiểm soát / Tổng tool call", { aliases: ["agent.tool_call_success_rate"], thresholdLabel: ">= 95%", metricType: "coverage", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("repair_loop_rate", "Tỷ lệ vòng sửa lỗi agent", "Repair loop rate", "%", "lte", 0.15, "Trace Runtime Metrics", "Số lần repair schema, citation hoặc valuation trace / Tổng stage output", { aliases: ["agent.repair_loop_rate"], thresholdLabel: "<= 15%", metricType: "error_rate", scope: "system_window", severity: "P2", blocksPublish: false }),
      metric("token_budget_adherence", "Tỷ lệ tuân thủ token budget", "Token budget adherence", "%", "gte", 0.9, "Cost Telemetry", "Số run nằm trong token budget theo stage / Tổng run", { aliases: ["agent.token_budget_adherence"], thresholdLabel: ">= 90%", metricType: "coverage", scope: "system_window", severity: "P2", blocksPublish: false }),
    ],
    methodology: [
      "LLM Judge sử dụng rubric cố định; điểm cao không được ghi đè lỗi tất định hoặc vi phạm quản trị.",
      "Seeded Issue Evaluation đo khả năng Agent phản biện phát hiện các lỗi đã được chủ động cài vào bộ kiểm thử.",
    ],
  },
  {
    id: "report_quality",
    title: "5 · Chất lượng báo cáo",
    subtitle: "Đánh giá rubric báo cáo, độ đầy đủ của section, lý giải forecast và tính minh bạch định giá",
    artifact: "report_eval.json",
    artifactAliases: ["report_quality_eval.json"],
    metrics: [
      metric("report.benchmark_hardness_score", "Điểm chất lượng báo cáo (chuẩn hoá độ khó)", "Report quality (difficulty-adjusted)", "", "gte", 75, "Hard-mode Report Quality Rubric", "Weighted score phat diem yeu nhat trong thesis, evidence, risk, valuation va sensitivity disclosure", { thresholdLabel: ">= 75%", metricType: "score", scope: "report_run", severity: "P1", blocksPublish: false }),
      metric("report.quality_total", "Điểm chất lượng báo cáo tổng hợp", "Report quality total", "", "gte", 85, "Report Quality Rubric", "Tổng điểm rubric report quality trên các section bắt buộc", { aliases: ["report_quality_score"], thresholdLabel: "≥ 85%", metricType: "score", scope: "report_run", severity: "P1", blocksPublish: false }),
      metric("report.completeness", "Độ đầy đủ của báo cáo", "Report completeness", "%", "gte", 90, "Report Completeness Gate", "Số section, bảng và chart bắt buộc đã có / Tổng yêu cầu", { thresholdLabel: "≥ 90%", metricType: "coverage", scope: "report_run", severity: "P1", blocksPublish: true }),
      metric("report.valuation_transparency", "Tính minh bạch định giá", "Valuation transparency", "", "gte", 85, "Valuation Transparency Gate", "Điểm rubric cho method selection, assumptions, WACC, bridge và sensitivity", { thresholdLabel: "≥ 85%", metricType: "score", scope: "report_run", severity: "P1", blocksPublish: true }),
    ],
    methodology: [
      "Report quality là diagnostic và release gate riêng cho completeness và valuation transparency.",
      "Rubric score không được ghi đè lỗi deterministic hoặc các cổng kiểm soát xuất bản khác.",
    ],
  },
  {
    id: "observability",
    title: "6 · Vận hành, chi phí và độ trễ",
    subtitle: "Theo dõi độ ổn định, phương án dự phòng và lỗi trong quá trình tạo báo cáo",
    artifact: "observability_eval.json",
    metrics: [
      metric("ops.telemetry_quality_score", "Diem hard-mode telemetry", "Telemetry quality stress score", "%", "gte", 0.8, "Hard-mode Operations Telemetry Audit", "Weighted stress score phat trace missing cho latency, retrieval, upload, render, cost, retry, fallback va OCR health", { thresholdLabel: ">= 80%", metricType: "score", scope: "benchmark_suite", severity: "P2", blocksPublish: false }),
      metric("llm_retry_rate", "Tỷ lệ gọi LLM phải thử lại", "LLM retry rate", "%", "lte", 0.05, "Langfuse Tracing", "Số lượt gọi LLM phải retry / Tổng lượt gọi LLM", { aliases: ["ops.llm_retry_rate"], thresholdLabel: "≤ 5%", metricType: "error_rate", scope: "system_window", severity: "P3", blocksPublish: false }),
      metric("retrieval_fallback_rate", "Tỷ lệ truy xuất dùng fallback", "Retrieval fallback rate", "%", "lte", 0.2, "Retrieval Telemetry", "Số truy vấn dùng fallback / Tổng truy vấn retrieval", { aliases: ["ops.retrieval_fallback_rate"], thresholdLabel: "≤ 20%", metricType: "error_rate", scope: "system_window", severity: "P2", blocksPublish: false }),
      metric("ocr_failure_rate", "Tỷ lệ OCR thất bại trên tài liệu trọng yếu", "Material OCR failure rate", "%", "lte", 0.05, "OCR Runtime Metrics", "Số tài liệu OCR trọng yếu thất bại / Tổng tài liệu OCR trọng yếu", { aliases: ["ops.material_ocr_failure_rate"], thresholdLabel: "≤ 5%", metricType: "error_rate", scope: "system_window", severity: "P1", blocksPublish: true }),
      metric("final_ocr_error_count", "Số lỗi OCR ảnh hưởng số liệu final", "Final numeric OCR error count", "", "lte", 0, "OCR Final Artifact Gate", "Số lỗi OCR làm sai số liệu trong final report", { aliases: ["ops.final_ocr_error_count"], thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("artifact_upload_failures", "Số lỗi upload artifact cuối", "Final artifact upload failure", "", "lte", 0, "Artifact Storage Gate", "Số artifact cuối tải lên thất bại", { aliases: ["ops.artifact_upload_failure"], thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("pdf_render_failures", "Số lỗi render PDF cuối", "Final PDF render failure", "", "lte", 0, "PDF Render Gate", "Số lần render PDF cuối thất bại", { aliases: ["ops.pdf_render_failure"], thresholdLabel: "= 0", metricType: "error_count", scope: "report_run", severity: "P0", blocksPublish: true }),
      metric("warm_full_report_p95_latency", "Độ trễ p95 full report khi warm run", "Full report p95 latency, warm run", "phút", "lte", 10, "Runtime Latency Window", "p95 thời gian tạo full report khi dữ liệu/artifact đã có sẵn", { aliases: ["ops.full_report_p95_warm_seconds"], thresholdLabel: "≤ 10 phút", metricType: "latency_percentile", scope: "system_window", severity: "P3", blocksPublish: false }),
      metric("cold_full_report_p95_latency", "Độ trễ p95 full report khi cold run", "Full report p95 latency, cold run", "phút", "lte", 30, "Runtime Latency Window", "p95 thời gian tạo full report khi cần ingest/OCR/xử lý lại", { aliases: ["ops.full_report_p95_cold_seconds"], thresholdLabel: "≤ 30 phút", metricType: "latency_percentile", scope: "system_window", severity: "P3", blocksPublish: false }),
      metric("render_only_p95_latency", "Độ trễ p95 dựng PDF từ artifact đã khóa", "Render-only p95 latency", "phút", "lte", 2, "PDF Render Telemetry", "p95 thời gian dựng PDF từ artifact đã khóa", { aliases: ["ops.render_only_p95_seconds"], thresholdLabel: "≤ 2 phút", metricType: "latency_percentile", scope: "system_window", severity: "P1", blocksPublish: true }),
      metric("flash_memo_warm_p95_latency", "Độ trễ p95 flash memo khi warm run", "Flash memo p95 latency, warm run", "giây", "lte", 90, "Runtime Latency Window", "p95 thời gian tạo flash memo khi dữ liệu đã có sẵn", { aliases: ["ops.flash_memo_warm_p95_seconds"], thresholdLabel: "≤ 90 giây", metricType: "latency_percentile", scope: "system_window", severity: "P3", blocksPublish: false }),
      metric("flash_memo_cold_retrieval_p95_latency", "Độ trễ p95 flash memo khi cần retrieval", "Flash memo p95 latency, cold retrieval", "phút", "lte", 3, "Runtime Latency Window", "p95 thời gian tạo flash memo khi cần retrieval/crawl thêm", { aliases: ["ops.flash_memo_cold_retrieval_p95_seconds"], thresholdLabel: "≤ 3 phút", metricType: "latency_percentile", scope: "system_window", severity: "P3", blocksPublish: false }),
      metric("latency_regression_ratio", "Tỷ lệ hồi quy độ trễ so với baseline", "Latency regression", "", "lte", 1.25, "Latency Regression Gate", "p95 mới / p95 baseline", { aliases: ["ops.latency_regression_ratio"], thresholdLabel: "≤ 1.25x", metricType: "score", scope: "benchmark_suite", severity: "P3", blocksPublish: false }),
      metric("cost_per_report", "Cost per full report", "Cost per full report", "", "lte", 2, "Cost Ledger", "Tổng chi phí ước tính để tạo full report so với soft budget", { aliases: ["cost_per_full_report", "ops.cost_per_full_report_usd"], thresholdLabel: "<= soft budget", metricType: "score", scope: "system_window", severity: "P2", blocksPublish: false }),
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
  "Agent và LLM Judge",
  "Chất lượng báo cáo",
  "Vận hành",
];

export const ACCEPTANCE_EXPLANATION: string[] = [
  "Bảng sử dụng một bộ ngưỡng chuẩn dành cho bản vận hành chính thức; P0, P1 và P2 đã được phân loại để tránh tạo trạng thái trung gian không phục vụ quyết định.",
  "Chỉ số dùng điều kiện ≥ sẽ Chưa đạt khi thấp hơn ngưỡng; chỉ số dùng điều kiện ≤ sẽ Chưa đạt khi cao hơn ngưỡng.",
  "Thiếu dữ liệu benchmark được xem là Chưa đạt vì hệ thống không có đủ bằng chứng để xác nhận chất lượng.",
];

// Curated, ordered visibility allowlist per dashboard layer. The dashboard shows
// EXACTLY these metric IDs, in this order. IDs not listed here are hidden (e.g.
// hard-mode stress scores and redundant error-count duplicates). Use the bare
// static metric ID when a static MetricDef exists (aliases are resolved upstream
// by resultsForLayer); use the packet metric_id for dynamic-only metrics
// (dataframe_schema_validity, raw_bctc_non_empty, full_run_duration).
export const LAYER_VISIBLE_METRIC_IDS: Record<string, string[]> = {
  data_reliability: [
    "data_reliability_score",
    "core_metric_coverage",
    "material_ocr_error_count",
    "duplicate_fact_count",
    "dataframe_schema_validity",
    "raw_bctc_non_empty",
  ],
  rag_evidence: [
    "rag.retrieval_difficulty_score",
    "hit_rate_at_5",
    "mrr_at_5",
    "context_precision",
    "context_recall",
    "faithfulness",
    "response_relevancy",
    "source_tier_hit_rate",
  ],
  financial: [
    "finance.model_quality_score",
    "accounting_invariant_violations",
    "fcff",
    "target_price",
    "gordon_growth",
    "net_debt",
    "formula_trace",
  ],
  agent: [
    "agent.workflow_quality_score",
    "tool_permission_compliance",
    "schema_validity",
    "no_unauthorized_calc",
    "stage_handoff_completeness",
    "tool_call_success_rate",
    "repair_loop_rate",
    "token_budget_adherence",
  ],
  report_quality: [
    "report.quality_total",
    "report.completeness",
    "report.valuation_transparency",
  ],
  observability: [
    "llm_retry_rate",
    "retrieval_fallback_rate",
    "final_ocr_error_count",
    "artifact_upload_failures",
    "pdf_render_failures",
    "warm_full_report_p95_latency",
    "cost_per_report",
    "full_run_duration",
  ],
};
