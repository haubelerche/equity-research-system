"""Tests for backend.documents.pdf_extractor — all offline, no real PDF needed."""

import pytest
from backend.documents.pdf_extractor import (
    _slug_label,
    _parse_eps_raw,
    _parse_vnd_bn,
    _map_label_to_metric,
    ExtractedRow,
    VietnameseBCTCExtractor,
)


# ---------------------------------------------------------------------------
# _slug_label
# ---------------------------------------------------------------------------

class TestSlugLabel:
    def test_removes_diacritics(self):
        assert _slug_label("Doanh thu thuần") == "doanh thu thuan"

    def test_lowercase(self):
        assert _slug_label("LNST") == "lnst"

    def test_strips_whitespace(self):
        assert _slug_label("  test  ") == "test"

    def test_collapses_multiple_spaces(self):
        assert _slug_label("loi  nhuan  gop") == "loi nhuan gop"

    def test_empty_string(self):
        assert _slug_label("") == ""


# ---------------------------------------------------------------------------
# _parse_vnd_bn
# ---------------------------------------------------------------------------

class TestParseVndBn:
    def test_billions_value(self):
        # 4,127,400 triệu → 4127.4 tỷ
        result = _parse_vnd_bn("4,127,400")
        assert result is not None
        assert abs(result - 4127.4) < 0.01

    def test_already_in_bn(self):
        result = _parse_vnd_bn("4127.4")
        assert result is not None
        assert abs(result - 4127.4) < 0.01

    def test_negative(self):
        result = _parse_vnd_bn("(273,600)")
        assert result is not None
        assert abs(result - (-273.6)) < 0.01

    def test_none_on_blank(self):
        assert _parse_vnd_bn("") is None

    def test_none_on_dash(self):
        assert _parse_vnd_bn("—") is None

    def test_none_on_single_dash(self):
        assert _parse_vnd_bn("-") is None

    def test_none_on_na(self):
        assert _parse_vnd_bn("N/A") is None
        assert _parse_vnd_bn("n/a") is None

    def test_small_value_unchanged(self):
        # 123.5 tỷ — stays as-is
        result = _parse_vnd_bn("123.5")
        assert result is not None
        assert abs(result - 123.5) < 0.001

    def test_rounding(self):
        result = _parse_vnd_bn("1,234,567")
        assert result is not None
        # 1234567 > 500000 → divide by 1000 = 1234.567
        assert abs(result - 1234.567) < 0.001


# ---------------------------------------------------------------------------
# _map_label_to_metric
# ---------------------------------------------------------------------------

class TestMapLabelToMetric:
    def test_revenue_mapped(self):
        assert _map_label_to_metric("doanh thu thuan") == "revenue.net"

    def test_net_income_mapped(self):
        # "lnst - co dong cong ty me" slugged form
        assert _map_label_to_metric("loi nhuan sau thue cong ty me") == "net_income.parent"

    def test_total_assets_mapped(self):
        assert _map_label_to_metric("tong tai san") == "total_assets.ending"

    def test_operating_cash_flow_mapped(self):
        assert _map_label_to_metric(
            "luu chuyen tien thuan tu hoat dong kinh doanh"
        ) == "operating_cash_flow.total"

    def test_unknown_returns_none(self):
        assert _map_label_to_metric("completely unknown metric xyz") is None

    def test_gross_profit_mapped(self):
        assert _map_label_to_metric("loi nhuan gop") == "gross_profit.total"

    def test_operating_profit_mapped(self):
        assert _map_label_to_metric(
            "loi nhuan tu hoat dong kinh doanh"
        ) == "operating_profit.total"

    def test_profit_before_tax_mapped(self):
        assert _map_label_to_metric("loi nhuan truoc thue") == "profit_before_tax.total"

    def test_eps_basic_mapped(self):
        assert _map_label_to_metric("lai co ban tren co phieu") == "eps.basic"

    def test_total_liabilities_mapped(self):
        assert _map_label_to_metric("tong no phai tra") == "total_liabilities.ending"

    def test_cash_mapped(self):
        assert _map_label_to_metric("tien va tuong duong tien") == "cash_and_equivalents.ending"

    def test_capex_mapped(self):
        assert _map_label_to_metric("mua sam tai san co dinh") == "capex.total"

    def test_investing_cf_mapped(self):
        assert _map_label_to_metric(
            "luu chuyen tien thuan tu hoat dong dau tu"
        ) == "investing_cash_flow.total"

    def test_financing_cf_mapped(self):
        assert _map_label_to_metric(
            "luu chuyen tien thuan tu hoat dong tai chinh"
        ) == "financing_cash_flow.total"

    def test_lnst_cong_ty_me_variant(self):
        assert _map_label_to_metric("lnst cong ty me") == "net_income.parent"

    def test_equity_parent_mapped(self):
        assert _map_label_to_metric("von chu so huu cong ty me") == "equity.parent"

    def test_short_term_debt_mapped(self):
        assert _map_label_to_metric("vay ngan han") == "short_term_debt.ending"

    def test_long_term_debt_mapped(self):
        assert _map_label_to_metric("vay dai han") == "long_term_debt.ending"


