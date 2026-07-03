"""
youtube.py — YouTubeAdapter using yt-dlp (no API key required).

yt-dlp extracts publicly available metadata from YouTube channels and videos
without requiring a Google API key. It handles @handles, channel IDs, and URLs.

Requirements covered: 10.2, 10.3, 10.4, 10.5, 10.6
"""

from __future__ import annotations

import logging
import os
import ssl
import certifi
from datetime import datetime, timezone
from typing import Any

# Fix SSL certificate verification on macOS with pyenv Python
os.environ.setdefault("SSL_CERT_FILE", certifi.where())
os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
ssl._create_default_https_context = ssl._create_unverified_context

from ..base_adapter import BaseAdapter
from ..models import NormalisedComment, NormalisedEngagement, NormalisedPost

logger = logging.getLogger(__name__)

# Browser to pull YouTube cookies from, to bypass "confirm you're not a bot"
# bot-detection. Configurable via env; defaults to chrome. Set to empty to disable.
_COOKIE_BROWSER = os.environ.get("YT_COOKIE_BROWSER", "chrome").strip()


def _base_ydl_opts() -> dict:
    """Return base yt-dlp options with browser cookies if configured."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "ignoreerrors": True,
    }
    if _COOKIE_BROWSER:
        opts["cookiesfrombrowser"] = (_COOKIE_BROWSER,)
    return opts


def _parse_yt_date(date_str: str | None) -> datetime:
    """Parse yt-dlp's upload_date (YYYYMMDD) or ISO timestamp to UTC datetime."""
    if not date_str:
        return datetime.now(tz=timezone.utc)
    # yt-dlp returns upload_date as 'YYYYMMDD'
    if len(date_str) == 8 and date_str.isdigit():
        try:
            return datetime(
                int(date_str[:4]),
                int(date_str[4:6]),
                int(date_str[6:8]),
                tzinfo=timezone.utc,
            )
        except ValueError:
            pass
    # Try ISO format
    try:
        normalised = date_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalised)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return datetime.now(tz=timezone.utc)


