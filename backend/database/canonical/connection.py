"""Shared connection factory for v2 DAL modules."""
from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

from backend.database.config import connect_with_retry, require_database_url


def _dsn() -> str:
    return require_database_url()


@contextmanager
def get_conn(autocommit: bool = False):
    """Yield a psycopg2 connection. Commits on exit, rolls back on exception."""
    conn = connect_with_retry(_dsn())
    conn.autocommit = autocommit
    try:
        yield conn
        if not autocommit:
            conn.commit()
    except Exception:
        if not autocommit:
            conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def get_dict_conn():
    """Yield a psycopg2 connection with RealDictCursor as default factory."""
    with get_conn() as conn:
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        yield conn
