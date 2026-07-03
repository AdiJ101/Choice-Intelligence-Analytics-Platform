"""
Smoke tests for the choice_analytics MySQL schema.

Requires a live MySQL connection. Set the MYSQL_DSN environment variable to
enable these tests, e.g.:
    MYSQL_DSN=mysql://user:password@localhost:3306/choice_analytics

If MYSQL_DSN is not set, the entire module is skipped.

Requirements: 1.1–1.8, 5.1–5.5
"""

import os
import re
import urllib.parse

import pytest

# ---------------------------------------------------------------------------
# Module-level skip guard — skip everything if MYSQL_DSN is not configured.
# ---------------------------------------------------------------------------

MYSQL_DSN = os.environ.get("MYSQL_DSN", "")

if not MYSQL_DSN:
    pytest.skip(
        "MYSQL_DSN environment variable not set — skipping MySQL schema smoke tests.",
        allow_module_level=True,
    )

mysql_connector = pytest.importorskip(
    "mysql.connector",
    reason="mysql-connector-python is not installed",
)


# ---------------------------------------------------------------------------
# DSN parser
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
# Module-level fixture: single shared connection
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
# Expected schema metadata
# ---------------------------------------------------------------------------

EXPECTED_TABLES = [
    "categories",
    "platforms",
    "platform_config",
    "handles",
    "posts",
    "comments",
    "engagement_metrics",
    "scraping_config",
    "sync_watermarks",
    "dead_letter_queue",
    "content_deletions",
]

EXPECTED_FK_CONSTRAINTS = [
    "fk_handles_category",
    "fk_handles_platform",
    # fk_posts_handle and fk_posts_platform are intentionally omitted:
    # MySQL 9.x does not support FK constraints on partitioned tables.
    # Referential integrity for posts is enforced at the application layer.
    # fk_comments_post is also omitted: MySQL 9.x does not allow FK references
    # TO a partitioned table. Enforced at the application layer.
    "fk_em_platform",
    "fk_platform_config_platform",
]

EXPECTED_INDEXES = [
    # handles
    "idx_handles_category_id",
    "idx_handles_platform_id",
    # posts
    "idx_posts_handle_id",
    "idx_posts_platform_id",
    "idx_posts_publish_ts",
    "idx_posts_cat_plat_ts",
    # comments
    "idx_comments_post_id",
    "idx_comments_publish_ts",
    # engagement_metrics
    "idx_em_source",
    "idx_em_platform_id",
    "idx_em_snapshot_ts",
    # dead_letter_queue
    "idx_dlq_source",
    "idx_dlq_failed_at",
    # content_deletions
    "idx_cd_propagated",
    "idx_cd_source",
]

EXPECTED_CHECK_CONSTRAINTS = [
    "chk_platform_code",
    "chk_scraping_interval",
    "chk_max_content",
    "chk_cooling_days",
]

DB_NAME = "choice_analytics"
EXPECTED_CHARSET = "utf8mb4"
EXPECTED_COLLATION = "utf8mb4_unicode_ci"


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
# 1. Tables — existence, charset, and collation
# ---------------------------------------------------------------------------

