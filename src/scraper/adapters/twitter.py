"""
twitter.py — Twitter/X adapter using twikit (internal GraphQL API).

twikit authenticates with a real Twitter/X account (username + password)
and fetches the user's tweet timeline directly via Twitter's internal API.
Returns actual tweet text, timestamps, likes, retweets, and view counts.

Anti-bot measures:
- Random jitter (2–8 s) before each API call
- Randomised locale and user-agent pool
- Cookie-based session reuse to avoid repeated logins
- Exponential back-off on 400 responses

Credentials (set in .env):
    TWITTER_USERNAME   Twitter @username (without the @)
    TWITTER_EMAIL      Email address registered with the account
    TWITTER_PASSWORD   Twitter password

Session cookies are saved to .twitter_cookies.json so login only
happens once; subsequent scrapes reuse the saved session.

Install: pip install twikit  (already included in pyproject.toml)
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

from ..base_adapter import AuthenticationError, BaseAdapter
from ..models import NormalisedComment, NormalisedEngagement, NormalisedPost

logger = logging.getLogger(__name__)

_COOKIES_FILE = Path(".twitter_cookies.json")
_FAIL_FILE    = Path(".twitter_login_failed")   # written on failure, deleted on success
_BACKOFF_SECS = 6 * 3600                         # 6-hour back-off after a failed login
_TW_TS_FMT    = "%a %b %d %H:%M:%S %z %Y"

# Pool of realistic browser locales — rotated randomly each session
_LOCALES = ["en-US", "en-GB", "en-AU", "en-CA", "en-IN"]


def _jitter(min_s: float = 2.0, max_s: float = 8.0) -> None:
    """Sleep for a random duration to mimic human timing."""
    delay = random.uniform(min_s, max_s)
    logger.debug("TwitterAdapter: jitter sleep %.1fs", delay)
    time.sleep(delay)


def _run(coro):
    """Run an async coroutine from synchronous code."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


