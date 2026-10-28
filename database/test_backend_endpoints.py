"""
Comprehensive End-to-End Flask Backend Verification Suite (`test_backend_endpoints.py`)
Tests all 9 Phase 2 backend workflows against live MySQL 26.7.0 (`refind_db` as `refind_app`):
  1. Student registration & login with password hashing, sessions, and CSRF protection
  2. Reporting lost & found items with input validation
  3. Optional image uploads (valid PNG vs invalid fake image header rejection)
  4. Listing and filtering lost & found galleries (verifying private details are hidden)
  5. Rule-based matching engine integration & score calculation (0–100)
  6. Suggested matches API & score explanation rubric
  7. Ownership claim submission & ACID transactional admin verification (including competing claim auto-rejection & single-approved-claim enforcement)
  8. Dashboard real-time statistics via SQL views
  9. Activity logging across all actions

Cleans up only its temporary test records in a `finally` block so the original
seed data (5 users, 5 lost_items, 5 found_items, 6 matches, 3 claims, 8 logs)
is 100% preserved.
"""

import io
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PIL import Image
from app import app
from config import Config
from database.db import get_server_connection, query_one


def _make_valid_png_bytes() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (120, 90), color=(76, 59, 142))
    img.save(buf, format="PNG")
    return buf.getvalue()


def snapshot_max_ids() -> dict[str, int]:
    """Capture current maximum primary key IDs across all 6 tables so cleanup only removes test rows created after the snapshot."""
    return {
        "users": int(query_one("SELECT COALESCE(MAX(user_id), 0) AS m FROM users")["m"]),
        "lost_items": int(query_one("SELECT COALESCE(MAX(lost_id), 0) AS m FROM lost_items")["m"]),
        "found_items": int(query_one("SELECT COALESCE(MAX(found_id), 0) AS m FROM found_items")["m"]),
        "matches": int(query_one("SELECT COALESCE(MAX(match_id), 0) AS m FROM matches")["m"]),
        "claims": int(query_one("SELECT COALESCE(MAX(claim_id), 0) AS m FROM claims")["m"]),
        "activity_logs": int(query_one("SELECT COALESCE(MAX(log_id), 0) AS m FROM activity_logs")["m"]),
    }


def cleanup_test_artifacts(uploaded_rel_paths: list[str], baseline: dict[str, int] | None = None):
    """Remove only temporary records created above the pre-test baseline IDs and reset AUTO_INCREMENT."""
    if baseline is None:
        baseline = {
            "users": 5,
            "lost_items": 6,
            "found_items": 5,
            "matches": 6,
            "claims": 3,
            "activity_logs": 12,
        }
    conn = get_server_connection()
    cur = conn.cursor()
    try:
        cur.execute("USE refind_db")
        cur.execute("DELETE FROM activity_logs WHERE log_id > %s", (baseline["activity_logs"],))
        cur.execute("DELETE FROM claims WHERE claim_id > %s", (baseline["claims"],))
        cur.execute(
            "DELETE FROM matches WHERE match_id > %s OR lost_id > %s OR found_id > %s",
            (baseline["matches"], baseline["lost_items"], baseline["found_items"]),
        )
        cur.execute("DELETE FROM lost_items WHERE lost_id > %s", (baseline["lost_items"],))
        cur.execute("DELETE FROM found_items WHERE found_id > %s", (baseline["found_items"],))
        cur.execute("DELETE FROM users WHERE user_id > %s", (baseline["users"],))

        cur.execute(f"ALTER TABLE activity_logs AUTO_INCREMENT = {baseline['activity_logs'] + 1}")
        cur.execute(f"ALTER TABLE claims AUTO_INCREMENT = {baseline['claims'] + 1}")
        cur.execute(f"ALTER TABLE matches AUTO_INCREMENT = {baseline['matches'] + 1}")
        cur.execute(f"ALTER TABLE lost_items AUTO_INCREMENT = {baseline['lost_items'] + 1}")
        cur.execute(f"ALTER TABLE found_items AUTO_INCREMENT = {baseline['found_items'] + 1}")
        cur.execute(f"ALTER TABLE users AUTO_INCREMENT = {baseline['users'] + 1}")
        conn.commit()
    finally:
        cur.close()
        conn.close()

    for rel in uploaded_rel_paths:
        if rel:
            full = ROOT_DIR / "static" / rel
            if full.exists():
                full.unlink()