# ---------------------------------------------------------------------------
# ExtractedRow
# ---------------------------------------------------------------------------

class TestExtractedRow:
    def _make_row(self) -> ExtractedRow:
        return ExtractedRow(
            ticker="DHG",
            fiscal_year=2023,
            period_type="annual",
            statement_type="income_statement",
            metric_id="revenue.net",
            value=4127.4,
            unit="vnd_bn",
            document_title="DHG BCTC 2023",
            page_number=5,
            table_name="Kết quả HĐKD",
            extracted_text="Doanh thu thuần về bán hàng",
            extraction_method="pdf_table",
            verified_by="",
            verified_at="",
        )

    def test_to_csv_row_has_all_fields(self):
        row = self._make_row()
        d = row.to_csv_dict()
        assert "metric_id" in d
        assert "value" in d
        assert "ticker" in d
        assert d["value"] == "4127.4"

    def test_to_csv_dict_returns_strings(self):
        row = self._make_row()
        d = row.to_csv_dict()
        for k, v in d.items():
            assert isinstance(v, str), f"Field {k!r} is not a string: {v!r}"

    def test_to_csv_dict_ticker(self):
        row = self._make_row()
        assert row.to_csv_dict()["ticker"] == "DHG"

    def test_to_csv_dict_fiscal_year(self):
        row = self._make_row()
        assert row.to_csv_dict()["fiscal_year"] == "2023"


# ---------------------------------------------------------------------------
# VietnameseBCTCExtractor
# ---------------------------------------------------------------------------

