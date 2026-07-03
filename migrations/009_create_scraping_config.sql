-- Migration: 009_create_scraping_config
-- Creates the scraping_config table for storing scraper runtime configuration.
-- Validates: Requirements 3.1

USE choice_analytics;

CREATE TABLE IF NOT EXISTS scraping_config (
    id                                    INT UNSIGNED      NOT NULL AUTO_INCREMENT,
    scraping_interval_minutes             SMALLINT UNSIGNED NOT NULL
                                              COMMENT 'Range: 1–10080 (1 week in minutes)',
    max_new_content_per_handle_per_iter   SMALLINT UNSIGNED NOT NULL
                                              COMMENT 'Range: 1–1000',
    cooling_time_days                     SMALLINT UNSIGNED NOT NULL
                                              COMMENT 'Range: 1–9999',
    config_version                        INT UNSIGNED      NOT NULL DEFAULT 1,
    loaded_at                             DATETIME          NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    CONSTRAINT chk_scraping_interval
        CHECK (scraping_interval_minutes BETWEEN 1 AND 10080),
    CONSTRAINT chk_max_content
        CHECK (max_new_content_per_handle_per_iter BETWEEN 1 AND 1000),
    CONSTRAINT chk_cooling_days
        CHECK (cooling_time_days BETWEEN 1 AND 9999)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
