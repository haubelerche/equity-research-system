from pathlib import Path

from backend.reporting import pdf_quality_gate


def _client_pdf_bytes(label: bytes = b"report") -> bytes:
    return b"%PDF-1.4\n" + label + (b"\n0" * 6000)


def test_pdf_quality_gate_rejects_raw_benchmark_stub(tmp_path: Path):
    pdf = tmp_path / "stub.pdf"
    pdf.write_bytes(_client_pdf_bytes(b"benchmark_valuation_v1 analyst draft"))

    result = pdf_quality_gate.validate_client_pdf(pdf)

    assert not result.passed
    assert "forbidden_byte_marker:benchmark_valuation_v1" in result.reasons
    assert "forbidden_byte_marker:analyst draft" in result.reasons


def test_pdf_quality_gate_rejects_mojibake_in_extracted_text(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "mojibake.pdf"
    pdf.write_bytes(_client_pdf_bytes(b"clean binary payload"))
    monkeypatch.setattr(
        pdf_quality_gate,
        "_extract_pdf_text_best_effort",
        lambda path: "Khuyáº¿n nghá»‹ có ký tự lỗi vÃ trong text layer.",
    )

    result = pdf_quality_gate.validate_client_pdf(pdf)

    assert not result.passed
    assert "forbidden_text_marker:vÃ" in result.reasons


def test_pdf_quality_gate_ignores_mojibake_like_binary_noise(tmp_path: Path, monkeypatch):
    pdf = tmp_path / "real.pdf"
    pdf.write_bytes(_client_pdf_bytes("binary noise vÃ not text".encode("utf-8")))
    monkeypatch.setattr(
        pdf_quality_gate,
        "_extract_pdf_text_best_effort",
        lambda path: "Báo cáo nghiên cứu cổ phiếu sạch.",
    )

    result = pdf_quality_gate.validate_client_pdf(pdf)

    assert result.passed
    assert result.reasons == ()
