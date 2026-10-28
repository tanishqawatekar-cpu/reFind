# ReFind — Live SQL Demonstration Execution Evidence (`refind_db`)

- **Executed Against:** MySQL `26.7.0` on `127.0.0.1:3307`
- **Connected Account:** `refind_app@127.0.0.1` (Least-Privilege Runtime User)
- **Active Database:** `refind_db`
- **Source SQL Script:** [`docs/DBMS_SQL_DEMONSTRATIONS.sql`](file:///C:/Projects/ReFind/docs/DBMS_SQL_DEMONSTRATIONS.sql)
- **Mode:** 100% Read-Only (`SELECT` only — 0 rows modified)

---

## 1. Three-Table INNER JOIN (`matches` + `lost_items` + `found_items`)

```sql
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
```

### Actual Query Result:

| match_id | lost_id | lost_item_name | item_category | location_lost | date_lost | found_id | found_item_name | location_found | date_found | category_points | name_points | location_points | date_points | description_points | match_score | match_status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4 | 2 | Casio fx-991CW Scientific Calculator | Electronics | Block B Computer Lab 2 | 2026-10-25 | 2 | Casio fx-991CW Scientific Calculator | Block B Computer Lab 2 | 2026-10-25 | 30.00 | 25.00 | 20.00 | 15.00 | 7.67 | 97.67 | SUGGESTED |
| 5 | 4 | Brown Leather Bi-Fold Wallet | Bags & Wallets | Central Canteen Food Court | 2026-10-26 | 4 | Dark Brown Leather Wallet | Campus Canteen Outdoor Tables | 2026-10-26 | 30.00 | 18.87 | 18.00 | 15.00 | 8.73 | 90.60 | SUGGESTED |
| 1 | 1 | Apple AirPods Pro (2nd Gen) | Electronics | Central Library Reading Room (2nd Floor) | 2026-10-24 | 1 | AirPods Pro in Lavender Case | Central Library 2nd Floor Study Hall | 2026-10-24 | 30.00 | 18.21 | 18.00 | 15.00 | 7.67 | 88.88 | SUGGESTED |
| 2 | 1 | Apple AirPods Pro (2nd Gen) | Electronics | Central Library Reading Room (2nd Floor) | 2026-10-24 | 2 | Casio fx-991CW Scientific Calculator | Block B Computer Lab 2 | 2026-10-25 | 30.00 | 5.56 | 0.00 | 13.00 | 0.00 | 48.56 | SUGGESTED |
| 6 | 4 | Brown Leather Bi-Fold Wallet | Bags & Wallets | Central Canteen Food Court | 2026-10-26 | 5 | College Student ID Card & Lanyard | Sports Complex Basketball Court | 2026-10-26 | 12.00 | 4.10 | 10.00 | 15.00 | 0.00 | 41.10 | SUGGESTED |
| 3 | 2 | Casio fx-991CW Scientific Calculator | Electronics | Block B Computer Lab 2 | 2026-10-25 | 1 | AirPods Pro in Lavender Case | Central Library 2nd Floor Study Hall | 2026-10-24 | 30.00 | 3.12 | 0.00 | 5.00 | 0.00 | 38.12 | SUGGESTED |

**Rows returned:** `6`

---

## 2. GROUP BY with COUNT & Conditional Status Aggregation (`lost_items`)

```sql
SELECT
    category,
    COUNT(*) AS total_lost_reports,
    SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END) AS open_count,
    SUM(CASE WHEN status = 'MATCHED' THEN 1 ELSE 0 END) AS matched_count,
    SUM(CASE WHEN status = 'RECOVERED' THEN 1 ELSE 0 END) AS recovered_count
FROM lost_items
GROUP BY category
ORDER BY total_lost_reports DESC, category ASC;
```

### Actual Query Result:

| category | total_lost_reports | open_count | matched_count | recovered_count |
| --- | --- | --- | --- | --- |
| Electronics | 2 | 0 | 2 | 0 |
| Water Bottles & Umbrellas | 1 | 0 | 0 | 1 |
| Bags & Wallets | 1 | 0 | 1 | 0 |
| Clothing & Eyewear | 1 | 1 | 0 | 0 |

**Rows returned:** `4`

---

## 3A. SQL View — Real-Time Dashboard Statistics (`vw_dashboard_stats`)

```sql
SELECT * FROM vw_dashboard_stats;
```

### Actual Query Result:

| total_lost | open_lost | recovered_lost | total_found | available_found | returned_found | active_matches | high_confidence_matches | pending_claims | approved_claims | registered_students |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | 1 | 1 | 5 | 1 | 1 | 6 | 3 | 2 | 1 | 4 |

**Rows returned:** `1`

---

## 3B. SQL View — Public Lost Gallery (`vw_public_lost_gallery`, hiding private `identifying_marks`)

```sql
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
```

### Actual Query Result:

| lost_id | reporter_name | reporter_student_id | item_name | category | location_lost | date_lost | status | match_count |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Alex Rivera | CS2024018 | Apple AirPods Pro (2nd Gen) | Electronics | Central Library Reading Room (2nd Floor) | 2026-10-24 | MATCHED | 2 |
| 2 | Sam Carter | IT2024042 | Casio fx-991CW Scientific Calculator | Electronics | Block B Computer Lab 2 | 2026-10-25 | MATCHED | 2 |
| 3 | Taylor Morgan | EN2023089 | Milton Thermosteel 1L Water Bottle | Water Bottles & Umbrellas | Main Auditorium Seminar Hall | 2026-10-23 | RECOVERED | 0 |
| 4 | Casey Jordan | ME2024105 | Brown Leather Bi-Fold Wallet | Bags & Wallets | Central Canteen Food Court | 2026-10-26 | MATCHED | 2 |
| 5 | Alex Rivera | CS2024018 | Lenskart Blu-Cut Spectacles in Case | Clothing & Eyewear | Block A Tutorial Room 104 | 2026-10-26 | OPEN | 0 |

**Rows returned:** `6`

---

## 3C. SQL View — Public Found Gallery (`vw_public_found_gallery`, hiding private `secret_detail`)

```sql
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
```

### Actual Query Result:

| found_id | finder_name | item_name | category | location_found | storage_location | status | pending_claims_count |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Sam Carter | AirPods Pro in Lavender Case | Electronics | Central Library 2nd Floor Study Hall | Campus Lost & Found Desk (Main Admin Block, Room 102) | MATCHED | 1 |
| 2 | Taylor Morgan | Casio fx-991CW Scientific Calculator | Electronics | Block B Computer Lab 2 | IT Department Office (Block B, Ground Floor) | MATCHED | 1 |
| 3 | Casey Jordan | Navy Blue Milton Insulated Bottle | Water Bottles & Umbrellas | Main Auditorium Stage Left | Campus Lost & Found Desk (Main Admin Block, Room 102) | RETURNED | 0 |
| 4 | Alex Rivera | Dark Brown Leather Wallet | Bags & Wallets | Campus Canteen Outdoor Tables | Campus Security Office (Main Gate 1) | MATCHED | 0 |
| 5 | Sam Carter | College Student ID Card & Lanyard | ID & Cards | Sports Complex Basketball Court | Sports Gymkhana Office | AVAILABLE | 0 |

**Rows returned:** `5`

---

## 4. Meaningful Subquery — Lost Items Scoring Above Database Average Match Score

```sql
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
```

### Actual Query Result:

| lost_id | item_name | category | location_lost | status | highest_match_score | overall_avg_score |
| --- | --- | --- | --- | --- | --- | --- |
| 2 | Casio fx-991CW Scientific Calculator | Electronics | Block B Computer Lab 2 | MATCHED | 97.67 | 67.49 |
| 4 | Brown Leather Bi-Fold Wallet | Bags & Wallets | Central Canteen Food Court | MATCHED | 90.60 | 67.49 |
| 1 | Apple AirPods Pro (2nd Gen) | Electronics | Central Library Reading Room (2nd Floor) | MATCHED | 88.88 | 67.49 |

**Rows returned:** `3`

---

## 5. Primary-Key, Unique-Key, and Foreign-Key Inspection (`information_schema`)

```sql
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
```

### Actual Query Result:

| table_name | constraint_name | constraint_type | columns_involved | referenced_table | referenced_column | on_update_action | on_delete_action |
| --- | --- | --- | --- | --- | --- | --- | --- |
| activity_logs | PRIMARY | PRIMARY KEY | log_id | `NULL` | `NULL` | `NULL` | `NULL` |
| activity_logs | fk_activity_user | FOREIGN KEY | user_id | users | user_id | CASCADE | SET NULL |
| claims | PRIMARY | PRIMARY KEY | claim_id | `NULL` | `NULL` | `NULL` | `NULL` |
| claims | uq_claims_single_approved_per_found | UNIQUE | approved_found_id | `NULL` | `NULL` | `NULL` | `NULL` |
| claims | uq_claims_user_found | UNIQUE | found_id,claimant_id | `NULL` | `NULL` | `NULL` | `NULL` |
| claims | fk_claims_claimant | FOREIGN KEY | claimant_id | users | user_id | CASCADE | RESTRICT |
| claims | fk_claims_found | FOREIGN KEY | found_id | found_items | found_id | RESTRICT | RESTRICT |
| claims | fk_claims_lost | FOREIGN KEY | lost_id | lost_items | lost_id | CASCADE | SET NULL |
| claims | fk_claims_reviewer | FOREIGN KEY | reviewed_by | users | user_id | CASCADE | SET NULL |
| found_items | PRIMARY | PRIMARY KEY | found_id | `NULL` | `NULL` | `NULL` | `NULL` |
| found_items | fk_found_items_user | FOREIGN KEY | user_id | users | user_id | CASCADE | CASCADE |
| lost_items | PRIMARY | PRIMARY KEY | lost_id | `NULL` | `NULL` | `NULL` | `NULL` |
| lost_items | fk_lost_items_user | FOREIGN KEY | user_id | users | user_id | CASCADE | CASCADE |
| matches | PRIMARY | PRIMARY KEY | match_id | `NULL` | `NULL` | `NULL` | `NULL` |
| matches | uq_matches_pair | UNIQUE | lost_id,found_id | `NULL` | `NULL` | `NULL` | `NULL` |
| matches | fk_matches_found | FOREIGN KEY | found_id | found_items | found_id | CASCADE | CASCADE |
| matches | fk_matches_lost | FOREIGN KEY | lost_id | lost_items | lost_id | CASCADE | CASCADE |
| users | PRIMARY | PRIMARY KEY | user_id | `NULL` | `NULL` | `NULL` | `NULL` |
| users | uq_users_email | UNIQUE | email | `NULL` | `NULL` | `NULL` | `NULL` |
| users | uq_users_student_id | UNIQUE | student_id | `NULL` | `NULL` | `NULL` | `NULL` |

**Rows returned:** `20`

---

## 6A. Read-Only Transaction & Single-Approval Integrity Evidence (`claims` + `approved_found_id`)

```sql
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
```

### Actual Query Result:

| claim_id | found_id | found_item | found_item_status | lost_id | lost_item_status | claimant_name | claim_status | generated_unique_lock_col | reviewed_by_admin | reviewed_at |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | AirPods Pro in Lavender Case | MATCHED | 1 | MATCHED | Alex Rivera | PENDING | `NULL` | `NULL` | `NULL` |
| 2 | 2 | Casio fx-991CW Scientific Calculator | MATCHED | 2 | MATCHED | Sam Carter | PENDING | `NULL` | `NULL` | `NULL` |
| 3 | 3 | Navy Blue Milton Insulated Bottle | RETURNED | 3 | RECOVERED | Taylor Morgan | APPROVED | 3 | Dr. Jordan Blake (Campus Admin) | 2026-10-24 14:30:00 |

**Rows returned:** `3`

---

## 6B. Audit Trail Evidence of Reporting, Matching, Claiming & Transactional Return (`activity_logs`)

```sql
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
```

### Actual Query Result:

| log_id | created_at | action_type | entity_type | entity_id | actor_name | summary |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 2026-10-27 22:06:50 | LOST_REPORTED | LOST_ITEM | 1 | Alex Rivera | Alex Rivera reported lost 'Apple AirPods Pro (2nd Gen)' at Central Library Reading Room. |
| 2 | 2026-10-27 22:06:50 | FOUND_REPORTED | FOUND_ITEM | 1 | Sam Carter | Sam Carter reported found 'AirPods Pro in Lavender Case' at Central Library 2nd Floor Study Hall. |
| 3 | 2026-10-27 22:06:50 | CLAIM_SUBMITTED | CLAIM | 1 | Alex Rivera | Alex Rivera submitted an ownership claim for Found Item #1 (AirPods Pro in Lavender Case). |
| 4 | 2026-10-27 22:06:50 | LOST_REPORTED | LOST_ITEM | 2 | Sam Carter | Sam Carter reported lost 'Casio fx-991CW Scientific Calculator' at Block B Computer Lab 2. |
| 5 | 2026-10-27 22:06:50 | FOUND_REPORTED | FOUND_ITEM | 2 | Taylor Morgan | Taylor Morgan reported found 'Casio fx-991CW Scientific Calculator' at Block B Computer Lab 2. |
| 6 | 2026-10-27 22:06:50 | CLAIM_SUBMITTED | CLAIM | 3 | Taylor Morgan | Taylor Morgan submitted an ownership claim for Found Item #3 (Navy Blue Milton Insulated Bottle). |
| 7 | 2026-10-27 22:06:50 | CLAIM_APPROVED | CLAIM | 3 | Dr. Jordan Blake (Campus Admin) | Admin Dr. Jordan Blake approved Claim #3 and verified return of 'Navy Blue Milton Insulated Bottle' to Taylor Morgan. |
| 8 | 2026-10-27 22:06:50 | ITEM_RETURNED | FOUND_ITEM | 3 | Dr. Jordan Blake (Campus Admin) | Found Item #3 marked as RETURNED and Lost Item #3 marked as RECOVERED via ACID transaction. |

**Rows returned:** `12`

---
