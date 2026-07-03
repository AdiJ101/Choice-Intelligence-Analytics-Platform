-- Migration: 001_create_database.sql
-- Description: Creates the choice_analytics database if it does not already exist.
-- Idempotent: safe to run multiple times (IF NOT EXISTS guard).
-- Requirement: 9.1

CREATE DATABASE IF NOT EXISTS choice_analytics
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
