# ReFind — DBMS Technical Summary & Engineering Reference (`DBMS_TECHNICAL_SUMMARY.md`)

**Project Name:** ReFind — Smart Campus Lost & Found System  
**Database Schema:** `refind_db` ([`database/schema.sql`](file:///C:/Projects/ReFind/database/schema.sql))  
**Storage Engine & Character Set:** MySQL `8.0+ / 26.7.0` (`InnoDB`, `utf8mb4_unicode_ci`)  
**Application Runtime Account:** `refind_app@127.0.0.1` (`GRANT SELECT, INSERT, UPDATE ON refind_db.*`)

---

## 1. Relational Database Normalization (1NF $\to$ 2NF $\to$ 3NF) & Functional Dependencies

The `refind_db` schema is decomposed into **six normalized relational tables in Third Normal Form (3NF)** (`users`, `lost_items`, `found_items`, `matches`, `claims`, `activity_logs`) to eliminate data redundancy and prevent insertion, update, and deletion anomalies:

1. **First Normal Form (1NF — Atomicity & Repeating Groups):**
   - Every attribute in all six tables stores a single atomic scalar value (`VARCHAR`, `INT`, `BIGINT`, `DECIMAL(5,2)`, `DATE`, `ENUM`, `TIMESTAMP`, `BOOLEAN`).
   - There are no comma-separated lists or multi-valued attributes; multiple candidate matches or multiple ownership claims for a single item are modeled as separate rows in `matches` and `claims`.
2. **Second Normal Form (2NF — Full Functional Dependency on Candidate Keys):**
   - Every table uses a single-attribute surrogate primary key (`user_id`, `lost_id`, `found_id`, `match_id`, `claim_id`, `log_id`) alongside composite and natural candidate keys enforced via `UNIQUE` constraints (`uq_users_student_id`, `uq_users_email`, `uq_matches_pair(lost_id, found_id)`, `uq_claims_user_found(found_id, claimant_id)`).
   - In `matches`, all score attributes (`match_score`, `category_points`, `name_points`, `location_points`, `date_points`, `description_points`) depend on the **entire** candidate key pair `(lost_id, found_id)`—never on `lost_id` or `found_id` alone.
3. **Third Normal Form (3NF — No Transitive Dependencies):**
   - Student profile attributes (`full_name`, `email`, `phone`, `department`, `student_id`) are stored **only once** in `users` and referenced via foreign keys (`lost_items.user_id`, `found_items.user_id`, `claims.claimant_id`, `claims.reviewed_by`, `activity_logs.user_id`). Updating a student's phone number or department updates a single row in `users` with zero update anomalies.
   - `lost_items` and `found_items` are separated into distinct relations rather than merged into a sparse single table with nullable columns (`storage_location`, `verification_question`, `secret_detail` apply only to found custody items, whereas `identifying_marks` applies only to lost reports).

### Formal Functional Dependency ($FD$) Analysis by Table:
- **`users`**:
  - Candidate Keys: $\{ \text{user\_id} \}$, $\{ \text{student\_id} \}$, $\{ \text{email} \}$.
  - $\text{user\_id} \to \{ \text{student\_id}, \text{full\_name}, \text{email}, \text{phone}, \text{department}, \text{password\_hash}, \text{role}, \text{is\_active}, \text{created\_at} \}$.
  - Every determinant is a candidate key (satisfies 3NF and BCNF).
- **`lost_items`**:
  - Candidate Key: $\{ \text{lost\_id} \}$.
  - $\text{lost\_id} \to \{ \text{user\_id}, \text{item\_name}, \text{category}, \text{brand\_color}, \text{location\_lost}, \text{date\_lost}, \text{description}, \text{identifying\_marks}, \text{image\_path}, \text{status}, \text{created\_at}, \text{updated\_at} \}$.
  - No non-key attribute determines another non-key attribute (satisfies 3NF).
- **`found_items`**:
  - Candidate Key: $\{ \text{found\_id} \}$.
  - $\text{found\_id} \to \{ \text{user\_id}, \text{item\_name}, \text{category}, \text{brand\_color}, \text{location\_found}, \text{date\_found}, \text{description}, \text{storage\_location}, \text{verification\_question}, \text{secret\_detail}, \text{image\_path}, \text{status}, \text{created\_at}, \text{updated\_at} \}$.
  - Satisfies 3NF.
- **`matches`**:
  - Candidate Keys: $\{ \text{match\_id} \}$, $\{ \text{lost\_id}, \text{found\_id} \}$.
  - $(\text{lost\_id}, \text{found\_id}) \to \{ \text{match\_id}, \text{category\_points}, \text{name\_points}, \text{location\_points}, \text{date\_points}, \text{description\_points}, \text{match\_score}, \text{score\_explanation}, \text{match\_status}, \text{matched\_at} \}$.
  - Note: presentation titles use **3NF** because `match_score` is the persisted sum of the 5 component point columns for fast indexed ordering (`idx_matches_score DESC`).
- **`claims`**:
  - Candidate Keys: $\{ \text{claim\_id} \}$, $\{ \text{found\_id}, \text{claimant\_id} \}$.
  - $\text{claim\_id} \to \{ \text{found\_id}, \text{lost\_id}, \text{claimant\_id}, \text{proof\_description}, \text{id\_card\_reference}, \text{status}, \text{approved\_found\_id}, \text{reviewed\_by}, \text{admin\_remarks}, \text{created\_at}, \text{reviewed\_at} \}$.
  - Note: `approved_found_id` is a deterministic SQL `GENERATED ALWAYS AS (...) STORED` column derived from `(status, found_id)` to enforce the single-approved-claim uniqueness rule in InnoDB.
- **`activity_logs`**:
  - Candidate Key: $\{ \text{log\_id} \}$.
  - $\text{log\_id} \to \{ \text{user\_id}, \text{action\_type}, \text{entity\_type}, \text{entity\_id}, \text{summary}, \text{created\_at} \}$.
  - Satisfies 3NF.

---

## 2. Keys, Relationships, Nullability & Referential Integrity (6 PKs & 9 FKs)

### Primary Keys (6):
- `users(user_id)` — `INT AUTO_INCREMENT NOT NULL PRIMARY KEY`
- `lost_items(lost_id)` — `INT AUTO_INCREMENT NOT NULL PRIMARY KEY`
- `found_items(found_id)` — `INT AUTO_INCREMENT NOT NULL PRIMARY KEY`
- `matches(match_id)` — `INT AUTO_INCREMENT NOT NULL PRIMARY KEY`
- `claims(claim_id)` — `INT AUTO_INCREMENT NOT NULL PRIMARY KEY`
- `activity_logs(log_id)` — `BIGINT AUTO_INCREMENT NOT NULL PRIMARY KEY`

### Foreign Keys, Nullability & Cardinality Verification (9):
| # | Foreign Key Constraint | Child Column & Nullability | Parent Column | Verified Cardinality (Parent : Child) | `ON DELETE` | `ON UPDATE` | Engineering Justification |
| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :--- |
| 1 | `fk_lost_items_user` | `lost_items.user_id` (`NOT NULL`) | `users.user_id` | **`1 : 0..*`** | `CASCADE` | `CASCADE` | Every lost report has exactly 1 reporter; removing a user removes their unreferenced reports. |
| 2 | `fk_found_items_user` | `found_items.user_id` (`NOT NULL`) | `users.user_id` | **`1 : 0..*`** | `CASCADE` | `CASCADE` | Every found report has exactly 1 finder; keeps finder reports synchronized with user lifecycle. |
| 3 | `fk_matches_lost` | `matches.lost_id` (`NOT NULL`) | `lost_items.lost_id` | **`1 : 0..*`** | `CASCADE` | `CASCADE` | Every match row requires 1 lost item; candidate matches depend on the lost report's existence. |
| 4 | `fk_matches_found` | `matches.found_id` (`NOT NULL`) | `found_items.found_id` | **`1 : 0..*`** | `CASCADE` | `CASCADE` | Every match row requires 1 found item; candidate matches depend on the found item's existence. |
| 5 | `fk_claims_found` | `claims.found_id` (`NOT NULL`) | `found_items.found_id` | **`1 : 0..*`** | `RESTRICT` | `RESTRICT` | **Prevents deleting a found item that has ownership claims**; also required by InnoDB for the stored generated column `approved_found_id`. |
| 6 | `fk_claims_lost` | `claims.lost_id` (`DEFAULT NULL`) | `lost_items.lost_id` | **`0..1 : 0..*`** | `SET NULL` | `CASCADE` | Optional link (`NULL` allowed if student claims directly from gallery without a prior lost report); if a lost report is removed, claim history remains intact. |
| 7 | `fk_claims_claimant` | `claims.claimant_id` (`NOT NULL`) | `users.user_id` | **`1 : 0..*`** | `RESTRICT` | `CASCADE` | Every claim requires 1 claimant user; `RESTRICT` protects custody claim records from accidental user deletion. |
| 8 | `fk_claims_reviewer` | `claims.reviewed_by` (`DEFAULT NULL`) | `users.user_id` | **`0..1 : 0..*`** | `SET NULL` | `CASCADE` | `NULL` while claim is `PENDING`; populated with admin `user_id` on review; `SET NULL` preserves claim record if an admin account changes. |
| 9 | `fk_activity_user` | `activity_logs.user_id` (`DEFAULT NULL`) | `users.user_id` | **`0..1 : 0..*`** | `SET NULL` | `CASCADE` | Nullable for system-initiated events; preserves immutable audit trail entries even if an actor is removed. |

---

## 3. Domain, Uniqueness & Check Constraints (5 Unique Constraints & 8 Check Constraints)

### Unique Constraints (5 — Verified in `information_schema.TABLE_CONSTRAINTS`):
1. **`uq_users_student_id`** on `users(student_id)`: Single-column unique constraint preventing duplicate university roll/staff IDs.
2. **`uq_users_email`** on `users(email)`: Single-column unique constraint preventing duplicate email registrations.
3. **`uq_matches_pair`** on `matches(lost_id, found_id)`: Composite unique constraint ensuring at most one match evaluation row per `(lost_id, found_id)` pair and enabling idempotent `INSERT ... ON DUPLICATE KEY UPDATE` in the matching engine.
4. **`uq_claims_user_found`** on `claims(found_id, claimant_id)`: Composite unique constraint preventing the same student from submitting duplicate claims for the same found item.
5. **`uq_claims_single_approved_per_found`** on `claims(approved_found_id)`:
   - Defined on the stored generated column `approved_found_id INT GENERATED ALWAYS AS (CASE WHEN status = 'APPROVED' THEN found_id ELSE NULL END) STORED`.
   - Because MySQL `UNIQUE` constraints permit multiple `NULL` values (for `PENDING` and `REJECTED` claims) but reject duplicate non-null integers, **InnoDB enforces at the storage engine level that at most one claim can ever be `APPROVED` for any `found_id`**.

### Check Constraints (8) & `ENUM` Domains:
1. `chk_users_name_len`: `CHAR_LENGTH(TRIM(full_name)) >= 2`
2. `chk_users_email_fmt`: `email LIKE '%_@__%.__%'`
3. `chk_lost_item_name_len`: `CHAR_LENGTH(TRIM(item_name)) >= 2`
4. `chk_lost_location_len`: `CHAR_LENGTH(TRIM(location_lost)) >= 2`
5. `chk_found_item_name_len`: `CHAR_LENGTH(TRIM(item_name)) >= 2`
6. `chk_found_location_len`: `CHAR_LENGTH(TRIM(location_found)) >= 2`
7. `chk_matches_score_range`: `match_score >= 0.00 AND match_score <= 100.00`
8. `chk_claims_proof_len`: `CHAR_LENGTH(TRIM(proof_description)) >= 5`

---

## 4. Indexing Strategy (Distinguishing Unique Indexes vs. 18 Non-Unique Secondary Indexes)

In MySQL InnoDB, `PRIMARY KEY` (6) and `UNIQUE` constraints (5) automatically create unique B-tree indexes. In addition, `database/schema.sql` explicitly declares **18 non-unique secondary `INDEX`es** for query performance:
- **`users` (2 secondary indexes):** `idx_users_role (role)`, `idx_users_department (department)`
- **`lost_items` (4 secondary indexes):** `idx_lost_category_status (category, status)`, `idx_lost_date (date_lost)`, `idx_lost_location (location_lost)`, `idx_lost_user (user_id)`
- **`found_items` (4 secondary indexes):** `idx_found_category_status (category, status)`, `idx_found_date (date_found)`, `idx_found_location (location_found)`, `idx_found_user (user_id)`
- **`matches` (2 secondary indexes):** `idx_matches_score (match_score DESC)`, `idx_matches_status (match_status)`
- **`claims` (3 secondary indexes):** `idx_claims_found_status (found_id, status)`, `idx_claims_claimant (claimant_id)`, `idx_claims_status (status)`
- **`activity_logs` (3 secondary indexes):** `idx_activity_created_at (created_at DESC)`, `idx_activity_action_type (action_type)`, `idx_activity_user (user_id)`

---

## 5. SQL Views (`SQL SECURITY INVOKER`) & Relational Joins (Verified Against `schema.sql`)

All four views in [`database/schema.sql`](file:///C:/Projects/ReFind/database/schema.sql#L236-L334) use `SQL SECURITY INVOKER` so queries execute under the least-privilege `refind_app` account:
1. **`vw_public_lost_gallery`**:
   - **Definition:** `lost_items l INNER JOIN users u ON l.user_id = u.user_id` plus correlated scalar subquery `(SELECT COUNT(*) FROM matches m WHERE m.lost_id = l.lost_id AND m.match_status != 'DISMISSED') AS match_count`.
   - **Privacy enforcement:** Projects public lost-item and reporter columns (`reporter_name`, `reporter_student_id`, `reporter_department`) while **excluding `l.identifying_marks` and `l.updated_at`**.
2. **`vw_public_found_gallery`**:
   - **Definition:** `found_items f INNER JOIN users u ON f.user_id = u.user_id` plus correlated scalar subquery `(SELECT COUNT(*) FROM claims c WHERE c.found_id = f.found_id AND c.status = 'PENDING') AS pending_claims_count`.
   - **Privacy enforcement:** Projects public found-item, custody (`storage_location`, `verification_question`), and finder columns while **excluding `f.secret_detail` and `f.updated_at`**.
3. **`vw_detailed_matches`**:
   - **Definition:** Performs **4 `INNER JOIN` clauses across 4 distinct base tables (`matches`, `lost_items`, `found_items`, and `users` joined twice as `lu` and `fu`)**:
     - `FROM matches m`
     - `INNER JOIN lost_items l ON m.lost_id = l.lost_id`
     - `INNER JOIN users lu ON l.user_id = lu.user_id` (lost reporter)
     - `INNER JOIN found_items f ON m.found_id = f.found_id`
     - `INNER JOIN users fu ON f.user_id = fu.user_id` (finder)
   - **Purpose:** Exposes `match_score`, all 5 component point columns, and side-by-side public metadata for both items while omitting `l.identifying_marks` and `f.secret_detail`.
4. **`vw_dashboard_stats`**:
   - **Definition:** Executes **11 real-time scalar subqueries** across `lost_items`, `found_items`, `matches`, `claims`, and `users` (`total_lost`, `open_lost`, `recovered_lost`, `total_found`, `available_found`, `returned_found`, `active_matches`, `high_confidence_matches` where `match_score >= 70.00 AND match_status != 'DISMISSED'`, `pending_claims`, `approved_claims`, and `registered_students` where `role = 'STUDENT' AND is_active = TRUE`).
   - Note: The percentage `recovery_rate` displayed on the homepage is computed in `_build_dashboard_data()` in [`app.py`](file:///C:/Projects/ReFind/app.py) from the view's `returned_found` and `total_found` counts.

---

## 6. ACID Transactions & Pessimistic Concurrency Control

Implemented in [`services/claim_service.py`](file:///C:/Projects/ReFind/services/claim_service.py) using [`db_transaction()`](file:///C:/Projects/ReFind/database/db.py#L60):
1. **Atomicity & Isolation (`SELECT ... FOR UPDATE`):** When an Administrator reviews a claim (`approve_claim_transaction`), the service starts an explicit transaction (`conn.start_transaction()`) and locks both the `claims` row and its parent `found_items` row using `SELECT ... FOR UPDATE`.
2. **Coordinated Multi-Table State Transition:**
   - Sets the target claim to `APPROVED` (`reviewed_by`, `reviewed_at`, `admin_remarks`), which populates `approved_found_id = found_id`.
   - Auto-rejects all competing `PENDING` claims on the same `found_id` (`status = 'REJECTED'`).
   - Updates `found_items.status = 'RETURNED'`.
   - Updates linked `lost_items.status = 'RECOVERED'`.
   - Promotes the matched pair in `matches` to `CONFIRMED` and dismisses remaining open suggestions.
   - Inserts `CLAIM_APPROVED` and `ITEM_RETURNED` rows into `activity_logs`.
3. **Commit / Rollback Guarantee:** Calls `conn.commit()` only after all statements succeed; any database or integrity error triggers `conn.rollback()`, leaving zero partial updates.

---

## 7. Rule-Based Smart Matching Algorithm (0–100 Score)

Implemented in [`services/matching_engine.py`](file:///C:/Projects/ReFind/services/matching_engine.py#L82):

$$\text{Match Score} = S_{\text{category}} (30) + S_{\text{name}} (25) + S_{\text{location}} (20) + S_{\text{date}} (15) + S_{\text{description}} (10)$$

- **Category (`0–30 pts`):** Exact match = `30.0`; related category pair (`Bags & Wallets` $\leftrightarrow$ `ID & Cards`, `Electronics` $\leftrightarrow$ `Keys & Accessories`) = `12.0`.
- **Item Name & Brand (`0–25 pts`):** Weighted combination (`70%` token Jaccard/recall overlap + `30%` `SequenceMatcher` ratio) across `item_name` and `brand_color`.
- **Campus Location (`0–20 pts`):** Exact normalized location = `20.0`; same canonical campus zone (`library`, `canteen`, `academic_b`, `auditorium`, etc.) = `15.0–18.0`; shared location tokens = `8.0–16.0`.
- **Date Compatibility (`0–15 pts`):** Same day (`0d` delta) = `15.0`; `1–2d` after lost = `13.0`; `3–5d` = `10.0`; `6–14d` = `7.0`; `15–30d` = `4.0`; `1d` early tolerance = `5.0`; found $>1\text{d}$ before lost applies a `0.35x` timeline penalty.
- **Description Keywords (`0–10 pts`):** Stop-word-filtered keyword overlap between `lost_items.description` and `found_items.description`.
- **Thresholds:** Pairs scoring $\ge 35.0$ are upserted into `matches`; pairs scoring $\ge 60.0$ promote `OPEN`/`AVAILABLE` items to `MATCHED`.
