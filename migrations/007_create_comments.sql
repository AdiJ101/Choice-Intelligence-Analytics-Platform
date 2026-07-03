-- Migration: 007_create_comments.sql
-- Creates the `comments` table.
-- References: Requirements 1.6, 9.1, 9.2, 9.3
--
-- Note: post_id references posts(id) only (not the composite PK).
-- MySQL allows this because `id` is itself unique within `posts`;
-- the partition column is not required in the child FK.

USE choice_analytics;

CREATE TABLE IF NOT EXISTS comments (
    id                         BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    post_id                    BIGINT UNSIGNED  NOT NULL,
    platform_native_comment_id VARCHAR(255)     NOT NULL,
    author_handle              VARCHAR(255)     NOT NULL
                                                    COMMENT 'Platform-native author identifier',
    comment_text               VARCHAR(10000)   NOT NULL,
    language_code              CHAR(2)          NULL
                                                    COMMENT 'ISO 639-1, NULL if not detected',
    publish_timestamp          DATETIME         NOT NULL
                                                    COMMENT 'UTC',
    discovered_at              DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                    COMMENT 'UTC',
    updated_at                 DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                    ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uq_comments_dedup     (post_id, platform_native_comment_id),
    KEY        idx_comments_post_id  (post_id),
    KEY        idx_comments_publish_ts (publish_timestamp)

    -- NOTE: FK to posts(id) omitted — MySQL 9.x does not allow FK references
    -- TO a partitioned table. Referential integrity enforced at the app layer.

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