class TestTables:
    def test_all_expected_tables_exist(self, conn):
        """All expected tables must be present in choice_analytics."""
        rows = _fetchall(
            conn,
            """
            SELECT TABLE_NAME
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
              AND TABLE_TYPE = 'BASE TABLE'
            """,
            (DB_NAME,),
        )
        existing_tables = {row["TABLE_NAME"] for row in rows}
        missing = set(EXPECTED_TABLES) - existing_tables
        assert not missing, (
            f"The following expected tables are missing from {DB_NAME!r}: {sorted(missing)}"
        )

    def test_tables_use_utf8mb4_charset(self, conn):
        """Every expected table must use the utf8mb4 character set."""
        rows = _fetchall(
            conn,
            """
            SELECT TABLE_NAME, CCSA.CHARACTER_SET_NAME
            FROM information_schema.TABLES t
            JOIN information_schema.COLLATION_CHARACTER_SET_APPLICABILITY CCSA
              ON t.TABLE_COLLATION = CCSA.COLLATION_NAME
            WHERE t.TABLE_SCHEMA = %s
              AND t.TABLE_TYPE = 'BASE TABLE'
            """,
            (DB_NAME,),
        )
        charset_map = {row["TABLE_NAME"]: row["CHARACTER_SET_NAME"] for row in rows}
        wrong_charset = {
            table: charset_map.get(table, "<missing>")
            for table in EXPECTED_TABLES
            if charset_map.get(table) != EXPECTED_CHARSET
        }
        assert not wrong_charset, (
            f"Tables with wrong charset (expected {EXPECTED_CHARSET!r}): {wrong_charset}"
        )

    def test_tables_use_utf8mb4_unicode_ci_collation(self, conn):
        """Every expected table must use utf8mb4_unicode_ci collation."""
        rows = _fetchall(
            conn,
            """
            SELECT TABLE_NAME, TABLE_COLLATION
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
              AND TABLE_TYPE = 'BASE TABLE'
            """,
            (DB_NAME,),
        )
        collation_map = {row["TABLE_NAME"]: row["TABLE_COLLATION"] for row in rows}
        wrong_collation = {
            table: collation_map.get(table, "<missing>")
            for table in EXPECTED_TABLES
            if collation_map.get(table) != EXPECTED_COLLATION
        }
        assert not wrong_collation, (
            f"Tables with wrong collation (expected {EXPECTED_COLLATION!r}): {wrong_collation}"
        )


# ---------------------------------------------------------------------------
# 2. FK constraints
# ---------------------------------------------------------------------------

class TestForeignKeys:
    def test_all_fk_constraints_exist(self, conn):
        """All required FK constraints must be present in the schema."""
        rows = _fetchall(
            conn,
            """
            SELECT CONSTRAINT_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE CONSTRAINT_SCHEMA = %s
              AND REFERENCED_TABLE_NAME IS NOT NULL
            """,
            (DB_NAME,),
        )
        existing_fks = {row["CONSTRAINT_NAME"] for row in rows}
        missing = set(EXPECTED_FK_CONSTRAINTS) - existing_fks
        assert not missing, (
            f"The following FK constraints are missing from {DB_NAME!r}: {sorted(missing)}"
        )

    def test_fk_handles_category_references_categories(self, conn):
        """fk_handles_category must reference the categories table."""
        rows = _fetchall(
            conn,
            """
            SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE CONSTRAINT_SCHEMA = %s
              AND CONSTRAINT_NAME = 'fk_handles_category'
            """,
            (DB_NAME,),
        )
        assert rows, "fk_handles_category not found"
        row = rows[0]
        assert row["TABLE_NAME"] == "handles"
        assert row["REFERENCED_TABLE_NAME"] == "categories"

    def test_fk_handles_platform_references_platforms(self, conn):
        """fk_handles_platform must reference the platforms table."""
        rows = _fetchall(
            conn,
            """
            SELECT TABLE_NAME, REFERENCED_TABLE_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE CONSTRAINT_SCHEMA = %s
              AND CONSTRAINT_NAME = 'fk_handles_platform'
            """,
            (DB_NAME,),
        )
        assert rows, "fk_handles_platform not found"
        assert rows[0]["TABLE_NAME"] == "handles"
        assert rows[0]["REFERENCED_TABLE_NAME"] == "platforms"

    def test_fk_posts_handle_and_platform_omitted_for_mysql9(self, conn):
        """
        MySQL 9.x dropped support for FK constraints on partitioned tables.
        fk_posts_handle and fk_posts_platform are intentionally not present.
        Referential integrity is enforced at the application layer.
        This test documents the intentional omission.
        """
        for fk_name in ("fk_posts_handle", "fk_posts_platform", "fk_comments_post"):
            rows = _fetchall(
                conn,
                """
                SELECT CONSTRAINT_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE CONSTRAINT_SCHEMA = %s AND CONSTRAINT_NAME = %s
                """,
                (DB_NAME, fk_name),
            )
            assert not rows, (
                f"{fk_name} was unexpectedly found — MySQL 9.x should not allow "
                "FK constraints on or referencing partitioned tables."
            )

    def test_fk_em_platform_references_platforms(self, conn):
        """fk_em_platform must reference the platforms table."""
        rows = _fetchall(
            conn,
            """
            SELECT TABLE_NAME, REFERENCED_TABLE_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE CONSTRAINT_SCHEMA = %s
              AND CONSTRAINT_NAME = 'fk_em_platform'
            """,
            (DB_NAME,),
        )
        assert rows, "fk_em_platform not found"
        assert rows[0]["TABLE_NAME"] == "engagement_metrics"
        assert rows[0]["REFERENCED_TABLE_NAME"] == "platforms"

    def test_fk_platform_config_platform_references_platforms(self, conn):
        """fk_platform_config_platform must reference the platforms table."""
        rows = _fetchall(
            conn,
            """
            SELECT TABLE_NAME, REFERENCED_TABLE_NAME
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE CONSTRAINT_SCHEMA = %s
              AND CONSTRAINT_NAME = 'fk_platform_config_platform'
            """,
            (DB_NAME,),
        )
        assert rows, "fk_platform_config_platform not found"
        assert rows[0]["TABLE_NAME"] == "platform_config"
        assert rows[0]["REFERENCED_TABLE_NAME"] == "platforms"


