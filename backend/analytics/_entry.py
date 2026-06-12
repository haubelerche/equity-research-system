"""Single source of truth for coercing a fact-like input to float."""
from __future__ import annotations
from typing import Any


def entry_value(entry: Any, _depth: int = 0) -> float | None:
    """Coerce a FactEntry / number / numeric-string / fact-dict to float."""
    # Raises TypeError (not ValueError) when the input cannot be interpreted as a number.
    if _depth > 10:
        raise TypeError(
            f"entry_value: recursion depth exceeded — possible circular .value reference: {type(entry).__name__}"
        )
    if entry is None:
        return None
    if hasattr(entry, "value"):
        return entry_value(entry.value, _depth + 1)
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
            if key in entry:
                return entry_value(entry[key], _depth + 1) if entry[key] is not None else None
        raise TypeError(f"entry_value: dict has no numeric value key: keys={sorted(entry)}")
    raise TypeError(f"entry_value: unsupported type {type(entry).__name__}: {entry!r}")
