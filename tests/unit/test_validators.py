"""
Unit tests for src/db/validators.py
"""

import pytest
from src.db.validators import (
    validate_platform_code,
    validate_language_code,
    validate_post_type,
    validate_scraping_config_values,
)


# ---------------------------------------------------------------------------
# validate_platform_code
# ---------------------------------------------------------------------------


class TestValidatePlatformCode:
    # --- valid cases ---
    def test_single_letter(self):
        assert validate_platform_code("a") is True

    def test_single_digit(self):
        assert validate_platform_code("9") is True

    def test_simple_word(self):
        assert validate_platform_code("youtube") is True

    def test_hyphenated_code(self):
        assert validate_platform_code("twitter-x") is True

    def test_multiple_hyphens(self):
        assert validate_platform_code("some-platform-name") is True

    def test_digits_and_letters(self):
        assert validate_platform_code("platform42") is True

    def test_max_length_50(self):
        code = "a" * 50
        assert validate_platform_code(code) is True

    def test_length_2_no_hyphen(self):
        assert validate_platform_code("ab") is True

    # --- invalid cases ---
    def test_empty_string(self):
        assert validate_platform_code("") is False

    def test_starts_with_hyphen(self):
        assert validate_platform_code("-bad") is False

    def test_ends_with_hyphen(self):
        assert validate_platform_code("bad-") is False

    def test_hyphen_only(self):
        assert validate_platform_code("-") is False

    def test_uppercase_letters(self):
        assert validate_platform_code("YouTube") is False

    def test_contains_space(self):
        assert validate_platform_code("you tube") is False

    def test_contains_underscore(self):
        assert validate_platform_code("you_tube") is False

    def test_exceeds_50_chars(self):
        code = "a" * 51
        assert validate_platform_code(code) is False

    def test_non_string_input(self):
        assert validate_platform_code(123) is False  # type: ignore[arg-type]

    def test_hyphen_between_digits(self):
        assert validate_platform_code("123-456") is True

    def test_double_hyphen(self):
        # Double hyphens in the middle are allowed by the regex
        assert validate_platform_code("a--b") is True


# ---------------------------------------------------------------------------
# validate_post_type
# ---------------------------------------------------------------------------


class TestValidatePostType:
    def test_post(self):
        assert validate_post_type("post") is True

    def test_video(self):
        assert validate_post_type("video") is True

    def test_text(self):
        assert validate_post_type("text") is True

    def test_uppercase_rejected(self):
        assert validate_post_type("Post") is False

    def test_image_rejected(self):
        assert validate_post_type("image") is False

    def test_empty_rejected(self):
        assert validate_post_type("") is False

    def test_whitespace_rejected(self):
        assert validate_post_type(" post") is False


# ---------------------------------------------------------------------------
# validate_language_code
# ---------------------------------------------------------------------------


class TestValidateLanguageCode:
    def test_none_is_valid(self):
        assert validate_language_code(None) is True

    def test_lowercase_two_letters(self):
        assert validate_language_code("en") is True

    def test_uppercase_two_letters(self):
        assert validate_language_code("EN") is True

    def test_mixed_case_two_letters(self):
        assert validate_language_code("En") is True

    def test_three_letters_invalid(self):
        assert validate_language_code("eng") is False

    def test_one_letter_invalid(self):
        assert validate_language_code("e") is False

    def test_digit_in_code_invalid(self):
        assert validate_language_code("e1") is False

    def test_empty_string_invalid(self):
        assert validate_language_code("") is False

    def test_non_string_invalid(self):
        assert validate_language_code(42) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_scraping_config_values
# ---------------------------------------------------------------------------


class TestValidateScrapingConfigValues:
    # --- all valid boundary values ---
    def test_minimum_valid_values(self):
        # Should not raise
        validate_scraping_config_values(1, 1, 1)

    def test_maximum_valid_values(self):
        # Should not raise
        validate_scraping_config_values(10080, 1000, 365)

    def test_typical_valid_values(self):
        validate_scraping_config_values(60, 100, 30)

    # --- interval out of range ---
    def test_interval_zero_raises(self):
        with pytest.raises(ValueError, match="scraping_interval_minutes"):
            validate_scraping_config_values(0, 100, 30)

    def test_interval_too_large_raises(self):
        with pytest.raises(ValueError, match="scraping_interval_minutes"):
            validate_scraping_config_values(10081, 100, 30)

    def test_interval_negative_raises(self):
        with pytest.raises(ValueError, match="scraping_interval_minutes"):
            validate_scraping_config_values(-1, 100, 30)

    # --- max_content out of range ---
    def test_max_content_zero_raises(self):
        with pytest.raises(ValueError, match="max_new_content_per_handle_per_iter"):
            validate_scraping_config_values(60, 0, 30)

    def test_max_content_too_large_raises(self):
        with pytest.raises(ValueError, match="max_new_content_per_handle_per_iter"):
            validate_scraping_config_values(60, 1001, 30)

    # --- cooling_days out of range ---
    def test_cooling_days_zero_raises(self):
        with pytest.raises(ValueError, match="cooling_time_days"):
            validate_scraping_config_values(60, 100, 0)

    def test_cooling_days_too_large_raises(self):
        with pytest.raises(ValueError, match="cooling_time_days"):
            validate_scraping_config_values(60, 100, 366)

    def test_error_message_includes_bad_value(self):
        with pytest.raises(ValueError, match="10081"):
            validate_scraping_config_values(10081, 100, 30)
