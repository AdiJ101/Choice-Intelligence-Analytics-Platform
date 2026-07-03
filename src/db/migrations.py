"""
migrations.py — Lightweight SQL migration runner for the Customer Intelligence
& Analytics Platform.

Provides :func:`run_migrations`, which applies any pending ``.sql`` files from
a directory to a MySQL database in lexicographic order, tracking applied
migrations in a ``schema_migrations`` bookkeeping table.  The function is fully
idempotent: already-applied migrations are silently skipped on every subsequent
call.
"""

from __future__ import annotations

import os
from pathlib import Path

import mysql.connector


# ---------------------------------------------------------------------------
# DDL for the bookkeeping table
# ---------------------------------------------------------------------------

_CREATE_BOOKKEEPING_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id          INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    filename    VARCHAR(255)  NOT NULL,
    applied_at  DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_schema_migrations_filename (filename)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
"""

_SELECT_APPLIED = "SELECT filename FROM schema_migrations;"

_INSERT_APPLIED = "INSERT INTO schema_migrations (filename) VALUES (%s);"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_migrations(conn: mysql.connector.MySQLConnection, migrations_dir: str | Path) -> None:
    """Apply pending SQL migrations from *migrations_dir* to the database
    reachable through *conn*.

    The function:

    1. Creates the ``schema_migrations`` bookkeeping table if it doesn't already
       exist.
    2. Reads all ``.sql`` files from *migrations_dir*, sorted lexicographically
       by filename (ascending).
    3. For each file checks whether its filename is already recorded in
       ``schema_migrations``; if so, skips it.
    4. For unapplied files: reads the file, splits on ``';'`` to extract
       individual statements (strips whitespace, skips blank statements),
       executes each statement, then records the filename.
    5. Does **not** close *conn* — the caller retains ownership of the
       connection.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection` (or
        ``CMySQLConnection``) instance.  The caller is responsible for opening
        and closing the connection.
    migrations_dir:
        Path (``str`` or :class:`~pathlib.Path`) to the directory that contains
        ``.sql`` migration files.

    Raises
    ------
    Exception
        Any SQL error raised by ``mysql.connector`` is re-raised as-is; no
        errors are suppressed.
    FileNotFoundError
        If *migrations_dir* does not exist or is not a directory.
    """
    migrations_dir = Path(migrations_dir)
    if not migrations_dir.is_dir():
        raise FileNotFoundError(
            f"migrations_dir does not exist or is not a directory: {migrations_dir}"
        )

    cursor = conn.cursor()
    try:
        # 1. Ensure the bookkeeping table exists.
        cursor.execute(_CREATE_BOOKKEEPING_TABLE)
        conn.commit()

        # 2. Collect already-applied filenames.
        cursor.execute(_SELECT_APPLIED)
        applied: set[str] = {row[0] for row in cursor.fetchall()}

        # 3. Gather .sql files sorted lexicographically.
        sql_files = sorted(migrations_dir.glob("*.sql"), key=lambda p: p.name)

        for sql_file in sql_files:
            filename = sql_file.name

            # 4. Skip already-applied migrations.
            if filename in applied:
                continue

            # 5. Read, split, and execute each statement.
            raw_sql = sql_file.read_text(encoding="utf-8")
            statements = [stmt.strip() for stmt in raw_sql.split(";")]

            for statement in statements:
                if not statement:
                    continue
                cursor.execute(statement)

            # 6. Record the migration as applied.
            cursor.execute(_INSERT_APPLIED, (filename,))
            conn.commit()

    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# __main__ guard — run from the command line for manual bootstrapping
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    dsn = os.environ.get("MYSQL_DSN")
    if not dsn:
        print("ERROR: MYSQL_DSN environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    migrations_dir_env = os.environ.get("MIGRATIONS_DIR")
    if not migrations_dir_env:
        print("ERROR: MIGRATIONS_DIR environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    # Parse a mysql+mysqlconnector:// DSN into keyword arguments for
    # mysql.connector.connect().
    # Expected format: mysql+mysqlconnector://user:password@host:port/dbname
    # Fall back to treating the value as a plain host if it doesn't match the
    # expected scheme.
    import re

    _DSN_RE = re.compile(
        r"^(?:mysql\+mysqlconnector|mysql)://"
        r"(?P<user>[^:@]+)"
        r"(?::(?P<password>[^@]*))?"
        r"@(?P<host>[^:/]+)"
        r"(?::(?P<port>\d+))?"
        r"(?:/(?P<database>.+))?$"
    )

    match = _DSN_RE.match(dsn)
    if not match:
        print(
            f"ERROR: Could not parse MYSQL_DSN: {dsn!r}\n"
            "Expected format: mysql+mysqlconnector://user:password@host:port/dbname",
            file=sys.stderr,
        )
        sys.exit(1)

    connect_kwargs: dict = {
        "user": match.group("user"),
        "host": match.group("host"),
    }
    if match.group("password") is not None:
        connect_kwargs["password"] = match.group("password")
    if match.group("port") is not None:
        connect_kwargs["port"] = int(match.group("port"))
    if match.group("database") is not None:
        connect_kwargs["database"] = match.group("database")

    _conn = mysql.connector.connect(**connect_kwargs)
    try:
        run_migrations(_conn, migrations_dir_env)
        print("Migrations applied successfully.")
    finally:
        _conn.close()