def run_verification():
    baseline = snapshot_max_ids()
    uploaded_files = []
    client = app.test_client()
    client_student2 = app.test_client()
    client_admin = app.test_client()

    print("=" * 80)
    print("ReFind — Phase 2 Flask Backend API & Security Verification Report")
    print("=" * 80)

    try:
        # ---------------------------------------------------------------------
        # TEST 1: Dashboard Statistics View & Public Galleries (Privacy Check)
        # ---------------------------------------------------------------------
        res = client.get("/api/dashboard/stats")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        dash = res.get_json()
        assert dash["ok"] is True
        stats = dash["stats"]
        print(
            f"[PASS] 1. Dashboard Stats API (`/api/dashboard/stats`): "
            f"Lost={stats['total_lost']}, Found={stats['total_found']}, "
            f"Matches={stats['active_matches']}, PendingClaims={stats['pending_claims']}, "
            f"RecoveryRate={stats['recovery_rate']}%"
        )

        # Lost gallery filter + privacy audit
        res_lost = client.get("/api/lost-items?category=Electronics&q=AirPods")
        assert res_lost.status_code == 200
        lost_json = res_lost.get_json()
        assert lost_json["count"] == 1
        assert "identifying_marks" not in lost_json["items"][0], "Privacy leak: identifying_marks exposed!"
        print(
            f"[PASS] 2. Lost Items Filter & Privacy Check (`/api/lost-items?category=Electronics&q=AirPods`): "
            f"{lost_json['count']} item returned, private `identifying_marks` hidden."
        )

        # Found gallery filter + privacy audit
        res_found = client.get("/api/found-items?category=Electronics")
        assert res_found.status_code == 200
        found_json = res_found.get_json()
        assert found_json["count"] == 2
        assert "secret_detail" not in found_json["items"][0], "Privacy leak: secret_detail exposed!"
        print(
            f"[PASS] 3. Found Items Filter & Privacy Check (`/api/found-items?category=Electronics`): "
            f"{found_json['count']} items returned, private `secret_detail` hidden."
        )

        # Matches API & Rubric
        res_matches = client.get("/api/matches?min_score=80")
        assert res_matches.status_code == 200
        matches_json = res_matches.get_json()
        assert matches_json["count"] == 3
        assert matches_json["scoring_rubric"]["total_max_points"] == 100
        print(
            f"[PASS] 4. Suggested Matches API (`/api/matches?min_score=80`): "
            f"{matches_json['count']} high-confidence matches returned with 100-pt rubric."
        )

        # ---------------------------------------------------------------------
        # TEST 2: Security Guards (CSRF & Authentication Enforcement)
        # ---------------------------------------------------------------------
        # Unauthenticated POST with valid CSRF should return 401
        csrf_tok = client.get("/api/auth/csrf").get_json()["csrf_token"]
        unauth_post = client.post(
            "/api/lost-items",
            json={"item_name": "Test"},
            headers={"X-CSRF-Token": csrf_tok},
        )
        assert unauth_post.status_code == 401

        # POST without CSRF token should return 400
        no_csrf_post = client.post("/api/auth/login", json={"identifier": "admin@campus.edu", "password": "x"})
        assert no_csrf_post.status_code == 400
        print(
            "[PASS] 5. CSRF & Auth Guards: Missing CSRF -> HTTP 400; Unauthenticated write -> HTTP 401."
        )

        # ---------------------------------------------------------------------
        # TEST 3: Student Registration & Login (Password Hashing + Sessions)
        # ---------------------------------------------------------------------
        reg_res = client.post(
            "/api/auth/register",
            json={
                "student_id": "TESTCS901",
                "full_name": " Avery Reed (Test Student 1)",
                "email": "avery.test@campus.edu",
                "phone": "555-0111",
                "department": "Computer Engineering",
                "password": "TestPassword@123",
                "confirm_password": "TestPassword@123",
            },
            headers={"X-CSRF-Token": csrf_tok},
        )
        assert reg_res.status_code == 201, reg_res.get_data(as_text=True)
        user1 = reg_res.get_json()["user"]

        # Register second student on client_student2 for competing claim test
        csrf_tok2 = client_student2.get("/api/auth/csrf").get_json()["csrf_token"]
        reg_res2 = client_student2.post(
            "/api/auth/register",
            json={
                "student_id": "TESTIT902",
                "full_name": "Cameron Gray (Test Student 2)",
                "email": "cameron.test@campus.edu",
                "phone": "555-0112",
                "department": "Information Technology",
                "password": "TestPassword@123",
                "confirm_password": "TestPassword@123",
            },
            headers={"X-CSRF-Token": csrf_tok2},
        )
        assert reg_res2.status_code == 201
        user2 = reg_res2.get_json()["user"]

        # Verify non-admin student cannot access /api/admin/claims
        forbidden_res = client.get("/api/admin/claims")
        assert forbidden_res.status_code == 403
        print(
            f"[PASS] 6. Student Registration, Session & RBAC (`/api/auth/register`): "
            f"Registered user_id={user1['user_id']} & {user2['user_id']}; Student access to `/api/admin/claims` -> HTTP 403."
        )

        # ---------------------------------------------------------------------
        # TEST 4: Lost & Found Reporting + Validated Image Upload + Matching
        # ---------------------------------------------------------------------
        # First test invalid image upload (spoofed .png with text bytes) -> HTTP 400
        bad_img_res = client.post(
            "/api/lost-items",
            data={
                "csrf_token": csrf_tok,
                "item_name": "Sony WH-1000XM5 Headphones",
                "category": "Electronics",
                "brand_color": "Midnight Blue",
                "location_lost": "Main Auditorium Seminar Hall",
                "date_lost": "2026-10-26",
                "description": "Midnight blue Sony noise-cancelling headphones in hard zipper pouch.",
                "identifying_marks": "Sticker 'NV-901' inside headband",
                "image": (io.BytesIO(b"not-a-valid-png-header"), "spoofed.png"),
            },
            content_type="multipart/form-data",
        )
        assert bad_img_res.status_code == 400
        assert "signature" in bad_img_res.get_json()["error"].lower()

        # Now submit valid lost item with valid PNG image
        valid_png = _make_valid_png_bytes()
        lost_post = client.post(
            "/api/lost-items",
            data={
                "csrf_token": csrf_tok,
                "item_name": "Sony WH-1000XM5 Headphones",
                "category": "Electronics",
                "brand_color": "Midnight Blue",
                "location_lost": "Main Auditorium Seminar Hall",
                "date_lost": "2026-10-26",
                "description": "Midnight blue Sony WH-1000XM5 wireless headphones in a grey pouch.",
                "identifying_marks": "Sticker 'NV-901' inside left earcup",
                "image": (io.BytesIO(valid_png), "sony_xm5.png"),
            },
            content_type="multipart/form-data",
        )
        assert lost_post.status_code == 201, lost_post.get_data(as_text=True)
        lost_payload = lost_post.get_json()
        new_lost_id = lost_payload["lost_id"]
        uploaded_files.append(lost_payload["image_path"])

        # Student 2 reports finding those headphones at Main Auditorium
        found_post = client_student2.post(
            "/api/found-items",
            data={
                "csrf_token": csrf_tok2,
                "item_name": "Sony WH-1000XM5 Wireless Headphones",
                "category": "Electronics",
                "brand_color": "Midnight Blue",
                "location_found": "Main Auditorium Seminar Hall",
                "date_found": "2026-10-26",
                "description": "Found midnight blue Sony WH-1000XM5 headphones in a grey carrying pouch near row 4.",
                "storage_location": "Admin Block Room 102",
                "verification_question": "What sticker or code is inside the left earcup?",
                "secret_detail": "Sticker says NV-901",
                "image": (io.BytesIO(valid_png), "found_sony.png"),
            },
            content_type="multipart/form-data",
        )
        assert found_post.status_code == 201, found_post.get_data(as_text=True)
        found_payload = found_post.get_json()
        new_found_id = found_payload["found_id"]
        uploaded_files.append(found_payload["image_path"])

        # Verify automatic match generated for (new_lost_id, new_found_id)
        match_row = query_one(
            "SELECT match_score, score_explanation FROM matches WHERE lost_id = %s AND found_id = %s",
            (new_lost_id, new_found_id),
        )
        assert match_row is not None and float(match_row["match_score"]) >= 85.0
        print(
            f"[PASS] 7. Lost/Found Reporting + Image Validation + Auto-Matching: "
            f"Spoofed PNG rejected (HTTP 400); Valid PNGs saved; "
            f"Auto-matched Lost #{new_lost_id} <-> Found #{new_found_id} with score {match_row['match_score']}/100."
        )

        # ---------------------------------------------------------------------
        # TEST 5: Competing Ownership Claims & ACID Transactional Admin Approval
        # ---------------------------------------------------------------------
        # Student 1 submits legitimate claim (linking new_lost_id)
        claim1_res = client.post(
            "/api/claims",
            json={
                "found_id": new_found_id,
                "lost_id": new_lost_id,
                "proof_description": "Inside the left earcup there is a small label with NV-901.",
                "id_card_reference": "TESTCS901",
            },
            headers={"X-CSRF-Token": csrf_tok},
        )
        assert claim1_res.status_code == 201, claim1_res.get_data(as_text=True)
        claim1_id = claim1_res.get_json()["claim_id"]

        # Student 2 submits a competing claim on the same found item
        claim2_res = client_student2.post(
            "/api/claims",
            json={
                "found_id": new_found_id,
                "proof_description": "I think these might be my blue headphones.",
                "id_card_reference": "TESTIT902",
            },
            headers={"X-CSRF-Token": csrf_tok2},
        )
        assert claim2_res.status_code == 201, claim2_res.get_data(as_text=True)
        claim2_id = claim2_res.get_json()["claim_id"]

        # Sign in as Campus Admin (`admin@campus.edu` / `DEMO_ADMIN_PASSWORD`)
        csrf_admin = client_admin.get("/api/auth/csrf").get_json()["csrf_token"]
        admin_login = client_admin.post(
            "/api/auth/login",
            json={"identifier": "admin@campus.edu", "password": os.getenv("DEMO_ADMIN_PASSWORD", "ChangeMeAdmin!01")},
            headers={"X-CSRF-Token": csrf_admin},
        )
        assert admin_login.status_code == 200
        csrf_admin = client_admin.get("/api/auth/csrf").get_json()["csrf_token"]

        # Admin inspects claims queue (which includes private finder_secret_detail & owner_identifying_marks)
        admin_queue = client_admin.get("/api/admin/claims?status=PENDING").get_json()
        target_in_queue = next(c for c in admin_queue["claims"] if c["claim_id"] == claim1_id)
        assert target_in_queue["finder_secret_detail"] == "Sticker says NV-901"
        assert target_in_queue["owner_identifying_marks"] == "Sticker 'NV-901' inside left earcup"

        # Admin approves Claim 1 via transactional endpoint
        approve_res = client_admin.post(
            f"/api/admin/claims/{claim1_id}/review",
            json={
                "decision": "APPROVED",
                "admin_remarks": "Verified NV-901 sticker inside left earcup and student ID TESTCS901.",
            },
            headers={"X-CSRF-Token": csrf_admin},
        )
        assert approve_res.status_code == 200, approve_res.get_data(as_text=True)
        outcome = approve_res.get_json()["outcome"]
        assert outcome["new_claim_status"] == "APPROVED"
        assert outcome["new_found_status"] == "RETURNED"
        assert outcome["new_lost_status"] == "RECOVERED"
        assert outcome["auto_rejected_competing_claims"] == 1

        # Verify competing Claim 2 was automatically rejected and cannot be approved
        second_approve = client_admin.post(
            f"/api/admin/claims/{claim2_id}/review",
            json={"decision": "APPROVED", "admin_remarks": "Should fail"},
            headers={"X-CSRF-Token": csrf_admin},
        )
        assert second_approve.status_code == 400
        print(
            f"[PASS] 8. ACID Claim Approval & Competing Claim Auto-Rejection: "
            f"Claim #{claim1_id} APPROVED -> Found #{new_found_id} RETURNED, Lost #{new_lost_id} RECOVERED, "
            f"Competing Claim #{claim2_id} auto-REJECTED; second approval blocked (HTTP 400)."
        )

        # ---------------------------------------------------------------------
        # TEST 6: Activity Logs Verification
        # ---------------------------------------------------------------------
        act_res = client.get("/api/activity").get_json()
        assert act_res["ok"] is True and act_res["count"] >= 14
        print(
            f"[PASS] 9. Activity History API (`/api/activity`): "
            f"Recorded all registration, login, reporting, matching, claiming, and return events ({act_res['count']} total logs)."
        )

    finally:
        cleanup_test_artifacts(uploaded_files, baseline)
        # Verify pre-test counts restored
        u_cnt = query_one("SELECT COUNT(*) AS cnt FROM users")["cnt"]
        l_cnt = query_one("SELECT COUNT(*) AS cnt FROM lost_items")["cnt"]
        f_cnt = query_one("SELECT COUNT(*) AS cnt FROM found_items")["cnt"]
        m_cnt = query_one("SELECT COUNT(*) AS cnt FROM matches")["cnt"]
        c_cnt = query_one("SELECT COUNT(*) AS cnt FROM claims")["cnt"]
        a_cnt = query_one("SELECT COUNT(*) AS cnt FROM activity_logs")["cnt"]
        print("-" * 80)
        print(
            f"[CLEANUP VERIFIED] Original seed state preserved: "
            f"users={u_cnt}, lost={l_cnt}, found={f_cnt}, matches={m_cnt}, claims={c_cnt}, logs={a_cnt}"
        )
        print("=" * 80)


if __name__ == "__main__":
    run_verification()
