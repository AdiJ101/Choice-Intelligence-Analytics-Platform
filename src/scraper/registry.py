"""
registry.py — Central mapping from platform code to Adapter class.

To add a new platform:
  1. Create src/scraper/adapters/<platform>.py subclassing BaseAdapter.
  2. Add one entry here: ADAPTER_REGISTRY["<platform_code>"] = YourAdapter
  3. No other file needs modification.
"""
from __future__ import annotations
from .base_adapter import BaseAdapter
from .adapters.youtube   import YouTubeAdapter
from .adapters.twitter   import TwitterAdapter
from .adapters.linkedin  import LinkedInAdapter
from .adapters.instagram import InstagramAdapter
from .adapters.facebook  import FacebookAdapter

ADAPTER_REGISTRY: dict[str, type[BaseAdapter]] = {
    "youtube":   YouTubeAdapter,
    "twitter-x": TwitterAdapter,
    "linkedin":  LinkedInAdapter,
    "instagram": InstagramAdapter,
    "facebook":  FacebookAdapter,
}
