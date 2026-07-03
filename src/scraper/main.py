"""
main.py — Entry point for the Scraper Service.

Wires together all components in the correct startup order:
  1. Configure structured JSON-lines logging.
  2. Read and parse the scraping config JSON file (SCRAPER_CONFIG_PATH).
  3. Validate the config with validate_config().
  4. Check platform credentials with check_credentials().
  5. Connect to MySQL using settings from config/settings.py.
  6. Load config into MySQL with load_scraping_config().
  7. Query the current config_version.
  8. Construct ScraperOrchestrator and run the scraping loop.

Requirements: 1.1, 1.2, 1.8, 1.9, 1.11, 2.6, 9.1
"""

from __future__ import annotations

import json
import logging
import os
import sys
import urllib.parse

import mysql.connector

from config import settings
from src.config_loader.loader import load_scraping_config
from src.scraper.config_validator import validate_config
from src.scraper.credential_checker import check_credentials
from src.scraper.logger import configure_logging
from src.scraper.orchestrator import ScraperOrchestrator

logger = logging.getLogger(__name__)


def main() -> None:
    """Start the Scraper Service.

    Exits with code 1 on any fatal startup error, logging the reason
    as a structured ERROR entry before exiting.
    """

    # 1. Configure structured logging first so all subsequent messages
    #    are emitted as JSON Lines.
    configure_logging()

    # 2. Read SCRAPER_CONFIG_PATH from the environment.
    config_path = os.environ.get("SCRAPER_CONFIG_PATH", "")
    if not config_path:
        logger.error("SCRAPER_CONFIG_PATH environment variable is not set")
        sys.exit(1)

    # 3. Open and parse the JSON config file.
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            config_dict: dict = json.load(fh)
    except OSError as exc:
        logger.error("Failed to open config file %r: %s", config_path, exc)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse config file %r: %s", config_path, exc)
        sys.exit(1)

    # 4. Validate config structure and value ranges.
    try:
        validate_config(config_dict)
    except ValueError as exc:
        logger.error("Config validation failed: %s", exc)
        sys.exit(1)

    # 5. Check platform credentials; at least one must be enabled.
    enabled_platforms = check_credentials()
    if not any(enabled_platforms.values()):
        logger.error(
            "No platform credentials are configured. "
            "Set at least one of YOUTUBE_API_KEY, TWITTER_BEARER_TOKEN, "
            "LINKEDIN_ACCESS_TOKEN, INSTAGRAM_ACCESS_TOKEN, or FACEBOOK_PAGE_ACCESS_TOKEN."
        )
        sys.exit(1)

    # 6. Connect to MySQL.
    #    MYSQL_DSN format: mysql://user:password@host:port/database
    #    (or mysql+mysqlconnector://...)
    parsed = urllib.parse.urlparse(settings.MYSQL_DSN)
    db_host = parsed.hostname or "localhost"
    db_port = parsed.port or 3306
    db_user = parsed.username or ""
    # Password may be URL-encoded (e.g. %23 for #); decode it.
    db_password = urllib.parse.unquote(parsed.password or "")
    # Strip the leading "/" from the path to get the database name.
    db_name = parsed.path.lstrip("/")

    conn = mysql.connector.connect(
        host=db_host,
        port=db_port,
        user=db_user,
        password=db_password,
        database=db_name,
    )

    # 7. Load the scraping config into MySQL (upserts categories, handles, etc.).
    try:
        load_scraping_config(conn, config_dict)
    except ValueError as exc:
        logger.error("Failed to load scraping config into database: %s", exc)
        conn.close()
        sys.exit(1)

    # 8. Query the current MAX(config_version) from scraping_config.
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT MAX(config_version) FROM scraping_config")
        row = cursor.fetchone()
        config_version: int = row[0] if row and row[0] is not None else 1
    finally:
        cursor.close()

    # 9. Construct the orchestrator with all wired dependencies.
    orchestrator = ScraperOrchestrator(
        config=config_dict,
        conn=conn,
        enabled_platforms=enabled_platforms,
        config_version=config_version,
    )

    # 10. Run the scraping loop; always close the connection on exit.
    try:
        orchestrator.run_loop()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
