# DEV-ONLY: production rendering runs through scripts/run_research.py.
"""Render a caller-provided Markdown file to local development HTML/PDF.

This script is intentionally isolated from production run artifacts. It refuses
paths under `artifacts/runs` or `storage/runs`, never resolves latest artifacts,
and writes only to `storage/dev_report_runs/<dev_run_id>`.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import markdown as _markdown

ROOT = Path(__file__).resolve().parents[1]
DEV_REPORT_ROOT = ROOT / "storage" / "dev_report_runs"
PRODUCTION_ARTIFACT_ROOTS = (
    ROOT / "artifacts" / "runs",
    ROOT / "storage" / "runs",
)


def _safe_dev_run_id(raw: str | None) -> str:
    value = (raw or "manual_render").strip()
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    value = value.strip("._-")
    return value[:120] or "manual_render"


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _assert_dev_only_path(path: Path) -> None:
    resolved = path.resolve(strict=False)
    for root in PRODUCTION_ARTIFACT_ROOTS:
        if _is_relative_to(resolved, root.resolve(strict=False)):
            raise RuntimeError(
                "scripts/render_report.py is DEV-ONLY and refuses production "
                f"artifact paths: {resolved}"
            )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DEV-ONLY Markdown report renderer")
    parser.add_argument("--input-markdown", required=True, help="Path to a non-production Markdown file")
    parser.add_argument("--dev-run-id", default="manual_render", help="Development output namespace")
    parser.add_argument("--pdf", action="store_true", help="Also attempt PDF rendering")
    return parser.parse_args(argv)


def render_dev_markdown(input_markdown: str | Path, dev_run_id: str, pdf: bool = False) -> dict[str, str]:
    source = Path(input_markdown)
    _assert_dev_only_path(source)
    if not source.exists():
        raise FileNotFoundError(source)

    output_dir = DEV_REPORT_ROOT / _safe_dev_run_id(dev_run_id)
    _assert_dev_only_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_body = _markdown.markdown(
        source.read_text(encoding="utf-8"),
        extensions=["tables", "fenced_code", "sane_lists"],
    )
    html_path = output_dir / f"{source.stem}.html"
    html_path.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{source.stem}</title></head><body>{html_body}</body></html>",
        encoding="utf-8",
    )
    result = {"html": str(html_path)}

    if pdf:
        from backend.reporting.pdf_renderer import PDFRenderer

        pdf_path = PDFRenderer().render(
            html_path,
            output_dir=output_dir,
            run_id="",
            allow_stub=True,
        )
        result["pdf"] = str(pdf_path)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result = render_dev_markdown(args.input_markdown, args.dev_run_id, args.pdf)
    for key, path in result.items():
        print(f"[{key}] {path}")


if __name__ == "__main__":
    main()
