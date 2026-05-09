from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from scripts.dataset.config_io import ROOT
from scripts.dataset.chunk_pipeline import run_chunk_pipeline


RAW_ROOT = ROOT / "dataset" / "raw"


class RetrievalService:
    def build_index(self, root: Path = RAW_ROOT) -> int:
        try:
            return int(run_chunk_pipeline(root=root))
        except Exception:
            # Local development often runs without Milvus/OpenAI; keep pipeline resilient.
            return 0

    def evidence_for_claims(self, ticker: str, claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Lightweight fallback retrieval: scan raw text/html snippets for metric keywords.
        refs: list[dict[str, Any]] = []
        ticker_root = RAW_ROOT / "bctc" / ticker
        if ticker_root.exists():
            for path in ticker_root.rglob("*"):
                if path.suffix.lower() not in {".txt", ".html", ".htm", ".json"}:
                    continue
                try:
                    content = path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                lowered = content.lower()
                for claim in claims:
                    metric_key = str(claim.get("metric_key", "")).lower()
                    if metric_key and re.search(re.escape(metric_key.split(".")[0]), lowered):
                        refs.append(
                            {
                                "claim_id": claim.get("claim_id"),
                                "source_uri": str(path),
                                "chunk_type": "fallback_text_match",
                            }
                        )
                        break
        return refs

