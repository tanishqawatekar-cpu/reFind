-- ============================================================================
-- ReFind — Smart Campus Lost & Found System
-- Stage 5: DBMS SQL Demonstration Queries (100% Read-Only Verification Suite)
-- Database: refind_db (MySQL 8.0+ / 26.7 on Port 3307)
-- ============================================================================
-- NOTE: Every query in this file is strictly READ-ONLY (SELECT).
-- It modifies zero rows and can be executed safely in MySQL Workbench or CLI.
-- ============================================================================

USE refind_db;

-- ============================================================================
-- QUERY 1: Three-Table INNER JOIN (`matches` + `lost_items` + `found_items`)
-- Purpose: Retrieve all candidate matches along with the matched lost item,
--          found item, locations, dates, 5 component scores, and total score.
-- ============================================================================
SELECT
    m.match_id,
    l.lost_id,
    l.item_name AS lost_item_name,
    l.category AS item_category,
    l.location_lost,
    l.date_lost,
    f.found_id,
    f.item_name AS found_item_name,
    f.location_found,
    f.date_found,
    m.category_points,
    m.name_points,
    m.location_points,
    m.date_points,
    m.description_points,
    m.match_score,
    m.match_status
FROM matches m
INNER JOIN lost_items l ON m.lost_id = l.lost_id
INNER JOIN found_items f ON m.found_id = f.found_id
ORDER BY m.match_score DESC, m.match_id ASC;

-- ============================================================================
-- QUERY 2: GROUP BY with COUNT & Conditional Aggregation
-- Purpose: Summarize lost item reports per campus category, showing total
--          reports, open reports, matched reports, and recovered items.
-- ============================================================================
SELECT
    category,
    COUNT(*) AS total_lost_reports,
    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) AS open_count,
    SUM(CASE WHEN status = 'MATCHED' THEN 1 ELSE 0 END) AS matched_count,
    SUM(CASE WHEN status = 'RECOVERED' THEN 1 ELSE 0 END) AS recovered_count
FROM lost_items
GROUP BY category
ORDER BY total_lost_reports DESC, category ASC;

-- ============================================================================
-- QUERY 3A: SQL View Demonstration — Real-Time Dashboard Statistics (`vw_dashboard_stats`)
-- Purpose: Query the pre-defined SQL view that aggregates 11 live campus KPIs.
-- ============================================================================
SELECT * FROM vw_dashboard_stats;

-- ============================================================================
-- QUERY 3B: SQL View Demonstration — Public Galleries (`vw_public_lost_gallery`
--           & `vw_public_found_gallery`) vs Base Table Privacy Protection
-- Purpose: Demonstrate how SQL Views project public columns and calculate
--          correlated match/claim counts while hiding `identifying_marks`
--          and `secret_detail`.
-- ============================================================================
SELECT
    lost_id,
    reporter_name,
    reporter_student_id,
    item_name,
    category,
    location_lost,
    date_lost,
    status,
    match_count
FROM vw_public_lost_gallery
ORDER BY lost_id ASC;

SELECT
    found_id,
    finder_name,
    item_name,
    category,
    location_found,
    storage_location,
    status,
    pending_claims_count
FROM vw_public_found_gallery
ORDER BY found_id ASC;

-- ============================================================================
-- QUERY 4: Meaningful Subquery (Correlated Subquery + Scalar Average Comparison)
-- Purpose: Find all lost items that have achieved a candidate match score
--          strictly higher than the overall database average match_score,
--          along with their highest match score and number of candidate matches.
-- ============================================================================
SELECT
    l.lost_id,
    l.item_name,
    l.category,
    l.location_lost,
    l.status,
    (SELECT MAX(m2.match_score)
     FROM matches m2
     WHERE m2.lost_id = l.lost_id) AS highest_match_score,
    ROUND((SELECT AVG(match_score) FROM matches), 2) AS overall_avg_score
