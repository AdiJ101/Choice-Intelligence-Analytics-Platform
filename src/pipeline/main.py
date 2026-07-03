"""
src/pipeline/main.py — Entry point for the sync pipeline.

Reads posts and comments from MySQL, embeds them with BAAI/bge-m3,
and upserts the vectors into the Qdrant content_embeddings collection.

Usage:
    python -m src.pipeline.main

Runs a single full sync pass (posts then comments), then exits.
For continuous operation, run it on a cron or wrap in a loop externally.
"""

from __future__ import annotations

import logging
import sys
import urllib.parse

import mysql.connector
from qdrant_client import QdrantClient

from config import settings
from src.pipeline.embedder import EmbedderClient
from src.pipeline.processor import process_batch
from src.vector_db.collection import create_collection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    logger.info("Sync pipeline starting…")

    # ── MySQL connection ──────────────────────────────────────────────────
    parsed = urllib.parse.urlparse(settings.MYSQL_DSN)
    conn = mysql.connector.connect(
        host=parsed.hostname or "localhost",
        port=parsed.port or 3306,
        user=urllib.parse.unquote(parsed.username or ""),
        password=urllib.parse.unquote(parsed.password or ""),
        database=parsed.path.lstrip("/"),
    )
    logger.info("Connected to MySQL.")

    # ── Qdrant connection ─────────────────────────────────────────────────
    qdrant = QdrantClient(
        url=settings.QDRANT_URL,
        api_key=settings.QDRANT_API_KEY,
    )
    create_collection(qdrant)
    logger.info("Qdrant collection ready.")

    # ── Embedder ──────────────────────────────────────────────────────────
    logger.info("Loading embedding model '%s'…", settings.EMBED_MODEL)
    embedder = EmbedderClient(
        model_name=settings.EMBED_MODEL,
        target_dim=settings.EMBED_DIM,
    )
    logger.info("Embedding model loaded (native_dim=%d).", embedder.native_dim)

    # ── Process posts ─────────────────────────────────────────────────────
    total_posts = 0
    while True:
        count = process_batch(conn, qdrant, embedder, "post")
        total_posts += count
        logger.info("Post batch: %d processed (total so far: %d)", count, total_posts)
        if count == 0:
            break

    # ── Process comments ──────────────────────────────────────────────────
    total_comments = 0
    while True:
        count = process_batch(conn, qdrant, embedder, "comment")
        total_comments += count
        logger.info("Comment batch: %d processed (total so far: %d)", count, total_comments)
        if count == 0:
            break

    # ── Done ──────────────────────────────────────────────────────────────
    conn.close()
    logger.info(
        "Sync pipeline complete: %d posts + %d comments embedded.",
        total_posts, total_comments,
    )


if __name__ == "__main__":
    main()
