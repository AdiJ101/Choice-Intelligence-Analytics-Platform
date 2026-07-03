"""
dashboard/backend/db.py — MySQL connection pool for the Analytics Dashboard backend.

Reads MYSQL_DSN from the project .env file, parses it, and creates a pooled
connection manager. Credentials are URL-decoded (handles %23 → # etc.).
"""

from __future__ import annotations

import contextlib
import os
import urllib.parse

import mysql.connector.pooling
from dotenv import load_dotenv

# Load .env from project root (three levels up: dashboard/backend/ → project root)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

_dsn = os.environ.get("MYSQL_DSN", "")
if not _dsn:
    raise RuntimeError("MYSQL_DSN environment variable is not set")

_parsed = urllib.parse.urlparse(_dsn)

_pool = mysql.connector.pooling.MySQLConnectionPool(
    pool_name="analytics_pool",
    pool_size=5,
    host=_parsed.hostname or "localhost",
    port=_parsed.port or 3306,
    user=urllib.parse.unquote(_parsed.username or ""),
    password=urllib.parse.unquote(_parsed.password or ""),
    database=_parsed.path.lstrip("/"),
    charset="utf8mb4",
    use_unicode=True,
    autocommit=True,
)


@contextlib.contextmanager
def get_conn():
    """Yield a pooled MySQL connection; close it on exit."""
    conn = _pool.get_connection()
    try:
        yield conn
    finally:
        conn.close()
