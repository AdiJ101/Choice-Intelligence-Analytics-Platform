"""
scripts/cleanup_qdrant_duplicates.py
─────────────────────────────────────
Removes Qdrant vectors whose MySQL source post has been deleted by the
014_deduplicate_posts.sql migration.

Run order
─────────
1. Apply the SQL migration first:
       mysql -u <user> -p choice_analytics < migrations/014_deduplicate_posts.sql
2. Then run this script:
       python scripts/cleanup_qdrant_duplicates.py
   Or for a preview without deleting:
       python scripts/cleanup_qdrant_duplicates.py --dry-run

How it works
────────────
- Loads every post id currently in MySQL.
- Scrolls through the Qdrant `content_embeddings` collection and collects
  every unique `source_record_id` that belongs to a 'post' vector.
- Any id present in Qdrant but absent from MySQL is considered orphaned.
- Orphaned vectors are deleted in batches using a payload filter.

Requirements: MYSQL_DSN, QDRANT_URL (and optionally QDRANT_API_KEY) must be
set in the project .env file (or in the shell environment).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import urllib.parse
from pathlib import Path

import mysql.connector
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

COLLECTION_NAME = "content_embeddings"
SCROLL_BATCH    = 1_000   # Qdrant scroll page size
DELETE_BATCH    = 500     # IDs per delete request


# ---------------------------------------------------------------------------
# MySQL helpers
# ---------------------------------------------------------------------------

def _mysql_conn() -> mysql.connector.MySQLConnection:
    dsn = os.environ.get("MYSQL_DSN", "")
    if not dsn:
        log.error("MYSQL_DSN is not set in the environment / .env file.")
        sys.exit(1)
    p = urllib.parse.urlparse(dsn)
    return mysql.connector.connect(
        host=p.hostname or "localhost",
        port=p.port or 3306,
        user=urllib.parse.unquote(p.username or ""),
        password=urllib.parse.unquote(p.password or ""),
        database=p.path.lstrip("/"),
    )


def get_mysql_post_ids(conn: mysql.connector.MySQLConnection) -> set[int]:
    """Return the set of every post id that currently exists in MySQL."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM posts")
        return {int(row[0]) for row in cursor.fetchall()}
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Qdrant helpers
# ---------------------------------------------------------------------------

def _qdrant_client() -> QdrantClient:
    url     = os.environ.get("QDRANT_URL", "http://localhost:6333")
    api_key = os.environ.get("QDRANT_API_KEY") or None
    return QdrantClient(url=url, api_key=api_key)


def get_qdrant_post_ids(client: QdrantClient) -> set[int]:
    """Scroll through Qdrant and return all unique post source_record_ids."""
    post_ids: set[int] = set()
    offset = None

    while True:
        results, next_offset = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="source_table",
                        match=MatchValue(value="post"),
                    )
                ]
            ),
            with_payload=["source_record_id"],
            with_vectors=False,
            limit=SCROLL_BATCH,
            offset=offset,
        )

        for point in results:
            if point.payload and "source_record_id" in point.payload:
                post_ids.add(int(point.payload["source_record_id"]))

        if next_offset is None:
            break
        offset = next_offset

    return post_ids


def delete_orphaned_vectors(
    client: QdrantClient,
    orphaned_ids: list[int],
    dry_run: bool,
) -> int:
    """Delete Qdrant vectors for each orphaned post id.

    Returns the total number of ids processed (regardless of dry_run).
    """
    if not orphaned_ids:
        log.info("No orphaned vectors found — Qdrant is already clean.")
        return 0

    total = 0
    for batch_start in range(0, len(orphaned_ids), DELETE_BATCH):
        batch = orphaned_ids[batch_start : batch_start + DELETE_BATCH]
        log.info(
            "  [batch %d/%d] %s vectors for %d post ids…",
            batch_start // DELETE_BATCH + 1,
            (len(orphaned_ids) + DELETE_BATCH - 1) // DELETE_BATCH,
            "Would delete" if dry_run else "Deleting",
            len(batch),
        )
        if not dry_run:
            client.delete(
                collection_name=COLLECTION_NAME,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="source_table",
                            match=MatchValue(value="post"),
                        ),
                        FieldCondition(
                            key="source_record_id",
                            match=MatchAny(any=batch),
                        ),
                    ]
                ),
            )
        total += len(batch)

    return total


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Delete orphaned Qdrant vectors after the dedup migration."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without making any changes.",
    )
    args = parser.parse_args()

    if args.dry_run:
        log.info("=== DRY RUN — no data will be modified ===")

    # ── MySQL ────────────────────────────────────────────────────────────────
    log.info("Connecting to MySQL…")
    conn = _mysql_conn()
    try:
        log.info("Reading current post ids from MySQL…")
        mysql_ids = get_mysql_post_ids(conn)
        log.info("  %d posts found in MySQL.", len(mysql_ids))
    finally:
        conn.close()

    # ── Qdrant ───────────────────────────────────────────────────────────────
    log.info("Connecting to Qdrant…")
    qdrant = _qdrant_client()

    log.info("Scrolling Qdrant for 'post' source_record_ids…")
    qdrant_ids = get_qdrant_post_ids(qdrant)
    log.info("  %d unique post ids referenced in Qdrant.", len(qdrant_ids))

    # ── Compare ──────────────────────────────────────────────────────────────
    orphaned = sorted(qdrant_ids - mysql_ids)
    log.info(
        "Orphaned post ids (in Qdrant but not in MySQL): %d", len(orphaned)
    )

    if orphaned:
        deleted = delete_orphaned_vectors(qdrant, orphaned, dry_run=args.dry_run)
        verb = "Would have deleted" if args.dry_run else "Deleted"
        log.info("%s vectors for %d orphaned post ids.", verb, deleted)
    
    log.info("Done.")


if __name__ == "__main__":
    main()
