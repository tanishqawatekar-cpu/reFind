-- ============================================================================
-- ReFind — Smart Campus Lost & Found System
-- DBMS Course Project — Normalized Relational Schema (MySQL 8.0+)
-- Database: refind_db
-- ============================================================================

CREATE DATABASE IF NOT EXISTS refind_db
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE refind_db;

-- ============================================================================
-- 1. TABLE: users
-- Stores registered students, faculty, and campus administrators.
-- Normalized to 3NF/BCNF: student_id and email are candidate keys.
-- ============================================================================
CREATE TABLE IF NOT EXISTS users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    student_id VARCHAR(30) NOT NULL,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL,
    phone VARCHAR(20) NOT NULL,
    department VARCHAR(80) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('STUDENT', 'ADMIN') NOT NULL DEFAULT 'STUDENT',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_users_student_id UNIQUE (student_id),
    CONSTRAINT uq_users_email UNIQUE (email),
    CONSTRAINT chk_users_name_len CHECK (CHAR_LENGTH(TRIM(full_name)) >= 2),
    CONSTRAINT chk_users_email_fmt CHECK (email LIKE '%_@__%.__%'),
    INDEX idx_users_role (role),
    INDEX idx_users_department (department)
) ENGINE=InnoDB;

-- ============================================================================
-- 2. TABLE: lost_items
-- Stores items reported lost by campus members.
-- Note: identifying_marks is kept private for ownership verification comparison
-- and is excluded from public gallery views.
-- ============================================================================
CREATE TABLE IF NOT EXISTS lost_items (
    lost_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    item_name VARCHAR(120) NOT NULL,
    category ENUM(
        'Electronics',
        'ID & Cards',
        'Books & Stationery',
        'Bags & Wallets',
        'Keys & Accessories',
        'Clothing & Eyewear',
        'Water Bottles & Umbrellas',
        'Other'
    ) NOT NULL,
    brand_color VARCHAR(100) DEFAULT NULL,
    location_lost VARCHAR(120) NOT NULL,
    date_lost DATE NOT NULL,
    description TEXT NOT NULL,
    identifying_marks VARCHAR(255) DEFAULT NULL,
    image_path VARCHAR(255) DEFAULT NULL,
    status ENUM('OPEN', 'MATCHED', 'RECOVERED', 'CLOSED') NOT NULL DEFAULT 'OPEN',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_lost_items_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_lost_item_name_len CHECK (CHAR_LENGTH(TRIM(item_name)) >= 2),
    CONSTRAINT chk_lost_location_len CHECK (CHAR_LENGTH(TRIM(location_lost)) >= 2),
    INDEX idx_lost_category_status (category, status),
    INDEX idx_lost_date (date_lost),
    INDEX idx_lost_location (location_lost),
    INDEX idx_lost_user (user_id)
) ENGINE=InnoDB;

-- ============================================================================
-- 3. TABLE: found_items
-- Stores items found on campus.
-- Note: verification_question is shown to claimants; secret_detail is hidden
-- from public views and only visible to administrators during claim review.
-- ============================================================================
CREATE TABLE IF NOT EXISTS found_items (
    found_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    item_name VARCHAR(120) NOT NULL,
    category ENUM(
        'Electronics',
        'ID & Cards',
        'Books & Stationery',
        'Bags & Wallets',
        'Keys & Accessories',
        'Clothing & Eyewear',
        'Water Bottles & Umbrellas',
        'Other'
    ) NOT NULL,
    brand_color VARCHAR(100) DEFAULT NULL,
    location_found VARCHAR(120) NOT NULL,
    date_found DATE NOT NULL,
    description TEXT NOT NULL,
    storage_location VARCHAR(150) NOT NULL DEFAULT 'Campus Lost & Found Desk (Main Admin Block)',
    verification_question VARCHAR(255) NOT NULL DEFAULT 'Describe any unique mark, lock-screen wallpaper, contents, or serial/ID detail to prove ownership.',
    secret_detail VARCHAR(255) DEFAULT NULL,
    image_path VARCHAR(255) DEFAULT NULL,
    status ENUM('AVAILABLE', 'MATCHED', 'CLAIMED', 'RETURNED') NOT NULL DEFAULT 'AVAILABLE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_found_items_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT chk_found_item_name_len CHECK (CHAR_LENGTH(TRIM(item_name)) >= 2),
    CONSTRAINT chk_found_location_len CHECK (CHAR_LENGTH(TRIM(location_found)) >= 2),
    INDEX idx_found_category_status (category, status),
    INDEX idx_found_date (date_found),
    INDEX idx_found_location (location_found),
    INDEX idx_found_user (user_id)
) ENGINE=InnoDB;

