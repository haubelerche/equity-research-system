import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND_ROOT = path.resolve(SCRIPT_DIR, "..");
const REPO_ROOT = path.resolve(FRONTEND_ROOT, "..");
const mode = process.argv.includes("--dist") ? "dist" : "source";

const EXPECTED_TICKERS = [
  "DHG", "IMP", "DMC", "TRA", "DBD", "MKP", "TNH", "JVC", "DVN", "DHT",
  "LDP", "PPP", "DP3", "DP1", "TW3", "MED", "PMC", "AMV", "YTC", "VHE",
  "VDP", "DCL", "SPM", "VMD", "DNM", "DBT", "DPP", "DTP", "AMP",
  "BCP", "BIO", "CDP", "CNC", "DAN", "DBM", "DDN", "DHN", "DP2", "DTG",
  "HDP", "MTP", "NDC", "DHD", "DPH", "OPC",
];

const REQUIRED_ARTIFACT_METRICS = {
  "data_quality.json": [
    ["data_reliability_score"],
    ["core_metric_coverage"],
    ["material_ocr_error_count", "ocr_material_error_count"],
    ["duplicate_fact_count", "duplicate_fact_rate"],
    ["dataframe_schema_validity"],
    ["raw_bctc_non_empty"],
  ],
  "retrieval_eval.json": [
    ["hit_rate_at_5"],
    ["mrr_at_5"],
    ["context_precision"],
    ["context_recall"],
    ["faithfulness"],
    ["response_relevancy"],
    ["source_tier_hit_rate"],
  ],
  "financial_eval.json": [
    ["accounting_invariant_violations", "critical_failures"],
    ["fcff"],
    ["target_price"],
    ["gordon_growth"],
    ["net_debt"],
    ["formula_trace"],
  ],
  "agent_eval.json": [
    ["tool_permission_compliance"],
    ["schema_validity"],
    ["no_unauthorized_calc"],
    ["stage_handoff_completeness", "agent.stage_handoff_completeness"],
    ["tool_call_success_rate", "agent.tool_call_success_rate"],
    ["repair_loop_rate", "agent.repair_loop_rate"],
    ["token_budget_adherence", "agent.token_budget_adherence"],
  ],
  "report_eval.json": [
    ["report.quality_total", "report_quality_score"],
    ["report.completeness"],
    ["report.valuation_transparency"],
  ],
  "observability_eval.json": [
    ["llm_retry_rate", "ops.llm_retry_rate"],
    ["retrieval_fallback_rate", "ops.retrieval_fallback_rate"],
    ["final_ocr_error_count", "ops.final_ocr_error_count"],
    ["artifact_upload_failures", "ops.artifact_upload_failure"],
    ["pdf_render_failures", "ops.pdf_render_failure"],
    ["warm_full_report_p95_latency", "ops.full_report_p95_warm_seconds"],
    ["cost_per_report", "cost_per_full_report", "ops.cost_per_full_report_usd"],
    ["full_run_duration"],
  ],
};

const NO_STORE_VALUE = "no-store, max-age=0, must-revalidate";

function fail(message) {
  console.error(`[deploy-assets] ${message}`);
  process.exitCode = 1;
}

function readText(relativePath, root = FRONTEND_ROOT) {
  return fs.readFileSync(path.join(root, relativePath), "utf8");
}

function parseCsvLine(line) {
  const cells = [];
  let current = "";
  let inQuotes = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const next = line[index + 1];
    if (char === "\"" && inQuotes && next === "\"") {
      current += "\"";
      index += 1;
    } else if (char === "\"") {
      inQuotes = !inQuotes;
    } else if (char === "," && !inQuotes) {
      cells.push(current);
      current = "";
    } else {
      current += char;
    }
  }
  cells.push(current);
  return cells;
}

function parseTickerCsv(csvText) {
  const lines = csvText.split(/\r?\n/).filter((line) => line.trim().length > 0);
  if (lines.length < 2) return [];
  const headers = parseCsvLine(lines[0]).map((header) => header.trim());
  const tickerIndex = headers.indexOf("ticker");
  if (tickerIndex === -1) return [];
  return lines.slice(1)
    .map((line) => (parseCsvLine(line)[tickerIndex] ?? "").trim().toUpperCase())
    .filter(Boolean);
}

function extractUniverseTickers() {
  const source = readText("src/data/universe.ts");
  return [...source.matchAll(/ticker:\s*"([^"]+)"/g)].map((match) => match[1].toUpperCase());
}

function duplicates(items) {
  const seen = new Set();
  const repeated = new Set();
  for (const item of items) {
    if (seen.has(item)) repeated.add(item);
    seen.add(item);
  }
  return [...repeated].sort();
}

function assertSameSet(actual, expected, label) {
  const actualSet = new Set(actual);
  const expectedSet = new Set(expected);
  const missing = expected.filter((item) => !actualSet.has(item));
  const extra = actual.filter((item) => !expectedSet.has(item));
  if (missing.length || extra.length) {
    fail(`${label} mismatch. missing=[${missing.join(", ")}] extra=[${extra.join(", ")}]`);
  }
}