# ---------------------------------------------------------------------------
# 3. Indexes
# ---------------------------------------------------------------------------

class TestIndexes:
    def test_all_indexes_exist(self, conn):
        """All required indexes must be present in the schema."""
        rows = _fetchall(
            conn,
            """
            SELECT DISTINCT INDEX_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s
            """,
            (DB_NAME,),
        )
        existing_indexes = {row["INDEX_NAME"] for row in rows}
        missing = set(EXPECTED_INDEXES) - existing_indexes
        assert not missing, (
            f"The following indexes are missing from {DB_NAME!r}: {sorted(missing)}"
        )

    def test_idx_posts_cat_plat_ts_is_composite(self, conn):
        """idx_posts_cat_plat_ts must be a composite index on (handle_id, platform_id, publish_timestamp)."""
        rows = _fetchall(
            conn,
            """
            SELECT COLUMN_NAME, SEQ_IN_INDEX
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = 'posts'
              AND INDEX_NAME = 'idx_posts_cat_plat_ts'
            ORDER BY SEQ_IN_INDEX
            """,
            (DB_NAME,),
        )
        assert rows, "idx_posts_cat_plat_ts not found on posts table"
        column_names = [row["COLUMN_NAME"] for row in rows]
        assert "handle_id" in column_names, (
            f"handle_id missing from idx_posts_cat_plat_ts columns: {column_names}"
        )
        assert "platform_id" in column_names, (
            f"platform_id missing from idx_posts_cat_plat_ts columns: {column_names}"
        )
        assert "publish_timestamp" in column_names, (
            f"publish_timestamp missing from idx_posts_cat_plat_ts columns: {column_names}"
        )

    def test_idx_em_source_is_composite(self, conn):
        """idx_em_source must cover (source_table, source_record_id)."""
        rows = _fetchall(
            conn,
            """
            SELECT COLUMN_NAME, SEQ_IN_INDEX
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = 'engagement_metrics'
              AND INDEX_NAME = 'idx_em_source'
            ORDER BY SEQ_IN_INDEX
            """,
            (DB_NAME,),
        )
        assert rows, "idx_em_source not found on engagement_metrics table"
        column_names = [row["COLUMN_NAME"] for row in rows]
        assert "source_table" in column_names
        assert "source_record_id" in column_names

    def test_idx_dlq_source_is_composite(self, conn):
        """idx_dlq_source must cover (source_table, source_record_id)."""
        rows = _fetchall(
            conn,
            """
            SELECT COLUMN_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = 'dead_letter_queue'
              AND INDEX_NAME = 'idx_dlq_source'
            ORDER BY SEQ_IN_INDEX
            """,
            (DB_NAME,),
        )
        assert rows, "idx_dlq_source not found on dead_letter_queue table"
        column_names = [row["COLUMN_NAME"] for row in rows]
        assert "source_table" in column_names
        assert "source_record_id" in column_names

    def test_idx_cd_source_is_composite(self, conn):
        """idx_cd_source must cover (source_table, source_record_id)."""
        rows = _fetchall(
            conn,
            """
            SELECT COLUMN_NAME
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = %s
              AND TABLE_NAME = 'content_deletions'
              AND INDEX_NAME = 'idx_cd_source'
            ORDER BY SEQ_IN_INDEX
            """,
            (DB_NAME,),
        )
        assert rows, "idx_cd_source not found on content_deletions table"
        column_names = [row["COLUMN_NAME"] for row in rows]
        assert "source_table" in column_names
        assert "source_record_id" in column_names


