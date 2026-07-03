"""
config_validator.py — Runtime config validation for the Scraper Service.

Validates the parsed Scraping_Config dict against all Requirement 1 rules.
Raises ValueError on any violation; never touches the database.

Note: This wraps and extends the _validate() function already in
src/config_loader/loader.py. It is called BEFORE load_scraping_config() so
that validation errors produce the correct field-path error messages.
"""

from __future__ import annotations

_VALID_PLATFORM_CODES = frozenset({
    "youtube", "twitter-x", "linkedin", "instagram", "facebook"
})

_SC_RANGES: dict[str, tuple[int, int]] = {
    "scraping_interval_minutes":                (1, 10080),
    "max_new_content_per_handle_per_iteration": (1, 1000),
    "cooling_time_days":                        (1, 9999),
    "post_collection_days":                     (1, 3650),
}


def validate_config(config_dict: dict) -> None:
    """Validate *config_dict* against all Requirement 1 rules.

    Raises ValueError identifying the failing field path and invalid value.
    Returns None on success.

    Validates:
    - Top-level keys present: ``scraping_config`` and ``categories``
    - ``scraping_config`` sub-fields are integers in specified ranges
    - ``categories`` is a non-empty list
    - Each category has a non-empty name (1–255 chars) and at least one handle
    - Every handle key is one of the five valid platform codes
    """
    if not isinstance(config_dict, dict):
        raise ValueError("Config must be a JSON object (dict)")

    for key in ("scraping_config", "categories"):
        if key not in config_dict:
            raise ValueError(f"Missing required top-level key: '{key}'")

    sc = config_dict["scraping_config"]
    if not isinstance(sc, dict):
        raise ValueError("'scraping_config' must be a JSON object")

    for field, (lo, hi) in _SC_RANGES.items():
        if field not in sc:
            raise ValueError(f"'scraping_config.{field}' is required")
        value = sc[field]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(
                f"'scraping_config.{field}' must be an integer, "
                f"got {type(value).__name__!r}"
            )
        if not (lo <= value <= hi):
            raise ValueError(
                f"'scraping_config.{field}' = {value!r} is outside "
                f"the allowed range [{lo}, {hi}]"
            )

    categories = config_dict["categories"]
    if not isinstance(categories, list) or len(categories) == 0:
        raise ValueError("'categories' must be a non-empty array")

    for i, cat in enumerate(categories):
        if not isinstance(cat, dict):
            raise ValueError(f"categories[{i}] must be a JSON object")

        name = cat.get("name", "")
        if not isinstance(name, str) or not (1 <= len(name) <= 255):
            raise ValueError(
                f"categories[{i}].name must be a non-empty string "
                f"(1–255 chars), got {name!r}"
            )

        handles = cat.get("handles", {})
        if not isinstance(handles, dict) or len(handles) == 0:
            raise ValueError(
                f"categories[{i}].handles must be a non-empty object"
            )

        for platform_code in handles:
            if platform_code not in _VALID_PLATFORM_CODES:
                raise ValueError(
                    f"categories[{i}].handles contains invalid platform code "
                    f"{platform_code!r}; valid codes: {sorted(_VALID_PLATFORM_CODES)}"
                )
