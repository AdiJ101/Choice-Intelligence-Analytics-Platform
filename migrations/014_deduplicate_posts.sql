-- Migration: 014_deduplicate_posts.sql
-- Purpose : Remove duplicate post rows that share the same
--           (platform_id, platform_native_post_id) but differ in
--           publish_timestamp (a known side-effect of the MySQL
--           RANGE-partition dedup key including publish_timestamp).
--
-- Strategy: For each duplicate group, keep the row with MAX(id)
--           (latest inserted / most up-to-date scrape).
--           Before deletion, dependent rows are either reassigned to
--           the canonical post or removed safely.
--
-- Safe to re-run: DROP TEMPORARY TABLE IF EXISTS at the top ensures the
-- temp table is always recreated cleanly on each execution.

USE choice_analytics;

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 0: Clean up from any previous partial run
-- ─────────────────────────────────────────────────────────────────────────────
DROP TEMPORARY TABLE IF EXISTS _dedup_map;

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 1: Map every duplicate post to its canonical (MAX id) sibling
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TEMPORARY TABLE _dedup_map AS
SELECT
    p.id        AS dup_id,
    canon.keep  AS canonical_id
FROM posts p
INNER JOIN (
    SELECT
        platform_id,
        platform_native_post_id,
        MAX(id) AS keep
    FROM   posts
    GROUP  BY platform_id, platform_native_post_id
    HAVING COUNT(*) > 1
) canon
  ON  canon.platform_id             = p.platform_id
  AND canon.platform_native_post_id = p.platform_native_post_id
  AND p.id                         != canon.keep;

SELECT COUNT(*) AS duplicate_posts_to_remove FROM _dedup_map;

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 2a: Drop conflicting comments before reassignment.
--
-- MySQL error 1093 prevents a DELETE on a table that also appears in a
-- subquery in the same statement.  The fix is to join a second alias of
-- the comments table directly instead of using an EXISTS subquery.
-- ─────────────────────────────────────────────────────────────────────────────
DELETE c_dup
FROM   comments c_dup
INNER  JOIN _dedup_map  dm     ON dm.dup_id       = c_dup.post_id
INNER  JOIN comments    c_canon
    ON  c_canon.post_id                    = dm.canonical_id
    AND c_canon.platform_native_comment_id = c_dup.platform_native_comment_id;

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 2b: Reassign remaining comments to the canonical post
-- ─────────────────────────────────────────────────────────────────────────────
UPDATE comments c
INNER  JOIN _dedup_map dm ON dm.dup_id = c.post_id
SET    c.post_id = dm.canonical_id;

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 3: Delete engagement_metrics snapshots for duplicate posts
--         The canonical post keeps its own metric history unchanged.
-- ─────────────────────────────────────────────────────────────────────────────
DELETE em
FROM   engagement_metrics em
INNER  JOIN _dedup_map dm ON dm.dup_id = em.source_record_id
WHERE  em.source_table = 'post';

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 4: Remove dead-letter queue entries for duplicate posts
-- ─────────────────────────────────────────────────────────────────────────────
DELETE dlq
FROM   dead_letter_queue dlq
INNER  JOIN _dedup_map dm ON dm.dup_id = dlq.source_record_id
WHERE  dlq.source_table = 'post';

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 5: Delete the duplicate post rows
-- ─────────────────────────────────────────────────────────────────────────────
DELETE p
FROM   posts p
INNER  JOIN _dedup_map dm ON dm.dup_id = p.id;

SELECT ROW_COUNT() AS posts_deleted;

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 6: Clean up
-- ─────────────────────────────────────────────────────────────────────────────
DROP TEMPORARY TABLE _dedup_map;
