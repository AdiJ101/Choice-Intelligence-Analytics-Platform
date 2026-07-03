-- Migration: 006_create_posts.sql
-- Creates the posts table, partitioned by publish_timestamp (year-month RANGE).
-- MySQL RANGE partitioning requires the partition key to appear in every unique
-- key, so the PRIMARY KEY is composite (id, publish_timestamp) and the
-- deduplication unique key also includes publish_timestamp.
-- Requirements: 1.5, 5.1, 5.2, 5.4, 5.5

USE choice_analytics;

CREATE TABLE IF NOT EXISTS posts (
    id                      BIGINT UNSIGNED      NOT NULL AUTO_INCREMENT,
    handle_id               INT UNSIGNED         NOT NULL,
    platform_id             INT UNSIGNED         NOT NULL,
    platform_native_post_id VARCHAR(255)         NOT NULL,
    post_type               ENUM('post','video','text') NOT NULL,
    title                   VARCHAR(1000)        NULL,
    body                    TEXT                 NULL
                                                     COMMENT 'Up to 65535 bytes',
    url                     VARCHAR(2048)        NULL,
    language_code           CHAR(2)              NULL
                                                     COMMENT 'ISO 639-1, NULL if not detected',
    publish_timestamp       DATETIME             NOT NULL
                                                     COMMENT 'UTC',
    discovered_at           DATETIME             NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                     COMMENT 'UTC',
    updated_at              DATETIME             NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                     ON UPDATE CURRENT_TIMESTAMP,

    -- Composite PK: publish_timestamp must be part of PK for RANGE partitioning
    PRIMARY KEY (id, publish_timestamp),

    -- Deduplication key: includes publish_timestamp to satisfy partition key rule
    UNIQUE KEY uq_posts_dedup (platform_id, platform_native_post_id, publish_timestamp),

    KEY idx_posts_handle_id (handle_id),
    KEY idx_posts_platform_id (platform_id),
    KEY idx_posts_publish_ts (publish_timestamp),
    -- Composite index for dashboard queries filtering by handle + platform + date range
    KEY idx_posts_cat_plat_ts (handle_id, platform_id, publish_timestamp)

    -- NOTE: FK constraints (fk_posts_handle, fk_posts_platform) are omitted here
    -- because MySQL 8.0.14+ / 9.x does not support foreign keys on partitioned tables.
    -- Referential integrity is enforced at the application layer via platform_guard.py
    -- and the handle lookup in the scraper before inserting any post.

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  PARTITION BY RANGE (YEAR(publish_timestamp) * 100 + MONTH(publish_timestamp)) (
    PARTITION p202401 VALUES LESS THAN (202402),
    PARTITION p202402 VALUES LESS THAN (202403),
    PARTITION p202403 VALUES LESS THAN (202404),
    PARTITION p202404 VALUES LESS THAN (202405),
    PARTITION p202405 VALUES LESS THAN (202406),
    PARTITION p202406 VALUES LESS THAN (202407),
    PARTITION p202407 VALUES LESS THAN (202408),
    PARTITION p202408 VALUES LESS THAN (202409),
    PARTITION p202409 VALUES LESS THAN (202410),
    PARTITION p202410 VALUES LESS THAN (202411),
    PARTITION p202411 VALUES LESS THAN (202412),
    PARTITION p202412 VALUES LESS THAN (202501),
    PARTITION p202501 VALUES LESS THAN (202502),
    PARTITION p202502 VALUES LESS THAN (202503),
    PARTITION p202503 VALUES LESS THAN (202504),
    PARTITION p202504 VALUES LESS THAN (202505),
    PARTITION p202505 VALUES LESS THAN (202506),
    PARTITION p202506 VALUES LESS THAN (202507),
    PARTITION p_future VALUES LESS THAN MAXVALUE
);
