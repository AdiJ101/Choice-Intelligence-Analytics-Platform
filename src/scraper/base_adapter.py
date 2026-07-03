"""
base_adapter.py — Abstract Adapter base class and shared exceptions.

Every per-platform Adapter MUST subclass BaseAdapter and implement all
four abstract methods. The orchestrator interacts exclusively with this
interface; it never imports a concrete adapter class directly.

Requirements covered: 3.1, 3.5, 3.6, 3.7, 3.8
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import NormalisedComment, NormalisedEngagement, NormalisedPost


class AuthenticationError(Exception):
    """Raised when an Adapter credential is invalid, expired, or absent.

    The message MUST include:
    - The platform code (e.g. ``"youtube"``)
    - The name (NOT the value) of the missing/invalid credential env var

    Example
    -------
    >>> raise AuthenticationError("youtube", "YOUTUBE_API_KEY")
    AuthenticationError: Platform 'youtube' authentication failed: \
env var 'YOUTUBE_API_KEY' is missing or invalid.

    Parameters
    ----------
    platform_code : str
        The short platform identifier (e.g. ``"youtube"``, ``"twitter-x"``).
    env_var_name : str
        The name of the environment variable that holds the credential.
        Never pass the value — only the variable name.
    """

    def __init__(self, platform_code: str, env_var_name: str) -> None:
        self.platform_code = platform_code
        self.env_var_name = env_var_name
        super().__init__(
            f"Platform {platform_code!r} authentication failed: "
            f"env var {env_var_name!r} is missing or invalid."
        )


class RateLimitError(Exception):
    """Raised when the platform API returns HTTP 429 (Too Many Requests).

    Attributes
    ----------
    platform_code : str
        The short platform identifier (e.g. ``"youtube"``).
    retry_after : int | None
        Value of the ``Retry-After`` response header in seconds, or ``None``
        if the header was absent.

    Example
    -------
    >>> raise RateLimitError("twitter-x", retry_after=60)
    RateLimitError: Rate limit exceeded for 'twitter-x'; Retry-After=60s

    Parameters
    ----------
    platform_code : str
        The platform that returned the rate limit response.
    retry_after : int | None
        Seconds to wait before retrying, sourced from the ``Retry-After``
        header. Pass ``None`` if the header was not present.
    """

    def __init__(self, platform_code: str, retry_after: int | None = None) -> None:
        self.platform_code = platform_code
        self.retry_after = retry_after
        super().__init__(
            f"Rate limit exceeded for {platform_code!r}"
            + (f"; Retry-After={retry_after}s" if retry_after is not None else "")
        )


class BaseAdapter(ABC):
    """Abstract base class for all platform Adapters.

    All concrete Adapters (YouTube, Twitter/X, LinkedIn, Instagram, Facebook)
    MUST subclass ``BaseAdapter`` and:

    1. Set ``platform_code`` as a class-level string attribute.
    2. Implement all four abstract methods (``authenticate``,
       ``fetch_new_posts``, ``fetch_comments``, ``fetch_engagement``).
    3. Call ``self._require_auth()`` at the start of every *fetch* method
       (not in ``authenticate`` itself).

    Class Attributes
    ----------------
    platform_code : str
        Short, kebab-case platform identifier. Must match the key used in
        ``ADAPTER_REGISTRY`` (e.g. ``"youtube"``, ``"twitter-x"``).

    Instance Attributes
    -------------------
    _authenticated : bool
        Set to ``True`` inside ``authenticate()`` on success.
        ``_require_auth()`` checks this flag before any fetch operation.

    Raises
    ------
    TypeError
        If ``platform_code`` is not set on a concrete subclass (enforced at
        instantiation via ABC machinery — the missing abstract attribute will
        surface as a ``TypeError``).
    """

    platform_code: str  # MUST be overridden in every concrete subclass

    def __init__(self) -> None:
        self._authenticated: bool = False

    # ------------------------------------------------------------------
    # Auth guard
    # ------------------------------------------------------------------

    def _require_auth(self) -> None:
        """Raise ``RuntimeError`` if ``authenticate()`` has not been called.

        This is a guard that every fetch method calls first. It exists so
        that a developer who forgets to call ``authenticate()`` gets an
        explicit, actionable error message rather than a cryptic API failure.

        Raises
        ------
        RuntimeError
            When ``self._authenticated`` is ``False``, with a message that
            names the platform so the caller knows which adapter is affected.
        """
        if not self._authenticated:
            raise RuntimeError(
                f"Adapter for platform {self.platform_code!r} is not authenticated. "
                "Call authenticate() before fetching data."
            )

    # ------------------------------------------------------------------
    # Abstract methods
    # ------------------------------------------------------------------

    @abstractmethod
    def authenticate(self) -> None:
        """Authenticate with the platform API using credentials from env vars.

        Implementations MUST:
        - Read credentials exclusively from environment variables (never
          hard-code values or accept them as constructor parameters).
        - Set ``self._authenticated = True`` on success.
        - Raise ``AuthenticationError`` if the credential is absent, empty,
          invalid, or expired — passing the env var *name*, never its value.

        This method does NOT call ``_require_auth()`` — it is the bootstrapper
        that makes authentication possible in the first place.

        Raises
        ------
        AuthenticationError
            If the required env var is absent, empty, or the API rejects it.
        """

    @abstractmethod
    def fetch_new_posts(
        self,
        handle: str,
        limit: int,
        since_timestamp: NormalisedPost | None = None,
    ) -> list[NormalisedPost]:
        """Fetch new posts for *handle*, up to *limit* items.

        Implementations MUST call ``self._require_auth()`` as their first
        statement.

        Parameters
        ----------
        handle : str
            The platform-native handle identifier (e.g. a YouTube channel ID,
            a Twitter ``@username``, a LinkedIn organisation URN).
        limit : int
            Maximum number of posts to return. Implementations must respect
            this ceiling strictly — never return more than *limit* items.
        since_timestamp : datetime | None
            If provided, only return posts published strictly *after* this
            UTC-aware datetime. If ``None``, no lower-bound filter is applied
            (first-run / backfill behaviour).

        Returns
        -------
        list[NormalisedPost]
            Possibly empty list. Empty result is not an error — it simply
            means no new posts exist since *since_timestamp*.

        Raises
        ------
        RuntimeError
            If called before a successful ``authenticate()``.
        AuthenticationError
            If the session has expired mid-run.
        RateLimitError
            If the platform returns HTTP 429.
        """

    @abstractmethod
    def fetch_comments(
        self,
        post: NormalisedPost,
        limit: int,
    ) -> list[NormalisedComment]:
        """Fetch comments for *post*, up to *limit* items.

        Implementations MUST call ``self._require_auth()`` as their first
        statement.

        Parameters
        ----------
        post : NormalisedPost
            The post whose comments should be fetched. Implementations may
            use ``post.platform_native_post_id`` to construct the API request.
        limit : int
            Maximum number of comments to return. Must be respected strictly.

        Returns
        -------
        list[NormalisedComment]
            Possibly empty list. Empty result is not an error.

        Raises
        ------
        RuntimeError
            If called before a successful ``authenticate()``.
        AuthenticationError
            If the session has expired mid-run.
        RateLimitError
            If the platform returns HTTP 429.
        """

    @abstractmethod
    def fetch_engagement(
        self,
        post: NormalisedPost,
    ) -> NormalisedEngagement:
        """Fetch current engagement metrics for *post*.

        Implementations MUST call ``self._require_auth()`` as their first
        statement.

        Implementations should return a ``NormalisedEngagement`` populated
        with whatever counters the platform exposes; fields the platform does
        not provide should be left at their defaults (``0`` for counts,
        ``None`` for ``reactions_count`` when unsupported).

        Parameters
        ----------
        post : NormalisedPost
            The post whose engagement metrics should be fetched.

        Returns
        -------
        NormalisedEngagement
            A snapshot of the post's engagement counters at the time of the
            call.

        Raises
        ------
        RuntimeError
            If called before a successful ``authenticate()``.
        AuthenticationError
            If the session has expired mid-run.
        RateLimitError
            If the platform returns HTTP 429.
        """
