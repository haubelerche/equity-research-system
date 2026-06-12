"""Single source of truth for coercing a fact-like input to float."""
from __future__ import annotations
from typing import Any


def entry_value(entry: Any) -> float | None:
    """Coerce a FactEntry / number / numeric-string / fact-dict to float."""
    if entry is None:
        return None
    if hasattr(entry, "value"):
        return entry_value(entry.value)
    if isinstance(entry, bool):
        raise TypeError(f"entry_value: refusing to coerce bool {entry!r}")
    if isinstance(entry, (int, float)):
        return float(entry)
    if isinstance(entry, str):
        try:
            return float(entry.replace(",", "").strip())
        except ValueError as exc:
            raise TypeError(f"entry_value: non-numeric string {entry!r}") from exc
    if isinstance(entry, dict):
        for key in ("value", "amount", "val"):
            if key in entry and entry[key] is not None:
                return entry_value(entry[key])
        raise TypeError(f"entry_value: dict has no numeric value key: keys={sorted(entry)}")
    raise TypeError(f"entry_value: unsupported type {type(entry).__name__}: {entry!r}")
