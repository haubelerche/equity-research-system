"""Typed artifact contracts for the six-agent equity-research workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class ArtifactContract(BaseModel):
    """Lineage fields required on every persisted workflow artifact."""

    schema_version: str = "1.0"
    run_id: str
    ticker: str
    producer: str
    input_refs: list[str] = Field(default_factory=list)
    version: int = Field(default=1, ge=1)
    checksum: str
    created_at: str = Field(default_factory=_now_iso)
    updated_at: str = Field(default_factory=_now_iso)


class ResearchQuestion(BaseModel):
    question_id: str
    question: str
    priority: Literal["high", "medium", "low"]
    required_artifacts: list[str] = Field(default_factory=list)
    required_evidence_types: list[str] = Field(default_factory=list)


class CompletionCriteria(BaseModel):
    minimum_evidence_coverage: float = Field(ge=0, le=1)
    required_tables: list[str] = Field(default_factory=list)
    required_charts: list[str] = Field(default_factory=list)
    required_valuation_outputs: list[str] = Field(default_factory=list)
    required_critic_scores: dict[str, float] = Field(default_factory=dict)


class ResearchPlan(ArtifactContract):
    producer: Literal["research_manager_agent"] = "research_manager_agent"
    research_questions: list[ResearchQuestion] = Field(default_factory=list)
    required_sections: list[str] = Field(default_factory=list)
    specialist_instructions: dict[str, list[str] | str] = Field(default_factory=dict)
    completion_criteria: CompletionCriteria
    known_constraints: list[str] = Field(default_factory=list)


class ReportInstructions(BaseModel):
    key_thesis_to_test: list[str] = Field(default_factory=list)
    required_emphasis: list[str] = Field(default_factory=list)
    required_caveats: list[str] = Field(default_factory=list)
    prohibited_claims: list[str] = Field(default_factory=list)


class ReadinessReview(ArtifactContract):
    producer: Literal["research_manager_agent"] = "research_manager_agent"
    decision: Literal["ready_for_report", "human_review_required"]
    answered_questions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    critical_missing_items: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    report_instructions: ReportInstructions


class CanonicalFactRef(BaseModel):
    fact_id: str
    metric: str
    period: str
    value: int | float | str
    unit: str
    source_ref: str
    confidence: float = Field(ge=0, le=1)


class DocumentEvidence(BaseModel):
    evidence_id: str
    source_type: str
    source_title: str
    source_date: str | None = None
    source_ref: str
    excerpt_summary: str
    relevant_sections: list[str] = Field(default_factory=list)
    reliability_tier: int = Field(ge=1)


class SourceCoverage(BaseModel):
    required_item: str
    status: Literal["covered", "partial", "missing"]
    evidence_refs: list[str] = Field(default_factory=list)


class EvidenceConflict(BaseModel):
    conflict_id: str
    topic: str
    source_a: str
    source_b: str
    conflict_description: str
    suggested_handling: str


class EvidencePack(ArtifactContract):
    producer: Literal["data_and_evidence_agent"] = "data_and_evidence_agent"
    canonical_fact_refs: list[CanonicalFactRef] = Field(default_factory=list)
    document_evidence: list[DocumentEvidence] = Field(default_factory=list)
    business_evidence: dict[str, Any] = Field(default_factory=dict)
    pharma_catalyst_evidence: dict[str, Any] = Field(default_factory=dict)
    source_coverage: list[SourceCoverage] = Field(default_factory=list)
    conflicts: list[EvidenceConflict] = Field(default_factory=list)
    unanswered_requests: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class CompanyEvidenceRecord(BaseModel):
    """One auditable company-specific observation or approved analyst estimate."""

    value: Any
    as_of: str
    status: Literal["observed", "approved_estimate", "insufficient_evidence"]
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(default_factory=list)
    source_class: Literal["company", "regulator", "analyst_estimate"]


class CompanyResearchPackV2(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    ticker: str
    archetype: str
    topics: dict[str, dict[str, CompanyEvidenceRecord] | list[dict[str, Any]]] = Field(default_factory=dict)
    analyst_insights: list[dict[str, Any]] = Field(default_factory=list)
    source_map: dict[str, Any] = Field(default_factory=dict)
    coverage: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class CausalInsight(BaseModel):
    schema_version: Literal["2.0"] = "2.0"
    observation: str
    operating_cause: str
    financial_transmission: dict[str, Any]
    scenario_delta: dict[str, Any]
    valuation_delta: dict[str, Any]
    monitoring_kpi: str
    evidence_refs: list[str] = Field(default_factory=list)
    confidence: float | Literal["low", "medium", "high"]
    status: Literal["ready", "insufficient_evidence"]


class EvidenceRequest(BaseModel):
    request_id: str
    requested_items: list[str] = Field(default_factory=list)
    reason: str
    critical: bool = False


class FinancialAnalysis(ArtifactContract):
    producer: Literal["financial_analysis_agent"] = "financial_analysis_agent"
    historical_periods: list[str] = Field(default_factory=list)
    latest_period: str
    income_statement_analysis: dict[str, Any] = Field(default_factory=dict)
    balance_sheet_analysis: dict[str, Any] = Field(default_factory=dict)
    cash_flow_analysis: dict[str, Any] = Field(default_factory=dict)
    ratio_diagnostics: dict[str, Any] = Field(default_factory=dict)
    business_interpretation: dict[str, Any] = Field(default_factory=dict)
    segment_channel_analysis: dict[str, Any] = Field(default_factory=dict)
    financial_risks: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_request: EvidenceRequest | None = None


class ForecastHorizon(BaseModel):
    start_year: int
    end_year: int
    explicit_years: list[int] = Field(default_factory=list)


class ForecastModel(ArtifactContract):
    producer: Literal["forecast_valuation_agent"] = "forecast_valuation_agent"
    forecast_horizon: ForecastHorizon
    revenue_forecast: dict[str, Any] = Field(default_factory=dict)
    gross_margin_forecast: dict[str, Any] = Field(default_factory=dict)
    opex_forecast: dict[str, Any] = Field(default_factory=dict)
    working_capital_forecast: dict[str, Any] = Field(default_factory=dict)
    capex_and_depreciation: dict[str, Any] = Field(default_factory=dict)
    debt_cash_interest: dict[str, Any] = Field(default_factory=dict)
    share_count: dict[str, Any] = Field(default_factory=dict)
    forecast_quality_checks: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AssumptionRationale(BaseModel):
    assumption: str
    value: Any
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)
    sensitivity_importance: Literal["low", "medium", "high"]


class ValuationProposal(ArtifactContract):
    producer: Literal["forecast_valuation_agent"] = "forecast_valuation_agent"
    selected_methods: list[Literal["FCFF", "FCFE"]] = Field(default_factory=lambda: ["FCFF", "FCFE"])
    method_weights: dict[str, float] = Field(default_factory=lambda: {"FCFF": 50.0, "FCFE": 50.0})
    key_assumptions: dict[str, Any] = Field(default_factory=dict)
    assumption_rationale: list[AssumptionRationale] = Field(default_factory=list)
    scenario_design: dict[str, Any] = Field(default_factory=dict)
    approval_required_items: list[str] = Field(default_factory=list)
    evidence_request: EvidenceRequest | None = None


class Valuation(ArtifactContract):
    producer: Literal["valuation_engine"] = "valuation_engine"
    approved_assumption_refs: list[str] = Field(default_factory=list)
    fcff: dict[str, Any] = Field(default_factory=dict)
    fcfe: dict[str, Any] = Field(default_factory=dict)
    weighted_target_price: dict[str, Any] = Field(default_factory=dict)
    sensitivity: dict[str, Any] = Field(default_factory=dict)
    sanity_checks: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)


class ReportClaim(BaseModel):
    claim_id: str
    section: str
    text: str
    claim_type: Literal["fact", "inference", "opinion"]
    quantitative: bool
    supporting_refs: list[str] = Field(default_factory=list)
    source_artifact_refs: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    uncertainty: str | None = None
    reviewer_note: str | None = None


class ReportDraft(ArtifactContract):
    producer: Literal["thesis_report_agent"] = "thesis_report_agent"
    sections: dict[str, Any] = Field(default_factory=dict)
    claims: list[ReportClaim] = Field(default_factory=list)
    required_tables: list[str] = Field(default_factory=list)
    required_charts: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    evidence_request: EvidenceRequest | None = None


class CriticScore(BaseModel):
    score: float = Field(ge=0, le=10)
    explanation: str


class CriticFinding(BaseModel):
    finding_id: str
    severity: Literal["low", "medium", "high", "critical"]
    target_section: str
    target_agent: str
    claim_id: str | None = None
    issue_type: Literal[
        "unsupported_claim",
        "weak_thesis",
        "missing_driver",
        "forecast_not_driver_based",
        "valuation_incoherent",
        "numeric_mismatch",
        "citation_mismatch",
        "missing_risk",
        "overconfident_recommendation",
        "poor_storytelling",
        "missing_table_or_chart",
    ]
    explanation: str
    evidence_refs: list[str] = Field(default_factory=list)
    required_action: str


class CriticReview(ArtifactContract):
    producer: Literal["senior_critic_agent"] = "senior_critic_agent"
    decision: Literal["pass", "revision_required", "human_review_required"]
    scorecard: dict[str, CriticScore] = Field(default_factory=dict)
    findings: list[CriticFinding] = Field(default_factory=list)
    revision_instructions: list[str] = Field(default_factory=list)


# Explicit aliases keep configuration names descriptive while preserving one
# schema per persisted artifact.
ResearchPlanArtifact = ResearchPlan
ReadinessReviewArtifact = ReadinessReview
EvidencePackArtifact = EvidencePack
FinancialAnalysisArtifact = FinancialAnalysis
ForecastModelArtifact = ForecastModel
ValuationProposalArtifact = ValuationProposal
ValuationArtifact = Valuation
ReportDraftArtifact = ReportDraft
CriticReviewArtifact = CriticReview
ResearchManagerArtifact = ResearchPlan | ReadinessReview
ForecastValuationArtifact = ForecastModel | ValuationProposal

ARTIFACT_CONTRACTS: dict[str, Any] = {
    "ResearchManagerArtifact": ResearchManagerArtifact,
    "EvidencePack": EvidencePack,
    "FinancialAnalysis": FinancialAnalysis,
    "ForecastValuationArtifact": ForecastValuationArtifact,
    "ReportDraft": ReportDraft,
    "CriticReview": CriticReview,
}


def validate_agent_artifact(schema_name: str, payload: dict[str, Any]) -> BaseModel:
    """Validate an agent payload against its configured persisted-artifact contract."""
    contract = ARTIFACT_CONTRACTS.get(schema_name)
    if contract is None:
        raise ValueError(f"Unknown agent artifact schema: {schema_name}")
    return TypeAdapter(contract).validate_python(payload)