class TestVietnameseBCTCExtractor:
    def _make_extractor(self) -> VietnameseBCTCExtractor:
        return VietnameseBCTCExtractor(
            ticker="DHG",
            fiscal_year=2023,
            document_title="DHG BCTC 2023",
        )

    def test_extract_from_table_rows_income(self):
        extractor = self._make_extractor()
        rows = [
            ["Doanh thu thuần về bán hàng", "4,127,400", "3,850,100"],
            ["Lợi nhuận gộp", "1,834,400", "1,650,200"],
            ["LNST - cổ đông công ty mẹ", "803,100", "720,500"],
        ]
        extracted = extractor.extract_from_table_rows(
            rows,
            statement_type="income_statement",
            fiscal_years=[2023, 2022],
        )
        metric_ids = {r.metric_id for r in extracted}
        assert "revenue.net" in metric_ids
        assert "gross_profit.total" in metric_ids
        assert "net_income.parent" in metric_ids

    def test_values_converted_to_vnd_bn(self):
        extractor = self._make_extractor()
        rows = [["Doanh thu thuần về bán hàng", "4,127,400", ""]]
        extracted = extractor.extract_from_table_rows(
            rows,
            statement_type="income_statement",
            fiscal_years=[2023],
        )
        assert len(extracted) == 1
        assert abs(extracted[0].value - 4127.4) < 1.0

    def test_skips_unknown_metrics(self):
        extractor = self._make_extractor()
        rows = [["Chỉ tiêu không xác định XYZ", "999,999", ""]]
        extracted = extractor.extract_from_table_rows(
            rows,
            statement_type="income_statement",
            fiscal_years=[2023],
        )
        assert extracted == []

    def test_skips_empty_value_columns(self):
        extractor = self._make_extractor()
        rows = [["Doanh thu thuần về bán hàng", "4,127,400", "—"]]
        extracted = extractor.extract_from_table_rows(
            rows,
            statement_type="income_statement",
            fiscal_years=[2023, 2022],
        )
        # Only 2023 should produce a row; 2022 is "—"
        assert len(extracted) == 1
        assert extracted[0].fiscal_year == 2023

    def test_multiple_years_produces_multiple_rows(self):
        extractor = self._make_extractor()
        rows = [["Doanh thu thuần về bán hàng", "4,127,400", "3,850,100"]]
        extracted = extractor.extract_from_table_rows(
            rows,
            statement_type="income_statement",
            fiscal_years=[2023, 2022],
        )
        assert len(extracted) == 2
        years = {r.fiscal_year for r in extracted}
        assert years == {2023, 2022}

    def test_correct_statement_type_stored(self):
        extractor = self._make_extractor()
        rows = [["Tổng tài sản", "8,500,000", ""]]
        extracted = extractor.extract_from_table_rows(
            rows,
            statement_type="balance_sheet",
            fiscal_years=[2023],
        )
        assert len(extracted) == 1
        assert extracted[0].statement_type == "balance_sheet"

    def test_extract_from_pdf_returns_list(self):
        """extract_from_pdf on a non-existent path returns [] gracefully."""
        from pathlib import Path
        extractor = self._make_extractor()
        result = extractor.extract_from_pdf(Path("nonexistent_file_xyz.pdf"))
        assert isinstance(result, list)
        assert result == []

    def test_extract_from_pdf_handles_import_error(self, monkeypatch):
        """If pdfplumber is not importable, extract_from_pdf returns []."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pdfplumber":
                raise ImportError("pdfplumber not installed")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)

        from pathlib import Path
        extractor = self._make_extractor()
        result = extractor.extract_from_pdf(Path("any.pdf"))
        assert result == []

    def test_unit_is_vnd_bn_for_non_eps(self):
        extractor = self._make_extractor()
        rows = [["Doanh thu thuần về bán hàng", "4,127,400", ""]]
        extracted = extractor.extract_from_table_rows(
            rows,
            statement_type="income_statement",
            fiscal_years=[2023],
        )
        assert extracted[0].unit == "vnd_bn"

    def test_unit_is_vnd_for_eps(self):
        extractor = self._make_extractor()
        rows = [["Lãi cơ bản trên cổ phiếu", "7,500", ""]]
        extracted = extractor.extract_from_table_rows(
            rows,
            statement_type="income_statement",
            fiscal_years=[2023],
        )
        assert len(extracted) == 1
        assert extracted[0].metric_id == "eps.basic"
        assert extracted[0].unit == "vnd"

    def test_ticker_stored_on_row(self):
        extractor = self._make_extractor()
        rows = [["Doanh thu thuần về bán hàng", "4,127,400", ""]]
        extracted = extractor.extract_from_table_rows(
            rows,
            statement_type="income_statement",
            fiscal_years=[2023],
        )
        assert extracted[0].ticker == "DHG"


# ---------------------------------------------------------------------------
# Bug 1 regression: EPS must NOT be scaled by /1000
# ---------------------------------------------------------------------------

class TestEPSParsing:
    def test_eps_value_not_divided(self):
        """EPS '7,500' must produce 7500.0, not 7.5."""
        ext = VietnameseBCTCExtractor("DHG", 2023, "BCTN DHG 2023")
        rows = [["Lãi cơ bản trên cổ phiếu", "7,500", ""]]
        extracted = ext.extract_from_table_rows(
            rows, statement_type="income_statement", fiscal_years=[2023]
        )
        assert len(extracted) == 1
        assert extracted[0].metric_id == "eps.basic"
        assert extracted[0].value == pytest.approx(7500.0, abs=1.0)
        assert extracted[0].unit == "vnd"

    def test_negative_eps_value_correct(self):
        ext = VietnameseBCTCExtractor("DHG", 2023, "BCTN DHG 2023")
        rows = [["Lãi cơ bản trên cổ phiếu", "(2,000)", ""]]
        extracted = ext.extract_from_table_rows(
            rows, statement_type="income_statement", fiscal_years=[2023]
        )
        assert len(extracted) == 1
        assert extracted[0].value == pytest.approx(-2000.0, abs=1.0)

    def test_parse_eps_raw_plain(self):
        assert _parse_eps_raw("7,500") == pytest.approx(7500.0)

    def test_parse_eps_raw_negative(self):
        assert _parse_eps_raw("(2,000)") == pytest.approx(-2000.0)

    def test_parse_eps_raw_null(self):
        assert _parse_eps_raw("—") is None
        assert _parse_eps_raw("") is None


# ---------------------------------------------------------------------------
# Bug 2 regression: total_assets anchor — subtotals must not match
# ---------------------------------------------------------------------------

class TestTotalAssetsAnchor:
    def test_subtotal_ngan_han_not_mapped_to_total_assets(self):
        """'tong tai san ngan han' must NOT map to total_assets.ending."""
        assert _map_label_to_metric("tong tai san ngan han") is None

    def test_subtotal_dai_han_not_mapped_to_total_assets(self):
        """'tong tai san dai han' must NOT map to total_assets.ending."""
        assert _map_label_to_metric("tong tai san dai han") is None

    def test_total_assets_still_mapped(self):
        assert _map_label_to_metric("tong tai san") == "total_assets.ending"

    def test_tong_cong_tai_san_mapped(self):
        assert _map_label_to_metric("tong cong tai san") == "total_assets.ending"


# ---------------------------------------------------------------------------
# Bug 3 regression: lai co phieu thuong must NOT map to eps.basic
# ---------------------------------------------------------------------------

class TestFalsePositiveEPS:
    def test_lai_co_phieu_thuong_not_eps(self):
        """Common stock label must NOT map to eps.basic."""
        assert _map_label_to_metric("lai co phieu thuong") is None


# ---------------------------------------------------------------------------
# Bug 4 regression: IFRS-style debt labels must match
# ---------------------------------------------------------------------------

class TestModernDebtLabels:
    def test_ifrs_short_term_debt_mapped(self):
        m = _map_label_to_metric("vay va no thue tai chinh ngan han")
        assert m == "short_term_debt.ending"

    def test_ifrs_long_term_debt_mapped(self):
        m = _map_label_to_metric("vay va no thue tai chinh dai han")
        assert m == "long_term_debt.ending"
