# ReFind (`refind_db`) — Editable Entity-Relationship Diagram Source (Normalized 3NF Schema)

This file contains the editable **Mermaid (`erDiagram`)** source and **Foreign-Key / Unique-Constraint / Secondary-Index** specification for the normalized 6-table 3NF relational schema implemented in [`database/schema.sql`](file:///C:/Projects/ReFind/database/schema.sql).

---

## 1. Mermaid ER Diagram (`erDiagram`)

```mermaid
erDiagram
    users {
        INT user_id PK "AUTO_INCREMENT NOT NULL"
        VARCHAR(30) student_id UK "NOT NULL, uq_users_student_id"
        VARCHAR(100) full_name "NOT NULL, CHECK >= 2 chars"
        VARCHAR(120) email UK "NOT NULL, uq_users_email, CHECK email format"
        VARCHAR(20) phone "NOT NULL"
        VARCHAR(80) department "NOT NULL, idx_users_department"
        VARCHAR(255) password_hash "NOT NULL (Werkzeug scrypt)"
        ENUM role "NOT NULL ('STUDENT','ADMIN'), idx_users_role"
        BOOLEAN is_active "NOT NULL DEFAULT TRUE"
        TIMESTAMP created_at "NOT NULL DEFAULT CURRENT_TIMESTAMP"
    }

    lost_items {
        INT lost_id PK "AUTO_INCREMENT NOT NULL"
        INT user_id FK "NOT NULL -> users.user_id (ON DELETE CASCADE)"
        VARCHAR(120) item_name "NOT NULL, CHECK >= 2 chars"
        ENUM category "NOT NULL (8 campus categories), idx_lost_category_status"
        VARCHAR(100) brand_color "DEFAULT NULL"
        VARCHAR(120) location_lost "NOT NULL, CHECK >= 2 chars, idx_lost_location"
        DATE date_lost "NOT NULL, idx_lost_date"
        TEXT description "NOT NULL"
        VARCHAR(255) identifying_marks "DEFAULT NULL, PRIVATE (Excluded from vw_public_lost_gallery)"
        VARCHAR(255) image_path "DEFAULT NULL"
        ENUM status "NOT NULL ('OPEN','MATCHED','RECOVERED','CLOSED')"
        TIMESTAMP created_at "NOT NULL DEFAULT CURRENT_TIMESTAMP"
        TIMESTAMP updated_at "NOT NULL ON UPDATE CURRENT_TIMESTAMP"
    }

    found_items {
        INT found_id PK "AUTO_INCREMENT NOT NULL"
        INT user_id FK "NOT NULL -> users.user_id (ON DELETE CASCADE)"
        VARCHAR(120) item_name "NOT NULL, CHECK >= 2 chars"
        ENUM category "NOT NULL (8 campus categories), idx_found_category_status"
        VARCHAR(100) brand_color "DEFAULT NULL"
        VARCHAR(120) location_found "NOT NULL, CHECK >= 2 chars, idx_found_location"
        DATE date_found "NOT NULL, idx_found_date"
        TEXT description "NOT NULL"
        VARCHAR(150) storage_location "NOT NULL"
        VARCHAR(255) verification_question "NOT NULL"
        VARCHAR(255) secret_detail "DEFAULT NULL, PRIVATE (Excluded from vw_public_found_gallery)"
        VARCHAR(255) image_path "DEFAULT NULL"
        ENUM status "NOT NULL ('AVAILABLE','MATCHED','CLAIMED','RETURNED')"
        TIMESTAMP created_at "NOT NULL DEFAULT CURRENT_TIMESTAMP"
        TIMESTAMP updated_at "NOT NULL ON UPDATE CURRENT_TIMESTAMP"
    }

    matches {
        INT match_id PK "AUTO_INCREMENT NOT NULL"
        INT lost_id FK "NOT NULL -> lost_items.lost_id (ON DELETE CASCADE), uq_matches_pair"
        INT found_id FK "NOT NULL -> found_items.found_id (ON DELETE CASCADE), uq_matches_pair"
        DECIMAL(5_2) match_score "NOT NULL, CHECK (0.00..100.00), idx_matches_score DESC"
        VARCHAR(500) score_explanation "NOT NULL"
        DECIMAL(5_2) category_points "NOT NULL DEFAULT 0.00 (Max 30)"
        DECIMAL(5_2) name_points "NOT NULL DEFAULT 0.00 (Max 25)"
        DECIMAL(5_2) location_points "NOT NULL DEFAULT 0.00 (Max 20)"
        DECIMAL(5_2) date_points "NOT NULL DEFAULT 0.00 (Max 15)"
        DECIMAL(5_2) description_points "NOT NULL DEFAULT 0.00 (Max 10)"
        ENUM match_status "NOT NULL ('SUGGESTED','CONFIRMED','DISMISSED'), idx_matches_status"
        TIMESTAMP matched_at "NOT NULL DEFAULT CURRENT_TIMESTAMP"
    }

    claims {
        INT claim_id PK "AUTO_INCREMENT NOT NULL"
        INT found_id FK "NOT NULL -> found_items.found_id (ON DELETE RESTRICT), uq_claims_user_found"
        INT lost_id FK "DEFAULT NULL -> lost_items.lost_id (ON DELETE SET NULL)"
        INT claimant_id FK "NOT NULL -> users.user_id (ON DELETE RESTRICT), uq_claims_user_found"
        TEXT proof_description "NOT NULL, CHECK >= 5 chars (CONFIDENTIAL)"
        VARCHAR(100) id_card_reference "NOT NULL"
        ENUM status "NOT NULL ('PENDING','APPROVED','REJECTED'), idx_claims_status"
        INT approved_found_id UK "STORED GENERATED, uq_claims_single_approved_per_found"
        INT reviewed_by FK "DEFAULT NULL -> users.user_id (ON DELETE SET NULL)"
        VARCHAR(255) admin_remarks "DEFAULT NULL"
        TIMESTAMP created_at "NOT NULL DEFAULT CURRENT_TIMESTAMP"
        TIMESTAMP reviewed_at "DEFAULT NULL"
    }

    activity_logs {
        BIGINT log_id PK "AUTO_INCREMENT NOT NULL"
        INT user_id FK "DEFAULT NULL -> users.user_id (ON DELETE SET NULL), idx_activity_user"
        ENUM action_type "NOT NULL (9 lifecycle event types), idx_activity_action_type"
        ENUM entity_type "NOT NULL ('USER','LOST_ITEM','FOUND_ITEM','MATCH','CLAIM')"
        INT entity_id "NOT NULL"
        VARCHAR(300) summary "NOT NULL"
        TIMESTAMP created_at "NOT NULL DEFAULT CURRENT_TIMESTAMP, idx_activity_created_at DESC"
    }

    users ||--o{ lost_items : "reports lost (1 : 0..*, fk_lost_items_user)"
    users ||--o{ found_items : "reports found (1 : 0..*, fk_found_items_user)"
    lost_items ||--o{ matches : "evaluated in (1 : 0..*, fk_matches_lost)"
    found_items ||--o{ matches : "evaluated in (1 : 0..*, fk_matches_found)"
    found_items ||--o{ claims : "claimed via (1 : 0..*, fk_claims_found)"
    lost_items o|--o{ claims : "optional link (0..1 : 0..*, fk_claims_lost)"
    users ||--o{ claims : "submits claim (1 : 0..*, fk_claims_claimant)"
    users o|--o{ claims : "reviews claim (0..1 : 0..*, fk_claims_reviewer)"
    users o|--o{ activity_logs : "triggers audit (0..1 : 0..*, fk_activity_user)"
```

---

## 2. Verified Relationship Cardinalities & Foreign Key Referential Actions (9 Foreign Keys)

| # | Foreign Key Constraint | Parent Table (Referenced) | Child Table & Column | Child Nullability | Verified Cardinality (Parent : Child) | `ON DELETE` | `ON UPDATE` |
| :---: | :--- | :--- | :--- | :---: | :---: | :---: | :---: |
| 1 | `fk_lost_items_user` | `users(user_id)` | `lost_items(user_id)` | `NOT NULL` | **`1 : 0..*`** (Mandatory parent) | `CASCADE` | `CASCADE` |
| 2 | `fk_found_items_user` | `users(user_id)` | `found_items(user_id)` | `NOT NULL` | **`1 : 0..*`** (Mandatory parent) | `CASCADE` | `CASCADE` |
| 3 | `fk_matches_lost` | `lost_items(lost_id)` | `matches(lost_id)` | `NOT NULL` | **`1 : 0..*`** (Mandatory parent) | `CASCADE` | `CASCADE` |
| 4 | `fk_matches_found` | `found_items(found_id)` | `matches(found_id)` | `NOT NULL` | **`1 : 0..*`** (Mandatory parent) | `CASCADE` | `CASCADE` |
| 5 | `fk_claims_found` | `found_items(found_id)` | `claims(found_id)` | `NOT NULL` | **`1 : 0..*`** (Mandatory parent) | `RESTRICT` | `RESTRICT` |
| 6 | `fk_claims_lost` | `lost_items(lost_id)` | `claims(lost_id)` | `DEFAULT NULL` | **`0..1 : 0..*`** (Optional parent) | `SET NULL` | `CASCADE` |
| 7 | `fk_claims_claimant` | `users(user_id)` | `claims(claimant_id)` | `NOT NULL` | **`1 : 0..*`** (Mandatory parent) | `RESTRICT` | `CASCADE` |
| 8 | `fk_claims_reviewer` | `users(user_id)` | `claims(reviewed_by)` | `DEFAULT NULL` | **`0..1 : 0..*`** (Optional parent) | `SET NULL` | `CASCADE` |
| 9 | `fk_activity_user` | `users(user_id)` | `activity_logs(user_id)` | `DEFAULT NULL` | **`0..1 : 0..*`** (Optional parent) | `SET NULL` | `CASCADE` |

---

## 3. Reconciliation of `UNIQUE` Constraints (5) vs. Non-Unique Secondary Indexes (18)

| Category | Count | Exact Identifiers in `database/schema.sql` & `information_schema` |
| :--- | :---: | :--- |
| **`PRIMARY KEY` Constraints** | **6** | `users(user_id)`, `lost_items(lost_id)`, `found_items(found_id)`, `matches(match_id)`, `claims(claim_id)`, `activity_logs(log_id)` |
| **`UNIQUE` Constraints (Backed by Unique Indexes)** | **5** | 1. `uq_users_student_id` on `users(student_id)`<br>2. `uq_users_email` on `users(email)`<br>3. `uq_matches_pair` on `matches(lost_id, found_id)`<br>4. `uq_claims_user_found` on `claims(found_id, claimant_id)`<br>5. `uq_claims_single_approved_per_found` on `claims(approved_found_id)` (Stored Generated Column) |
| **Non-Unique Secondary `INDEX`es** | **18** | • `users` (2): `idx_users_role`, `idx_users_department`<br>• `lost_items` (4): `idx_lost_category_status`, `idx_lost_date`, `idx_lost_location`, `idx_lost_user`<br>• `found_items` (4): `idx_found_category_status`, `idx_found_date`, `idx_found_location`, `idx_found_user`<br>• `matches` (2): `idx_matches_score (DESC)`, `idx_matches_status`<br>• `claims` (3): `idx_claims_found_status`, `idx_claims_claimant`, `idx_claims_status`<br>• `activity_logs` (3): `idx_activity_created_at (DESC)`, `idx_activity_action_type`, `idx_activity_user` |