# ---------------------------------------------------------------------------
# 4. CHECK constraints
# ---------------------------------------------------------------------------

class TestCheckConstraints:
    def test_all_check_constraints_exist(self, conn):
        """All required CHECK constraints must be present in the schema."""
        rows = _fetchall(
            conn,
            """
            SELECT CONSTRAINT_NAME
            FROM information_schema.CHECK_CONSTRAINTS
            WHERE CONSTRAINT_SCHEMA = %s
            """,
            (DB_NAME,),
        )
        existing_checks = {row["CONSTRAINT_NAME"] for row in rows}
        missing = set(EXPECTED_CHECK_CONSTRAINTS) - existing_checks
        assert not missing, (
            f"The following CHECK constraints are missing from {DB_NAME!r}: {sorted(missing)}"
        )

    def test_chk_platform_code_on_platforms_table(self, conn):
        """chk_platform_code must be defined on the platforms table."""
        rows = _fetchall(
            conn,
            """
            SELECT tc.CONSTRAINT_NAME, tc.TABLE_NAME
            FROM information_schema.TABLE_CONSTRAINTS tc
            WHERE tc.CONSTRAINT_SCHEMA = %s
              AND tc.CONSTRAINT_NAME = 'chk_platform_code'
              AND tc.CONSTRAINT_TYPE = 'CHECK'
            """,
            (DB_NAME,),
        )
        assert rows, "chk_platform_code CHECK constraint not found"
        assert rows[0]["TABLE_NAME"] == "platforms"

    def test_chk_scraping_interval_on_scraping_config_table(self, conn):
        """chk_scraping_interval must be defined on the scraping_config table."""
        rows = _fetchall(
            conn,
            """
            SELECT tc.TABLE_NAME
            FROM information_schema.TABLE_CONSTRAINTS tc
            WHERE tc.CONSTRAINT_SCHEMA = %s
              AND tc.CONSTRAINT_NAME = 'chk_scraping_interval'
              AND tc.CONSTRAINT_TYPE = 'CHECK'
            """,
            (DB_NAME,),
        )
        assert rows, "chk_scraping_interval CHECK constraint not found"
        assert rows[0]["TABLE_NAME"] == "scraping_config"

    def test_chk_max_content_on_scraping_config_table(self, conn):
        """chk_max_content must be defined on the scraping_config table."""
        rows = _fetchall(
            conn,
            """
            SELECT tc.TABLE_NAME
            FROM information_schema.TABLE_CONSTRAINTS tc
            WHERE tc.CONSTRAINT_SCHEMA = %s
              AND tc.CONSTRAINT_NAME = 'chk_max_content'
              AND tc.CONSTRAINT_TYPE = 'CHECK'
            """,
            (DB_NAME,),
        )
        assert rows, "chk_max_content CHECK constraint not found"
        assert rows[0]["TABLE_NAME"] == "scraping_config"

    def test_chk_cooling_days_on_scraping_config_table(self, conn):
        """chk_cooling_days must be defined on the scraping_config table."""
        rows = _fetchall(
            conn,
            """
            SELECT tc.TABLE_NAME
            FROM information_schema.TABLE_CONSTRAINTS tc
            WHERE tc.CONSTRAINT_SCHEMA = %s
              AND tc.CONSTRAINT_NAME = 'chk_cooling_days'
              AND tc.CONSTRAINT_TYPE = 'CHECK'
            """,
            (DB_NAME,),
        )
        assert rows, "chk_cooling_days CHECK constraint not found"
        assert rows[0]["TABLE_NAME"] == "scraping_config"
