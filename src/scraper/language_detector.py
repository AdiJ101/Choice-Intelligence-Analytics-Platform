"""
language_detector.py — Thin wrapper around the langdetect library.

Why langdetect:
- Open-source (Apache 2.0), works fully offline — no API key needed.
- Supports 55+ languages including Hindi (hi), Chinese (zh-cn/zh-tw),
  Arabic (ar), Japanese (ja), Korean (ko), and all major European languages.
- Returns ISO 639-1 two-character codes directly.
- Confidence threshold: langdetect's detect_langs() returns a list of
  Language objects with probability scores; we use detect() which returns
  the highest-probability language only. We rely on its built-in threshold.

Requirement 8: language detection for posts and comments.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def detect_language(text: str | None) -> str | None:
    """Detect the ISO 639-1 language code for *text*.

    Parameters
    ----------
    text:
        The text to analyse. If None or empty/whitespace-only, returns None
        immediately without calling langdetect.

    Returns
    -------
    str | None
        Exactly 2 lowercase ASCII characters (ISO 639-1 code), or None if:
        - text is None or empty / whitespace-only
        - langdetect raises any exception
        - the returned code is not exactly 2 lowercase ASCII letters

    Notes
    -----
    langdetect can occasionally return codes like "zh-cn" for Chinese.
    We normalise these by taking only the first 2 characters.
    This function NEVER raises — all exceptions are caught and None returned.
    """
    if not text or not text.strip():
        return None

    try:
        from langdetect import detect  # lazy import

        raw: str = detect(text)

        # Normalise: take first 2 chars and lowercase
        code = raw[:2].lower()

        # Validate: must be exactly 2 lowercase ASCII letters
        if len(code) == 2 and code.isalpha() and code.isascii():
            return code
        return None

    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "Language detection failed for text (len=%d): %s",
            len(text),
            exc,
        )
        return None
