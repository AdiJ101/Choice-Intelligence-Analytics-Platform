"""
retry.py — Exponential-backoff retry decorator for transient failures.

Implements Requirement 15.1:
  - 3 total attempts (not 3 retries — attempt 1 is the first call)
  - Wait intervals: attempt 1 → immediate (0s), attempt 2 → 1s, attempt 3 → 2s
  - Formula: wait = 2^(attempt - 1)  →  0s, 1s, 2s for attempts 1, 2, 3
  - Retries on: RateLimitError, HTTP 429/500/502/503/504,
                connection/read timeouts, transient MySQL errors
  - Does NOT retry on: AuthenticationError, non-transient ValueError
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Transient MySQL error messages (substring match)
_TRANSIENT_MYSQL_MSGS: tuple[str, ...] = (
    "Lost connection to MySQL server",
    "MySQL server has gone away",
    "Lock wait timeout exceeded",
    "Deadlock found",
)

# HTTP status codes that trigger a retry
_RETRYABLE_HTTP_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})


def _is_transient(exc: BaseException) -> bool:
    """Return True if *exc* represents a transient, retryable failure.

    Transient conditions:
    - ``RateLimitError`` from ``.base_adapter``
    - ``requests.HTTPError`` whose response status is in {429, 500, 502, 503, 504}
    - ``requests.ConnectionError`` or ``requests.Timeout``
    - Any exception whose str() contains a known transient MySQL message

    Non-transient (returns False):
    - ``AuthenticationError`` from ``.base_adapter``
    - ``ValueError`` without a matching MySQL message
    - Any other exception not listed above
    """
    from .base_adapter import RateLimitError, AuthenticationError

    # AuthenticationError is never transient — don't retry
    if isinstance(exc, AuthenticationError):
        return False

    if isinstance(exc, RateLimitError):
        return True

    # Transient MySQL error messages (substring match on str(exc))
    msg = str(exc)
    for fragment in _TRANSIENT_MYSQL_MSGS:
        if fragment in msg:
            return True

    # Check for requests library errors
    try:
        import requests

        if isinstance(exc, requests.HTTPError) and exc.response is not None:
            return exc.response.status_code in _RETRYABLE_HTTP_STATUSES
        if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
            return True
    except ImportError:
        pass

    return False


def with_retry(max_attempts: int = 3) -> Callable[[F], F]:
    """Decorator that retries a function with exponential backoff.

    Parameters
    ----------
    max_attempts:
        Total number of call attempts (default 3).
        Wait schedule: attempt 1 → 0s, attempt 2 → 1s, attempt 3 → 2s.

    Usage
    -----
    @with_retry(max_attempts=3)
    def call_api():
        ...

    The decorated function is called at most *max_attempts* times.
    On every failure where the exception is transient, the decorator waits
    ``2^(attempt - 1)`` seconds before the next attempt (first attempt: 0s).
    On the final attempt failure, the original exception is re-raised.
    Non-transient exceptions are re-raised immediately without retry.
    """
    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    if not _is_transient(exc):
                        raise
                    last_exc = exc
                    if attempt < max_attempts:
                        wait = 2 ** (attempt - 1)  # 0s, 1s, 2s
                        logger.warning(
                            "Attempt %d/%d failed (%s). Retrying in %ds.",
                            attempt,
                            max_attempts,
                            type(exc).__name__,
                            wait,
                        )
                        if wait > 0:
                            time.sleep(wait)
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