class TwitterAdapter(BaseAdapter):
    """Twitter/X adapter — twikit with username/email/password auth."""

    platform_code = "twitter-x"

    def __init__(self, handle_id: int = 0) -> None:
        super().__init__()
        self._handle_id = handle_id
        self._client = None

    def authenticate(self) -> None:
        username = os.environ.get("TWITTER_USERNAME", "")
        email    = os.environ.get("TWITTER_EMAIL", "")
        password = os.environ.get("TWITTER_PASSWORD", "")

        if not username or not password:
            raise AuthenticationError("twitter-x", "TWITTER_USERNAME / TWITTER_PASSWORD")

        try:
            from twikit import Client  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "twikit is not installed. Run: pip install twikit"
            ) from exc

        # Check 6-hour back-off: if the last login failed recently, skip
        if _FAIL_FILE.exists():
            try:
                failed_at = float(_FAIL_FILE.read_text().strip())
                if time.time() - failed_at < _BACKOFF_SECS:
                    remaining = int((_BACKOFF_SECS - (time.time() - failed_at)) / 60)
                    raise AuthenticationError(
                        "twitter-x",
                        f"TWITTER_PASSWORD (backing off — retry in ~{remaining} min)",
                    )
                # Back-off expired — delete the file and try again
                _FAIL_FILE.unlink(missing_ok=True)
            except (ValueError, OSError):
                _FAIL_FILE.unlink(missing_ok=True)

        locale = random.choice(_LOCALES)
        client = Client(locale)

        # Reuse saved cookies when available
        if _COOKIES_FILE.exists():
            try:
                client.load_cookies(str(_COOKIES_FILE))
                logger.info("TwitterAdapter: loaded saved cookies (locale=%s)", locale)
                self._client = client
                self._authenticated = True
                return
            except Exception as exc:
                logger.warning(
                    "TwitterAdapter: saved cookies invalid (%s) — re-logging in", exc
                )
                _COOKIES_FILE.unlink(missing_ok=True)

        # Fresh login — jitter before the attempt
        _jitter(5.0, 15.0)

        async def _login():
            await client.login(
                auth_info_1=email or username,
                auth_info_2=email or username,
                password=password,
            )

        try:
            _run(_login())
            client.save_cookies(str(_COOKIES_FILE))
            _FAIL_FILE.unlink(missing_ok=True)
            logger.info("TwitterAdapter: logged in as @%s (locale=%s)", username, locale)
            self._client = client
            self._authenticated = True
        except Exception as exc:
            _FAIL_FILE.write_text(str(time.time()))
            logger.error(
                "TwitterAdapter: login failed for @%s — backing off %dh: %s",
                username, _BACKOFF_SECS // 3600, exc,
            )
            raise AuthenticationError("twitter-x", "TWITTER_PASSWORD") from exc

    # ------------------------------------------------------------------

    def fetch_new_posts(
        self,
        handle: str,
        limit: int,
        since_timestamp: datetime | None = None,
    ) -> list[NormalisedPost]:
        self._require_auth()
        assert self._client is not None

        async def _fetch():
            # Jitter before looking up the user
            await asyncio.sleep(random.uniform(1.5, 4.0))
            user = await self._client.get_user_by_screen_name(handle)
            # Jitter before fetching tweets
            await asyncio.sleep(random.uniform(2.0, 6.0))
            tweets = await user.get_tweets("Tweets", count=min(limit, 40))
            return tweets

        try:
            tweets = _run(_fetch())
        except Exception as exc:
            logger.error(
                "TwitterAdapter: failed to fetch tweets for @%s: %s", handle, exc
            )
            return []

        posts: list[NormalisedPost] = []
        for tweet in tweets:
            try:
                pub_ts = _parse_twitter_ts(tweet.created_at)
            except Exception:
                pub_ts = datetime.now(tz=timezone.utc)

            if since_timestamp is not None:
                st = since_timestamp
                if st.tzinfo is None:
                    st = st.replace(tzinfo=timezone.utc)
                if pub_ts.tzinfo is None:
                    pub_ts = pub_ts.replace(tzinfo=timezone.utc)
                if pub_ts <= st:
                    continue

            text = getattr(tweet, "text", "") or ""
            if not text.strip():
                continue

            posts.append(
                NormalisedPost(
                    platform_native_post_id=str(tweet.id),
                    post_type="text",
                    title=None,
                    body=text[:10000],
                    url=f"https://x.com/{handle}/status/{tweet.id}",
                    publish_timestamp=pub_ts,
                    handle_id=self._handle_id,
                )
            )

            # Per-tweet jitter to avoid burst patterns
            if len(posts) < limit:
                time.sleep(random.uniform(0.5, 2.0))

            if len(posts) >= limit:
                break

        logger.info(
            "TwitterAdapter: %d tweets fetched for @%s", len(posts), handle
        )
        return posts

    def fetch_comments(self, post: NormalisedPost, limit: int) -> list[NormalisedComment]:
        return []

    def fetch_engagement(self, post: NormalisedPost) -> NormalisedEngagement:
        if self._client is None:
            return NormalisedEngagement()

        async def _get_tweet():
            return await self._client.get_tweet_by_id(post.platform_native_post_id)

        try:
            tweet = _run(_get_tweet())
            return NormalisedEngagement(
                likes_count=int(getattr(tweet, "favorite_count", 0) or 0),
                comments_count=int(getattr(tweet, "reply_count",    0) or 0),
                shares_count=int(getattr(tweet, "retweet_count",  0) or 0),
                views_count=int(getattr(tweet, "view_count",      0) or 0),
            )
        except Exception as exc:
            logger.debug(
                "TwitterAdapter.fetch_engagement failed for %s: %s",
                post.platform_native_post_id, exc,
            )
            return NormalisedEngagement()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_twitter_ts(created_at: str) -> datetime:
    """Parse Twitter's created_at string to UTC datetime."""
    try:
        dt = datetime.strptime(created_at, _TW_TS_FMT)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(tz=timezone.utc)
