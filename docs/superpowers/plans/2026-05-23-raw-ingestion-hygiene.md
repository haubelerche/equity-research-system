# Raw Ingestion Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix raw snapshot storage so it goes to `storage/raw/` (gitignored), deduplicates by payload hash, writes a per-run manifest, and enforces a BCTC row-count quality gate — making ingestion auditable without polluting git with runtime data.

**Architecture:** The `SourceRegistry.save_raw_snapshot()` method is the single write point for all raw payloads. We fix the path there and add hash-dedup + manifest logic. Both finance and company connectors pass the path through `_register_source_version` / `_register_payload`, so changing the base path constant in one place propagates everywhere. The row-count gate is added inside `sync_financial_for_ticker` after frames are fetched, before facts are extracted.

**Tech Stack:** Python 3.11+, pathlib, hashlib (already in use), pytest, existing `PostgresFactStore` + `SourceRegistry` infrastructure.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `scripts/db/source_registry.py` | Add hash-dedup; write per-run manifest; change base path to `storage/raw/` |
| Modify | `scripts/connectors/vnstock_finance_connector.py` | Replace hardcoded `dataset/raw/bctc/...` path with `storage/raw/bctc/...`; add row-count gate |
| Modify | `scripts/connectors/vnstock_company_connector.py` | Replace hardcoded `dataset/raw/market/...` path with `storage/raw/market/...` |
| Modify | `.gitignore` | Add `storage/raw/` and `storage/` rules |
| Create | `tests/test_raw_ingestion_hygiene.py` | Unit tests for dedup, manifest, path, row-count gate |
| Delete (one-time) | `dataset/raw/bctc/DHG/*_quarter.*` | Remove stale quarter files not covered by gitignore |

---

## Task 1: Add `storage/raw/` to `.gitignore` and delete stale quarter files

**Files:**
- Modify: `.gitignore`
- Delete: `dataset/raw/bctc/DHG/balance_sheet_quarter.json`, `dataset/raw/bctc/DHG/balance_sheet_quarter.json.sha256`, `dataset/raw/bctc/DHG/cash_flow_quarter.json`, `dataset/raw/bctc/DHG/cash_flow_quarter.json.sha256`, `dataset/raw/bctc/DHG/income_statement_quarter.json`, `dataset/raw/bctc/DHG/income_statement_quarter.json.sha256`, `dataset/raw/bctc/DHG/ratio_quarter.json`, `dataset/raw/bctc/DHG/ratio_quarter.json.sha256`

- [ ] **Step 1: Add `storage/` to `.gitignore`**

Open `.gitignore` and add after the existing `dataset/raw/` line:

```gitignore
# Runtime raw snapshots and generated artifacts
storage/raw/
storage/
```

The full block in `.gitignore` should look like:

```gitignore
# Data / artifacts (large files, not for git)
data/raw/
data/cache/
artifacts/
dataset/raw/
storage/raw/
storage/
```

- [ ] **Step 2: Delete stale quarter files**

Run:

```bash
rm dataset/raw/bctc/DHG/balance_sheet_quarter.json
rm dataset/raw/bctc/DHG/balance_sheet_quarter.json.sha256
rm dataset/raw/bctc/DHG/cash_flow_quarter.json
rm dataset/raw/bctc/DHG/cash_flow_quarter.json.sha256
rm dataset/raw/bctc/DHG/income_statement_quarter.json
rm dataset/raw/bctc/DHG/income_statement_quarter.json.sha256
rm dataset/raw/bctc/DHG/ratio_quarter.json
rm dataset/raw/bctc/DHG/ratio_quarter.json.sha256
```

Verify nothing is left:

```bash
ls dataset/raw/bctc/DHG/
```

