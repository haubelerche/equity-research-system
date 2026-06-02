# Vietnam Pharma Dataset Config

This directory contains source-controlled dataset configuration for the Vietnam pharma equity research pipeline. Runtime extracts, raw snapshots, downloaded PDFs, discovered document lists, and report artifacts belong under `data/` or `artifacts/` and are ignored.

## Directory Map

- `universe/`: company universe and MVP subset.
- `sources/`: source catalog with update frequency, legal notes, and keys.
- `contracts/`: JSON schemas for source, fact, catalyst, chunk, citation, agent-message, and tool-call records.
- `taxonomy/`: financial and catalyst taxonomy for normalization.
- `mvp/`: templates for MVP fact ingestion and golden dataset checks.
- `golden/`: verified fallback fixtures and provenance metadata.

## Operating Principles

1. Facts before narrative.
2. Static config is source-controlled; runtime data is not.
3. Lineage by default.
4. Quality before persistence.
5. AI drafts, humans approve.
