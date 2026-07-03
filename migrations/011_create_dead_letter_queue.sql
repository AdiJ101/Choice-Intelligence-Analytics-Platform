-- Migration 011: Create dead_letter_queue table
-- Requirement 7.7 — Sync Pipeline failure routing
-- Records entries that have exhausted all retry attempts during sync processing.

USE choice_analytics;

CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id                INT UNSIGNED     NOT NULL AUTO_INCREMENT,
    source_table      VARCHAR(64)      NOT NULL,
    source_record_id  BIGINT UNSIGNED  NOT NULL,
    failure_reason    TEXT             NOT NULL,
    retry_count       TINYINT UNSIGNED NOT NULL DEFAULT 0,
    failed_at         DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP,
    cleared_at        DATETIME         NULL
                                           COMMENT 'Set when manually cleared for retry',
    PRIMARY KEY (id),
    KEY idx_dlq_source   (source_table, source_record_id),
    KEY idx_dlq_failed_at (failed_at)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
