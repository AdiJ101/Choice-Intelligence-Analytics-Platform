"""
dashboard/backend/routers/scraper_status.py — Scraper status and control endpoints.

Reads persistent state from storage/scraper_state.json (written by the
ScraperOrchestrator) and provides control via storage/scraper_control.json.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from dashboard.backend.db import get_conn

router = APIRouter()
logger = logging.getLogger(__name__)

_STORAGE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage")


class ScraperControlRequest(BaseModel):
    command: str


def _is_scraper_running() -> bool:
    """Check if the scraper process (src.scraper.main) is alive."""
    try:
        result = subprocess.run(
            ["pgrep", "-f", "src.scraper.main"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


@router.get("/scraper/status")
def get_scraper_status():
    state_file = os.path.join(_STORAGE_DIR, "scraper_state.json")
    state: dict = {
        "status": "Stopped",
        "last_updated": None,
        "next_scheduled_scrape": None,
        "last_successful_scrape": None,
        "last_iteration_stats": None,
        "scraping_interval_minutes": None,
    }

    # Read persisted state
    try:
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                state.update(json.load(f))
    except Exception as exc:
        logger.warning("Could not read scraper state: %s", exc)

    # Fallback for last_successful_scrape using the history log
    if not state.get("last_successful_scrape"):
        try:
            history_file = os.path.join(_STORAGE_DIR, "scraper_history.jsonl")
            if os.path.exists(history_file):
                with open(history_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    if lines:
                        last_line = json.loads(lines[-1])
                        state["last_successful_scrape"] = last_line.get("ended_at") or last_line.get("started_at")
        except Exception as exc:
            logger.warning("Could not read scraper history: %s", exc)

    # If state says Running/Sleeping but the process is dead, correct it
    if state["status"] in ("Running", "Sleeping") and not _is_scraper_running():
        state["status"] = "Stopped"
        state["next_scheduled_scrape"] = None

    # Query DB for scraped-today count & recent videos
    scraped_today = 0
    recent_videos: list = []
    try:
        with get_conn() as conn:
            cursor = conn.cursor(dictionary=True)

            cursor.execute(
                "SELECT COUNT(*) as count FROM posts WHERE DATE(created_at) = CURDATE()"
            )
            row = cursor.fetchone()
            if row:
                scraped_today = row["count"]

            cursor.execute("""
                SELECT p.title, p.publish_timestamp, c.name as category_name,
                       pl.platform_code
                FROM posts p
                JOIN handles h ON p.handle_id = h.id
                JOIN categories c ON h.category_id = c.id
                JOIN platforms pl ON p.platform_id = pl.id
                ORDER BY p.created_at DESC
                LIMIT 5
            """)
            recent_videos = cursor.fetchall()
            for v in recent_videos:
                if v["publish_timestamp"]:
                    v["publish_timestamp"] = v["publish_timestamp"].isoformat()

        # If state file has no last_successful_scrape, fall back to DB
        if not state.get("last_successful_scrape"):
            cursor2 = conn.cursor(dictionary=True)
            cursor2.execute(
                "SELECT MAX(created_at) as last_scrape FROM posts"
            )
            r = cursor2.fetchone()
            if r and r["last_scrape"]:
                state["last_successful_scrape"] = r["last_scrape"].isoformat()
    except Exception as exc:
        logger.warning("Could not query scraper stats: %s", exc)

    state["scraped_today"] = scraped_today
    state["recent_videos"] = recent_videos
    return state


@router.post("/scraper/control")
def control_scraper(req: ScraperControlRequest):
    if req.command not in ("run_now", "stop", "start"):
        return {"error": "Invalid command"}
    control_file = os.path.join(_STORAGE_DIR, "scraper_control.json")
    try:
        os.makedirs(_STORAGE_DIR, exist_ok=True)
        with open(control_file, "w", encoding="utf-8") as f:
            json.dump(
                {"command": req.command, "timestamp": datetime.now(tz=timezone.utc).isoformat()},
                f,
            )
    except Exception as exc:
        logger.error("Failed to write scraper control: %s", exc)
        return {"error": str(exc)}
    return {"status": "success"}
