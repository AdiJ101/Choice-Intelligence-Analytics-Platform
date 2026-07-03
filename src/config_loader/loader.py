"""
loader.py — Scraping configuration loader for the Customer Intelligence &
Analytics Platform.

Provides :func:`load_scraping_config`, which validates a Scraping_Config JSON
document and persists it to MySQL within a single atomic transaction.

The loader:

* Validates required top-level keys, nested scraping-config fields, and all
  value ranges before touching the database.
* Upserts the ``scraping_config``, ``categories``, ``platforms``, and
  ``handles`` tables using ``INSERT … ON DUPLICATE KEY UPDATE`` semantics.
* Marks any Handle that is present in MySQL but absent from the loaded config
  as ``is_active = 0``, preserving all historical Posts and Engagement Metrics.
* Rolls back the entire transaction and re-raises the original exception on any
  SQL error.

Expected *config_dict* shape::

    {
        "scraping_config": {
            "scraping_interval_minutes": 60,
            "max_new_content_per_handle_per_iteration": 20,
            "cooling_time_days": 30
        },
        "categories": [
            {
                "name": "Choice TechLab",
                "handles": {
                    "youtube":   "@ChoiceTechLab",
                    "instagram": "choicetechlab"
                }
            }
        ]
    }

Requirements: 3.1, 3.2, 3.3, 3.5, 3.6
"""

from __future__ import annotations

from typing import Any

import mysql.connector


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_REQUIRED_TOP_KEYS = ("scraping_config", "categories")

_REQUIRED_SC_KEYS = (
    "scraping_interval_minutes",
    "max_new_content_per_handle_per_iteration",
    "cooling_time_days",
    "post_collection_days",
)

_SC_RANGES: dict[str, tuple[int, int]] = {
    "scraping_interval_minutes": (1, 10080),
    "max_new_content_per_handle_per_iteration": (1, 1000),
    "cooling_time_days": (1, 9999),
    "post_collection_days": (1, 3650),
}


def _validate(config_dict: dict) -> None:
    """Raise :class:`ValueError` if *config_dict* fails any validation rule.

    Validation is purely in-memory — this function never touches the database.

    Raises
    ------
    ValueError
        On any structural or range violation.
    """
    # 1. Required top-level keys.
    for key in _REQUIRED_TOP_KEYS:
        if key not in config_dict:
            raise ValueError(f"Missing required top-level key: '{key}'")

    sc = config_dict["scraping_config"]
    if not isinstance(sc, dict):
        raise ValueError("'scraping_config' must be a JSON object (dict)")

    # 2. Required sub-keys inside scraping_config.
    for key in _REQUIRED_SC_KEYS:
        if key not in sc:
            raise ValueError(f"'scraping_config' is missing required field: '{key}'")

    # 3. Range checks.
    for key, (lo, hi) in _SC_RANGES.items():
        value = sc[key]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(
                f"'scraping_config.{key}' must be an integer, got {type(value).__name__}"
            )
        if not (lo <= value <= hi):
            raise ValueError(
                f"'scraping_config.{key}' must be between {lo} and {hi}, got {value}"
            )

    # 4. categories must be a non-empty list.
    categories = config_dict["categories"]
    if not isinstance(categories, list):
        raise ValueError("'categories' must be a JSON array (list)")
    if len(categories) == 0:
        raise ValueError("'categories' must not be empty")


# ---------------------------------------------------------------------------
# SQL statements
# ---------------------------------------------------------------------------

_UPSERT_SCRAPING_CONFIG = """
INSERT INTO scraping_config
    (scraping_interval_minutes,
     max_new_content_per_handle_per_iter,
     cooling_time_days,
     post_collection_days,
     config_version)
VALUES (%s, %s, %s, %s, 1)
ON DUPLICATE KEY UPDATE
    scraping_interval_minutes           = VALUES(scraping_interval_minutes),
    max_new_content_per_handle_per_iter = VALUES(max_new_content_per_handle_per_iter),
    cooling_time_days                   = VALUES(cooling_time_days),
    post_collection_days                = VALUES(post_collection_days),
    config_version                      = config_version + 1,
    loaded_at                           = NOW()
"""

_UPSERT_CATEGORY = """
INSERT INTO categories (name)
VALUES (%s)
ON DUPLICATE KEY UPDATE updated_at = NOW()
"""

