"""Deterministic assembly of the artifact-governed final report model.

The assembler is intentionally editorially inert: it orders and copies approved
inputs, but never writes narrative, calculates values, or fills missing content.
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


REQUIRED_SECTIONS: tuple[str, ...] = (
    "cover_investment_summary",
    "trading_snapshot",
    "company_overview",
    "business_model",
    "recent_financial_performance",
    "channel_and_product_analysis",
    "industry_and_catalyst_analysis",
    "driver_based_forecast",
    "valuation_and_recommendation",
    "risks_and_monitoring_factors",
    "forecast_financial_summary",
    "appendix",
)

REQUIRED_ARTIFACTS: tuple[str, ...] = (
    "claim_ledger",
    "financial_analysis",
    "forecast_model",
    "valuation",
    "market_snapshot",
)

REQUIRED_SPECS: tuple[str, ...] = ("chart_specs", "table_specs")

_IDENTITY_FIELDS: tuple[str, ...] = ("run_id", "ticker")


@dataclass(frozen=True)
class ReportAssemblyValidation:
    """Structured validation result suitable for gates and tests."""

    errors: tuple[str, ...] = ()

    @property
    def valid(self) -> bool:
        return not self.errors

    @property
    def passed(self) -> bool:
        return self.valid

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate": "REPORT_ASSEMBLY_VALIDATION",
            "status": "pass" if self.valid else "fail",
            "valid": self.valid,
            "errors": list(self.errors),
        }


class ReportAssemblyError(ValueError):
    """Raised when approved inputs cannot form a valid final report model."""

    def __init__(self, validation: ReportAssemblyValidation):
        self.validation = validation
        super().__init__("Report assembly validation failed: " + "; ".join(validation.errors))


class ReportAssembler:
    """Arrange approved report artifacts without creating report content."""

    def __init__(self, required_sections: tuple[str, ...] = REQUIRED_SECTIONS):
        if not required_sections or len(set(required_sections)) != len(required_sections):
            raise ValueError("required_sections must be non-empty and unique")
        self.required_sections = tuple(required_sections)

    def validate(
        self,
        report_draft: Mapping[str, Any],
        artifacts: Mapping[str, Any] | None = None,
        specs: Mapping[str, Any] | None = None,
        **inputs: Any,
    ) -> ReportAssemblyValidation:
        """Validate assembly inputs without mutating or assembling them."""
        errors: list[str] = []

        if not isinstance(report_draft, Mapping):
            return ReportAssemblyValidation(("report_draft must be a mapping",))

        merged_artifacts, merged_specs = self._merge_inputs(artifacts, specs, inputs)
        sections = report_draft.get("sections")
        if not isinstance(sections, Mapping):
            errors.append("report_draft.sections must be a mapping")
        else:
            missing_sections = [
                section
                for section in self.required_sections
                if section not in sections or _is_empty(sections[section])
            ]
            if missing_sections:
                errors.append("missing required sections: " + ", ".join(missing_sections))

        for name in REQUIRED_ARTIFACTS:
            if name not in merged_artifacts or not isinstance(merged_artifacts[name], Mapping):
                errors.append(f"missing or invalid required artifact: {name}")

        for name in REQUIRED_SPECS:
            if name not in merged_specs or not isinstance(
                merged_specs[name], (Mapping, list, tuple)
            ):
                errors.append(f"missing or invalid required spec: {name}")

        errors.extend(self._identity_errors(report_draft, merged_artifacts, merged_specs))
        errors.extend(self._snapshot_errors(merged_artifacts))
        return ReportAssemblyValidation(tuple(errors))

    def assemble(
        self,
        report_draft: Mapping[str, Any],
        artifacts: Mapping[str, Any] | None = None,
        specs: Mapping[str, Any] | None = None,
        **inputs: Any,
    ) -> dict[str, Any]:
        """Return a deterministic ``final_report_model`` from approved inputs.

        Inputs may be supplied in the ``artifacts``/``specs`` mappings or as
        keyword arguments named by ``REQUIRED_ARTIFACTS``/``REQUIRED_SPECS``.
        """
        validation = self.validate(report_draft, artifacts, specs, **inputs)
        if not validation.valid:
            raise ReportAssemblyError(validation)

        merged_artifacts, merged_specs = self._merge_inputs(artifacts, specs, inputs)
        sections = report_draft["sections"]
        model: dict[str, Any] = {
            "schema_version": copy.deepcopy(report_draft.get("schema_version")),
            "run_id": copy.deepcopy(report_draft.get("run_id")),
            "ticker": copy.deepcopy(report_draft.get("ticker")),
            "producer": "report_assembler",
            "sections": {
                section: copy.deepcopy(sections[section])
                for section in self.required_sections
            },
            "claim_ledger": copy.deepcopy(merged_artifacts["claim_ledger"]),
            "chart_specs": copy.deepcopy(merged_specs["chart_specs"]),
            "table_specs": copy.deepcopy(merged_specs["table_specs"]),
            "source_artifacts": {
                name: copy.deepcopy(merged_artifacts[name])
                for name in REQUIRED_ARTIFACTS
                if name != "claim_ledger"
            },
        }
        snapshot_id = self._snapshot_id(merged_artifacts)
        if snapshot_id:
            model["snapshot_id"] = snapshot_id

        # These are authored draft fields, so preserving them does not create content.
        for field in (
            "claims",
            "required_tables",
            "required_charts",
            "limitations",
            "recommendation",
            "target_price",
            "target_price_vnd",
            "publication_status",
            "approval_status",
        ):
            if field in report_draft:
                model[field] = copy.deepcopy(report_draft[field])

        model["checksum"] = _content_checksum(model)
        return model

    def validate_final_report_model(
        self, final_report_model: Mapping[str, Any]
    ) -> ReportAssemblyValidation:
        """Validate the structural output contract and its deterministic checksum."""
        if not isinstance(final_report_model, Mapping):
            return ReportAssemblyValidation(("final_report_model must be a mapping",))

        errors: list[str] = []
        sections = final_report_model.get("sections")
        if not isinstance(sections, Mapping):
            errors.append("final_report_model.sections must be a mapping")
        else:
            missing = [
                section
                for section in self.required_sections
                if section not in sections or _is_empty(sections[section])
            ]
            if missing:
                errors.append("missing required sections: " + ", ".join(missing))
            if tuple(sections) != self.required_sections:
                errors.append("final_report_model.sections are not in required order")

        for field in ("claim_ledger", "chart_specs", "table_specs", "source_artifacts"):
            if field not in final_report_model:
                errors.append(f"missing final report field: {field}")

        expected_checksum = final_report_model.get("checksum")
        if not isinstance(expected_checksum, str):
            errors.append("missing or invalid final report checksum")
        else:
            content = {k: v for k, v in final_report_model.items() if k != "checksum"}
            if expected_checksum != _content_checksum(content):
                errors.append("final report checksum mismatch")

        return ReportAssemblyValidation(tuple(errors))

    @staticmethod
    def _merge_inputs(
        artifacts: Mapping[str, Any] | None,
        specs: Mapping[str, Any] | None,
        inputs: Mapping[str, Any],
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        merged_artifacts = dict(artifacts) if isinstance(artifacts, Mapping) else {}
        merged_specs = dict(specs) if isinstance(specs, Mapping) else {}
        for name in REQUIRED_ARTIFACTS:
            if name in inputs:
                merged_artifacts[name] = inputs[name]
        for name in REQUIRED_SPECS:
            if name in inputs:
                merged_specs[name] = inputs[name]
        return merged_artifacts, merged_specs

    @staticmethod
    def _identity_errors(
        report_draft: Mapping[str, Any],
        artifacts: Mapping[str, Any],
        specs: Mapping[str, Any],
    ) -> list[str]:
        errors: list[str] = []
        for field in _IDENTITY_FIELDS:
            expected = report_draft.get(field)
            if _is_empty(expected):
                errors.append(f"report_draft missing identity field: {field}")
                continue
            for name, payload in {**artifacts, **specs}.items():
                if isinstance(payload, Mapping):
                    actual = payload.get(field)
                    if not _is_empty(actual) and actual != expected:
                        errors.append(
                            f"{name}.{field} does not match report_draft.{field}"
                        )
        return errors

    @staticmethod
    def _snapshot_id(artifacts: Mapping[str, Any]) -> str | None:
        for name in ("valuation", "forecast_model", "market_snapshot", "financial_analysis"):
            payload = artifacts.get(name)
            if isinstance(payload, Mapping) and payload.get("snapshot_id"):
                return str(payload["snapshot_id"])
        return None

    @staticmethod
    def _snapshot_errors(artifacts: Mapping[str, Any]) -> list[str]:
        snapshots = {
            str(payload["snapshot_id"])
            for payload in artifacts.values()
            if isinstance(payload, Mapping) and payload.get("snapshot_id")
        }
        if len(snapshots) > 1:
            return ["source artifacts do not share one snapshot_id"]
        return []


def assemble_report(
    report_draft: Mapping[str, Any],
    artifacts: Mapping[str, Any] | None = None,
    specs: Mapping[str, Any] | None = None,
    **inputs: Any,
) -> dict[str, Any]:
    """Functional convenience wrapper around :class:`ReportAssembler`."""
    return ReportAssembler().assemble(report_draft, artifacts, specs, **inputs)


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _content_checksum(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
