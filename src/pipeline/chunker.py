"""
src.pipeline.chunker — Text chunking utilities for the Sync Pipeline.

Splits long text into overlapping token windows suitable for embedding with
the BAAI/bge-m3 model.  Each chunk is returned as a (chunk_index, text) tuple
where chunk_index is zero-based.

The tokenizer is loaded lazily on the first call to chunk_text() and cached
for the lifetime of the process so that repeated calls do not pay the model-
load overhead.

Requirements: 7.5, 7.8
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass  # avoid circular imports at type-check time

# ---------------------------------------------------------------------------
# Model identifier
# ---------------------------------------------------------------------------

_MODEL_NAME = "BAAI/bge-m3"


# ---------------------------------------------------------------------------
# Custom exception
# ---------------------------------------------------------------------------


class OversizedChunkError(Exception):
    """Raised when a produced chunk still exceeds the model's token limit.

    This should not happen under normal operation because the sliding-window
    algorithm guarantees each slice is at most *max_tokens* long.  The check
    acts as a final safety guard.

    Attributes:
        chunk_index (int): Zero-based index of the offending chunk.
        token_count (int): Actual token count of the offending chunk.
    """

    def __init__(self, chunk_index: int, token_count: int) -> None:
        self.chunk_index = chunk_index
        self.token_count = token_count
        super().__init__(
            f"Chunk {chunk_index} has {token_count} tokens, which exceeds the "
            "model's maximum token limit."
        )


# ---------------------------------------------------------------------------
# Lazy tokenizer singleton
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=1)
def _get_tokenizer():
    """Load and return the BAAI/bge-m3 tokenizer (cached after first call).

    Raises:
        ImportError: If the ``transformers`` package is not installed.
    """
    try:
        from transformers import AutoTokenizer  # type: ignore[import]
    except ModuleNotFoundError as exc:
        raise ImportError(
            "The 'transformers' package is required for text chunking. "
            "Install it with: pip install transformers"
        ) from exc

    return AutoTokenizer.from_pretrained(_MODEL_NAME, use_fast=True)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def chunk_text(
    text: str | None,
    max_tokens: int = 512,
    overlap: int = 50,
    max_chunks: int = 500,
) -> list[tuple[int, str]]:
    """Split *text* into overlapping token windows for embedding.

    Parameters
    ----------
    text:
        Input text to chunk.  ``None`` and empty strings are treated
        identically — a single ``(0, "")`` tuple is returned.
    max_tokens:
        Maximum number of tokens per chunk (default: 512, matching
        bge-m3's practical window size for this pipeline).
    overlap:
        Number of tokens shared between consecutive windows
        (default: 50).  Must be less than *max_tokens*.
    max_chunks:
        Hard upper bound on the number of chunks produced per source
        record (default: 500, per Requirement 7.5).

    Returns
    -------
    list[tuple[int, str]]
        A list of ``(chunk_index, chunk_text)`` tuples.  ``chunk_index``
        is zero-based.  When the full text fits within *max_tokens*, the
        list contains exactly one tuple ``(0, text)`` using the *original*
        text string (not the re-decoded version).

    Raises
    ------
    OversizedChunkError
        If any produced chunk still has more tokens than *max_tokens*
        after slicing (guards against unexpected tokenizer behaviour).
    ImportError
        If the ``transformers`` package is not installed.
    """
    # ------------------------------------------------------------------
    # Edge-case: empty / None input
    # ------------------------------------------------------------------
    if not text:
        return [(0, "")]

    tokenizer = _get_tokenizer()

    # Tokenize without adding special tokens so the window arithmetic
    # stays clean.  Special tokens are skipped on decode as well.
    token_ids: list[int] = tokenizer.encode(text, add_special_tokens=False)
    total_tokens = len(token_ids)

    # ------------------------------------------------------------------
    # Fast path: whole text fits in one chunk — return original string
    # ------------------------------------------------------------------
    if total_tokens <= max_tokens:
        return [(0, text)]

    # ------------------------------------------------------------------
    # Sliding window over token IDs
    # ------------------------------------------------------------------
    step = max_tokens - overlap
    if step <= 0:
        # Degenerate config — avoid infinite loop
        step = 1

    chunks: list[tuple[int, str]] = []
    start = 0
    chunk_index = 0

    while start < total_tokens and chunk_index < max_chunks:
        chunk_ids = token_ids[start : start + max_tokens]
        decoded = tokenizer.decode(chunk_ids, skip_special_tokens=True)
        chunks.append((chunk_index, decoded))
        start += step
        chunk_index += 1

    # ------------------------------------------------------------------
    # Safety guard: verify no chunk exceeds max_tokens
    # ------------------------------------------------------------------
    for i, (idx, chunk_str) in enumerate(chunks):
        chunk_token_count = len(
            tokenizer.encode(chunk_str, add_special_tokens=False)
        )
        if chunk_token_count > max_tokens:
            raise OversizedChunkError(
                chunk_index=idx, token_count=chunk_token_count
            )

    return chunks
