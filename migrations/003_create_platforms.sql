-- Migration: 003_create_platforms.sql
-- Creates the platforms table with platform_code validation and seeds initial rows.
-- Requirements: 1.2, 10.1

CREATE TABLE IF NOT EXISTS platforms (
    id            INT UNSIGNED    NOT NULL AUTO_INCREMENT,
    platform_code VARCHAR(50)     NOT NULL
                                      COMMENT 'Lowercase alphanumeric + hyphens, e.g. youtube',
    display_name  VARCHAR(255)    NOT NULL,
    created_at    DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_platforms_code (platform_code),
    CONSTRAINT chk_platform_code
        CHECK (platform_code REGEXP '^[a-z0-9][a-z0-9-]*[a-z0-9]$'
               OR platform_code REGEXP '^[a-z0-9]$')
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci;

-- Seed data: initial supported platforms
INSERT IGNORE INTO platforms (platform_code, display_name) VALUES
    ('youtube',   'YouTube'),
    ('twitter-x', 'X / Twitter'),
    ('linkedin',  'LinkedIn'),
    ('instagram', 'Instagram'),
    ('facebook',  'Facebook');
