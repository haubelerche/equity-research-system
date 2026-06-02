"""
Ensures the pip-installed vnstock is found before the local vnstock/ reference folder.

The project root contains a `vnstock/` directory (a cloned reference repo) that Python
treats as a namespace package, shadowing the pip-installed `vnstock` package.
Reordering sys.path so that site-packages comes before '' (CWD) fixes the shadow.

Import this module before any `from vnstock import ...` statement.
"""
from __future__ import annotations

import sys


def _fix_vnstock_path() -> None:
    if "" in sys.path:
        sys.path = [p for p in sys.path if p != ""] + [""]


_fix_vnstock_path()
