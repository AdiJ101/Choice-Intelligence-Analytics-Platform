"""
validators.py — Input validation helpers for the Customer Intelligence & Analytics Platform.

Provides pure-Python validation functions that mirror the CHECK constraints and ENUM
definitions in the MySQL schema.  All functions are stateless, have no external
dependencies, and rely only on the standard-library ``re`` module.
"""

import re
from typing import Optional

# ---------------------------------------------------------------------------
# Compiled regex patterns (compiled once at module import for performance)
# ---------------------------------------------------------------------------

# Mirrors the MySQL CHECK constraint on platforms.platform_code:
#   CHECK (platform_code REGEXP '^[a-z0-9][a-z0-9-]*[a-z0-9]$'
#          OR platform_code REGEXP '^[a-z0-9]$')
# Combines both branches into a single pattern.
_PLATFORM_CODE_MULTI = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")
_PLATFORM_CODE_SINGLE = re.compile(r"^[a-z0-9]$")

# ISO 639-1 language code: exactly 2 ASCII letters (upper- or lower-case).
_LANGUAGE_CODE_RE = re.compile(r"^[A-Za-z]{2}$")

# ---------------------------------------------------------------------------
# Valid literal sets
# ---------------------------------------------------------------------------

_VALID_POST_TYPES: frozenset[str] = frozenset({"post", "video", "text"})


# ---------------------------------------------------------------------------
# Public validation functions
# ---------------------------------------------------------------------------


def validate_platform_code(code: str) -> bool:
    """Return ``True`` iff *code* is a valid platform code.

    A valid platform code:
    - Consists solely of lowercase alphanumeric characters (``a-z``, ``0-9``)
      and hyphens (``-``).
    - Does **not** start or end with a hyphen.
    - Has a length between 1 and 50 characters (inclusive).

    This mirrors exactly the ``CHECK`` constraint on ``platforms.platform_code``
    in the MySQL schema::

        CHECK (platform_code REGEXP '^[a-z0-9][a-z0-9-]*[a-z0-9]$'
               OR platform_code REGEXP '^[a-z0-9]$')

    Examples::

        >>> validate_platform_code("youtube")
        True
        >>> validate_platform_code("twitter-x")
        True
        >>> validate_platform_code("-bad")
        False
        >>> validate_platform_code("")
        False
    """
    if not isinstance(code, str):
        return False

    if len(code) > 50:
        return False

    # Single-character codes: must be a lowercase alphanumeric character.
    if len(code) == 1:
        return bool(_PLATFORM_CODE_SINGLE.match(code))

    # Multi-character codes: must not start or end with a hyphen.
    return bool(_PLATFORM_CODE_MULTI.match(code))


def validate_post_type(post_type: str) -> bool:
    """Return ``True`` iff *post_type* is exactly one of ``'post'``, ``'video'``,
    or ``'text'``.

    Mirrors the ``ENUM('post','video','text')`` column definition on
    ``posts.post_type``.

    Examples::

        >>> validate_post_type("video")
        True
        >>> validate_post_type("image")
        False
        >>> validate_post_type("Post")   # case-sensitive
        False
    """
    return post_type in _VALID_POST_TYPES


def validate_language_code(code: Optional[str]) -> bool:
    """Return ``True`` if *code* is ``None`` OR a valid ISO 639-1 language code.

    A valid ISO 639-1 code consists of exactly 2 ASCII letter characters
    (``A-Z`` or ``a-z``).  ``None`` is accepted to represent "language not
    detected", matching the nullable ``CHAR(2)`` column in the schema.

    Examples::

        >>> validate_language_code(None)
        True
        >>> validate_language_code("en")
        True
        >>> validate_language_code("EN")
        True
        >>> validate_language_code("eng")  # 3 characters — invalid
        False
        >>> validate_language_code("e1")   # digit — invalid
        False
    """
    if code is None:
        return True
    if not isinstance(code, str):
        return False
    return bool(_LANGUAGE_CODE_RE.match(code))


def validate_scraping_config_values(
    interval: int,
    max_content: int,
    cooling_days: int,
) -> None:
    """Validate scraping configuration values, raising ``ValueError`` on violation.

    Constraints (mirror the MySQL ``CHECK`` constraints on ``scraping_config``):

    * *interval* — ``scraping_interval_minutes``: must be between **1** and
      **10080** (inclusive).  10 080 = 7 days × 24 hours × 60 minutes.
    * *max_content* — ``max_new_content_per_handle_per_iter``: must be between
      **1** and **1000** (inclusive).
    * *cooling_days* — ``cooling_time_days``: must be between **1** and **365**
      (inclusive).

    :raises ValueError: If any value is outside its permitted range.

    Examples::

        >>> validate_scraping_config_values(60, 100, 30)   # all valid — no error
        >>> validate_scraping_config_values(0, 100, 30)
        Traceback (most recent call last):
            ...
        ValueError: scraping_interval_minutes must be between 1 and 10080 (got 0)
    """
    if not (1 <= interval <= 10080):
        raise ValueError(
            f"scraping_interval_minutes must be between 1 and 10080 (got {interval!r})"
        )
    if not (1 <= max_content <= 1000):
        raise ValueError(
            f"max_new_content_per_handle_per_iter must be between 1 and 1000 "
            f"(got {max_content!r})"
        )
    if not (1 <= cooling_days <= 365):
        raise ValueError(
            f"cooling_time_days must be between 1 and 365 (got {cooling_days!r})"
        )