_SELECT_CATEGORY_ID = "SELECT id FROM categories WHERE name = %s"

_UPSERT_PLATFORM = """
INSERT INTO platforms (platform_code, display_name)
VALUES (%s, %s)
ON DUPLICATE KEY UPDATE display_name = VALUES(display_name)
"""

_SELECT_PLATFORM_ID = "SELECT id FROM platforms WHERE platform_code = %s"

_UPSERT_HANDLE = """
INSERT INTO handles
    (category_id, platform_id, platform_native_handle, display_name, is_active)
VALUES (%s, %s, %s, %s, 1)
ON DUPLICATE KEY UPDATE
    category_id  = VALUES(category_id),
    display_name = VALUES(display_name),
    is_active    = 1
"""

_COUNT_ACTIVE_HANDLES = "SELECT COUNT(*) AS cnt FROM handles WHERE is_active = 1"

_DEACTIVATE_ABSENT_HANDLES = """
UPDATE handles
SET is_active = 0
WHERE (platform_id, platform_native_handle) NOT IN ({placeholders})
"""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_scraping_config(conn: Any, config_dict: dict) -> None:
    """Validate *config_dict* and persist it to MySQL within a single transaction.

    Parameters
    ----------
    conn:
        An open :class:`mysql.connector.connection.MySQLConnection` (or
        ``CMySQLConnection``) instance.  The caller retains ownership; this
        function never closes the connection.
    config_dict:
        A Python ``dict`` representing the parsed Scraping_Config JSON document.

    Raises
    ------
    ValueError
        If *config_dict* fails structural or range validation.  No database
        operations are performed in this case.
    Exception
        Any SQL error raised by ``mysql.connector``; ``conn.rollback()`` is
        called before re-raising.

    Requirements
    ------------
    3.1, 3.2, 3.3, 3.5, 3.6
    """
    # -- Validate first; never touch the DB if validation fails. -------------
    _validate(config_dict)

    sc = config_dict["scraping_config"]
    categories = config_dict["categories"]

    # -- Enter transaction. ---------------------------------------------------
    conn.autocommit = False

    cursor = conn.cursor(dictionary=True)
    try:
        # (a) Upsert scraping_config row.
        cursor.execute(
            _UPSERT_SCRAPING_CONFIG,
            (
                sc["scraping_interval_minutes"],
                sc["max_new_content_per_handle_per_iteration"],
                sc["cooling_time_days"],
                sc["post_collection_days"],
            ),
        )

        # Track every (platform_id, platform_native_handle) pair seen.
        seen_pairs: list[tuple[int, str]] = []

        for cat in categories:
            cat_name: str = cat["name"]

            # (b-i) Upsert category; retrieve its id.
            cursor.execute(_UPSERT_CATEGORY, (cat_name,))
            cursor.execute(_SELECT_CATEGORY_ID, (cat_name,))
            row = cursor.fetchone()
            category_id: int = row["id"]

            handles_dict: dict[str, str] = cat.get("handles", {})

            for platform_code, native_handle in handles_dict.items():
                display_name_platform = platform_code.title()

                # (b-ii) Upsert platform; retrieve its id.
                cursor.execute(_UPSERT_PLATFORM, (platform_code, display_name_platform))
                cursor.execute(_SELECT_PLATFORM_ID, (platform_code,))
                prow = cursor.fetchone()
                platform_id: int = prow["id"]

                # (b-iii) Upsert handle; display_name is the native handle string.
                cursor.execute(
                    _UPSERT_HANDLE,
                    (category_id, platform_id, native_handle, native_handle),
                )

                seen_pairs.append((platform_id, native_handle))

        # (c) Mark absent handles as inactive — only when active handles exist.
        if seen_pairs:
            cursor.execute(_COUNT_ACTIVE_HANDLES)
            count_row = cursor.fetchone()
            active_count: int = count_row["cnt"]

            if active_count > 0:
                # Build parameterized NOT IN clause.
                placeholders = ", ".join("(%s, %s)" for _ in seen_pairs)
                flat_params: list = []
                for pid, handle in seen_pairs:
                    flat_params.extend([pid, handle])

                deactivate_sql = _DEACTIVATE_ABSENT_HANDLES.format(
                    placeholders=placeholders
                )
                cursor.execute(deactivate_sql, flat_params)

        conn.commit()

    except Exception:
        conn.rollback()
        raise

    finally:
        cursor.close()
