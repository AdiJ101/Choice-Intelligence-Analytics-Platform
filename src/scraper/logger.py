"""
logger.py — Structured JSON-lines logging setup for the Scraper Service.

Provides:
- JsonLinesFormatter: formats log records as single-line JSON objects
- configure_logging():  wires a StreamHandler(stdout) to the root logger
- IterationStats:       dataclass tracking one iteration's counters and timing
- emit_iteration_start(): structured log event at iteration begin
- emit_iteration_end():   structured log event at iteration end

Requirement 17.1 — All log output uses newline-delimited JSON (JSON Lines).
Requirement 17.2 — Iteration start/end events include mandatory fields.
Requirement 17.6 — Credential values are NEVER included in any log entry.

Secret hygiene note: this module contains no reference to any env var value.
Every caller is responsible for passing only non-sensitive data to the emit_*
functions.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Module-level logger (used by emit_* helpers)
# ---------------------------------------------------------------------------
_logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# IterationStats — defined here so both logger and orchestrator can import it
# ---------------------------------------------------------------------------

@dataclass
class IterationStats:
    """Tracks counters and timing for one complete scraping iteration.

    Parameters
    ----------
    start_time:
        UTC-aware datetime when the iteration started.
    end_time:
        UTC-aware datetime when the iteration finished.  ``None`` until the
        iteration completes.
    posts_inserted, posts_updated, comments_inserted,
    engagement_snapshots_inserted, errors:
        Running tallies incremented by the orchestrator / handle processor.
    """

    start_time: datetime
    end_time: datetime | None = None
    posts_inserted: int = 0
    posts_updated: int = 0
    comments_inserted: int = 0
    engagement_snapshots_inserted: int = 0
    errors: int = 0

    @property
    def duration_seconds(self) -> float:
        """Elapsed wall-clock seconds, or 0.0 if the iteration has not ended."""
        if self.end_time is None:
            return 0.0
        return (self.end_time - self.start_time).total_seconds()


# ---------------------------------------------------------------------------
# JsonLinesFormatter
# ---------------------------------------------------------------------------

class JsonLinesFormatter(logging.Formatter):
    """Formats every log record as a single-line JSON object.

    Standard fields always emitted:
        level     — logging level name (e.g. "INFO")
        logger    — logger name (record.name)
        message   — the formatted log message
        timestamp — UTC ISO-8601 string (e.g. "2024-01-15T12:34:56.789012+00:00")

    Optional extension:
        If the log record carries an ``event_data`` attribute that is a dict,
        its key/value pairs are *merged* into the top-level JSON object.
        This lets callers attach structured context without nesting:

            record.event_data = {"event": "iteration_start", "active_handle_count": 3}
            # → {"level": "INFO", ..., "event": "iteration_start", "active_handle_count": 3}

    Any value that is not JSON-serialisable is converted to its string
    representation via ``default=str``.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        # Build the base dict
        data: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
        }

        # Merge event_data if present and is a dict
        event_data = getattr(record, "event_data", None)
        if isinstance(event_data, dict):
            data.update(event_data)

        return json.dumps(data, default=str)


# ---------------------------------------------------------------------------
# configure_logging
# ---------------------------------------------------------------------------

def configure_logging(level: int = logging.INFO) -> None:
    """Configure the root logger to emit JSON Lines to stdout.

    Replaces any existing handlers on the root logger so that every call
    produces exactly one ``StreamHandler`` using ``JsonLinesFormatter``.

    Parameters
    ----------
    level:
        Minimum log level for the root logger (default: ``logging.INFO``).
    """
    root = logging.getLogger()
    # Remove all existing handlers
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLinesFormatter())
    root.addHandler(handler)
    root.setLevel(level)


# ---------------------------------------------------------------------------
# Structured event helpers
# ---------------------------------------------------------------------------

def emit_iteration_start(
    timestamp: datetime,
    active_handle_count: int,
    config_version: int,
) -> None:
    """Emit an ``iteration_start`` structured log entry at INFO level.

    Parameters
    ----------
    timestamp:
        The UTC datetime when this iteration began (used as the event's
        ``timestamp`` field — distinct from the log record's own ``timestamp``).
    active_handle_count:
        Number of handles with ``is_active = 1`` at iteration start.
    config_version:
        The ``config_version`` integer from the loaded scraping_config row.

    Requirement 17.2 — iteration_start fields: event, timestamp,
    active_handle_count, config_version.
    """
    _logger.info(
        "Iteration started",
        extra={
            "event_data": {
                "event": "iteration_start",
                "timestamp": timestamp.isoformat(),
                "active_handle_count": active_handle_count,
                "config_version": config_version,
            }
        },
    )


def emit_iteration_end(stats: IterationStats) -> None:
    """Emit an ``iteration_end`` structured log entry at INFO level.

    Parameters
    ----------
    stats:
        The completed ``IterationStats`` instance.  ``end_time`` should be
        set before calling this function; if it is ``None``, ``end_timestamp``
        will be ``None`` and ``duration_seconds`` will be ``0.0``.

    Requirement 17.2 — iteration_end fields: event, start_timestamp,
    end_timestamp, duration_seconds, posts_inserted, posts_updated,
    comments_inserted, engagement_snapshots_inserted, errors.
    """
    _logger.info(
        "Iteration ended",
        extra={
            "event_data": {
                "event": "iteration_end",
                "start_timestamp": stats.start_time.isoformat(),
                "end_timestamp": stats.end_time.isoformat() if stats.end_time is not None else None,
                "duration_seconds": stats.duration_seconds,
                "posts_inserted": stats.posts_inserted,
                "posts_updated": stats.posts_updated,
                "comments_inserted": stats.comments_inserted,
                "engagement_snapshots_inserted": stats.engagement_snapshots_inserted,
                "errors": stats.errors,
            }
        },
    )