FROM lost_items l
WHERE EXISTS (
    SELECT 1
    FROM matches m
    WHERE m.lost_id = l.lost_id
      AND m.match_score > (SELECT AVG(match_score) FROM matches)
)
ORDER BY highest_match_score DESC;

-- ============================================================================
-- QUERY 5: Primary-Key, Unique-Key, and Foreign-Key Metadata Inspection
-- Purpose: Query MySQL's `information_schema` to prove all 6 Primary Keys,
--          5 Unique Constraints, and 9 Foreign Key relationships with their
--          exact ON UPDATE and ON DELETE referential actions in `refind_db`.
-- ============================================================================
SELECT
    tc.TABLE_NAME AS table_name,
    tc.CONSTRAINT_NAME AS constraint_name,
    tc.CONSTRAINT_TYPE AS constraint_type,
    GROUP_CONCAT(kcu.COLUMN_NAME ORDER BY kcu.ORDINAL_POSITION) AS columns_involved,
    kcu.REFERENCED_TABLE_NAME AS referenced_table,
    kcu.REFERENCED_COLUMN_NAME AS referenced_column,
    rc.UPDATE_RULE AS on_update_action,
    rc.DELETE_RULE AS on_delete_action
FROM information_schema.TABLE_CONSTRAINTS tc
JOIN information_schema.KEY_COLUMN_USAGE kcu
    ON tc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
   AND tc.TABLE_NAME = kcu.TABLE_NAME
   AND tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
LEFT JOIN information_schema.REFERENTIAL_CONSTRAINTS rc
    ON tc.CONSTRAINT_SCHEMA = rc.CONSTRAINT_SCHEMA
   AND tc.CONSTRAINT_NAME = rc.CONSTRAINT_NAME
WHERE tc.CONSTRAINT_SCHEMA = 'refind_db'
GROUP BY
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    tc.CONSTRAINT_TYPE,
    kcu.REFERENCED_TABLE_NAME,
    kcu.REFERENCED_COLUMN_NAME,
    rc.UPDATE_RULE,
    rc.DELETE_RULE
ORDER BY
    tc.TABLE_NAME ASC,
    FIELD(tc.CONSTRAINT_TYPE, 'PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY'),
    tc.CONSTRAINT_NAME ASC;

-- ============================================================================
-- QUERY 6A: Read-Only Transaction & Single-Approval Integrity Evidence
-- Purpose: Inspect the `claims` table alongside its linked `found_items`,
--          `lost_items`, `matches`, and the Stored Generated Column
--          `approved_found_id` (which enforces at the InnoDB index level that
--          at most one claim per `found_id` can ever have status = 'APPROVED').
-- ============================================================================
SELECT
    c.claim_id,
    c.found_id,
    f.item_name AS found_item,
    f.status AS found_item_status,
    c.lost_id,
    l.status AS lost_item_status,
    u.full_name AS claimant_name,
    c.status AS claim_status,
    c.approved_found_id AS generated_unique_lock_col,
    r.full_name AS reviewed_by_admin,
    c.reviewed_at
FROM claims c
INNER JOIN found_items f ON c.found_id = f.found_id
LEFT JOIN lost_items l ON c.lost_id = l.lost_id
INNER JOIN users u ON c.claimant_id = u.user_id
LEFT JOIN users r ON c.reviewed_by = r.user_id
ORDER BY c.claim_id ASC;

-- ============================================================================
-- QUERY 6B: Audit Trail Evidence of Atomic Claim Approval & Item Return
-- Purpose: Show the chronological `activity_logs` records proving that
--          CLAIM_SUBMITTED -> CLAIM_APPROVED -> ITEM_RETURNED are recorded
--          inside the transactional workflow without modifying any data.
-- ============================================================================
SELECT
    a.log_id,
    a.created_at,
    a.action_type,
    a.entity_type,
    a.entity_id,
    COALESCE(u.full_name, 'System') AS actor_name,
    a.summary
FROM activity_logs a
LEFT JOIN users u ON a.user_id = u.user_id
ORDER BY a.log_id ASC;
