USE choice_analytics;

CREATE TABLE IF NOT EXISTS handle_watermarks (
    handle_id              INT UNSIGNED    NOT NULL COMMENT 'FK to handles.id',
    platform_id            INT UNSIGNED    NOT NULL COMMENT 'FK to platforms.id',
    last_post_timestamp    DATETIME        NOT NULL COMMENT 'publish_timestamp of most recently fetched post (UTC)',
    updated_at             DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last time this watermark was advanced',
    PRIMARY KEY (handle_id, platform_id),
    CONSTRAINT fk_hwm_handle
        FOREIGN KEY (handle_id) REFERENCES handles (id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_hwm_platform
        FOREIGN KEY (platform_id) REFERENCES platforms (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Per-handle per-platform watermarks for incremental post collection. Use GREATEST() in upsert to prevent watermark regression.';
