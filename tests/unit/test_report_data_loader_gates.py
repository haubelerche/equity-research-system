from backend.reporting import report_data_loader as loader
from backend.reporting.section_builder import build_report_sections


def test_governance_artifact_blocks_unapproved_valuation(monkeypatch):
    """Latest governance output must override older default DCF artifacts."""
    legacy_val = {
        "ticker": "DBD",
        "fy_periods": ["2022FY", "2023FY", "2024FY", "2025FY"],
        "ratios": {
            "gross_margin": {"2025FY": 0.474},
            "net_margin": {"2025FY": 0.157},
            "roe": {"2025FY": 0.168},
            "roa": {"2025FY": 0.112},
        },
        "dcf": {
            "base": {
                "assumptions": {"wacc": 0.10, "terminal_growth": 0.03},
                "intrinsic_value_per_share_vnd": 333239.0,
            }
        },
        "multiples": {"current_price_vnd": 50200.0, "shares_mn": 109.18},
        "current_price_vnd": 50200.0,
        "sensitivity": {
            "wacc_range": [0.10],
            "g_range": [0.03],
            "matrix": {"0.100": {"0.03": 333239.0}},
        },
    }
    governance = {
        "ticker": "DBD",
        "current_price": 0.0,
        "target_price": 0.0,
        "upside_downside": 0.0,
        "rating_model_output": "UNDER_REVIEW",
        "assumptions": [],
    }

    monkeypatch.setattr(loader, "_latest_valuation", lambda ticker: legacy_val)
    monkeypatch.setattr(loader, "_latest_valuation_result", lambda ticker: governance)
    monkeypatch.setattr(loader, "_load_chart_paths", lambda ticker: {
        "C3": "DBD_C3.png",
        "C6": "DBD_C6.png",
        "C7": "DBD_C7.png",
    })

    ctx = loader.load_report_context("DBD")

    assert ctx.rating == "UNDER_REVIEW"
    assert ctx._current_price_missing is True
    assert ctx._target_price_missing is True
    assert ctx._upside_missing is True
    assert ctx._has_valuation is False
    assert ctx._has_sensitivity is False
    assert ctx._has_forecast_table is False
    assert ctx.valuation_reproducibility == "N/A"
    assert ctx.wacc_pct == 0.0
    assert ctx.terminal_growth_pct == 0.0
    assert "C3" not in ctx.chart_paths
    assert "C6" not in ctx.chart_paths
    assert "C7" not in ctx.chart_paths
    assert "333,239" not in ctx.investment_thesis
    assert "valuation artifact" in ctx.valuation_summary_table
    assert "PASS" in ctx.valuation_summary_table

    htmlish_markdown = "\n".join(section["markdown"] for section in build_report_sections(ctx))
    assert "333,239" not in htmlish_markdown
    assert "+563.8%" not in htmlish_markdown
    assert "UNDER_REVIEW" in htmlish_markdown
    assert "Biểu đồ DCF Value Bridge" in htmlish_markdown
    assert "BLOCKED" in htmlish_markdown


def test_load_report_context_uses_manifest_not_glob(tmp_path, monkeypatch):
    """With run_id, load_report_context must read from manifest path, not glob latest."""
    import json
    from backend.reporting.artifact_manifest import ArtifactManifest, write_manifest

    artifacts = tmp_path / "artifacts"
    val_dir = artifacts / "valuation"
    val_dir.mkdir(parents=True)

    # Write a SPECIFIC valuation file that the manifest points to
    specific_val = val_dir / "DHG_20260601T000000_specific_valuation.json"
    specific_val.write_text(
        json.dumps({"ratios": {}, "fy_periods": ["2021FY"], "MARKER": "correct_run"}),
        encoding="utf-8",
    )

    # Write a NEWER valuation file that glob would pick instead
    wrong_val = val_dir / "DHG_20260601T999999_newer_valuation.json"
    wrong_val.write_text(
        json.dumps({"ratios": {}, "fy_periods": ["2025FY"], "MARKER": "wrong_glob_file"}),
        encoding="utf-8",
    )

    # Write manifest pointing to the specific (older) file
    manifest = ArtifactManifest(
        run_id="run_dhg_loader_test",
        ticker="DHG",
        created_at="2026-06-01T00:00:00",
        schema_version=1,
        artifacts={"valuation": {"path": str(specific_val), "producer": "VALUATION_RUN"}},
    )
    write_manifest(manifest, base_dir=artifacts)

    # Patch ROOT to point to tmp_path (so loader finds artifacts/ there)
    monkeypatch.setattr("backend.reporting.report_data_loader.ROOT", tmp_path)

    from backend.reporting.report_data_loader import load_report_context
    ctx = load_report_context("DHG", run_id="run_dhg_loader_test")

    # If glob was used, fiscal_year would be 2025 (from the newer file)
    # If manifest was used, fiscal_year would be 2021 (from the specific file)
    assert ctx.fiscal_year == "2021", (
        f"Expected fiscal_year=2021 (from manifest), got {ctx.fiscal_year!r} — "
        "loader likely used glob instead of manifest"
    )


def test_load_report_context_accepts_run_id_param():
    """load_report_context signature must accept run_id kwarg."""
    import inspect
    from backend.reporting.report_data_loader import load_report_context
    sig = inspect.signature(load_report_context)
    assert "run_id" in sig.parameters


def test_load_report_context_warns_without_run_id(monkeypatch):
    """load_report_context without run_id must emit DeprecationWarning on glob fallback."""
    import warnings
    monkeypatch.setattr("backend.reporting.report_data_loader.ROOT",
                        __import__("pathlib").Path("/nonexistent_path_xyz"))
    from backend.reporting.report_data_loader import load_report_context
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        try:
            load_report_context("DHG", run_id=None)
        except Exception:
            pass  # may fail due to nonexistent path, that's ok
    dep_warnings = [x for x in w if issubclass(x.category, DeprecationWarning)]
    assert dep_warnings, (
        "Expected DeprecationWarning when run_id=None, but none was emitted"
    )


def test_db_fact_load_failure_is_logged_not_swallowed(caplog):
    """_load_db_facts must log a WARNING when DB connection fails — not silently return {}."""
    import logging
    from backend.reporting.report_data_loader import _load_db_facts
    with caplog.at_level(logging.WARNING, logger="backend.reporting.report_data_loader"):
        result = _load_db_facts("NONEXISTENT_TICKER_ZZZZZ_TEST")
    # Graceful degradation is correct (returns empty dict)
    assert result == {}
    # But must log the failure
    assert any(
        "canonical_facts" in r.message
        or "DB" in r.message
        or "psycopg2" in r.message
        or "NONEXISTENT_TICKER" in r.message
        for r in caplog.records
    ), f"DB failure must be logged at WARNING. Got records: {[r.message for r in caplog.records]}"
