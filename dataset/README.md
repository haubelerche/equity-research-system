# Vietnam Pharma Dataset Backbone

This directory contains implementation artifacts for the Vietnam pharma equity research dataset described in the backend plan.

## Scope

- Build a canonical data layer for Vietnam listed pharma and healthcare equities.
- Enforce source lineage, quality gates, and citation-safe retrieval.
- Support the run lifecycle: `ingestion -> facts -> valuation -> synthesis -> HITL`.

## Directory map

- `universe/`: tracked company universe and MVP subset.
- `sources/`: source catalog with update frequency, legal notes, and keys.
- `contracts/`: JSON schemas for source/fact/catalyst/chunk/citation records.
- `taxonomy/`: financial and catalyst taxonomy for normalization.
- `mvp/`: templates for MVP fact ingestion and golden dataset checks.
- `retrieval/`: claim-check seed set and citation policy.
- `evaluation/`: quality, hardening, and scale-out criteria.
- `finrobot/`: adapters that let FinRobot valuation/reporting consume canonical facts.

## Operating principles

1. Facts before narrative.
2. Local context first (Vietnam market and policy sources).
3. Lineage by default.
4. Quality before persistence.
5. AI drafts, humans approve.
