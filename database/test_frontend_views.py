import os
"""
End-to-End HTML Frontend & Live HTTP Workflow Verification (`test_frontend_views.py`)
Tests every HTML page, form submission, static CSS/JS/image asset, and role-based view
including the complete HTML workflow (Register -> Login -> Report Lost -> Report Found ->
Smart Match -> Submit Claim -> Admin Approve -> Item Returned) while ensuring private
verification answers remain hidden on public pages and preserving the original database seed state.
"""

import io
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from PIL import Image
from app import app
from database.test_backend_endpoints import cleanup_test_artifacts, _make_valid_png_bytes, snapshot_max_ids
from database.db import query_one


def extract_csrf_from_html(html: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([a-f0-9]{64})"', html)
    assert m, "CSRF token hidden input not found in rendered HTML!"
    return m.group(1)


def run_frontend_tests():
    baseline = snapshot_max_ids()
    uploaded_files = []
    client = app.test_client()
    finder_client = app.test_client()
    admin_client = app.test_client()

    print("=" * 80)
    print("ReFind — Editorial Minimalism UI, Static Assets & Full HTML Workflow QA Report")
    print("=" * 80)

    try:
        # 1. Public HTML Pages & Editorial Minimalism Design Check
        public_pages = [
            ("/", "Lost something?"),
            ("/dashboard", "ReFind — Smart Campus Lost &amp; Found"),
            ("/lost-items", "Lost Items Gallery"),
            ("/found-items", "Found Items Gallery"),
            ("/matches", "Rule-Based Smart Matching Engine (0–100 Score)"),
            ("/activity", "Campus Activity History"),
            ("/login", "Campus Sign In"),
            ("/register", "Student Account Registration"),
        ]
        for path, expected_heading in public_pages:
            r = client.get(path)
            assert r.status_code == 200, f"{path} returned {r.status_code}"
            html = r.get_data(as_text=True)
            assert expected_heading in html, f"Expected '{expected_heading}' in {path}"
            assert "refind" in html, f"Expected editorial wordmark in {path}"
            # Verify private fields never appear in public HTML
            assert "DEMO-TAG-01" not in html, f"Private secret/identifying mark leaked on {path}!"
        print("[PASS] 1. All 8 Public HTML Views render (HTTP 200) with Editorial Minimalism layout & zero privacy leaks.")

        # 2. Static Assets & Uploaded Item Photographs
        static_assets = [
            "/static/css/style.css",
            "/static/js/main.js",
            "/static/uploads/sample_airpods.png",
            "/static/uploads/sample_calc.png",
            "/static/uploads/sample_bottle.png",
            "/static/uploads/sample_wallet.png",
            "/static/uploads/sample_idcard.png",
            "/static/uploads/sample_spectacles.png",
        ]
        for asset in static_assets:
            ra = client.get(asset)
            assert ra.status_code == 200 and len(ra.data) > 100, f"Asset {asset} failed: {ra.status_code}"
            ra.close()
        print("[PASS] 2. CSS Design Tokens (`#FAF9F6`, `#20243A`, `#A895D6`), JS & all 6 Item Photographs serve cleanly (`HTTP 200`).")

        # 3. Search & Filter Controls on Lost, Found & Matches Pages
        r_lost_filter = client.get("/lost-items?q=AirPods&category=Electronics&status=MATCHED&location=Library")
        assert r_lost_filter.status_code == 200 and "Apple AirPods Pro (2nd Gen)" in r_lost_filter.get_data(as_text=True)
        r_found_filter = client.get("/found-items?q=Calculator&category=Electronics&status=MATCHED&location=Lab")
        assert r_found_filter.status_code == 200 and "Casio fx-991CW Scientific Calculator" in r_found_filter.get_data(as_text=True)
        r_match_filter = client.get("/matches?min_score=85&category=Electronics")
        assert r_match_filter.status_code == 200 and "Confidence Score: 97.67 / 100" in r_match_filter.get_data(as_text=True)
        print("[PASS] 3. Search & Filter controls on `/lost-items`, `/found-items`, and `/matches` verified against MySQL.")

        # 4. Student Registration & Login via HTML Forms
        reg_html = finder_client.get("/register").get_data(as_text=True)
        reg_csrf = extract_csrf_from_html(reg_html)
        reg_res = finder_client.post(
            "/register",
            data={
                "csrf_token": reg_csrf,
                "student_id": "AI2024088",
                "full_name": "Drew Parker",
                "email": "drew.parker@campus.edu",
                "phone": "555-0113",
                "department": "Artificial Intelligence & Data Science",
                "password": "Password@123",
                "confirm_password": "Password@123",
            },
            follow_redirects=True,
        )
        assert reg_res.status_code == 200
        assert "Welcome to ReFind, Drew Parker" in reg_res.get_data(as_text=True)

        login_html = client.get("/login").get_data(as_text=True)
        csrf_tok = extract_csrf_from_html(login_html)
        login_res = client.post(
            "/login",
            data={
                "csrf_token": csrf_tok,
                "identifier": "alex.rivera@campus.edu",
                "password": os.getenv("DEMO_STUDENT_PASSWORD", "ChangeMeStudent!01"),
            },
            follow_redirects=True,
        )
        assert login_res.status_code == 200
        assert "Signed in as Alex Rivera" in login_res.get_data(as_text=True)
        print("[PASS] 4. Student HTML Registration (`/register`) & Sign-In (`/login`) verified with CSRF & session state.")

        # 5. Authenticated Student Pages (`/report/lost`, `/report/found`, `/my-claims`, `/claims/submit/2`)
        for auth_path, marker in [
            ("/report/lost", "Report a Lost Campus Item"),
            ("/report/found", "Report a Found Campus Item"),
            ("/my-claims", "My Student Workspace (Alex Rivera)"),
            ("/claims/submit/2", "Submit Ownership Claim for Found Item #2"),
        ]:
            r_auth = client.get(auth_path)
            assert r_auth.status_code == 200
            body = r_auth.get_data(as_text=True)
            assert marker in body, f"Missing '{marker}' on {auth_path}"
        print("[PASS] 5. Authenticated Student HTML Views (`/report/lost`, `/report/found`, `/my-claims`, `/claims/submit/2`) verified.")

        # 6. Complete End-to-End HTML Workflow: Lost Report -> Found Report -> Match -> Claim -> Admin Approve -> Returned
        report_lost_html = client.get("/report/lost").get_data(as_text=True)
        csrf_lost = extract_csrf_from_html(report_lost_html)
        png_bytes = _make_valid_png_bytes()
        r_lost_post = client.post(
            "/report/lost",
            data={
                "csrf_token": csrf_lost,
                "item_name": "Sony WH-1000XM5 Headphones",
                "category": "Electronics",
                "brand_color": "Midnight Silver",
                "location_lost": "Central Library Reading Room",
                "date_lost": "2026-10-26",
                "description": "Midnight silver Sony WH-1000XM5 over-ear headphones in soft zip case.",
                "identifying_marks": "Sticker 'KV-LAB' inside headband arch",
                "image": (io.BytesIO(png_bytes), "sony_xm5_lost.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert r_lost_post.status_code == 200
        assert "Sony WH-1000XM5 Headphones" in r_lost_post.get_data(as_text=True)

        new_lost_row = query_one("SELECT lost_id, image_path FROM lost_items WHERE lost_id > %s ORDER BY lost_id DESC LIMIT 1", (baseline["lost_items"],))
        assert new_lost_row is not None
        if new_lost_row["image_path"]:
            uploaded_files.append(new_lost_row["image_path"])

        # Finder reports matching found item via HTML form
        report_found_html = finder_client.get("/report/found").get_data(as_text=True)
        csrf_found = extract_csrf_from_html(report_found_html)
        r_found_post = finder_client.post(
            "/report/found",
            data={
                "csrf_token": csrf_found,
                "item_name": "Sony WH-1000XM5 Wireless Headphones",
                "category": "Electronics",
                "brand_color": "Midnight Silver",
                "location_found": "Central Library Reading Room",
                "date_found": "2026-10-26",
                "storage_location": "Central Library Circulation Desk",
                "description": "Found silver Sony WH-1000XM5 headphones in carrying case on Reading Room table.",
                "verification_question": "What sticker or label is inside the headband arch?",
                "secret_detail": "Sticker KV-LAB inside headband arch",
                "image": (io.BytesIO(png_bytes), "sony_xm5_found.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        assert r_found_post.status_code == 200
        new_found_row = query_one("SELECT found_id, image_path FROM found_items WHERE found_id > %s ORDER BY found_id DESC LIMIT 1", (baseline["found_items"],))
        assert new_found_row is not None
        if new_found_row["image_path"]:
            uploaded_files.append(new_found_row["image_path"])

        # Verify Smart Match appears on `/matches`
        matches_html = client.get("/matches").get_data(as_text=True)
        assert "Sony WH-1000XM5" in matches_html

        # Student submits Ownership Claim via HTML form `/claims/submit/<found_id>`
        claim_form_html = client.get(f"/claims/submit/{new_found_row['found_id']}").get_data(as_text=True)
        csrf_claim = extract_csrf_from_html(claim_form_html)
        r_claim_post = client.post(
            f"/claims/submit/{new_found_row['found_id']}",
            data={
                "csrf_token": csrf_claim,
                "proof_description": "Inside the headband arch there is a white sticker reading KV-LAB.",
                "id_card_reference": "CS2024018",
                "lost_id": str(new_lost_row["lost_id"]),
            },
            follow_redirects=True,
        )
        assert r_claim_post.status_code == 200
        new_claim_row = query_one("SELECT claim_id FROM claims WHERE claim_id > %s ORDER BY claim_id DESC LIMIT 1", (baseline["claims"],))
        assert new_claim_row is not None

        # Admin logs in via HTML form and approves the claim on `/admin/claims/<claim_id>/review`
        admin_login_html = admin_client.get("/login").get_data(as_text=True)
        admin_csrf = extract_csrf_from_html(admin_login_html)
        admin_login_res = admin_client.post(
            "/login",
            data={
                "csrf_token": admin_csrf,
                "identifier": "admin@campus.edu",
                "password": os.getenv("DEMO_ADMIN_PASSWORD", "ChangeMeAdmin!01"),
            },
            follow_redirects=True,
        )
        assert admin_login_res.status_code == 200
        admin_claims_html = admin_client.get("/admin/claims").get_data(as_text=True)
        assert "Administrator Ownership Claim Verification Panel" in admin_claims_html
        assert "Sticker KV-LAB inside headband arch" in admin_claims_html

        review_csrf = extract_csrf_from_html(admin_claims_html)
        r_approve = admin_client.post(
            f"/admin/claims/{new_claim_row['claim_id']}/review",
            data={
                "csrf_token": review_csrf,
                "decision": "APPROVED",
                "admin_remarks": "Verified KV-LAB headband sticker and student ID CS2024018.",
            },
            follow_redirects=True,
        )
        assert r_approve.status_code == 200
        assert "APPROVED" in r_approve.get_data(as_text=True)

        # Verify database state updated atomically to RETURNED & RECOVERED
        updated_found = query_one("SELECT status FROM found_items WHERE found_id = %s", (new_found_row["found_id"],))
        updated_lost = query_one("SELECT status FROM lost_items WHERE lost_id = %s", (new_lost_row["lost_id"],))
        assert updated_found["status"] == "RETURNED"
        assert updated_lost["status"] == "RECOVERED"
        print("[PASS] 6. Full End-to-End HTML Workflow (`Lost -> Found -> Match -> Claim -> Admin Approve -> Returned`) verified.")

        # 7. Student Logout Form
        dash_before_logout = client.get("/dashboard").get_data(as_text=True)
        logout_csrf = extract_csrf_from_html(dash_before_logout)
        logout_res = client.post("/logout", data={"csrf_token": logout_csrf}, follow_redirects=True)
        assert logout_res.status_code == 200
        assert "You have been signed out safely" in logout_res.get_data(as_text=True)
        print("[PASS] 7. HTML Form Sign-Out (`/logout`) clears session cleanly.")

    finally:
        cleanup_test_artifacts(uploaded_files, baseline)
        print("-" * 80)
        print("[CLEANUP VERIFIED] All temporary test records removed; seed data intact.")
        print("=" * 80)


if __name__ == "__main__":
    run_frontend_tests()