Expected: only `*_year.json` and `*_year.json.sha256` files remain.

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: add storage/raw to gitignore; delete stale quarter raw files"
```

---

## Task 2: Write tests for raw snapshot dedup and manifest logic

**Files:**
- Create: `tests/test_raw_ingestion_hygiene.py`

- [ ] **Step 1: Create the test file**

```python
"""Tests for raw ingestion hygiene: dedup, manifest, path routing."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.db.source_registry import SourceRegistry, IngestionManifest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_registry(tmp_path: Path) -> SourceRegistry:
    mock_store = MagicMock()
    reg = SourceRegistry(store=mock_store)
    reg._raw_base = tmp_path / "storage" / "raw"
    return reg


# ---------------------------------------------------------------------------
# Test: raw snapshot path uses storage/raw, not dataset/raw
# ---------------------------------------------------------------------------

def test_save_raw_snapshot_writes_to_storage_raw(tmp_registry: SourceRegistry, tmp_path: Path) -> None:
    payload = b'{"test": 1}'
    out_path = tmp_registry._raw_base / "bctc" / "DHG" / "income_statement_year.json"
    checksum = tmp_registry.save_raw_snapshot(payload=payload, out_path=out_path)

    assert out_path.exists(), "Raw file must be written"
    assert out_path.with_suffix(out_path.suffix + ".sha256").exists(), "Checksum file must exist"
    assert checksum == hashlib.sha256(payload).hexdigest()
    assert "dataset" not in str(out_path), "Path must not go through dataset/"


# ---------------------------------------------------------------------------
# Test: dedup skips write when payload hash already exists
# ---------------------------------------------------------------------------

def test_save_raw_snapshot_dedup_skips_write_on_same_hash(tmp_registry: SourceRegistry, tmp_path: Path) -> None:
    payload = b'{"same": true}'
    out_path = tmp_registry._raw_base / "bctc" / "DHG" / "income_statement_year.json"

    checksum1 = tmp_registry.save_raw_snapshot(payload=payload, out_path=out_path)
    mtime_first = out_path.stat().st_mtime

    # Second call with same payload and SAME out_path — should NOT re-write the file.
    checksum2 = tmp_registry.save_raw_snapshot(payload=payload, out_path=out_path)
    mtime_second = out_path.stat().st_mtime

    assert checksum1 == checksum2
    assert mtime_first == mtime_second, "File must not be overwritten when hash matches"


def test_save_raw_snapshot_overwrites_when_payload_changes(tmp_registry: SourceRegistry, tmp_path: Path) -> None:
    payload_v1 = b'{"version": 1}'
    payload_v2 = b'{"version": 2}'
    out_path = tmp_registry._raw_base / "bctc" / "DHG" / "income_statement_year.json"

    tmp_registry.save_raw_snapshot(payload=payload_v1, out_path=out_path)
    checksum2 = tmp_registry.save_raw_snapshot(payload=payload_v2, out_path=out_path)

    assert out_path.read_bytes() == payload_v2, "File must be overwritten when payload changes"
    assert checksum2 == hashlib.sha256(payload_v2).hexdigest()


# ---------------------------------------------------------------------------
# Test: write_ingestion_manifest creates manifest.json
# ---------------------------------------------------------------------------

def test_write_ingestion_manifest_creates_file(tmp_registry: SourceRegistry, tmp_path: Path) -> None:
    run_dir = tmp_registry._raw_base / "bctc" / "DHG" / "run_20260523T120000"
    manifest = IngestionManifest(
        ingestion_run_id="run_20260523T120000",
        ticker="DHG",
        provider="vnstock_VCI",
        period_mode="year",
        required_periods=["2021FY", "2022FY", "2023FY", "2024FY", "2025FY"],
        files=[
            {
                "name": "income_statement_year.json",
                "endpoint": "income_statement",
                "period": "year",
                "row_count": 80,
                "payload_sha256": "abc123",
                "status": "ok",
            }
        ],
        created_at="2026-05-23T12:00:00+00:00",
    )
    tmp_registry.write_ingestion_manifest(run_dir=run_dir, manifest=manifest)

    manifest_path = run_dir / "manifest.json"
    assert manifest_path.exists()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["ticker"] == "DHG"
    assert data["period_mode"] == "year"
    assert len(data["files"]) == 1
    assert data["files"][0]["row_count"] == 80


# ---------------------------------------------------------------------------
# Test: BCTC row-count gate
# ---------------------------------------------------------------------------

def test_bctc_row_count_gate_passes_for_sufficient_rows() -> None:
    from scripts.connectors.vnstock_finance_connector import _check_bctc_frame_quality
    import pandas as pd

    # 30 rows × 5 period columns = adequate
    df = pd.DataFrame({"item": [f"r{i}" for i in range(30)], "2021FY": [1.0]*30, "2022FY": [2.0]*30})
    result = _check_bctc_frame_quality(df, statement="income_statement", from_year=2021, to_year=2022)
    assert result["status"] == "ok"
    assert result["row_count"] == 30


def test_bctc_row_count_gate_fails_for_empty_frame() -> None:
    from scripts.connectors.vnstock_finance_connector import _check_bctc_frame_quality
    import pandas as pd

    df = pd.DataFrame()
    result = _check_bctc_frame_quality(df, statement="income_statement", from_year=2021, to_year=2025)
    assert result["status"] == "source_limited"
    assert result["row_count"] == 0


def test_bctc_row_count_gate_fails_for_too_few_rows() -> None:
    from scripts.connectors.vnstock_finance_connector import _check_bctc_frame_quality
    import pandas as pd

    # Only 2 rows — below the minimum for a BCTC income statement
    df = pd.DataFrame({"item": ["r1", "r2"], "2024FY": [1.0, 2.0]})
    result = _check_bctc_frame_quality(df, statement="income_statement", from_year=2024, to_year=2024)
    assert result["status"] == "source_limited"
```

- [ ] **Step 2: Run tests to verify they fail (functions don't exist yet)**

```bash
pytest tests/test_raw_ingestion_hygiene.py -v
```

Expected: multiple `ImportError` or `AttributeError` — `IngestionManifest`, `_check_bctc_frame_quality`, `write_ingestion_manifest`, `_raw_base` don't exist yet.

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_raw_ingestion_hygiene.py
git commit -m "test: add failing tests for raw ingestion hygiene (dedup, manifest, quality gate)"
```

---

## Task 3: Implement `IngestionManifest` dataclass and `write_ingestion_manifest` in `SourceRegistry`

**Files:**
- Modify: `scripts/db/source_registry.py`

- [ ] **Step 1: Add `IngestionManifest` dataclass and update `SourceRegistry`**

Replace the full contents of `scripts/db/source_registry.py` with:

```python
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, UTC
from pathlib import Path

from scripts.db.fact_store import PostgresFactStore


@dataclass(frozen=True)
class SourceVersionInput:
    source_id: str
    source_uri: str
    source_type: str
    checksum: str
    connector_version: str
    raw_path: str | None = None
    effective_date: str | None = None
    published_at: str | None = None
    notes: str | None = None


@dataclass
class IngestionManifest:
    ingestion_run_id: str
    ticker: str
    provider: str
    period_mode: str
    required_periods: list[str]
    files: list[dict]
    created_at: str
    overall_status: str = "ok"


class SourceRegistry:
    def __init__(self, store: PostgresFactStore | None = None) -> None:
        self.store = store or PostgresFactStore()
        # Override in tests via reg._raw_base = tmp_path / ...
        from scripts.dataset.config_io import ROOT
        self._raw_base = ROOT / "storage" / "raw"

    @staticmethod
    def compute_checksum(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def compute_version_id(source_id: str, source_uri: str, checksum: str) -> str:
        raw = f"{source_id}|{source_uri}|{checksum}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def get_latest_by_uri(self, source_id: str, source_uri: str) -> tuple[str, str] | None:
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, checksum
                    FROM source_versions
                    WHERE source_id = %s AND source_uri = %s
                    ORDER BY ingested_at DESC
                    LIMIT 1
                    """,
                    (source_id, source_uri),
                )
                row = cur.fetchone()
        if row is None:
            return None
        return row[0], row[1]

    def register_version(self, data: SourceVersionInput) -> str:
        version_id = self.compute_version_id(data.source_id, data.source_uri, data.checksum)
        with self.store.conn() as connection:
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO source_versions
                    (id, source_id, source_uri, source_type, effective_date, published_at,
                     ingested_at, checksum, connector_version, raw_path, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        version_id,
                        data.source_id,
                        data.source_uri,
                        data.source_type,
                        data.effective_date,
                        data.published_at,
                        data.checksum,
                        data.connector_version,
                        data.raw_path,
                        data.notes,
                    ),
                )
        return version_id

    def save_raw_snapshot(self, payload: bytes, out_path: Path) -> str:
        """Write payload bytes to out_path. Skips write if existing file has the same hash.

        Returns the sha256 hex digest of the payload.
        """
        checksum = self.compute_checksum(payload)
        checksum_path = out_path.with_suffix(out_path.suffix + ".sha256")

        # Dedup: if file exists and checksum matches, do not overwrite.
        if out_path.exists() and checksum_path.exists():
            existing_checksum = checksum_path.read_text(encoding="utf-8").strip()
            if existing_checksum == checksum:
                return checksum

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        checksum_path.write_text(checksum, encoding="utf-8")
        return checksum

    def write_ingestion_manifest(self, run_dir: Path, manifest: IngestionManifest) -> Path:
        """Write a manifest.json file into run_dir describing the ingestion run."""
        run_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(asdict(manifest), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return manifest_path
```

- [ ] **Step 2: Run the tests — they should pass for dedup and manifest tests**

```bash
pytest tests/test_raw_ingestion_hygiene.py::test_save_raw_snapshot_writes_to_storage_raw tests/test_raw_ingestion_hygiene.py::test_save_raw_snapshot_dedup_skips_write_on_same_hash tests/test_raw_ingestion_hygiene.py::test_save_raw_snapshot_overwrites_when_payload_changes tests/test_raw_ingestion_hygiene.py::test_write_ingestion_manifest_creates_file -v
```

Expected: 4 PASS. The BCTC gate tests will still fail (no `_check_bctc_frame_quality` yet).

- [ ] **Step 3: Commit**

```bash
git add scripts/db/source_registry.py
git commit -m "feat: add IngestionManifest, hash-dedup, and write_ingestion_manifest to SourceRegistry"
```

---

## Task 4: Change raw snapshot paths in connectors from `dataset/raw/` → `storage/raw/`

**Files:**
- Modify: `scripts/connectors/vnstock_finance_connector.py` — `_register_source_version()`
- Modify: `scripts/connectors/vnstock_company_connector.py` — `_register_payload()`

The change is: replace `ROOT / "dataset" / "raw"` with `registry._raw_base` in both places. This means connectors no longer hardcode the path — they delegate to the registry's configured base.

- [ ] **Step 1: Update `_register_source_version` in `vnstock_finance_connector.py`**

Find the function `_register_source_version` at approximately line 268. Change:

```python
    raw_path = ROOT / "dataset" / "raw" / "bctc" / ticker / f"{statement}_{period}.json"
    checksum = registry.save_raw_snapshot(payload=payload, out_path=raw_path)
```

to:

```python
    raw_path = registry._raw_base / "bctc" / ticker / f"{statement}_{period}.json"
    checksum = registry.save_raw_snapshot(payload=payload, out_path=raw_path)
```

- [ ] **Step 2: Update `_register_payload` in `vnstock_company_connector.py`**

Find `_register_payload` at approximately line 39. Change:

```python
    raw_path = ROOT / "dataset" / "raw" / "market" / datetime.now(UTC).date().isoformat() / f"{ticker}_{endpoint}.json"
    checksum = registry.save_raw_snapshot(payload=payload, out_path=raw_path)
```

to:

```python
    raw_path = registry._raw_base / "market" / datetime.now(UTC).date().isoformat() / f"{ticker}_{endpoint}.json"
    checksum = registry.save_raw_snapshot(payload=payload, out_path=raw_path)
```

- [ ] **Step 3: Run the path test to confirm it still passes**

```bash
pytest tests/test_raw_ingestion_hygiene.py::test_save_raw_snapshot_writes_to_storage_raw -v
```

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/connectors/vnstock_finance_connector.py scripts/connectors/vnstock_company_connector.py
git commit -m "fix: redirect raw snapshot writes from dataset/raw to storage/raw via registry._raw_base"
```

---

## Task 5: Implement `_check_bctc_frame_quality` in `vnstock_finance_connector.py`

This function validates that a financial statement DataFrame has enough rows to be useful. It does not block ingestion — it returns a status dict that the caller uses to annotate the manifest.

**Files:**
- Modify: `scripts/connectors/vnstock_finance_connector.py`

- [ ] **Step 1: Add `_check_bctc_frame_quality` after the existing imports section**

Add this function near the top of `vnstock_finance_connector.py`, after `_VND_BN_DIVISOR`:

```python
# Minimum number of labelled line items expected in each BCTC statement type.
_MIN_BCTC_ROWS: dict[str, int] = {
    "income_statement": 10,
    "balance_sheet": 10,
    "cash_flow": 8,
    "ratio": 3,
}


def _check_bctc_frame_quality(
    frame: "pd.DataFrame",
    statement: str,
    from_year: int,
    to_year: int,
) -> dict:
    """Return a quality summary for a raw BCTC DataFrame.

    Returns a dict with keys:
        status: "ok" | "source_limited"
        row_count: int
        period_columns_found: list[str]
        required_periods_missing: list[str]
    """
    if frame.empty:
        return {
            "status": "source_limited",
            "row_count": 0,
            "period_columns_found": [],
            "required_periods_missing": [f"{y}FY" for y in range(from_year, to_year + 1)],
        }

    row_count = len(frame)
    min_rows = _MIN_BCTC_ROWS.get(statement, 5)

    period_columns_found = [
        str(col) for col in frame.columns if _period_from_column(str(col))
    ]
    required_periods = {f"{y}FY" for y in range(from_year, to_year + 1)}
    found_fy_labels = set()
    for col in period_columns_found:
        parsed = _period_from_column(col)
        if parsed and parsed[1] == "FY":
            found_fy_labels.add(f"{parsed[0]}FY")

    required_periods_missing = sorted(required_periods - found_fy_labels)

    status = "ok" if row_count >= min_rows else "source_limited"

    return {
        "status": status,
        "row_count": row_count,
        "period_columns_found": period_columns_found,
        "required_periods_missing": required_periods_missing,
    }
```

- [ ] **Step 2: Run the BCTC gate tests**

```bash
pytest tests/test_raw_ingestion_hygiene.py::test_bctc_row_count_gate_passes_for_sufficient_rows tests/test_raw_ingestion_hygiene.py::test_bctc_row_count_gate_fails_for_empty_frame tests/test_raw_ingestion_hygiene.py::test_bctc_row_count_gate_fails_for_too_few_rows -v
```

Expected: 3 PASS.

- [ ] **Step 3: Run all hygiene tests to confirm nothing is broken**

```bash
pytest tests/test_raw_ingestion_hygiene.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add scripts/connectors/vnstock_finance_connector.py
git commit -m "feat: add _check_bctc_frame_quality row-count gate for financial statement ingestion"
```

---

## Task 6: Wire `_check_bctc_frame_quality` into `sync_financial_for_ticker` and emit per-run manifest

The gate result should be logged and included in the inventory artifact. We also write an `IngestionManifest` to `storage/raw/bctc/<ticker>/run_<run_id>/manifest.json`.

**Files:**
- Modify: `scripts/connectors/vnstock_finance_connector.py` — `sync_financial_for_ticker()`

- [ ] **Step 1: Update `sync_financial_for_ticker` to call the quality gate and write the manifest**

Find `sync_financial_for_ticker`. The existing loop over `frames.items()` (approximately lines 362–387) processes each statement. Replace the loop body with a version that also runs the quality gate and accumulates manifest entries:

```python
    from scripts.db.source_registry import IngestionManifest

    all_facts: list[FinancialFact] = []
    parser_version = "vn_fin_parser_v1"
    manifest_files: list[dict] = []

    for statement, frame in frames.items():
        quality = _check_bctc_frame_quality(
            frame=frame,
            statement=statement,
            from_year=from_year,
            to_year=to_year,
        )
        if quality["status"] == "source_limited":
            print(
                f"[finance] {ticker} {statement}: source_limited "
                f"(row_count={quality['row_count']}, "
                f"missing_periods={quality['required_periods_missing']})"
            )

        if frame.empty:
            manifest_files.append({
                "name": f"{statement}_{period}.json",
                "endpoint": statement,
                "period": period,
                "row_count": 0,
                "payload_sha256": None,
                "status": "empty",
                "quality": quality,
            })
            continue

        statement_type = _statement_taxonomy_type.get(statement)
        alias_map = _build_alias_map(statement=statement_type)
        source_version_id = _register_source_version(
            registry=registry,
            ticker=ticker,
            source=provider_used,
            statement=statement,
            period=period,
            frame=frame,
        )
        # Derive the checksum that was just written.
        raw_path = registry._raw_base / "bctc" / ticker / f"{statement}_{period}.json"
        sha256 = raw_path.with_suffix(raw_path.suffix + ".sha256").read_text(encoding="utf-8").strip() if raw_path.with_suffix(raw_path.suffix + ".sha256").exists() else None

        manifest_files.append({
            "name": f"{statement}_{period}.json",
            "endpoint": statement,
            "period": period,
            "row_count": quality["row_count"],
            "payload_sha256": sha256,
            "status": quality["status"],
            "quality": quality,
        })

        facts = _extract_facts_from_frame(
            ticker=ticker,
            frame=frame,
            source_version_id=source_version_id,
            parser_version=parser_version,
            alias_map=alias_map,
            run_id=run_id,
            provider=provider_used,
            statement_type=statement,
            period_type=period,
        )
        all_facts.extend(facts)

    # Write the per-run manifest.
    required_periods = [f"{y}FY" for y in range(from_year, to_year + 1)]
    overall_status = "ok" if all(f["status"] in {"ok", "empty"} for f in manifest_files) else "source_limited"
    manifest = IngestionManifest(
        ingestion_run_id=run_id,
        ticker=ticker,
        provider=f"vnstock_{provider_used}",
        period_mode=period,
        required_periods=required_periods,
        files=manifest_files,
        created_at=datetime.now(UTC).isoformat(),
        overall_status=overall_status,
    )
    run_dir = registry._raw_base / "bctc" / ticker / f"run_{run_id}"
    registry.write_ingestion_manifest(run_dir=run_dir, manifest=manifest)
    print(f"[finance] {ticker}: manifest → {run_dir / 'manifest.json'} (status={overall_status})")
```

The old loop body (lines 363–387) is replaced entirely with the above. The code that follows (dedup of facts, skipping quarterly, etc.) remains unchanged.

- [ ] **Step 2: Run all hygiene tests**

```bash
pytest tests/test_raw_ingestion_hygiene.py -v
```

Expected: all 8 PASS.

- [ ] **Step 3: Run a smoke test against the real pipeline (requires DB)**

```bash
python scripts/ingest_ticker.py --ticker DHG --years 5 --skip-catalysts
```

Expected output includes:
- `[finance] DHG: manifest → storage/raw/bctc/DHG/run_.../manifest.json (status=ok or source_limited)`
- `[ingest] inventory saved → artifacts/runs/...`
- No `dataset/raw/` paths in output.

- [ ] **Step 4: Commit**

```bash
git add scripts/connectors/vnstock_finance_connector.py
git commit -m "feat: wire quality gate and per-run manifest into sync_financial_for_ticker"
```

---

## Self-Review

**Spec coverage check:**

| Requirement | Task |
|---|---|
| Move `dataset/raw/` → `storage/raw/` | Task 1 (gitignore) + Task 4 (connector paths) |
| Delete stale quarter files | Task 1 |
| Dedup by payload hash | Task 3 (save_raw_snapshot) |
| Add per-run manifest with row_count, sha256, status | Task 3 + Task 6 |
| BCTC row-count quality gate | Task 5 |
| Wire gate into ingestion flow, log source_limited | Task 6 |
| `IngestionManifest` dataclass | Task 3 |
| Connector path change in finance connector | Task 4 |
| Connector path change in company connector | Task 4 |
| Tests for all new behaviors | Task 2 |

**Placeholder scan:** No TBD, no "add validation later", no "similar to Task N" without code. All steps show actual code.

**Type consistency check:**
- `IngestionManifest` defined in Task 3, imported in Task 6 via `from scripts.db.source_registry import IngestionManifest` ✓
- `_check_bctc_frame_quality` defined in Task 5, called in Task 6 ✓
- `registry._raw_base` introduced in Task 3 (SourceRegistry), used in Task 4 (connectors) and Task 6 (manifest path) ✓
- `write_ingestion_manifest(run_dir, manifest)` signature in Task 3 matches usage in Task 6 ✓

**Known limitations not covered by this plan:**
- Company connector (`vnstock_company_connector.py`) still accumulates date-folder snapshots without a manifest. The dedup hash check prevents writing identical payloads twice, which mitigates the day-duplication problem. A full manifest for company snapshots is out of scope for this plan.
- `ratio_year.json` (provider-computed ratios) continues to be saved as reference raw data. The plan does not prevent this — it is acceptable as a reference-only artifact per the spec.
- Price connector path is not changed in this plan (price data has different accumulation semantics — daily rows, not bulk snapshots).
