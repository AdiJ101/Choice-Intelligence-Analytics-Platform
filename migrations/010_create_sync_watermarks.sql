-- Migration: 010_create_sync_watermarks.sql
-- Creates the sync_watermarks table used by the Sync Pipeline to track
-- incremental watermark progress per source table.
-- Validates: Requirements 7.2

USE choice_analytics;

CREATE TABLE IF NOT EXISTS sync_watermarks (
    id           INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    source_table VARCHAR(64)     NOT NULL,
    last_pk      BIGINT UNSIGNED NOT NULL DEFAULT 0
                                     COMMENT 'Last successfully processed primary key',
    last_ts      DATETIME        NOT NULL DEFAULT '1970-01-01 00:00:00'
                                     COMMENT 'Timestamp of last processed record',
    updated_at   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                     ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_watermark_table (source_table)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- Seed initial watermark rows for posts and comments
INSERT IGNORE INTO sync_watermarks (source_table, last_pk, last_ts) VALUES
    ('posts',    0, '1970-01-01 00:00:00'),
    ('comments', 0, '1970-01-01 00:00:00');
