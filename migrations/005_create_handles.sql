-- Migration 005: Create handles table
-- Requirements: 1.3, 1.4, 5.1
--
-- Stores platform-specific handles (channels, accounts, pages) assigned to
-- categories. The (platform_id, platform_native_handle) pair is unique per
-- platform. is_active supports soft-delete semantics so historical post data
-- is preserved when a handle is removed from the scraping config.

USE choice_analytics;

CREATE TABLE IF NOT EXISTS handles (
    id                       INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    category_id              INT UNSIGNED    NOT NULL,
    platform_id              INT UNSIGNED    NOT NULL,
    platform_native_handle   VARCHAR(255)    NOT NULL
                                                 COMMENT 'Platform-specific identifier: channel ID, @username, etc.',
    display_name             VARCHAR(255)    NOT NULL,
    is_active                TINYINT(1)      NOT NULL DEFAULT 1
                                                 COMMENT 'Soft-delete flag: 1 = active, 0 = deactivated',
    created_at               DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP
                                                 ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_handles_platform_native (platform_id, platform_native_handle),
    KEY idx_handles_category_id (category_id),
    KEY idx_handles_platform_id (platform_id),
    CONSTRAINT fk_handles_category
        FOREIGN KEY (category_id) REFERENCES categories (id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_handles_platform
        FOREIGN KEY (platform_id) REFERENCES platforms (id)
        ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;
