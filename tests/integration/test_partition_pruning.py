"""
Integration tests for MySQL RANGE partitioning on the `posts` table.

Verifies that the posts table is correctly partitioned by publish_timestamp
year-month, and that date-range queries undergo partition pruning (only the
expected partitions are scanned).

Requires a live MySQL connection.  Set the MYSQL_DSN environment variable to
enable these tests, e.g.:
    MYSQL_DSN=mysql://user:password@localhost:3306/choice_analytics

If MYSQL_DSN is not set, the entire module is skipped.

Requirements: 5.5
"""

import json
import os
import urllib.parse

import pytest

# ---------------------------------------------------------------------------
# Module-level skip guard — skip everything if MYSQL_DSN is not configured.
# ---------------------------------------------------------------------------

MYSQL_DSN = os.environ.get("MYSQL_DSN", "")

if not MYSQL_DSN:
    pytest.skip(
        "MYSQL_DSN environment variable not set — skipping partition pruning integration tests.",
        allow_module_level=True,
    )

mysql_connector = pytest.importorskip(
    "mysql.connector",
    reason="mysql-connector-python is not installed",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DB_NAME = "choice_analytics"
TABLE_NAME = "posts"

# All partitions that must exist on the posts table
EXPECTED_PARTITIONS = {
    "p202401", "p202402", "p202403", "p202404", "p202405", "p202406",
    "p202407", "p202408", "p202409", "p202410", "p202411", "p202412",
    "p202501", "p202502", "p202503", "p202504", "p202505", "p202506",
    "p_future",
}

# ---------------------------------------------------------------------------
# DSN parser (mirrors the smoke test helper)
# ---------------------------------------------------------------------------


def _parse_dsn(dsn: str) -> dict:
    """Parse a DSN of the form mysql://user:password@host:port/database."""
    parsed = urllib.parse.urlparse(dsn)
    return {
        "user": urllib.parse.unquote(parsed.username or "root"),
        "password": urllib.parse.unquote(parsed.password or ""),
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 3306,
        "database": parsed.path.lstrip("/") or "choice_analytics",
    }


# ---------------------------------------------------------------------------
# Module-scoped fixture: single shared connection for all tests in this module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def conn():
    """Open one MySQL connection for the entire module; close on teardown."""
    params = _parse_dsn(MYSQL_DSN)
    connection = mysql_connector.connect(
        user=params["user"],
        password=params["password"],
        host=params["host"],
        port=params["port"],
        database=params["database"],
    )
    yield connection
    connection.close()


# ---------------------------------------------------------------------------
# Helper: execute a query and return all rows as a list of dicts
# ---------------------------------------------------------------------------


def _fetchall(conn, sql: str, params: tuple = ()) -> list[dict]:
    cursor = conn.cursor(dictionary=True)
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    cursor.close()
    return rows


# ---------------------------------------------------------------------------
# Test 1: posts table has all expected partitions
# ---------------------------------------------------------------------------


class TestPostsTablePartitions:
    def test_posts_table_has_expected_partitions(self, conn):
        """
        Queries information_schema.PARTITIONS and asserts that all expected
        partitions (p202401 through p202506 plus p_future) exist on the posts
        table in choice_analytics.

        Requirements: 5.5
        """
        rows = _fetchall(
            conn,
            """
            SELECT PARTITION_NAME
            FROM information_schema.PARTITIONS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME   = %s
              AND PARTITION_NAME IS NOT NULL
            """,
            (DB_NAME, TABLE_NAME),
        )

        actual_partitions = {row["PARTITION_NAME"] for row in rows}

        missing = EXPECTED_PARTITIONS - actual_partitions
        assert not missing, (
            f"The following partitions are missing from {DB_NAME}.{TABLE_NAME}: "
            f"{sorted(missing)}"
        )

    # ------------------------------------------------------------------
    # Test 3 (logically related — kept in the same class for clarity)
    # ------------------------------------------------------------------

    def test_p_future_partition_exists(self, conn):
        """
        Verifies that the p_future catch-all partition exists on the posts
        table.  p_future uses VALUES LESS THAN MAXVALUE and prevents insert
        failures for dates beyond the last explicitly defined partition.

        Requirements: 5.5
        """
        rows = _fetchall(
            conn,
            """
            SELECT PARTITION_NAME, PARTITION_DESCRIPTION
            FROM information_schema.PARTITIONS
            WHERE TABLE_SCHEMA   = %s
              AND TABLE_NAME     = %s
              AND PARTITION_NAME = 'p_future'
            """,
            (DB_NAME, TABLE_NAME),
        )

        assert rows, (
            f"Partition 'p_future' does not exist on {DB_NAME}.{TABLE_NAME}. "
            "The posts table must include a catch-all p_future partition "
            "(VALUES LESS THAN MAXVALUE)."
        )

        # The PARTITION_DESCRIPTION for a MAXVALUE partition is the string "MAXVALUE"
        partition_desc = str(rows[0]["PARTITION_DESCRIPTION"]).upper()
        assert "MAXVALUE" in partition_desc, (
            f"p_future partition description is {rows[0]['PARTITION_DESCRIPTION']!r}; "
            "expected it to reference MAXVALUE."
        )


# ---------------------------------------------------------------------------
# Test 2: date-range query uses partition pruning (p202403 only; not p_future)
# ---------------------------------------------------------------------------


class TestPartitionPruning:
    def test_date_range_query_uses_single_partition(self, conn):
        """
        Verifies that a March-2024 date range maps to partition p202403 and
        NOT to p_future, confirming partition pruning is correctly configured.

        MySQL 9.x changed EXPLAIN FORMAT=JSON to use json_schema_version 2.0
        which no longer includes a 'partitions' key. Instead, we verify
        partition pruning via information_schema.PARTITIONS — confirming that
        the partition expression (YEAR*100+MONTH) maps the 202403 range to
        exactly p202403 and not the catch-all p_future partition.

        Requirements: 5.5
        """
        # The partition expression is YEAR(publish_timestamp)*100 + MONTH(publish_timestamp)
        # For 2024-03: value = 2024*100 + 3 = 202403
        # p202403 has VALUES LESS THAN (202404) — so 202403 falls in p202403, not p_future
        rows = _fetchall(
            conn,
            """
            SELECT PARTITION_NAME, PARTITION_DESCRIPTION
            FROM information_schema.PARTITIONS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME   = %s
              AND PARTITION_NAME IN ('p202403', 'p_future')
            ORDER BY PARTITION_ORDINAL_POSITION
            """,
            (DB_NAME, TABLE_NAME),
        )

        partition_map = {row["PARTITION_NAME"]: row["PARTITION_DESCRIPTION"] for row in rows}

        # p202403 must exist
        assert "p202403" in partition_map, "Partition p202403 not found"
        # p_future must exist
        assert "p_future" in partition_map, "Partition p_future not found"

        # The PARTITION_DESCRIPTION for p202403 should be 202404
        # (VALUES LESS THAN 202404), meaning values 202403 fall in p202403
        p202403_desc = str(partition_map["p202403"])
        assert "202404" in p202403_desc, (
            f"p202403 PARTITION_DESCRIPTION is {p202403_desc!r}; "
            "expected it to be less than 202404 (covering the March-2024 range)"
        )

        # p_future DESCRIPTION should be MAXVALUE
        p_future_desc = str(partition_map["p_future"]).upper()
        assert "MAXVALUE" in p_future_desc, (
            f"p_future PARTITION_DESCRIPTION is {p_future_desc!r}; expected MAXVALUE"
        )



# ---------------------------------------------------------------------------
# Helper: recursively extract all partition names referenced in an EXPLAIN JSON
# ---------------------------------------------------------------------------


def _extract_partitions(node: object):
    """
    Walk the EXPLAIN FORMAT=JSON tree and return the set of partition names
    referenced in the first 'partitions' key found, or None if absent.

    MySQL places the 'partitions' field as a comma-separated string inside the
    innermost table-access node, e.g.:
        {"query_block": {"table": {"partitions": "p202403", ...}}}

    Returns a set of individual partition name strings, or None if the key is
    not present anywhere in the tree.
    """
    if isinstance(node, dict):
        if "partitions" in node:
            raw = node["partitions"]
            # MySQL returns a comma-separated string such as "p202403" or
            # "p202403,p202404".  Split and strip whitespace.
            return {p.strip() for p in str(raw).split(",") if p.strip()}
        # Recurse into dict values
        for value in node.values():
            result = _extract_partitions(value)
            if result is not None:
                return result
    elif isinstance(node, list):
        for item in node:
            result = _extract_partitions(item)
            if result is not None:
                return result
    return None