function validateUniverseSource() {
  const tickers = extractUniverseTickers();
  const repeated = duplicates(tickers);
  if (repeated.length) fail(`frontend universe has duplicate tickers: ${repeated.join(", ")}`);
  assertSameSet(tickers, EXPECTED_TICKERS, "frontend report universe");
  if (tickers.includes("AGP")) fail("frontend report universe must not include AGP");

  const csvPath = path.join(REPO_ROOT, "config/dataset/universe/pharma_vn_universe.csv");
  if (fs.existsSync(csvPath)) {
    const csvTickers = parseTickerCsv(fs.readFileSync(csvPath, "utf8"));
    assertSameSet(tickers, csvTickers, "frontend universe vs canonical backend CSV");
  }
}

function validateVercelConfig() {
  const config = JSON.parse(readText("vercel.json"));
  if (config.buildCommand !== "npm run build") {
    fail("frontend/vercel.json buildCommand must remain 'npm run build' so validation runs on Vercel");
  }
  if (config.outputDirectory !== "dist") {
    fail("frontend/vercel.json outputDirectory must remain 'dist'");
  }

  const headers = Array.isArray(config.headers) ? config.headers : [];
  for (const route of ["/", "/reports", "/eval", "/index.html", "/eval/framework.json"]) {
    const headerBlock = headers.find((item) => item.source === route);
    const cacheHeader = headerBlock?.headers?.find((item) => item.key.toLowerCase() === "cache-control");
    if (cacheHeader?.value !== NO_STORE_VALUE) {
      fail(`frontend/vercel.json must set '${NO_STORE_VALUE}' for ${route}`);
    }
  }
}

function validateEvaluationPacket(packetPath) {
  if (!fs.existsSync(packetPath)) {
    fail(`missing evaluation packet: ${packetPath}`);
    return;
  }
  const stat = fs.statSync(packetPath);
  if (stat.size < 1024 * 1024) {
    fail(`evaluation packet is unexpectedly small: ${stat.size} bytes`);
  }

  let packet;
  try {
    packet = JSON.parse(fs.readFileSync(packetPath, "utf8"));
  } catch (error) {
    fail(`evaluation packet is not valid JSON: ${error.message}`);
    return;
  }

  if (!packet.generated_at || Number.isNaN(Date.parse(packet.generated_at))) {
    fail("evaluation packet must include a valid generated_at timestamp");
  }
  if (!Array.isArray(packet.artifacts)) {
    fail("evaluation packet must include an artifacts array");
    return;
  }

  const byArtifact = new Map(packet.artifacts.map((artifact) => [artifact.artifact, artifact]));
  for (const [artifactName, metricGroups] of Object.entries(REQUIRED_ARTIFACT_METRICS)) {
    const artifact = byArtifact.get(artifactName);
    if (!artifact) {
      fail(`evaluation packet missing artifact ${artifactName}`);
      continue;
    }
    const results = Array.isArray(artifact.metric_results)
      ? artifact.metric_results
      : Array.isArray(artifact.metrics)
        ? artifact.metrics
        : [];
    if (results.length === 0) {
      fail(`evaluation artifact ${artifactName} has no metric results`);
      continue;
    }
    const metricIds = new Set(results.map((metric) => String(metric.metric_id ?? metric.id ?? "")));
    const missingGroups = metricGroups.filter((aliases) => !aliases.some((alias) => metricIds.has(alias)));
    if (missingGroups.length) {
      fail(`evaluation artifact ${artifactName} missing metrics: ${missingGroups.map((aliases) => aliases.join("|")).join(", ")}`);
    }
  }
}

function listFilesRecursive(root) {
  const entries = fs.readdirSync(root, { withFileTypes: true });
  return entries.flatMap((entry) => {
    const fullPath = path.join(root, entry.name);
    return entry.isDirectory() ? listFilesRecursive(fullPath) : [fullPath];
  });
}

function validateDistBundle() {
  const distRoot = path.join(FRONTEND_ROOT, "dist");
  const indexPath = path.join(distRoot, "index.html");
  if (!fs.existsSync(indexPath)) fail("dist/index.html is missing");
  validateEvaluationPacket(path.join(distRoot, "eval/framework.json"));

  const jsBundle = listFilesRecursive(path.join(distRoot, "assets"))
    .filter((filePath) => filePath.endsWith(".js"))
    .map((filePath) => fs.readFileSync(filePath, "utf8"))
    .join("\n");
  for (const token of ["AGP", "Agimexpharm"]) {
    if (jsBundle.includes(token)) fail(`dist JavaScript bundle still contains removed ticker token ${token}`);
  }
}

if (mode === "source") {
  validateUniverseSource();
  validateVercelConfig();
  validateEvaluationPacket(path.join(FRONTEND_ROOT, "public/eval/framework.json"));
} else {
  validateDistBundle();
}

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log(`[deploy-assets] ${mode} assets validated`);
