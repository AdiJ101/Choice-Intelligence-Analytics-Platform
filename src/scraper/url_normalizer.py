"""
url_normalizer.py — Extract platform-native handles from social media URLs.

The scraper_config.json accepts both URLs and bare handles as values:
  youtube:   https://www.youtube.com/@ChoiceTechLab  →  @ChoiceTechLab
  twitter-x: https://twitter.com/ChoiceHQ_Social     →  ChoiceHQ_Social
  linkedin:  https://linkedin.com/company/choice-hq/ →  choice-hq
  instagram: https://www.instagram.com/choicetechlab/ → choicetechlab
  facebook:  https://www.facebook.com/ChoiceHQ/       → ChoiceHQ

If the value is already a bare handle (no http), returns it unchanged.
"""

from __future__ import annotations
import re
from urllib.parse import urlparse


def normalize_handle(platform_code: str, raw_value: str) -> str:
    """Extract a clean handle/identifier from a URL or bare handle string.
    
    Parameters
    ----------
    platform_code : str
        One of: youtube, twitter-x, linkedin, instagram, facebook
    raw_value : str
        Either a full URL (https://...) or a bare handle (@user, username, etc.)
    
    Returns
    -------
    str
        The clean handle suitable for passing to the adapter.
        For YouTube: keeps the @ prefix if present (e.g. @ChoiceTechLab)
        For others: just the username/slug portion
    """
    raw = raw_value.strip()
    
    # If not a URL, return as-is (already a bare handle)
    if not raw.startswith("http"):
        return raw
    
    parsed = urlparse(raw)
    # Remove trailing slashes and query strings from path
    path = parsed.path.rstrip("/")
    
    if platform_code == "youtube":
        # https://www.youtube.com/@ChoiceTechLab  → @ChoiceTechLab
        # https://www.youtube.com/channel/UCxxx   → UCxxx
        # https://www.youtube.com/user/SomeName   → SomeName
        # Strip any query params from path first
        path = path.split("?")[0].rstrip("/")
        segments = [s for s in path.split("/") if s]
        if segments:
            last = segments[-1]
            # Keep @ prefix for handles
            return last  # e.g. @ChoiceTechLab or UCxxxxxxxx
        return raw
    
    elif platform_code == "twitter-x":
        # https://twitter.com/ChoiceHQ_Social → ChoiceHQ_Social
        # https://x.com/ChoiceHQ_Social → ChoiceHQ_Social
        segments = [s for s in path.split("/") if s]
        if segments:
            return segments[-1].lstrip("@")
        return raw
    
    elif platform_code == "linkedin":
        # https://www.linkedin.com/company/choice-hq/ → choice-hq
        # https://linkedin.com/company/choice-techlab-solutions-pvt-ltd → choice-techlab-solutions-pvt-ltd
        match = re.search(r"/company/([^/?#]+)", path)
        if match:
            return match.group(1)
        segments = [s for s in path.split("/") if s]
        if segments:
            return segments[-1]
        return raw
    
    elif platform_code == "instagram":
        # https://www.instagram.com/choicetechlab_official/ → choicetechlab_official
        segments = [s for s in path.split("/") if s]
        if segments:
            return segments[-1]
        return raw
    
    elif platform_code == "facebook":
        # https://www.facebook.com/choicetechlab → choicetechlab
        # https://www.facebook.com/ChoiceHQ/ → ChoiceHQ
        segments = [s for s in path.split("/") if s]
        if segments:
            return segments[-1]
        return raw
    
    # Unknown platform — return as-is
    return raw
