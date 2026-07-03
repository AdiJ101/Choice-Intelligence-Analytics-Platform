-- Migration: 015_add_post_collection_days.sql
-- Adds the post_collection_days column to scraping_config.
-- This controls how far back the scraper looks for new posts on each handle.
-- Default: 15 days (only posts published in the last 15 days are collected).

USE choice_analytics;

ALTER TABLE scraping_config
    ADD COLUMN post_collection_days SMALLINT UNSIGNED NOT NULL DEFAULT 15
        COMMENT 'Range: 1–3650; only collect posts published within this many days',
    ADD CONSTRAINT chk_post_collection_days
        CHECK (post_collection_days BETWEEN 1 AND 3650);
