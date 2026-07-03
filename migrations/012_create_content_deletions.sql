-- Migration: 012_create_content_deletions.sql
-- Purpose: Tombstone table used by the deletion propagation worker to track
--          which MySQL deletions still need to be propagated to Qdrant.
-- Requirement: 8.5

USE choice_analytics;

CREATE TABLE IF NOT EXISTS content_deletions (
    id               BIGINT UNSIGNED  NOT NULL AUTO_INCREMENT,
    source_table     VARCHAR(64)      NOT NULL
                                          COMMENT '''post'' or ''comment''',
    source_record_id BIGINT UNSIGNED  NOT NULL
                                          COMMENT 'MySQL primary key of the deleted record',
    deleted_at       DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP
                                          COMMENT 'UTC timestamp of the MySQL delete',
    propagated_at    DATETIME         NULL
                                          COMMENT 'Set after Qdrant delete is confirmed; NULL = not yet propagated',
    PRIMARY KEY (id),
    KEY idx_cd_propagated (propagated_at),
    KEY idx_cd_source (source_table, source_record_id)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
