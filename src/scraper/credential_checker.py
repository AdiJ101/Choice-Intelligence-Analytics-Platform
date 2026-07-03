"""
credential_checker.py — Startup credential validation.

Per-platform availability logic:

  youtube    Always enabled — yt-dlp needs no credentials.

  instagram  Enabled if INSTAGRAM_USERNAME + INSTAGRAM_PASSWORD set (instagrapi).
             Falls back to Firecrawl if only FIRECRAWL_API_KEY is set.

  linkedin   Enabled if LINKEDIN_USERNAME + LINKEDIN_PASSWORD set (linkedin-api).
             Falls back to Firecrawl if only FIRECRAWL_API_KEY is set.

  facebook   Enabled if FACEBOOK_EMAIL + FACEBOOK_PASSWORD set (facebook-scraper).
             Falls back to Firecrawl if only FIRECRAWL_API_KEY is set.

  twitter-x  Enabled if TWITTER_USERNAME + TWITTER_PASSWORD set (twikit — best).
             Falls back to Firecrawl if only FIRECRAWL_API_KEY is set.
             Disabled if neither is present.

Credential values are never logged — only their presence or absence.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def check_credentials() -> dict[str, bool]:
    """Return a dict mapping each platform_code → True (available) / False (disabled)."""

    firecrawl_ok = bool(os.environ.get("FIRECRAWL_API_KEY", ""))

    ig_ok = bool(
        os.environ.get("INSTAGRAM_USERNAME", "")
        and os.environ.get("INSTAGRAM_PASSWORD", "")
    )
    li_ok = bool(
        os.environ.get("LINKEDIN_USERNAME", "")
        and os.environ.get("LINKEDIN_PASSWORD", "")
    )
    fb_ok = bool(
        os.environ.get("FACEBOOK_EMAIL", "")
        and os.environ.get("FACEBOOK_PASSWORD", "")
    )
    tw_ok = bool(
        os.environ.get("TWITTER_USERNAME", "")
        and os.environ.get("TWITTER_PASSWORD", "")
    )

    result = {
        "youtube":   True,
        "instagram": ig_ok or firecrawl_ok,
        "linkedin":  li_ok or firecrawl_ok,
        "facebook":  fb_ok or firecrawl_ok,
        "twitter-x": tw_ok or firecrawl_ok,   # twikit preferred, Firecrawl fallback
    }

    if not firecrawl_ok and not tw_ok:
        logger.warning(
            "twitter-x DISABLED — set TWITTER_USERNAME + TWITTER_PASSWORD "
            "(recommended) or FIRECRAWL_API_KEY to enable it."
        )

    _log_platform("instagram",  ig_ok, "INSTAGRAM_USERNAME + INSTAGRAM_PASSWORD",
                  firecrawl_ok, result["instagram"])
    _log_platform("linkedin",   li_ok, "LINKEDIN_USERNAME + LINKEDIN_PASSWORD",
                  firecrawl_ok, result["linkedin"])
    _log_platform("facebook",   fb_ok, "FACEBOOK_EMAIL + FACEBOOK_PASSWORD",
                  firecrawl_ok, result["facebook"])
    _log_platform("twitter-x",  tw_ok, "TWITTER_USERNAME + TWITTER_PASSWORD",
                  firecrawl_ok, result["twitter-x"])

    disabled = [p for p, ok in result.items() if not ok]
    if disabled:
        logger.warning("Disabled platforms (no credentials): %s", disabled)

    return result


def _log_platform(platform, creds_ok, cred_names, firecrawl_ok, enabled):
    if not enabled:
        logger.warning("%s DISABLED — set %s or FIRECRAWL_API_KEY.", platform, cred_names)
    elif creds_ok:
        logger.info("%s enabled — using dedicated credentials.", platform)
    else:
        logger.info("%s enabled — Firecrawl fallback (no dedicated credentials).", platform)
