from __future__ import annotations

import hashlib
import json
from datetime import datetime, UTC
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def deterministic_id(*parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def compact_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

