"""
settings.py — centralised configuration loader.

All settings are sourced from environment variables (loaded from a .env file
via python-dotenv).  The module raises a clear error at import time if a
required variable is missing, so mis-configuration is caught early rather than
at first use.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env from the project root (two levels up from this file: config/ → root)
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_ENV_PATH, override=False)


def _require(name: str) -> str:
    """Return the value of a required environment variable or raise."""
    value = os.environ.get(name)
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{name}' is not set. "
            f"Check your .env file or shell environment."
        )
    return value


# ---------------------------------------------------------------------------
# Required settings (no defaults — the application cannot run without these)
# ---------------------------------------------------------------------------

#: MySQL DSN in the format: mysql+mysqlconnector://user:password@host:port/dbname
MYSQL_DSN: str = _require("MYSQL_DSN")

# ---------------------------------------------------------------------------
# Optional settings (sensible defaults provided)
# ---------------------------------------------------------------------------

#: Base URL for the Qdrant REST/gRPC endpoint
QDRANT_URL: str = os.environ.get("QDRANT_URL", "http://localhost:6333")

#: API key for authenticated Qdrant Cloud instances (None for local/no-auth)
QDRANT_API_KEY: Optional[str] = os.environ.get("QDRANT_API_KEY", None) or None

#: HuggingFace model ID used for generating embeddings
EMBED_MODEL: str = os.environ.get("EMBED_MODEL", "BAAI/bge-m3")

#: Dimensionality of the output embedding vectors
EMBED_DIM: int = int(os.environ.get("EMBED_DIM", "1536"))

#: Number of MySQL rows fetched per sync pipeline iteration
SYNC_BATCH_SIZE: int = int(os.environ.get("SYNC_BATCH_SIZE", "500"))

#: Configurable lag window (minutes) for the sync pipeline (valid range: 1–1440)
SYNC_LAG_MINUTES: int = int(os.environ.get("SYNC_LAG_MINUTES", "15"))

#: Maximum number of chunks produced from a single source record
MAX_CHUNKS: int = int(os.environ.get("MAX_CHUNKS", "500"))

#: Maximum number of tokens per chunk before splitting
CHUNK_MAX_TOKENS: int = int(os.environ.get("CHUNK_MAX_TOKENS", "512"))

#: Number of overlapping tokens between consecutive chunks
CHUNK_OVERLAP: int = int(os.environ.get("CHUNK_OVERLAP", "50"))

#: Maximum retry attempts before a failed record is written to the dead-letter queue
DLQ_MAX_RETRIES: int = int(os.environ.get("DLQ_MAX_RETRIES", "5"))
