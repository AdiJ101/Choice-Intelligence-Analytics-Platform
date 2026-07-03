-- Migration: 008_create_engagement_metrics.sql
-- Creates the `engagement_metrics` table.
-- References: Requirements 2.1, 2.3, 2.4, 2.5, 5.3
--
-- Note: Uses a polymorphic (source_table, source_record_id) pattern rather than
-- separate post_metrics / comment_metrics tables. Because one FK column cannot
-- reference two parent tables simultaneously, referential integrity for the
-- source record is enforced at the application / upsert layer.
-- The `source_table` discriminant tells callers which parent table to join.
-- A real FK is still declared for platform_id → platforms(id).

USE choice_analytics;

CREATE TABLE IF NOT EXISTS engagement_metrics (
    id                 BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,

    -- Polymorphic source reference (app-layer integrity)
    source_table       ENUM('post','comment') NOT NULL
                           COMMENT 'Discriminant: which parent table source_record_id references',
    source_record_id   BIGINT UNSIGNED  NOT NULL
                           COMMENT 'FK to posts.id or comments.id depending on source_table; enforced at app layer',

    -- Platform reference (DB-level FK)
    platform_id        INT UNSIGNED     NOT NULL,

    -- Metric counters — unsigned, default 0 so partial data is safe to insert
    likes_count        INT UNSIGNED     NOT NULL DEFAULT 0,
    comments_count     INT UNSIGNED     NOT NULL DEFAULT 0,
    shares_count       INT UNSIGNED     NOT NULL DEFAULT 0,
    views_count        INT UNSIGNED     NOT NULL DEFAULT 0,
    reactions_count    INT UNSIGNED     NULL
                           COMMENT 'NULL where reactions are not supported by the platform',

    -- Temporal columns
    snapshot_timestamp DATETIME         NOT NULL
                           COMMENT 'UTC, second-level precision; point-in-time of the metric snapshot',
    created_at         DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP
                           COMMENT 'UTC',

    PRIMARY KEY (id),

    -- Composite index: look up all metric snapshots for a given source record
    KEY idx_em_source       (source_table, source_record_id),
    -- Index to support queries filtered / joined by platform
    KEY idx_em_platform_id  (platform_id),
    -- Index to support time-range queries on snapshot history
    KEY idx_em_snapshot_ts  (snapshot_timestamp),

    CONSTRAINT fk_em_platform
        FOREIGN KEY (platform_id) REFERENCES platforms (id)
        ON DELETE RESTRICT ON UPDATE CASCADE

) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
