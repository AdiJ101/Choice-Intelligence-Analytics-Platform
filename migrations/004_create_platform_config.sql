-- Migration: 004_create_platform_config.sql
-- Creates the platform_config table for extensible per-platform key-value
-- metric field mappings, enabling zero-DDL platform onboarding.
-- Requirements: 10.1, 10.3

CREATE TABLE IF NOT EXISTS platform_config (
    id            INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    platform_id   INT UNSIGNED    NOT NULL,
    config_key    VARCHAR(255)    NOT NULL
                                      COMMENT 'e.g. native_likes_field, api_endpoint_template',
    config_value  TEXT            NOT NULL,
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                      ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_platform_config (platform_id, config_key),
    CONSTRAINT fk_platform_config_platform
        FOREIGN KEY (platform_id) REFERENCES platforms (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- Seed: metric field mappings for all five platforms.
-- Platform IDs match the seed order from 002_create_platforms.sql:
--   1 = youtube, 2 = twitter-x, 3 = linkedin, 4 = instagram, 5 = facebook
-- 'NULL' (string) is used for fields not supported by the platform.
INSERT IGNORE INTO platform_config (platform_id, config_key, config_value) VALUES
    -- YouTube (1)
    (1, 'native_likes_field',     'likeCount'),
    (1, 'native_views_field',     'viewCount'),
    (1, 'native_comments_field',  'commentCount'),
    (1, 'native_shares_field',    'NULL'),
    (1, 'native_reactions_field', 'NULL'),

    -- X / Twitter (2)
    (2, 'native_likes_field',     'favorite_count'),
    (2, 'native_views_field',     'impression_count'),
    (2, 'native_comments_field',  'reply_count'),
    (2, 'native_shares_field',    'retweet_count'),
    (2, 'native_reactions_field', 'NULL'),

    -- LinkedIn (3)
    (3, 'native_likes_field',     'likeCount'),
    (3, 'native_views_field',     'NULL'),
    (3, 'native_comments_field',  'commentCount'),
    (3, 'native_shares_field',    'shareCount'),
    (3, 'native_reactions_field', 'NULL'),

    -- Instagram (4)
    (4, 'native_likes_field',     'like_count'),
    (4, 'native_views_field',     'video_view_count'),
    (4, 'native_comments_field',  'comments_count'),
    (4, 'native_shares_field',    'NULL'),
    (4, 'native_reactions_field', 'NULL'),

    -- Facebook (5)
    (5, 'native_likes_field',     'like_count'),
    (5, 'native_views_field',     'video_views'),
    (5, 'native_comments_field',  'comments'),
    (5, 'native_shares_field',    'shares'),
    (5, 'native_reactions_field', 'reactions');
