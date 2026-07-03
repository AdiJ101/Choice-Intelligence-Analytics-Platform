"""
orchestrator.py — ScraperOrchestrator: scheduling, iteration loop,
signal handling, and per-handle dispatch.

Key design decisions:

Fixed-interval scheduling (Requirement 4.2):
  next_start = iteration_start + timedelta(minutes=scraping_interval_minutes)
  This prevents drift — the gap between starts stays constant regardless
  of how long an iteration takes.

Signal handling (Requirement 4.6):
  A threading.Event (_stop_event) is set by SIGTERM/SIGINT handlers.
  The run_loop checks this event in its sleep phase using event.wait(timeout).
  The current MySQL write is allowed to complete before shutdown.

  threading.Event is preferred over flag variables because:
  - wait(timeout) is interruptible — signal arrives immediately, no busy-wait
  - It's thread-safe by design
  - Compatible with the GIL and the single-threaded nature of this service
"""

from __future__ import annotations

import json
import logging
import os
import signal
import threading
import time
from datetime import datetime, timezone
from typing import Any

from .logger import IterationStats, emit_iteration_end, emit_iteration_start
from .registry import ADAPTER_REGISTRY

logger = logging.getLogger(__name__)


class ScraperOrchestrator:
    """Manages the scraping loop and dispatches per-handle work.

    Parameters
    ----------
    config:
        The validated scraping config dict (output of validate_config).
    conn:
        Open MySQL connection (caller retains ownership).
    enabled_platforms:
        Dict mapping platform_code → bool from check_credentials().
    config_version:
        The config_version integer from the loaded scraping_config row.
    """

    def __init__(
        self,
        config: dict,
        conn: Any,
        enabled_platforms: dict[str, bool],
        config_version: int = 1,
    ) -> None:
        self._config = config
        self._conn = conn
        self._enabled_platforms = enabled_platforms
        self._config_version = config_version
        self._stop_event = threading.Event()

        # Register SIGTERM and SIGINT handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum: int, frame: Any) -> None:
        """Set the stop event when SIGTERM or SIGINT is received."""
        logger.info(
            "Received signal %d — will stop after current handle completes.",
            signum,
        )
        self._stop_event.set()

    def run_once(self) -> IterationStats:
        """Execute a single iteration: process all active handles once."""
        from .handle_processor import process_handle

        sc = self._config["scraping_config"]
        interval_minutes: int = sc["scraping_interval_minutes"]

        start_time = datetime.now(tz=timezone.utc)
        stats = IterationStats(start_time=start_time)

        # Track unknown platform codes to emit one WARNING per code per iteration
        warned_platforms: set[str] = set()

        emit_iteration_start(start_time, self._count_active_handles(), self._config_version)

        cursor = self._conn.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT h.*, p.platform_code "
                "FROM handles h "
                "JOIN platforms p ON h.platform_id = p.id "
                "WHERE h.is_active = 1"
            )
            handles = cursor.fetchall()
        finally:
            cursor.close()

        for handle_row in handles:
            if self._stop_event.is_set():
                break

            platform_code: str = handle_row["platform_code"]

            # Skip disabled platforms (credential absent or explicitly disabled)
            if not self._enabled_platforms.get(platform_code, False):
                continue

            # Registry dispatch — no platform-specific if/elif branching
            if platform_code not in ADAPTER_REGISTRY:
                if platform_code not in warned_platforms:
                    logger.warning(
                        "No adapter registered for platform code %r — "
                        "skipping all handles for this platform this iteration.",
                        platform_code,
                    )
                    warned_platforms.add(platform_code)
                continue

            AdapterClass = ADAPTER_REGISTRY[platform_code]
            adapter = AdapterClass()

            try:
                handle_stats = process_handle(
                    handle_row=handle_row,
                    adapter=adapter,
                    conn=self._conn,
                    config=self._config,
                )
                stats.posts_inserted += handle_stats.posts_inserted
                stats.posts_updated += handle_stats.posts_updated
                stats.comments_inserted += handle_stats.comments_inserted
                stats.engagement_snapshots_inserted += handle_stats.engagement_snapshots_inserted
            except Exception as exc:
                self._conn.rollback()
                stats.errors += 1
                logger.error(
                    "Handle processing failed: platform=%r handle=%r error=%s",
                    platform_code,
                    handle_row.get("platform_native_handle"),
                    exc,
                    exc_info=True,
                )

        stats.end_time = datetime.now(tz=timezone.utc)

        duration = stats.duration_seconds
        if duration > interval_minutes * 60:
            logger.warning(
                "Iteration exceeded configured interval: "
                "start=%s duration_seconds=%.1f interval_minutes=%d",
                start_time.isoformat(),
                duration,
                interval_minutes,
            )

        emit_iteration_end(stats)
        return stats

    def _get_state_file(self) -> str:
        return os.path.join(os.path.dirname(__file__), "..", "..", "storage", "scraper_state.json")

    def _get_control_file(self) -> str:
        return os.path.join(os.path.dirname(__file__), "..", "..", "storage", "scraper_control.json")

    def _update_state(self, status: str, next_scheduled_scrape: str | None = None) -> None:
        state = {
            "status": status,
            "last_updated": datetime.now(tz=timezone.utc).isoformat(),
            "next_scheduled_scrape": next_scheduled_scrape,
        }
        state_file = self._get_state_file()
        try:
            os.makedirs(os.path.dirname(state_file), exist_ok=True)
            if os.path.exists(state_file):
                with open(state_file, "r", encoding="utf-8") as f:
                    old_state = json.load(f)
                    
                    # Preserve old next_scheduled_scrape if not explicitly overridden
                    if next_scheduled_scrape is None and "next_scheduled_scrape" in old_state:
                        state["next_scheduled_scrape"] = old_state["next_scheduled_scrape"]
                        
                    # Preserve other persistent fields across state transitions
                    for key in ("last_successful_scrape", "last_iteration_stats",
                                "scraping_interval_minutes"):
                        if key in old_state:
                            state[key] = old_state[key]
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f)
        except Exception as exc:
            logger.warning("Failed to write scraper state: %s", exc)

    def _save_iteration_results(self, stats: IterationStats) -> None:
        """Persist last scrape timestamp and iteration stats to disk."""
        state_file = self._get_state_file()
        try:
            state = {}
            if os.path.exists(state_file):
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
            state["last_successful_scrape"] = datetime.now(tz=timezone.utc).isoformat()
            sc = self._config.get("scraping_config", {})
            state["scraping_interval_minutes"] = sc.get("scraping_interval_minutes", 60)
            state["last_iteration_stats"] = {
                "posts_inserted": stats.posts_inserted,
                "posts_updated": stats.posts_updated,
                "comments_inserted": stats.comments_inserted,
                "engagement_snapshots_inserted": stats.engagement_snapshots_inserted,
                "errors": stats.errors,
                "duration_seconds": round(stats.duration_seconds, 1),
                "started_at": stats.start_time.isoformat(),
                "ended_at": stats.end_time.isoformat() if stats.end_time else None,
            }
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(state, f)
        except Exception as exc:
            logger.warning("Failed to save iteration results: %s", exc)

        # Log history to JSON Lines file
        try:
            history_file = os.path.join(os.path.dirname(__file__), "..", "..", "storage", "scraper_history.jsonl")
            with open(history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "started_at": stats.start_time.isoformat(),
                    "ended_at": stats.end_time.isoformat() if stats.end_time else None,
                    "duration_seconds": round(stats.duration_seconds, 1),
                    "posts_inserted": stats.posts_inserted,
                    "posts_updated": stats.posts_updated,
                    "comments_inserted": stats.comments_inserted,
                    "engagement_snapshots_inserted": stats.engagement_snapshots_inserted,
                    "errors": stats.errors,
                }) + "\n")
        except Exception as exc:
            logger.warning("Failed to save iteration history log: %s", exc)

    def _check_control(self) -> str | None:
        control_file = self._get_control_file()
        try:
            if os.path.exists(control_file):
                with open(control_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data.get("command")
        except Exception:
            pass
        return None

    def _clear_control(self) -> None:
        control_file = self._get_control_file()
        try:
            if os.path.exists(control_file):
                os.remove(control_file)
        except Exception:
            pass

    def run_loop(self) -> None:
        """Run iterations in a fixed-interval loop until SIGTERM/SIGINT."""
        sc = self._config["scraping_config"]
        interval_seconds: float = sc["scraping_interval_minutes"] * 60

        # Startup check: should we wait before the first scrape?
        startup_sleep_seconds = 0.0
        next_run_str = None
        state_file = self._get_state_file()
        if os.path.exists(state_file):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    old_state = json.load(f)
                    next_run_str = old_state.get("next_scheduled_scrape")
                    if next_run_str:
                        next_run_dt = datetime.fromisoformat(next_run_str)
                        now_dt = datetime.now(tz=timezone.utc)
                        if next_run_dt > now_dt:
                            startup_sleep_seconds = (next_run_dt - now_dt).total_seconds()
                            logger.info(
                                "Scraper restarted. Next scheduled scrape is in the future: %s. "
                                "Sleeping for %.1f seconds before starting.",
                                next_run_str,
                                startup_sleep_seconds,
                            )
            except Exception as exc:
                logger.warning("Failed to check startup schedule: %s", exc)

        first_iteration = True

        while not self._stop_event.is_set():
            # Respect the previous next_scheduled_scrape on startup
            if first_iteration and startup_sleep_seconds > 0.0:
                self._update_state("Sleeping", next_scheduled_scrape=next_run_str)
                # Sleep incrementally, checking for user commands
                for _ in range(int(startup_sleep_seconds)):
                    if self._stop_event.is_set():
                        break
                    cmd = self._check_control()
                    if cmd == "run_now":
                        self._clear_control()
                        break
                    elif cmd == "stop":
                        break
                    time.sleep(1.0)
                startup_sleep_seconds = 0.0

            first_iteration = False

            cmd = self._check_control()
            if cmd == "stop":
                self._update_state("Stopped")
                self._clear_control()
                while not self._stop_event.is_set():
                    cmd = self._check_control()
                    if cmd in ("start", "run_now"):
                        self._clear_control()
                        break
                    time.sleep(1.0)
                if self._stop_event.is_set():
                    break

            iter_start = datetime.now(tz=timezone.utc)
            next_run = iter_start.timestamp() + interval_seconds
            next_dt = datetime.fromtimestamp(next_run, tz=timezone.utc).isoformat()
            
            # Set running state with the computed next scrape time
            self._update_state("Running", next_dt)
            stats = self.run_once()
            self._save_iteration_results(stats)

            if self._stop_event.is_set():
                break

            now = datetime.now(tz=timezone.utc)
            elapsed = (now - iter_start).total_seconds()
            sleep_seconds = max(0.0, interval_seconds - elapsed)
            
            self._update_state("Sleeping", next_dt)

            for _ in range(int(sleep_seconds)):
                if self._stop_event.is_set():
                    break
                cmd = self._check_control()
                if cmd == "run_now":
                    self._clear_control()
                    break
                elif cmd == "stop":
                    break
                time.sleep(1.0)

        self._update_state("Stopped")
        logger.info("ScraperOrchestrator shut down cleanly.")

    def _count_active_handles(self) -> int:
        """Return the count of handles with is_active=1."""
        cursor = self._conn.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM handles WHERE is_active = 1")
            row = cursor.fetchone()
            return int(row[0]) if row else 0
        finally:
            cursor.close()
