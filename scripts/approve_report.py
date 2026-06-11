"""Approval script — disabled.

Human approval gates have been removed from the pipeline.
All reports are auto-approved during the PUBLISH stage.
"""
from __future__ import annotations

import argparse
import sys


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="(Disabled) Human approval no longer required.")
    parser.add_argument("--run-id", dest="run_id")
    parser.add_argument("--stage", default="final")
    parser.add_argument("--decision", default="approve")
    parser.add_argument("--reviewer", default="auto")
    parser.add_argument("--comment", default="")
    parser.add_argument("--ticker")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    parse_args(argv)
    print("Approval gates have been removed. Reports are auto-approved at PUBLISH stage.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
