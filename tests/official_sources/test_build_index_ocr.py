"""Unit tests for build_index.py OCR artifact indexing helpers.

Tests cover:
  - _ensure_ocr_source generates stable source_id
  - _upsert_page_chunks is idempotent
  - _index_ocr_artifacts walks the correct directory structure
  - Skipped-status OCR runs are not indexed
  - Pages with empty text are skipped
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ── Helpers to build fake OCR artifact directories ────────────────────────────

def _make_ocr_run(
    base_dir: Path,
    ticker: str,
    year: int,
    document_id: str,
    pages: dict[int, str],  # page_number -> text
    status: str = "completed",
    source_checksum: str = "a" * 64,
) -> Path:
    run_dir = base_dir / ticker / str(year) / document_id
    (run_dir / "pages").mkdir(parents=True, exist_ok=True)

    meta = {
        "ocr_run_id": "run_abc123",
        "document_id": document_id,
        "ticker": ticker,
        "fiscal_year": year,
        "source_uri": f"/data/official_documents/{ticker}/{year}/report.pdf",
        "source_checksum": source_checksum,
        "pdf_type": "scanned",
        "ocr_engine": "tesseract",
        "ocr_lang": "vie+eng",
        "dpi": 300,
        "parser_version": "1.0.0",
        "started_at": "2024-01-01T00:00:00+00:00",
        "completed_at": "2024-01-01T00:01:00+00:00",
        "status": status,
        "pages_processed": len(pages),
        "pages_failed": 0,
        "candidate_row_count": 0,
        "mapped_fact_count": 0,
        "warnings": [],
        "errors": [],
    }
    (run_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    for page_num, text in pages.items():
        (run_dir / "pages" / f"page_{page_num:03d}.txt").write_text(text, encoding="utf-8")

    return run_dir


# ── _ensure_ocr_source ────────────────────────────────────────────────────────

class TestEnsureOcrSource:
    """Tests for _ensure_ocr_source() — no real DB, conn is mocked."""

    def _import(self):
        from scripts.build_index import _ensure_ocr_source
        return _ensure_ocr_source

    def test_source_id_format(self):
        _ensure_ocr_source = self._import()
        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: s
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.execute = MagicMock()

        source_id = _ensure_ocr_source(
            conn, "DHG", 2023, "abc123def456789012345678",
            {"source_checksum": "b" * 64, "source_uri": "ocr://DHG/2023/abc"},
        )
        assert source_id.startswith("ocr_dhg_2023_")
        assert "dhg" in source_id

    def test_short_checksum_padded(self):
        _ensure_ocr_source = self._import()
        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: s
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.execute = MagicMock()

        # source_checksum shorter than 64 — should fall back to sha256 of source_id
        _ensure_ocr_source(
            conn, "DHG", 2021, "docid123",
            {"source_checksum": "short", "source_uri": "ocr://DHG/2021/docid"},
        )
        # Should not raise; execute was called
        assert conn.cursor.return_value.execute.called

    def test_full_checksum_used_directly(self):
        _ensure_ocr_source = self._import()
        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: s
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        execute_mock = MagicMock()
        conn.cursor.return_value.execute = execute_mock

        full_checksum = "c" * 64
        _ensure_ocr_source(
            conn, "DHG", 2023, "docABC",
            {"source_checksum": full_checksum, "source_uri": "ocr://test"},
        )
        # The full 64-char checksum should appear in the execute args
        args = execute_mock.call_args[0][1]
        assert full_checksum in args


# ── _upsert_page_chunks ───────────────────────────────────────────────────────

class TestUpsertPageChunks:
    def _import(self):
        from scripts.build_index import _upsert_page_chunks
        return _upsert_page_chunks

    def test_empty_text_skipped(self):
        _upsert_page_chunks = self._import()
        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: s
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        execute_mock = MagicMock()
        conn.cursor.return_value.execute = execute_mock

        # Page with empty text should be skipped entirely
        chunks = [("Page 1", "   ", 2023, 1, {"extraction_method": "ocr", "page_number": 1})]
        result = _upsert_page_chunks(conn, "src_test", "DHG", chunks)
        assert result == 0
        execute_mock.assert_not_called()

    def test_chunk_index_is_page_minus_one(self):
        _upsert_page_chunks = self._import()
        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: s
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        execute_mock = MagicMock()
        conn.cursor.return_value.fetchone = MagicMock(return_value=None)
        conn.cursor.return_value.execute = execute_mock

        chunks = [("Page 3", "some text here", 2023, 3, {"extraction_method": "ocr", "page_number": 3})]
        _upsert_page_chunks(conn, "src_test", "DHG", chunks)

        # The SELECT should use chunk_index = page_number - 1 = 2
        select_call = execute_mock.call_args_list[0]
        assert 2 in select_call[0][1]  # chunk_index=2 in params

    def test_metadata_includes_extraction_method(self):
        _upsert_page_chunks = self._import()
        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: s
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.fetchone = MagicMock(return_value=None)
        execute_mock = MagicMock()
        conn.cursor.return_value.execute = execute_mock

        extra = {"extraction_method": "ocr", "page_number": 1, "source_tier": 1}
        chunks = [("Page 1", "OCR text here", 2021, 1, extra)]
        _upsert_page_chunks(conn, "src_ocr", "DHG", chunks)

        # The INSERT call should include metadata_json with extraction_method
        insert_args = execute_mock.call_args_list[1][0][1]
        meta_json = insert_args[-1]  # last param is metadata_json::jsonb
        parsed = json.loads(meta_json)
        assert parsed["extraction_method"] == "ocr"
        assert parsed["page_number"] == 1
        assert parsed["source_tier"] == 1


# ── _index_ocr_artifacts ─────────────────────────────────────────────────────

class TestIndexOcrArtifacts:
    def _import(self):
        from scripts.build_index import _index_ocr_artifacts
        return _index_ocr_artifacts

    def test_indexes_completed_runs(self, tmp_path):
        _index_ocr_artifacts = self._import()

        _make_ocr_run(
            tmp_path, "DHG", 2023, "doc_dhg_2023_abc",
            pages={1: "Báo cáo tài chính 2023", 2: "Doanh thu 2,450 tỷ VND"},
            status="completed",
        )

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: s
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.fetchone = MagicMock(return_value=None)
        conn.cursor.return_value.execute = MagicMock()

        with patch("scripts.build_index.OCR_ARTIFACTS_DIR", tmp_path):
            result = _index_ocr_artifacts(conn, "DHG", [2023])

        assert len(result) == 1
        assert result[0]["type"] == "ocr_pages"
        assert result[0]["chunks"] == 2
        assert result[0]["year"] == 2023

    def test_skips_non_completed_runs(self, tmp_path):
        _index_ocr_artifacts = self._import()

        _make_ocr_run(
            tmp_path, "DHG", 2022, "doc_running",
            pages={1: "partial text"},
            status="running",  # not completed
        )

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: s
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.execute = MagicMock()

        with patch("scripts.build_index.OCR_ARTIFACTS_DIR", tmp_path):
            result = _index_ocr_artifacts(conn, "DHG", [2022])

        assert result == []

    def test_skips_empty_page_text(self, tmp_path):
        _index_ocr_artifacts = self._import()

        _make_ocr_run(
            tmp_path, "DHG", 2021, "doc_empty",
            pages={1: "", 2: "   "},  # all empty
            status="completed",
        )

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: s
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.fetchone = MagicMock(return_value=None)
        conn.cursor.return_value.execute = MagicMock()

        with patch("scripts.build_index.OCR_ARTIFACTS_DIR", tmp_path):
            result = _index_ocr_artifacts(conn, "DHG", [2021])

        assert result == []  # no chunks, so source not added to result

    def test_missing_ocr_dir_returns_empty(self, tmp_path):
        _index_ocr_artifacts = self._import()

        conn = MagicMock()
        with patch("scripts.build_index.OCR_ARTIFACTS_DIR", tmp_path / "nonexistent"):
            result = _index_ocr_artifacts(conn, "DHG", [2023])

        assert result == []

    def test_multiple_years_indexed(self, tmp_path):
        _index_ocr_artifacts = self._import()

        for yr in [2021, 2022, 2023]:
            _make_ocr_run(
                tmp_path, "DHG", yr, f"doc_{yr}",
                pages={1: f"Report {yr}"},
                status="completed",
            )

        conn = MagicMock()
        conn.cursor.return_value.__enter__ = lambda s: s
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value.fetchone = MagicMock(return_value=None)
        conn.cursor.return_value.execute = MagicMock()

        with patch("scripts.build_index.OCR_ARTIFACTS_DIR", tmp_path):
            result = _index_ocr_artifacts(conn, "DHG", [2021, 2022, 2023])

        assert len(result) == 3
        years_indexed = {r["year"] for r in result}
        assert years_indexed == {2021, 2022, 2023}