-- ============================================================================
-- 4. TABLE: matches
-- Stores rule-based candidate matches between lost_items and found_items
-- with an explainable 0-100 match_score and detailed breakdown.
-- ============================================================================
CREATE TABLE IF NOT EXISTS matches (
    match_id INT AUTO_INCREMENT PRIMARY KEY,
    lost_id INT NOT NULL,
    found_id INT NOT NULL,
    match_score DECIMAL(5, 2) NOT NULL,
    score_explanation VARCHAR(500) NOT NULL,
    category_points DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    name_points DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    location_points DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    date_points DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    description_points DECIMAL(5, 2) NOT NULL DEFAULT 0.00,
    match_status ENUM('SUGGESTED', 'CONFIRMED', 'DISMISSED') NOT NULL DEFAULT 'SUGGESTED',
    matched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_matches_lost
        FOREIGN KEY (lost_id) REFERENCES lost_items(lost_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_matches_found
        FOREIGN KEY (found_id) REFERENCES found_items(found_id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT uq_matches_pair UNIQUE (lost_id, found_id),
    CONSTRAINT chk_matches_score_range CHECK (match_score >= 0.00 AND match_score <= 100.00),
    INDEX idx_matches_score (match_score DESC),
    INDEX idx_matches_status (match_status)
) ENGINE=InnoDB;

-- ============================================================================
-- 5. TABLE: claims
-- Ownership claims submitted by students for a found item.
-- Includes a STORED GENERATED column `approved_found_id` with a UNIQUE
-- constraint: when status = 'APPROVED', it holds `found_id`; otherwise NULL.
-- Because MySQL UNIQUE allows multiple NULLs but forbids duplicate integers,
-- this enforces at the schema level that AT MOST ONE claim can ever be
-- APPROVED for any given found_id!
-- ============================================================================
CREATE TABLE IF NOT EXISTS claims (
    claim_id INT AUTO_INCREMENT PRIMARY KEY,
    found_id INT NOT NULL,
    lost_id INT DEFAULT NULL,
    claimant_id INT NOT NULL,
    proof_description TEXT NOT NULL,
    id_card_reference VARCHAR(100) NOT NULL,
    status ENUM('PENDING', 'APPROVED', 'REJECTED') NOT NULL DEFAULT 'PENDING',
    approved_found_id INT GENERATED ALWAYS AS (
        CASE WHEN status = 'APPROVED' THEN found_id ELSE NULL END
    ) STORED,
    reviewed_by INT DEFAULT NULL,
    admin_remarks VARCHAR(255) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TIMESTAMP NULL DEFAULT NULL,

    CONSTRAINT fk_claims_found
        FOREIGN KEY (found_id) REFERENCES found_items(found_id)
        ON DELETE RESTRICT ON UPDATE RESTRICT,
    CONSTRAINT fk_claims_lost
        FOREIGN KEY (lost_id) REFERENCES lost_items(lost_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_claims_claimant
        FOREIGN KEY (claimant_id) REFERENCES users(user_id)
        ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_claims_reviewer
        FOREIGN KEY (reviewed_by) REFERENCES users(user_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT uq_claims_single_approved_per_found UNIQUE (approved_found_id),
    CONSTRAINT uq_claims_user_found UNIQUE (found_id, claimant_id),
    CONSTRAINT chk_claims_proof_len CHECK (CHAR_LENGTH(TRIM(proof_description)) >= 5),
    INDEX idx_claims_found_status (found_id, status),
    INDEX idx_claims_claimant (claimant_id),
    INDEX idx_claims_status (status)
) ENGINE=InnoDB;

-- ============================================================================
-- 6. TABLE: activity_logs
-- Audit trail of all reporting, matching, claiming, verification, and returns.
-- ============================================================================
CREATE TABLE IF NOT EXISTS activity_logs (
    log_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT DEFAULT NULL,
    action_type ENUM(
        'USER_REGISTERED',
        'USER_LOGIN',
        'LOST_REPORTED',
        'FOUND_REPORTED',
        'MATCH_GENERATED',
        'CLAIM_SUBMITTED',
        'CLAIM_APPROVED',
        'CLAIM_REJECTED',
        'ITEM_RETURNED'
    ) NOT NULL,
    entity_type ENUM('USER', 'LOST_ITEM', 'FOUND_ITEM', 'MATCH', 'CLAIM') NOT NULL,
    entity_id INT NOT NULL,
    summary VARCHAR(300) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_activity_user
        FOREIGN KEY (user_id) REFERENCES users(user_id)
        ON DELETE SET NULL ON UPDATE CASCADE,
    INDEX idx_activity_created_at (created_at DESC),
    INDEX idx_activity_action_type (action_type),
    INDEX idx_activity_user (user_id)
) ENGINE=InnoDB;

-- ============================================================================
-- SQL VIEWS (Demonstrating Relational Joins, Abstraction & Data Privacy)
-- Uses SQL SECURITY INVOKER so queries execute with the calling user's
-- least-privilege permissions (`refind_app`) without requiring SHOW VIEW.
-- ============================================================================

-- View 1: Public Lost Items Gallery (Excludes private identifying_marks)
CREATE OR REPLACE SQL SECURITY INVOKER VIEW vw_public_lost_gallery AS
SELECT
    l.lost_id,
    l.user_id,
    u.full_name AS reporter_name,
    u.department AS reporter_department,
    u.student_id AS reporter_student_id,
    l.item_name,
    l.category,
    l.brand_color,
    l.location_lost,
    l.date_lost,
    l.description,
    l.image_path,
    l.status,
    l.created_at,
    (SELECT COUNT(*) FROM matches m WHERE m.lost_id = l.lost_id AND m.match_status != 'DISMISSED') AS match_count
FROM lost_items l
INNER JOIN users u ON l.user_id = u.user_id;

-- View 2: Public Found Items Gallery (Excludes private secret_detail)
CREATE OR REPLACE SQL SECURITY INVOKER VIEW vw_public_found_gallery AS
SELECT
    f.found_id,
    f.user_id,
    u.full_name AS finder_name,
    u.department AS finder_department,
    f.item_name,
    f.category,
    f.brand_color,
    f.location_found,
    f.date_found,
    f.description,
    f.storage_location,
    f.verification_question,
    f.image_path,
    f.status,
    f.created_at,
    (SELECT COUNT(*) FROM claims c WHERE c.found_id = f.found_id AND c.status = 'PENDING') AS pending_claims_count
FROM found_items f
INNER JOIN users u ON f.user_id = u.user_id;

-- View 3: Detailed Matches with Multi-Table Joins
CREATE OR REPLACE SQL SECURITY INVOKER VIEW vw_detailed_matches AS
SELECT
    m.match_id,
    m.match_score,
    m.score_explanation,
    m.category_points,
    m.name_points,
    m.location_points,
    m.date_points,
    m.description_points,
    m.match_status,
    m.matched_at,
    l.lost_id,
    l.item_name AS lost_item_name,
    l.category AS lost_category,
    l.brand_color AS lost_brand_color,
    l.location_lost,
    l.date_lost,
    l.description AS lost_description,
    l.image_path AS lost_image_path,
    l.status AS lost_status,
    lu.user_id AS lost_user_id,
    lu.full_name AS lost_reporter_name,
    lu.email AS lost_reporter_email,
    f.found_id,
    f.item_name AS found_item_name,
    f.category AS found_category,
    f.brand_color AS found_brand_color,
    f.location_found,
    f.date_found,
    f.description AS found_description,
    f.storage_location,
    f.image_path AS found_image_path,
    f.status AS found_status,
    fu.user_id AS found_user_id,
    fu.full_name AS found_reporter_name
FROM matches m
INNER JOIN lost_items l ON m.lost_id = l.lost_id
INNER JOIN users lu ON l.user_id = lu.user_id
INNER JOIN found_items f ON m.found_id = f.found_id
INNER JOIN users fu ON f.user_id = fu.user_id;

-- View 4: Real-time Dashboard Statistics Aggregation View
CREATE OR REPLACE SQL SECURITY INVOKER VIEW vw_dashboard_stats AS
SELECT
    (SELECT COUNT(*) FROM lost_items) AS total_lost,
    (SELECT COUNT(*) FROM lost_items WHERE status = 'OPEN') AS open_lost,
    (SELECT COUNT(*) FROM lost_items WHERE status = 'RECOVERED') AS recovered_lost,
    (SELECT COUNT(*) FROM found_items) AS total_found,
    (SELECT COUNT(*) FROM found_items WHERE status = 'AVAILABLE') AS available_found,
    (SELECT COUNT(*) FROM found_items WHERE status = 'RETURNED') AS returned_found,
    (SELECT COUNT(*) FROM matches WHERE match_status != 'DISMISSED') AS active_matches,
    (SELECT COUNT(*) FROM matches WHERE match_score >= 70.00 AND match_status != 'DISMISSED') AS high_confidence_matches,
    (SELECT COUNT(*) FROM claims WHERE status = 'PENDING') AS pending_claims,
    (SELECT COUNT(*) FROM claims WHERE status = 'APPROVED') AS approved_claims,
    (SELECT COUNT(*) FROM users WHERE role = 'STUDENT') AS registered_students;