class YouTubeAdapter(BaseAdapter):
    """YouTube adapter using yt-dlp — no API credentials required.

    yt-dlp fetches publicly available video metadata and comments directly
    from YouTube without needing a Google API key.

    Parameters
    ----------
    handle_id:
        The handles.id FK to stamp on each NormalisedPost. Defaults to 0.
    """

    platform_code = "youtube"

    def __init__(self, handle_id: int = 0) -> None:
        super().__init__()
        self._handle_id: int = handle_id

    def authenticate(self) -> None:
        """No credentials needed for yt-dlp. Just marks the adapter as ready."""
        self._authenticated = True
        logger.debug("YouTubeAdapter (yt-dlp): no authentication required.")

    def fetch_new_posts(
        self,
        handle: str,
        limit: int,
        since_timestamp: datetime | None = None,
    ) -> list[NormalisedPost]:
        """Fetch latest videos from a YouTube channel using yt-dlp.

        Parameters
        ----------
        handle:
            YouTube channel handle (@ChoiceTechLab), channel URL, or channel ID.
        limit:
            Maximum number of videos to return.
        since_timestamp:
            If provided, only return videos published after this datetime.
        """
        self._require_auth()

        try:
            import yt_dlp  # lazy import
        except ImportError:
            logger.error("yt-dlp is not installed. Run: pip install yt-dlp")
            return []

        # Build the channel URL yt-dlp understands
        # If handle starts with @ or looks like a channel ID, build a URL
        if handle.startswith("http"):
            channel_url = handle
        elif handle.startswith("@"):
            channel_url = f"https://www.youtube.com/{handle}/videos"
        elif handle.startswith("UC"):
            channel_url = f"https://www.youtube.com/channel/{handle}/videos"
        else:
            channel_url = f"https://www.youtube.com/@{handle}/videos"

        # Also scrape the /shorts tab
        if handle.startswith("http"):
            base = handle.rstrip("/").split("/videos")[0].split("/shorts")[0]
            shorts_url = f"{base}/shorts"
        elif handle.startswith("@"):
            shorts_url = f"https://www.youtube.com/{handle}/shorts"
        elif handle.startswith("UC"):
            shorts_url = f"https://www.youtube.com/channel/{handle}/shorts"
        else:
            shorts_url = f"https://www.youtube.com/@{handle}/shorts"

        ydl_opts = _base_ydl_opts()
        ydl_opts.update({
            "extract_flat": False,  # full metadata (includes upload_date)
            "playlistend": limit,
            "skip_download": True,
            "retries": 0,
            "fragment_retries": 0,
            "extractor_args": {"youtube": {"player_client": ["web"]}},
        })

        entries: list = []

        # Try /videos tab
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(channel_url, download=False)
                if info:
                    entries.extend(info.get("entries", []) or [])
        except Exception as exc:
            logger.warning("YouTubeAdapter: /videos tab failed for %r: %s", handle, exc)

        # Try /shorts tab
        try:
            shorts_remaining = limit - len([e for e in entries if e is not None])
            if shorts_remaining > 0:
                shorts_opts = dict(ydl_opts)
                shorts_opts["playlistend"] = shorts_remaining
                with yt_dlp.YoutubeDL(shorts_opts) as ydl:
                    shorts_info = ydl.extract_info(shorts_url, download=False)
                    if shorts_info:
                        entries.extend(shorts_info.get("entries", []) or [])
        except Exception as exc:
            logger.warning("YouTubeAdapter: /shorts tab failed for %r: %s", handle, exc)

        if not entries:
            return []

        posts: list[NormalisedPost] = []
        seen_ids: set[str] = set()

        for entry in entries:
            if entry is None:
                continue

            video_id = entry.get("id") or entry.get("url", "")
            if not video_id or video_id in seen_ids:
                continue
            seen_ids.add(video_id)

            upload_date = entry.get("upload_date")
            publish_ts = _parse_yt_date(upload_date)

            # Apply since_timestamp filter
            if since_timestamp is not None:
                st = since_timestamp
                if st.tzinfo is None:
                    st = st.replace(tzinfo=timezone.utc)
                if publish_ts <= st:
                    continue

            title = entry.get("title") or entry.get("fulltitle")
            description = entry.get("description")
            # Detect shorts by duration (< 61s) or URL pattern
            duration = entry.get("duration") or 999
            is_short = duration <= 60
            if is_short:
                url = f"https://www.youtube.com/shorts/{video_id}"
            else:
                url = f"https://www.youtube.com/watch?v={video_id}"

            posts.append(
                NormalisedPost(
                    platform_native_post_id=video_id,
                    post_type="video",
                    title=title,
                    body=description,
                    url=url,
                    publish_timestamp=publish_ts,
                    handle_id=self._handle_id,
                )
            )

            if len(posts) >= limit:
                break

        return posts

    def _get_video_upload_date(self, video_id: str) -> str | None:
        """Fetch upload_date for a single video (non-flat extraction)."""
        try:
            import yt_dlp
        except ImportError:
            return None

        ydl_opts = _base_ydl_opts()
        ydl_opts["skip_download"] = True

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False,
                )
                if info:
                    return info.get("upload_date")
        except Exception as exc:
            logger.debug(
                "YouTubeAdapter._get_video_upload_date failed for %s: %s",
                video_id, exc,
            )
        return None

    def fetch_comments(
        self,
        post: NormalisedPost,
        limit: int,
    ) -> list[NormalisedComment]:
        """Fetch top-level comments for a YouTube video using yt-dlp."""
        self._require_auth()

        try:
            import yt_dlp
        except ImportError:
            return []

        video_url = f"https://www.youtube.com/watch?v={post.platform_native_post_id}"

        ydl_opts = _base_ydl_opts()
        ydl_opts.update({
            "getcomments": True,
            "extractor_args": {"youtube": {"comment_sort": ["top"], "max_comments": [str(limit)]}},
        })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
        except Exception as exc:
            logger.debug("YouTubeAdapter.fetch_comments failed for %r: %s", post.platform_native_post_id, exc)
            return []

        if not info:
            return []

        raw_comments = info.get("comments") or []
        comments: list[NormalisedComment] = []

        for c in raw_comments[:limit]:
            if c is None:
                continue
            # Only top-level comments (parent == "root" or no parent)
            if c.get("parent") and c.get("parent") != "root":
                continue

            comment_id = str(c.get("id", ""))
            if not comment_id:
                continue

            author = c.get("author") or c.get("author_id") or "unknown"
            text = (c.get("text") or "")[:10000]
            if not text:
                continue

            timestamp = c.get("timestamp")
            if timestamp:
                try:
                    pub_ts = datetime.fromtimestamp(float(timestamp), tz=timezone.utc)
                except (ValueError, OSError):
                    pub_ts = datetime.now(tz=timezone.utc)
            else:
                pub_ts = datetime.now(tz=timezone.utc)

            comments.append(
                NormalisedComment(
                    platform_native_comment_id=comment_id,
                    author_handle=str(author),
                    comment_text=text,
                    publish_timestamp=pub_ts,
                )
            )

        return comments

    def fetch_engagement(self, post: NormalisedPost) -> NormalisedEngagement:
        """Fetch engagement stats for a YouTube video using yt-dlp."""
        self._require_auth()

        try:
            import yt_dlp
        except ImportError:
            return NormalisedEngagement()

        video_url = f"https://www.youtube.com/watch?v={post.platform_native_post_id}"

        ydl_opts = _base_ydl_opts()
        ydl_opts.update({
            "skip_download": True,
            "retries": 0,
            "fragment_retries": 0,
            # web client returns metadata counts reliably and avoids the
            # 403 format-extraction hangs seen with the default clients.
            "extractor_args": {"youtube": {"player_client": ["web"]}},
        })

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
        except Exception as exc:
            logger.warning("YouTubeAdapter.fetch_engagement failed for %r: %s", post.platform_native_post_id, exc)
            return NormalisedEngagement()

        if not info:
            return NormalisedEngagement()

        likes = int(info.get("like_count") or 0)
        views = int(info.get("view_count") or 0)
        comments = int(info.get("comment_count") or 0)

        # Guard: if all metrics are zero, yt-dlp likely failed silently
        # (SSL error, rate limit, etc.) — don't return zeros that would
        # overwrite real data in the engagement_metrics table.
        if likes == 0 and views == 0 and comments == 0:
            logger.warning(
                "YouTubeAdapter.fetch_engagement: all zeros for %r — treating as failed fetch",
                post.platform_native_post_id,
            )
            return None  # Signal to caller: skip this engagement snapshot

        return NormalisedEngagement(
            likes_count=likes,
            views_count=views,
            comments_count=comments,
            shares_count=0,
            reactions_count=None,
        )
